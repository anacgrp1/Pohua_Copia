"""El correo leído desde el Outlook que ya está abierto en la computadora.

Por qué existe
--------------
El buzón de ventas vive en Microsoft 365, y ahí Microsoft retiró la
autenticación básica de IMAP y POP: usuario y contraseña ya no abren nada, y
no se puede volver a activar. La otra puerta, Microsoft Graph, necesita
registrar una aplicación en Entra ID, y eso depende de quien administre el
tenant.

Pero hay una tercera puerta que no depende de nadie más: el Outlook de
escritorio de la planta, que ya tiene el buzón abierto y autenticado. Esta
clase entra por ahí —automatización COM, la misma que usan las macros de
siempre— y lee la carpeta configurada sin pedir una sola credencial.

Es el proveedor de la aplicación de escritorio (``desktop_app/``), y se elige
con ``MAIL_MODE=outlook``.

Lo que hay que saber
--------------------
* Necesita Windows, ``pywin32`` y el Outlook **clásico** abierto (el "nuevo
  Outlook" no expone COM). Fuera de ahí, `connect()` dice qué falta.
* Cada hilo que use COM tiene que inicializarlo; `connect()` lo hace por su
  cuenta, así que la aplicación puede leer desde su hilo de trabajo sin saber
  nada de esto.
* El identificador de cada correo es su ``EntryID``: es estable dentro del
  buzón y es lo que se usa para volver a buscarlo al marcarlo como leído.
* El `Message-ID` de internet —el que usa el sistema para no procesar dos
  veces el mismo correo— no está en la interfaz normal de Outlook: se saca por
  ``PropertyAccessor`` con su etiqueta MAPI. Sin él, cada relectura sería un
  correo nuevo.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from email.utils import format_datetime
from typing import List, Optional

from app.core.config import settings
from app.email.base_provider import BaseEmailProvider, EmailAttachment, EmailMessage

logger = logging.getLogger("OutlookEmailProvider")

# Etiquetas MAPI de las cabeceras de internet. Outlook no las expone como
# propiedades normales; se piden por su "esquema" con el PropertyAccessor.
PR_INTERNET_MESSAGE_ID = "http://schemas.microsoft.com/mapi/proptag/0x1035001F"
PR_IN_REPLY_TO_ID = "http://schemas.microsoft.com/mapi/proptag/0x1042001F"
PR_INTERNET_REFERENCES = "http://schemas.microsoft.com/mapi/proptag/0x1039001F"
PR_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"
# La dirección SMTP de quien manda, leída del propio mensaje.
#
# Esta es la que NO despierta al guardián de Outlook. `SenderEmailAddress`,
# `SenderEmailType` y `Sender.GetExchangeUser()` sí: son propiedades de
# LIBRETA DE DIRECCIONES, y tocarlas saca el cuadro «A program is trying to
# access email address information stored in Outlook». `PropertyAccessor`
# sobre estas dos lee lo mismo sin pasar por ahí.
PR_SENDER_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x5D01001F"

# --- El cuadro de «A program is trying to send an email message on your
# behalf» -------------------------------------------------------------------
#
# Lo saca el guardián de Outlook en CADA `Send()` cuando no confía en el
# programa, y a diferencia del de la libreta de direcciones NO tiene «permitir
# durante 10 minutos»: una ventana por correo. Outlook confía solo cuando ve un
# antivirus en buen estado (Archivo → Opciones → Centro de confianza → Acceso
# mediante programación). Eso no se arregla desde el código; lo que sí se hace
# aquí es que no se amontonen:
#
#   * Si alguien pulsa «Deny», Outlook contesta E_ABORT. Se deja de llamar a
#     `Send()` durante un rato y los correos esperan en la bandeja de salida,
#     en vez de sacar una ventana nueva por cada uno que quede.
#   * `outlook_confia()` lo pregunta UNA vez al arrancar, para decirlo en la
#     aplicación de escritorio en lugar de descubrirlo a base de ventanas.
E_ABORT = -2147467260                  # 0x80004004
PAUSA_TRAS_DENEGAR_S = 15 * 60
_denegado_en: Optional[float] = None   # del módulo: vale para todas las instancias


class EnvioDenegado(RuntimeError):
    """Outlook no dejó mandar: alguien pulsó «Deny», o se pulsó hace poco."""


def _es_denegado(error: BaseException) -> bool:
    """¿Es el E_ABORT de la ventana de Outlook? Viene en el HRESULT o dentro
    del excepinfo, según por dónde lo devuelva pywin32."""
    args = getattr(error, "args", ()) or ()
    if args and args[0] == E_ABORT:
        return True
    info = args[2] if len(args) > 2 else None
    return bool(isinstance(info, tuple) and len(info) > 5 and info[5] == E_ABORT)


def _marcar_denegado() -> None:
    global _denegado_en
    _denegado_en = time.monotonic()


def envio_en_pausa() -> bool:
    """¿Se pulsó «Deny» hace menos de PAUSA_TRAS_DENEGAR_S?"""
    return (_denegado_en is not None and
            time.monotonic() - _denegado_en < PAUSA_TRAS_DENEGAR_S)


def outlook_confia() -> Optional[bool]:
    """¿Manda Outlook sin preguntar? None si no se puede saber (sin Outlook,
    sin pywin32, u Outlook que no expone `IsTrusted`)."""
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        return bool(win32com.client.Dispatch("Outlook.Application").IsTrusted)
    except Exception as error:
        logger.debug("No se pudo preguntar a Outlook si confía: %s", error)
        return None
PR_SENT_REPRESENTING_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x5D02001F"
# Para incrustar la firma: el "cid" del HTML y la marca de "no la
# enseñes como archivo adjunto".
PR_ATTACH_CONTENT_ID = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
PR_ATTACHMENT_HIDDEN = "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"

CLASE_CORREO = 43          # olMail: lo demás (citas, avisos) no se procesa
MAX_BYTES_ADJUNTO = 25 * 1024 * 1024

AVISO_GUARDIAN = (
    "Outlook no dejó leer la dirección del remitente (el aviso de seguridad "
    "\"A program is trying to access e-mail address information\"). Marca en "
    "ese aviso la casilla \"Allow access for\" con 10 minutos antes de "
    "aceptar, o pide a sistemas que apruebe el acceso programático. Los "
    "correos se quedan SIN LEER: se vuelven a intentar solos."
)


class AccesoBloqueado(RuntimeError):
    """El guardián de Outlook cortó el acceso a la dirección del remitente.

    Es una excepción propia y no un remitente vacío a propósito. Sin la
    dirección no se puede ni reconocer al cliente ni contestarle, así que el
    correo no se procesa a medias: se deja sin leer y se reintenta cuando el
    permiso esté dado. Antes esto se veía como "0 correos", que es la peor
    manera de contar un permiso denegado.
    """


class OutlookEmailProvider(BaseEmailProvider):
    """Lee (y manda) por el Outlook de escritorio, sin credenciales propias."""

    def __init__(self) -> None:
        self._outlook = None
        self._mapi = None
        self._carpeta = None
        # Buzón (en minúsculas) → cuenta del perfil, o None si no está. Ver
        # `_cuenta`: recorrer las cuentas despierta al guardián de Outlook, y
        # esto es lo que hace que sólo lo despierte una vez.
        self._cuentas_vistas = {}

    # ---------------------------------------------------------------- COM

    def _iniciar_com(self) -> None:
        """COM se inicializa POR HILO. La aplicación lee en un hilo aparte."""
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception as error:          # ya inicializado, o no es Windows
            logger.debug("CoInitialize no hizo falta o no aplica: %s", error)

    def connect(self) -> bool:
        """Se engancha al Outlook abierto y localiza el buzón y la carpeta."""
        buzon = (getattr(settings, "OUTLOOK_BUZON", "") or
                 getattr(settings, "IMAP_USER", "") or "").strip()
        carpeta = (getattr(settings, "MAIL_FOLDER", "") or "INBOX").strip()

        self._iniciar_com()
        try:
            import win32com.client
        except ImportError:
            logger.error("Falta pywin32: pip install -r requirements-desktop.txt")
            return False

        try:
            self._outlook = win32com.client.Dispatch("Outlook.Application")
            self._mapi = self._outlook.GetNamespace("MAPI")
        except Exception as error:
            logger.error("No se pudo hablar con Outlook (¿está abierto, y es el "
                         "Outlook clásico?): %s", error)
            return False

        raiz = self._raiz_del_buzon(buzon)
        if raiz is None:
            logger.error("No encuentro el buzón '%s' en este Outlook. Buzones "
                         "abiertos: %s", buzon, ", ".join(self._buzones()))
            return False

        self._carpeta = (raiz if carpeta.upper() == "INBOX" and raiz is not None
                         and self._es_bandeja(raiz) else self._buscar_carpeta(raiz, carpeta))
        if self._carpeta is None:
            logger.error("El buzón '%s' no tiene una carpeta '%s'.", buzon, carpeta)
            return False

        logger.info("Leyendo '%s' del buzón '%s' por el Outlook de escritorio.",
                    carpeta, buzon)
        return True

    # ------------------------------------------------------- buzón y carpeta

    def _buzones(self) -> List[str]:
        try:
            return [self._mapi.Folders.Item(i + 1).Name
                    for i in range(self._mapi.Folders.Count)]
        except Exception:
            return []

    def _raiz_del_buzon(self, buzon: str):
        """La carpeta raíz del buzón pedido.

        Outlook nombra cada buzón abierto como una carpeta de primer nivel, y
        ese nombre puede ser la dirección ("sales.isc@…") o el nombre para
        mostrar ("ISC Sales"). Se acepta cualquiera de los dos, y si sólo hay
        un buzón abierto se usa ése: en la computadora de la planta es lo
        normal y ahorra tener que configurar nada.
        """
        try:
            carpetas = [self._mapi.Folders.Item(i + 1)
                        for i in range(self._mapi.Folders.Count)]
        except Exception as error:
            logger.error("No se pudieron listar los buzones de Outlook: %s", error)
            return None

        if not carpetas:
            return None
        if not buzon:
            return carpetas[0]

        objetivo = buzon.lower()
        for carpeta in carpetas:
            nombre = (carpeta.Name or "").lower()
            if objetivo == nombre or objetivo in nombre:
                return carpeta

        # Segundo intento: por la dirección SMTP de la cuenta, que no siempre
        # coincide con el nombre que se ve en la lista de carpetas.
        try:
            for i in range(self._mapi.Stores.Count):
                almacen = self._mapi.Stores.Item(i + 1)
                correo = ""
                try:
                    correo = (almacen.PropertyAccessor
                              .GetProperty(PR_SMTP_ADDRESS) or "")
                except Exception:
                    pass
                if correo and correo.lower() == objetivo:
                    return almacen.GetRootFolder()
        except Exception as error:
            logger.debug("No se pudo recorrer los almacenes: %s", error)
        return None

    def _es_bandeja(self, carpeta) -> bool:
        try:
            return (carpeta.Name or "").lower() in ("bandeja de entrada", "inbox")
        except Exception:
            return False

    def _buscar_carpeta(self, raiz, nombre: str, profundidad: int = 0):
        """La carpeta por su nombre, buscando hacia abajo desde la raíz.

        Se busca en todo el árbol porque TEST puede estar colgada de la bandeja
        de entrada o del propio buzón, y quien la creó no tiene por qué
        acordarse de dónde la puso.
        """
        if profundidad > 4:
            return None
        objetivo = nombre.lower()
        try:
            hijas = [raiz.Folders.Item(i + 1) for i in range(raiz.Folders.Count)]
        except Exception:
            return None

        for hija in hijas:
            try:
                if (hija.Name or "").lower() == objetivo:
                    return hija
            except Exception:
                continue
        for hija in hijas:
            encontrada = self._buscar_carpeta(hija, nombre, profundidad + 1)
            if encontrada is not None:
                return encontrada
        return None

    # ------------------------------------------------------------- lectura

    def fetch_unread_messages(self) -> List[EmailMessage]:
        """Los correos sin leer de la carpeta, del más viejo al más nuevo."""
        if self._carpeta is None and not self.connect():
            return []

        try:
            items = self._carpeta.Items
            items.Sort("[ReceivedTime]", False)          # los viejos primero
            sin_leer = items.Restrict("[Unread] = True")
        except Exception as error:
            logger.error("No se pudo consultar la carpeta: %s", error)
            return []

        correos: List[EmailMessage] = []
        try:
            total = sin_leer.Count
        except Exception:
            total = 0

        bloqueados = 0
        for i in range(total):
            try:
                item = sin_leer.Item(i + 1)
                if getattr(item, "Class", CLASE_CORREO) != CLASE_CORREO:
                    continue
                correos.append(self._a_mensaje(item))
            except AccesoBloqueado:
                # El permiso se pide una vez y se explica una vez: un correo
                # por línea sería el mismo aviso repetido veinte veces.
                bloqueados += 1
            except Exception as error:
                # Un correo que no se deja leer no puede parar a los demás.
                logger.exception("No se pudo leer un correo de la carpeta: %s", error)

        if bloqueados:
            logger.error("%d correo(s) no se pudieron leer. %s",
                         bloqueados, AVISO_GUARDIAN)

        logger.info("Se encontraron %d correo(s) sin leer.", len(correos))
        return correos

    def _propiedad(self, item, esquema: str) -> str:
        try:
            return str(item.PropertyAccessor.GetProperty(esquema) or "").strip()
        except Exception:
            return ""

    def _remitente(self, item) -> str:
        """La dirección SMTP del remitente, no el galimatías de Exchange.

        Dentro de una organización, `SenderEmailAddress` devuelve la ruta
        interna (`/O=EXCHANGELABS/OU=…`), que no sirve ni para responder ni
        para reconocer al cliente.

        El ORDEN importa y no es el obvio. Las propiedades que Outlook
        considera "libreta de direcciones" —`SenderEmailType`, `Sender`,
        `GetExchangeUser()`, `SenderEmailAddress`— despiertan al guardián y
        sacan el cuadro «A program is trying to access email address
        information stored in Outlook», que hay que aprobar a mano en cada
        correo. `PropertyAccessor` sobre las propiedades MAPI del mensaje lee
        la MISMA dirección sin pasar por ahí, así que va primero.

        Las guardadas quedan de respaldo para el caso raro en que el mensaje
        no traiga las MAPI: un correo importado de otro sistema, o uno que
        nunca salió de un PST. Entonces sí saldrá el cuadro, pero por una de
        cada mil y no por todas.
        """
        # Primero, sin despertar al guardián.
        for propiedad in (PR_SENDER_SMTP_ADDRESS,
                          PR_SENT_REPRESENTING_SMTP_ADDRESS,
                          PR_SMTP_ADDRESS):
            smtp = self._propiedad(item, propiedad)
            if smtp and "@" in smtp:
                return smtp

        logger.debug("Las propiedades MAPI del remitente vinieron vacías; se "
                     "prueban las de libreta, que pueden pedir permiso.")

        tipo = ""
        try:
            tipo = (item.SenderEmailType or "").upper()
        except Exception as error:
            logger.debug("No se pudo leer SenderEmailType: %s", error)

        if tipo == "EX":
            try:
                usuario = item.Sender.GetExchangeUser()
                if usuario and usuario.PrimarySmtpAddress:
                    return str(usuario.PrimarySmtpAddress)
            except Exception as error:
                logger.debug("GetExchangeUser no contestó: %s", error)

        try:
            directa = str(item.SenderEmailAddress or "")
        except Exception as error:
            logger.debug("SenderEmailAddress no contestó: %s", error)
            directa = ""
        if directa:
            return directa

        # Ninguno de los tres caminos dio nada. En una organización de
        # Exchange eso no pasa por un correo raro: pasa porque el guardián de
        # Outlook los está cortando todos.
        raise AccesoBloqueado(AVISO_GUARDIAN)

    def _fecha(self, item) -> str:
        try:
            recibido = item.ReceivedTime
            import datetime as _dt
            if isinstance(recibido, _dt.datetime):
                return format_datetime(recibido)
            return str(recibido)
        except Exception:
            return ""

    def _adjuntos(self, item) -> List[EmailAttachment]:
        fuera: List[EmailAttachment] = []
        try:
            cuantos = item.Attachments.Count
        except Exception:
            return fuera

        for i in range(cuantos):
            ruta = None
            try:
                adjunto = item.Attachments.Item(i + 1)
                nombre = str(adjunto.FileName or f"adjunto-{i + 1}")
                if getattr(adjunto, "Size", 0) > MAX_BYTES_ADJUNTO:
                    logger.warning("Adjunto '%s' demasiado grande: se omite.", nombre)
                    continue
                # ¿Va incrustado en el cuerpo? La firma con logo llega como un
                # adjunto más y Outlook no lo dice en ninguna propiedad
                # normal: hay que preguntarle a MAPI por el Content-ID, que es
                # justo lo que la distingue de un plano de verdad.
                cid = self._propiedad(adjunto, PR_ATTACH_CONTENT_ID)
                # Outlook no entrega los bytes: los escribe en disco.
                carpeta = tempfile.mkdtemp(prefix="pohua-adj-")
                ruta = os.path.join(carpeta, os.path.basename(nombre))
                adjunto.SaveAsFile(ruta)
                with open(ruta, "rb") as fichero:
                    fuera.append(EmailAttachment(filename=nombre,
                                                 content=fichero.read(),
                                                 content_id=cid or None))
            except Exception as error:
                logger.warning("No se pudo guardar un adjunto: %s", error)
            finally:
                if ruta and os.path.exists(ruta):
                    try:
                        os.remove(ruta)
                        os.rmdir(os.path.dirname(ruta))
                    except OSError:
                        pass
        return fuera

    def _a_mensaje(self, item) -> EmailMessage:
        cuerpo_html = ""
        try:
            cuerpo_html = str(item.HTMLBody or "")
        except Exception:
            pass
        cuerpo = cuerpo_html or str(getattr(item, "Body", "") or "")

        cabeceras = {}
        mensaje_id = self._propiedad(item, PR_INTERNET_MESSAGE_ID)
        if mensaje_id:
            cabeceras["Message-ID"] = mensaje_id
        respuesta_a = self._propiedad(item, PR_IN_REPLY_TO_ID)
        if respuesta_a:
            cabeceras["In-Reply-To"] = respuesta_a
        referencias = self._propiedad(item, PR_INTERNET_REFERENCES)
        if referencias:
            cabeceras["References"] = referencias

        return EmailMessage(
            id=str(item.EntryID),
            sender=self._remitente(item),
            subject=str(getattr(item, "Subject", "") or ""),
            body=cuerpo,
            date=self._fecha(item),
            attachments=self._adjuntos(item),
            raw_headers=cabeceras,
            body_is_html=bool(cuerpo_html),
        )

    # -------------------------------------------------------------- marcar

    def mark_as_read(self, message_id: str) -> bool:
        """Marca como leído el correo, buscándolo por su EntryID."""
        if self._mapi is None and not self.connect():
            return False
        try:
            item = self._mapi.GetItemFromID(message_id)
            item.UnRead = False
            item.Save()
            return True
        except Exception as error:
            logger.error("No se pudo marcar como leído (%s): %s", message_id, error)
            return False

    def _cuenta(self, buzon: str):
        """La cuenta de ese buzón en el perfil, preguntándolo UNA sola vez.

        Por qué el recuerdo
        -------------------
        Recorrer `Session.Accounts` y leer su `SmtpAddress` es, palabra por
        palabra, lo que el guardián de Outlook llama «email address
        information stored in Outlook». Cada recorrido puede levantar el
        cuadro de «A program is trying to access…», y esto se llamaba en CADA
        envío: la bandeja de salida se vacía en cada ciclo del lector, así que
        el cuadro salía una y otra vez y había que darle a Permitir a cada
        rato —que es justo la costumbre que hace que un día alguien le dé a
        Permitir a algo que no era esto—.

        Las cuentas de un perfil de Outlook no cambian mientras el programa
        corre. Preguntarlo una vez por proceso y recordarlo baja el cuadro de
        "en cada correo" a "como mucho una vez al arrancar", sin tocar
        permisos ni el registro de Windows.

        Se recuerda también el "no está": un buzón que no está en el perfil
        tampoco aparece solo, y buscarlo otra vez costaría otro cuadro para
        volver a no encontrarlo.
        """
        clave = (buzon or "").lower()
        if clave in self._cuentas_vistas:
            return self._cuentas_vistas[clave]
        cuenta = self._buscar_cuenta(buzon)
        self._cuentas_vistas[clave] = cuenta
        return cuenta

    def _buscar_cuenta(self, buzon: str):
        """La cuenta de Outlook que corresponde a ese buzón, si la hay.

        Importa de verdad para el remitente. Con `SentOnBehalfOfName` el correo
        sale "en nombre de" el buzón de ventas, y eso pide un permiso concreto
        en Exchange; si no se tiene, el mensaje llega con el remitente sin
        resolver —"System Administrator", con la ruta interna
        `/o=ExchangeLabs/...`— y el cliente ni siquiera puede contestar.

        Si ese buzón está añadido como CUENTA en el perfil de Outlook, se manda
        con ella y el correo sale COMO ventas, que es lo que se quiere. La otra
        vía se queda de respaldo.
        """
        try:
            cuentas = self._outlook.Session.Accounts
            for i in range(cuentas.Count):
                cuenta = cuentas.Item(i + 1)
                direccion = str(getattr(cuenta, "SmtpAddress", "") or "")
                if direccion.lower() == buzon.lower():
                    return cuenta
        except Exception as error:
            logger.debug("No se pudieron listar las cuentas de Outlook: %s", error)
        return None

    def _poner_cuenta(self, correo, cuenta) -> bool:
        """Deja el correo colgado de esa cuenta. Devuelve si de verdad quedó.

        `SendUsingAccount` no es una propiedad normal: guarda un OBJETO, y eso
        en COM se asigna con "propertyputref". La asignación de toda la vida
        (`correo.SendUsingAccount = cuenta`) unas veces funciona y otras se
        traga en silencio según la versión de pywin32 — y cuando se la traga,
        el correo sale por la cuenta personal de quien tenga Outlook abierto
        sin que nada falle. Por eso se comprueba después, y si no quedó se
        pone por el camino largo: 64209 es el identificador de la propiedad en
        el modelo de Outlook, y 8 es "guarda una referencia".
        """
        def puesta():
            try:
                actual = correo.SendUsingAccount
                return str(getattr(actual, "SmtpAddress", "") or "").lower()
            except Exception:
                return ""

        objetivo = str(getattr(cuenta, "SmtpAddress", "") or "").lower()
        try:
            correo.SendUsingAccount = cuenta
        except Exception as error:
            logger.debug("Asignación directa de la cuenta rechazada: %s", error)
        if puesta() == objetivo:
            return True

        try:
            correo._oleobj_.Invoke(*(64209, 0, 8, 0, cuenta))
        except Exception as error:
            logger.debug("Tampoco por propertyputref: %s", error)
        return puesta() == objetivo

    def _fijar_remitente(self, correo) -> None:
        """De quién sale el correo: del buzón de ventas, no de quien lo manda.

        Tres intentos, de mejor a peor: la cuenta de ese buzón si está en el
        perfil (sale COMO ventas), "en nombre de" si no está (necesita permiso
        en Exchange), y si nada de eso agarra, se dice en el registro — porque
        el correo saldrá con el remitente personal de quien tenga Outlook
        abierto, y eso el cliente lo ve.
        """
        buzon = (getattr(settings, "OUTLOOK_BUZON", "") or "").strip()
        if not buzon:
            return

        cuenta = self._cuenta(buzon)
        if cuenta is not None and self._poner_cuenta(correo, cuenta):
            logger.info("El correo sale como %s.", buzon)
            return

        if cuenta is not None:
            logger.warning("La cuenta %s está en Outlook, pero no se pudo "
                           "colgar el correo de ella; se intenta en su nombre.",
                           buzon)
        else:
            logger.info("%s no está como cuenta en este perfil de Outlook "
                        "(cuentas: %s); se manda en su nombre.",
                        buzon, ", ".join(self._cuentas_del_perfil()) or "ninguna")

        try:
            correo.SentOnBehalfOfName = buzon
        except Exception as error:
            logger.error("No se pudo fijar el remitente a %s (%s). El correo "
                         "saldría desde la cuenta personal del perfil.",
                         buzon, error)
            return

        puesto = str(getattr(correo, "SentOnBehalfOfName", "") or "")
        if not puesto:
            logger.error("Outlook no aceptó el remitente %s: el correo saldría "
                         "desde la cuenta personal del perfil. Hace falta el "
                         "permiso de 'enviar en nombre de' ese buzón, o "
                         "añadirlo como cuenta en Outlook.", buzon)

    def _cuentas_del_perfil(self):
        """Las direcciones de las cuentas del perfil, para poder decirlo.

        Sólo se llama para redactar un aviso —cuando el buzón configurado no
        está en el perfil—, nunca en el camino bueno: recorrer las cuentas
        cuesta un cuadro de permiso, y gastarlo para adornar un registro sería
        cobrarle al usuario por una frase.
        """
        fuera = []
        try:
            cuentas = self._outlook.Session.Accounts
            for i in range(cuentas.Count):
                direccion = str(getattr(cuentas.Item(i + 1), "SmtpAddress", "") or "")
                if direccion:
                    fuera.append(direccion)
        except Exception:
            pass
        return fuera

    # --------------------------------------------------------------- envío

    def send_email(self, to: str, subject: str, body: str,
                   attachments: Optional[List[EmailAttachment]] = None) -> bool:
        """Manda el correo POR OUTLOOK, desde el buzón que ya está abierto.

        Así la respuesta al cliente sale con la firma y el remitente de
        siempre, sin SMTP ni tokens: el mismo camino que si alguien la hubiera
        escrito a mano.
        """
        if envio_en_pausa():
            raise EnvioDenegado(
                "Outlook no dejó mandar hace menos de %d min; el correo espera en "
                "la bandeja de salida." % (PAUSA_TRAS_DENEGAR_S // 60))
        if self._outlook is None and not self.connect():
            return False

        temporales = []
        try:
            correo = self._outlook.CreateItem(0)      # olMailItem
            correo.To = to
            correo.Subject = subject
            if "<" in body and ">" in body:
                correo.HTMLBody = body
            else:
                correo.Body = body

            for adjunto in (attachments or []):
                carpeta = tempfile.mkdtemp(prefix="pohua-env-")
                ruta = os.path.join(carpeta, os.path.basename(adjunto.filename))
                with open(ruta, "wb") as fichero:
                    fichero.write(adjunto.content)
                temporales.append(ruta)
                puesto = correo.Attachments.Add(ruta)

                # La firma se incrusta: se le pone el mismo "cid" que lleva el
                # <img> del cuerpo y se esconde de la lista de adjuntos. Si
                # Outlook no deja marcarla, el correo sale igual —con el logo
                # como archivo adjunto, que es feo pero no roto—.
                if adjunto.content_id:
                    try:
                        propiedades = puesto.PropertyAccessor
                        propiedades.SetProperty(PR_ATTACH_CONTENT_ID,
                                                adjunto.content_id)
                        propiedades.SetProperty(PR_ATTACHMENT_HIDDEN, True)
                    except Exception as error:
                        logger.debug("No se pudo incrustar %s: %s",
                                     adjunto.filename, error)

            # Desde el buzón compartido, no desde la cuenta personal de quien
            # tenga Outlook abierto: el cliente contesta a ventas.
            self._fijar_remitente(correo)

            correo.Send()
            logger.info("Correo enviado por Outlook a %s.", to)
            return True
        except Exception as error:
            if _es_denegado(error):
                _marcar_denegado()
                logger.warning("Outlook no dejó mandar el correo a %s (se pulsó "
                               "«Deny»). No se vuelve a intentar en %d min.",
                               to, PAUSA_TRAS_DENEGAR_S // 60)
                raise EnvioDenegado("Outlook no dejó mandar el correo.") from error
            logger.error("No se pudo enviar por Outlook: %s", error)
            return False
        finally:
            for ruta in temporales:
                try:
                    os.remove(ruta)
                    os.rmdir(os.path.dirname(ruta))
                except OSError:
                    pass

    def disconnect(self) -> bool:
        """No hay nada que cerrar: Outlook sigue abierto, es de quien lo usa."""
        self._carpeta = None
        return True
