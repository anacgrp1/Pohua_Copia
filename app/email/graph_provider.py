import base64
import logging
from typing import List, Optional

import requests

from app.core.config import settings
from app.core.logging import track_email_errors
from app.email.base_provider import BaseEmailProvider, EmailAttachment, EmailMessage

logger = logging.getLogger("GraphEmailProvider")


class GraphEmailProvider(BaseEmailProvider):
    """Proveedor de correo electrónico concreto que utiliza la API de Microsoft Graph
    con autenticación basada en Token (OAuth2 / Azure AD Client Credentials)
    para el entorno de producción.
    """

    def __init__(self) -> None:
        self.token: Optional[str] = None
        # Los mensajes se piden POR CARPETA, no del buzón entero.
        #
        # `/users/{u}/messages` a secas devuelve todo el buzón: Enviados,
        # Archivo, subcarpetas. Aquí se lee sólo la carpeta configurada en
        # MAIL_FOLDER (INBOX por defecto), que es lo que hace IMAP y lo que
        # cualquiera espera de "leer la bandeja".
        self.url_messages = ("https://graph.microsoft.com/v1.0/users/{usuario}"
                             "/mailFolders/{carpeta}/messages")
        self.url_carpetas = "https://graph.microsoft.com/v1.0/users/{usuario}/mailFolders"
        self.url_token = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
        self._carpeta_id: Optional[str] = None

    @track_email_errors(default_fallback=False)
    def connect(self) -> bool:
        """Inicializa la sesión autenticada con Azure AD / MS Graph API usando
        las credenciales de OAuth2 (AZURE_CLIENT_ID, etc.).
        """
        tenant = settings.AZURE_TENANT_ID or settings.GRAPH_TENANT_ID
        client_id = settings.AZURE_CLIENT_ID or settings.GRAPH_CLIENT_ID
        client_secret = settings.AZURE_CLIENT_SECRET or settings.GRAPH_CLIENT_SECRET

        if not tenant or not client_id or not client_secret:
            err_msg = (
                "Credenciales de Azure incompletas. "
                "Verifique AZURE_TENANT_ID, CLIENT_ID y CLIENT_SECRET."
            )
            logger.error(err_msg)
            raise ValueError(err_msg)

        logger.info("Solicitando token de Azure AD...")
        respuesta = requests.post(
            self.url_token.format(tenant=tenant),
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
            timeout=30,
        )
        respuesta.raise_for_status()
        self.token = respuesta.json()["access_token"]
        logger.info("Token de Azure AD obtenido y guardado con éxito.")
        return True

    def disconnect(self) -> None:
        """Cierra la sesión y desconecta del servidor de correo.
        En Graph API (REST), la desconexión es simplemente descartar el token.
        """
        self.token = None
        logger.info("Desconectado de Azure AD (token descartado).")

    @track_email_errors(default_fallback=[])
    def fetch_unread_messages(self) -> List[EmailMessage]:
        """Busca y recupera correos no leídos vía llamadas REST de Microsoft Graph."""
        if not self.token:
            logger.warning("No hay token de Azure activo. Conectando primero...")
            self.connect()
        assert self.token is not None

        usuario = settings.GRAPH_USER or settings.IMAP_USER
        if not usuario:
            err_msg = "Usuario de Graph no configurado. Verifique GRAPH_USER o IMAP_USER."
            logger.error(err_msg)
            raise ValueError(err_msg)

        unread_emails: List[EmailMessage] = []
        carpeta_id = self._resolver_carpeta(usuario)
        url = self.url_messages.format(usuario=usuario, carpeta=carpeta_id)
        params = {
            "$filter": "isRead eq false",
            # `body`, no `bodyPreview`.
            #
            # `bodyPreview` es el resumen que Graph recorta a ~255 caracteres.
            # Con él, el detector de RFQ y el modelo de lenguaje analizaban un
            # correo truncado: un comprador que pone la cantidad y el material
            # en el tercer párrafo quedaba como "faltan datos". `body` trae el
            # cuerpo entero, y además dice si es HTML para poder limpiarlo.
            "$select": (
                "internetMessageId,subject,from,receivedDateTime,body,"
                "id,conversationId,internetMessageHeaders,hasAttachments"
            ),
            "$orderby": "receivedDateTime desc",
            "$top": 50,
        }
        headers = {"Authorization": f"Bearer {self.token}"}

        while url:
            respuesta = requests.get(url, headers=headers, params=params, timeout=30)
            respuesta.raise_for_status()
            datos = respuesta.json()

            for m in datos.get("value", []):
                msg_id = m.get("id")
                # Obtener cabeceras
                cabeceras = {h.get("name", "").lower(): h.get("value", "")
                             for h in (m.get("internetMessageHeaders") or [])}

                subject = m.get("subject") or "(Sin Asunto)"
                sender = m.get("from", {}).get("emailAddress", {}).get("address", "(Desconocido)")
                date = m.get("receivedDateTime", "")

                # Graph devuelve {"contentType": "html"|"text", "content": ...}.
                # El HTML se conserva TAL CUAL: limpiarlo es trabajo de
                # `app.shared.html_cleaner`, que se aplica más adelante en el
                # flujo y sabe quitar firmas, estilos y cabeceras citadas.
                # Aquí sólo se baja entero.
                cuerpo_graph = m.get("body") or {}
                body = cuerpo_graph.get("content") or ""
                es_html = (cuerpo_graph.get("contentType") or "").lower() == "html"
                if not body:
                    # Respaldo por si el buzón no devolvió el cuerpo: mejor el
                    # resumen recortado que nada.
                    body = m.get("bodyPreview", "")
                    es_html = False

                # Descargar adjuntos si existen
                attachments = []
                if m.get("hasAttachments"):
                    try:
                        attachments = self._fetch_attachments(usuario, msg_id)
                    except Exception as ex:
                        logger.warning(
                            f"No se pudieron descargar los adjuntos "
                            f"del correo {msg_id}: {ex}"
                        )

                # Registrar cabeceras útiles para hilos
                raw_headers = {
                    "Message-ID": m.get("internetMessageId", ""),
                    "In-Reply-To": cabeceras.get("in-reply-to", ""),
                    "References": cabeceras.get("references", ""),
                    "Conversation-ID": m.get("conversationId", "")
                }

                unread_emails.append(
                    EmailMessage(
                        id=msg_id,
                        sender=sender,
                        subject=subject,
                        body=body,
                        date=date,
                        attachments=attachments,
                        raw_headers=raw_headers,
                        body_is_html=es_html
                    )
                )

            url = datos.get("@odata.nextLink")
            params = None

        return unread_emails

    def _resolver_carpeta(self, usuario: str) -> str:
        """El id de Graph de la carpeta configurada en MAIL_FOLDER.

        Graph conoce las carpetas del sistema por un nombre fijo —``inbox``,
        ``sentitems``— que sirve directamente en la URL. Una carpeta creada a
        mano (TEST) no tiene ese nombre: hay que buscarla por su
        ``displayName`` y usar el id que devuelva. Se resuelve una vez por
        proveedor y se guarda; el id de una carpeta no cambia.
        """
        if self._carpeta_id:
            return self._carpeta_id

        carpeta = (getattr(settings, "MAIL_FOLDER", None) or "INBOX").strip()
        conocidas = {"inbox": "inbox", "sent items": "sentitems", "drafts": "drafts",
                     "deleted items": "deleteditems", "junk email": "junkemail",
                     "archive": "archive"}
        if carpeta.lower() in conocidas:
            self._carpeta_id = conocidas[carpeta.lower()]
            return self._carpeta_id

        headers = {"Authorization": f"Bearer {self.token}"}
        # Las comillas simples del nombre se doblan: es el escape de OData.
        nombre = carpeta.replace("'", "''")
        url = self.url_carpetas.format(usuario=usuario)
        params = {"$filter": f"displayName eq '{nombre}'", "$select": "id,displayName"}
        respuesta = requests.get(url, headers=headers, params=params, timeout=30)
        respuesta.raise_for_status()
        valores = respuesta.json().get("value") or []
        if not valores:
            # Puede ser una subcarpeta de la bandeja: se mira también ahí,
            # que es donde Outlook las crea cuando se hacen desde la bandeja.
            url_sub = url + "/inbox/childFolders"
            respuesta = requests.get(url_sub, headers=headers, params=params, timeout=30)
            respuesta.raise_for_status()
            valores = respuesta.json().get("value") or []
        if not valores:
            raise ValueError(
                f"No existe la carpeta '{carpeta}' en el buzón de {usuario} "
                f"(ni en la raíz ni dentro de la bandeja). Revisa MAIL_FOLDER.")
        self._carpeta_id = valores[0]["id"]
        logger.info(f"Leyendo la carpeta '{carpeta}' de Graph (id resuelto).")
        return self._carpeta_id

    def _fetch_attachments(self, usuario: str, message_id: str) -> List[EmailAttachment]:
        """Descarga y decodifica los adjuntos de un mensaje en Graph API."""
        url = f"https://graph.microsoft.com/v1.0/users/{usuario}/messages/{message_id}/attachments"
        headers = {"Authorization": f"Bearer {self.token}"}
        respuesta = requests.get(url, headers=headers, timeout=30)
        respuesta.raise_for_status()

        attachments = []
        for att in respuesta.json().get("value", []):
            if att.get("@odata.type") == "#microsoft.graph.fileAttachment":
                name = att.get("name", "adjunto")
                content_bytes_b64 = att.get("contentBytes", "")
                content = base64.b64decode(content_bytes_b64) if content_bytes_b64 else b""
                content_type = att.get("contentType")
                attachments.append(
                    EmailAttachment(
                        filename=name,
                        content=content,
                        content_type=content_type
                    )
                )
        return attachments

    @track_email_errors(default_fallback=False)
    def mark_as_read(self, message_id: str) -> bool:
        """Marca un correo como leído (isRead=True) en el servidor de Graph."""
        if not self.token:
            self.connect()
        assert self.token is not None

        usuario = settings.GRAPH_USER or settings.IMAP_USER
        url = f"https://graph.microsoft.com/v1.0/users/{usuario}/messages/{message_id}"

        logger.info(f"Marcando correo ID {message_id} como leído en Graph...")
        respuesta = requests.patch(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            },
            json={"isRead": True},
            timeout=30,
        )
        respuesta.raise_for_status()
        logger.info(f"Correo ID {message_id} marcado como leído exitosamente en Graph.")
        return True

    @track_email_errors(default_fallback=False)
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        attachments: Optional[List[EmailAttachment]] = None
    ) -> bool:
        """Despacha un correo electrónico saliente utilizando la Graph API de Microsoft."""
        if not self.token:
            self.connect()
        assert self.token is not None

        usuario = settings.GRAPH_USER or settings.IMAP_USER
        url = f"https://graph.microsoft.com/v1.0/users/{usuario}/sendMail"

        msg_payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "Text",
                    "content": body
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to
                        }
                    }
                ],
                "attachments": []
            }
        }

        if attachments:
            for att in attachments:
                content_b64 = base64.b64encode(att.content).decode("ascii")
                msg_payload["message"]["attachments"].append({
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": att.filename,
                    "contentType": att.content_type or "application/octet-stream",
                    "contentBytes": content_b64
                })

        logger.info(f"Enviando correo por Graph a {to}...")
        respuesta = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            },
            json=msg_payload,
            timeout=30
        )
        respuesta.raise_for_status()
        logger.info("Correo enviado exitosamente vía Graph.")
        return True
