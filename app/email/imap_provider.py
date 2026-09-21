import email
import imaplib
import logging
import smtplib
from email import encoders
from email.message import Message
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from app.core.config import settings
from app.core.logging import track_email_errors
from app.email.base_provider import BaseEmailProvider, EmailAttachment, EmailMessage

logger = logging.getLogger("ImapEmailProvider")


class ImapEmailProvider(BaseEmailProvider):
    """Proveedor de correo electrónico concreto para el desarrollo y entorno local.

    Implementa la comunicación sincrónica tradicional utilizando las librerías
    nativas de Python `imaplib` para lectura y `smtplib` para envío.
    """

    def __init__(self) -> None:
        self.imap_client: Optional[imaplib.IMAP4_SSL] = None

    @track_email_errors(default_fallback=False)
    def connect(self) -> bool:
        """Establece conexión SSL con el servidor IMAP utilizando credenciales de settings.

        Por defecto, se conecta a outlook.office365.com:993 si settings no define otro.
        """
        # Obtener configuraciones centralizadas
        server = settings.IMAP_SERVER or "outlook.office365.com"
        port = settings.IMAP_PORT or 993
        user = settings.IMAP_USER
        password = settings.IMAP_PASSWORD

        if not user or not password:
            err_msg = "Credenciales IMAP incompletas. Verifique IMAP_USER e IMAP_PASSWORD."
            logger.error(err_msg)
            raise ValueError(err_msg)

        logger.info(f"Conectando al servidor IMAP en {server}:{port}...")
        try:
            # Crear conexión SSL
            self.imap_client = imaplib.IMAP4_SSL(server, port)

            # Autenticación
            logger.info(f"Autenticando usuario IMAP: {user}...")
            self.imap_client.login(user, password)
            logger.info("Conexión IMAP establecida y autenticada con éxito.")
            return True
        except imaplib.IMAP4.error as e:
            logger.error(f"Fallo de autenticación o error de protocolo IMAP: {e}")
            self.imap_client = None
            raise e
        except Exception as e:
            logger.error(f"Error inesperado al conectar al servidor IMAP: {e}")
            self.imap_client = None
            raise e

    def _extract_body_and_attachments(
        self, msg: Message
    ) -> tuple[str, List[EmailAttachment], bool]:
        """Método auxiliar que recorre las partes de un mensaje MIME para
        extraer el cuerpo de texto plano y sus archivos adjuntos.

        Devuelve ``(cuerpo, adjuntos, es_html)``. El tercer valor dice si el
        cuerpo que sale es HTML —porque no había parte ``text/plain`` y hubo
        que caer a la ``text/html``—, para que el flujo sepa que tiene que
        pasarlo por el limpiador y no lo tenga que adivinar.
        """
        body = ""
        es_html = False
        attachments: List[EmailAttachment] = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition") or "")
                filename = part.get_filename()

                # Identificar si es un archivo adjunto
                if filename or "attachment" in content_disposition:
                    try:
                        payload = part.get_payload(decode=True)
                        if payload is not None:
                            # Decodificar y normalizar el nombre del archivo
                            # a veces viene en formato codificado RFC 2047, decode_header lo limpia
                            decoded_filename_tuple = email.header.decode_header(
                                filename or "adjunto"
                            )[0]
                            decoded_filename = decoded_filename_tuple[0]
                            if isinstance(decoded_filename, bytes):
                                charset = decoded_filename_tuple[1] or "utf-8"
                                try:
                                    decoded_filename = decoded_filename.decode(
                                        charset, errors="replace"
                                    )
                                except Exception:
                                    decoded_filename = decoded_filename.decode(
                                        "utf-8", errors="replace"
                                    )

                            # La firma con logo llega como un adjunto más,
                            # pero el MIME la distingue: trae Content-ID (el
                            # cuerpo la pinta con <img src="cid:...">) o se
                            # declara "inline". Se apunta para no confundirla
                            # con un plano.
                            cid = str(part.get("Content-ID") or "").strip("<> ")
                            if not cid and "inline" in content_disposition:
                                cid = str(decoded_filename)

                            attachments.append(
                                EmailAttachment(
                                    filename=str(decoded_filename),
                                    content=payload,
                                    content_type=content_type,
                                    content_id=cid or None,
                                )
                            )
                    except Exception as ex:
                        logger.warning(f"No se pudo extraer el adjunto {filename}: {ex}")
                    continue

                # Identificar el cuerpo de texto
                if content_type == "text/plain" and not filename:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            body += payload.decode(charset, errors="replace")
                    except Exception as ex:
                        logger.warning(f"Error decodificando parte de texto plano: {ex}")

            # Si no encontramos texto plano pero hay HTML, lo tomamos como fallback
            if not body.strip():
                es_html = True
                for part in msg.walk():
                    if part.get_content_type() == "text/html" and not part.get_filename():
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body += payload.decode(charset, errors="replace")
                        except Exception as ex:
                            logger.warning(f"Error decodificando parte HTML de fallback: {ex}")
        else:
            # Mensaje simple no multipart
            charset = msg.get_content_charset() or "utf-8"
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(charset, errors="replace")
                es_html = msg.get_content_type() == "text/html"

        return body, attachments, es_html

    @track_email_errors(default_fallback=[])
    def fetch_unread_messages(self) -> List[EmailMessage]:
        """Busca correos no leídos (UNSEEN), descarga sus bytes y los normaliza."""
        if not self.imap_client:
            logger.warning(
                "El cliente IMAP no está conectado. "
                "Intentando conectar automáticamente..."
            )
            self.connect()

        assert self.imap_client is not None
        unread_emails: List[EmailMessage] = []

        try:
            # Seleccionar la bandeja de entrada
            # La carpeta viene de la configuración, no va escrita aquí: es lo
            # que permite probar contra TEST sin tocar la bandeja de ventas.
            # Se entrecomilla porque IMAP exige comillas para nombres con
            # espacios o caracteres fuera de ASCII, y no hace daño en los demás.
            carpeta = getattr(settings, "MAIL_FOLDER", None) or "INBOX"
            status, messages_info = self.imap_client.select(f'"{carpeta}"')
            if status != "OK":
                raise RuntimeError(
                    f"No existe la carpeta '{carpeta}' en el buzón IMAP "
                    f"(respuesta: {messages_info}). Revisa MAIL_FOLDER.")
            logger.info(f"Leyendo la carpeta IMAP '{carpeta}'.")

            # Buscar correos no leídos
            status, data = self.imap_client.search(None, "UNSEEN")
            if status != "OK":
                raise imaplib.IMAP4.error(f"Error buscando correos no leídos: {status}")

            # Obtener lista de IDs
            mail_ids = data[0].split()
            logger.info(f"Se encontraron {len(mail_ids)} correos no leídos en '{carpeta}'.")

            for mail_id in mail_ids:
                id_str = mail_id.decode("utf-8")
                # Descargar el correo completo en formato BODY.PEEK[] para no
                # marcarlo como leído automáticamente
                status, response_data = self.imap_client.fetch(mail_id, "(BODY.PEEK[])")
                if status != "OK" or not response_data:
                    logger.error(f"Error al descargar correo ID {id_str}")
                    continue

                for response_part in response_data:
                    if isinstance(response_part, tuple):
                        # Parsear bytes del correo
                        raw_bytes = response_part[1]
                        msg: Message = email.message_from_bytes(raw_bytes)

                        # Extraer campos de cabecera básicos
                        subject_header = msg.get("Subject", "(Sin Asunto)")
                        # Decodificar cabecera de asunto
                        decoded_subject = ""
                        for part, encoding in email.header.decode_header(subject_header):
                            if isinstance(part, bytes):
                                decoded_subject += part.decode(
                                    encoding or "utf-8", errors="replace"
                                )
                            else:
                                decoded_subject += part

                        sender = msg.get("From", "(Desconocido)")
                        date_str = msg.get("Date", "")

                        # Extraer cuerpo y archivos adjuntos
                        body, attachments, es_html = \
                            self._extract_body_and_attachments(msg)

                        # Crear diccionario de cabeceras crudas para trazabilidad
                        raw_headers = {k: v for k, v in msg.items()}

                        unread_emails.append(
                            EmailMessage(
                                id=id_str,
                                sender=sender,
                                subject=decoded_subject,
                                body=body,
                                date=date_str,
                                attachments=attachments,
                                raw_headers=raw_headers,
                                body_is_html=es_html
                            )
                        )

            return unread_emails

        except Exception as e:
            logger.error(f"Fallo durante la lectura de correos no leídos: {e}")
            raise e

    @track_email_errors(default_fallback=False)
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        attachments: Optional[List[EmailAttachment]] = None
    ) -> bool:
        """Despacha un correo saliente mediante SMTP de forma segura (STARTTLS).

        Por defecto, se conecta a smtp.office365.com:587 si settings no define otro.
        """
        smtp_server = settings.SMTP_SERVER or "smtp.office365.com"
        smtp_port = settings.SMTP_PORT or 587
        sender = settings.IMAP_USER
        password = settings.IMAP_PASSWORD

        if not sender or not password:
            err_msg = "Credenciales SMTP incompletas. Verifique IMAP_USER e IMAP_PASSWORD."
            logger.error(err_msg)
            raise ValueError(err_msg)

        logger.info(f"Preparando correo para {to} vía {smtp_server}:{smtp_port}...")

        # 1. Crear el contenedor del mensaje (MIME)
        if attachments:
            msg = MIMEMultipart()
            msg.attach(MIMEText(body, "plain", "utf-8"))
        else:
            msg = MIMEText(body, "plain", "utf-8")

        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to

        # 2. Agregar archivos adjuntos si existen
        if attachments:
            for attach in attachments:
                try:
                    mime_part = (
                        MIMEBase(*attach.content_type.split("/", 1))
                        if attach.content_type
                        else MIMEBase("application", "octet-stream")
                    )
                    mime_part.set_payload(attach.content)
                    encoders.encode_base64(mime_part)

                    # Añadir cabeceras para el archivo adjunto
                    # Asegurar nombre correcto
                    mime_part.add_header(
                        "Content-Disposition",
                        f"attachment; filename={attach.filename}"
                    )
                    msg.attach(mime_part)
                except Exception as ex:
                    logger.error(f"Error adjuntando archivo '{attach.filename}': {ex}")
                    raise ex

        # 3. Establecer conexión SMTP y despachar correo
        try:
            logger.info("Estableciendo conexión con el servidor SMTP...")
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=15)

            # Si el puerto requiere STARTTLS
            if settings.SMTP_USE_TLS:
                logger.info("Iniciando negociación STARTTLS...")
                server.starttls()

            logger.info(f"Autenticando en el servidor SMTP: {sender}...")
            server.login(sender, password)

            logger.info(f"Enviando correo electrónico a {to}...")
            server.sendmail(sender, [to], msg.as_string())

            logger.info("Correo electrónico despachado exitosamente.")
            server.quit()
            return True
        except Exception as e:
            logger.error(f"Fallo al enviar correo por SMTP: {e}")
            raise e

    @track_email_errors(default_fallback=False)
    def mark_as_read(self, message_id: str) -> bool:
        """Marca un correo como leído (\\Seen) en el servidor IMAP."""
        if not self.imap_client:
            logger.warning(
                "El cliente IMAP no está conectado. "
                "Intentando conectar automáticamente..."
            )
            self.connect()
        assert self.imap_client is not None

        try:
            status, response = self.imap_client.store(message_id.encode(), "+FLAGS", "\\Seen")
            if status != "OK":
                raise imaplib.IMAP4.error(
                    f"Error al marcar como leído el correo ID {message_id}: {status}"
                )
            logger.info(f"Correo ID {message_id} marcado como leído exitosamente en el servidor.")
            return True
        except Exception as e:
            logger.error(f"Error al marcar correo ID {message_id} como leído: {e}")
            raise e

    def disconnect(self) -> None:
        """Cierra la sesión IMAP activa de forma segura."""
        if self.imap_client:
            try:
                logger.info("Cerrando sesión del servidor IMAP...")
                self.imap_client.close()
                self.imap_client.logout()
            except Exception as e:
                logger.debug(f"Error silencioso al cerrar la sesión IMAP: {e}")
            finally:
                self.imap_client = None
