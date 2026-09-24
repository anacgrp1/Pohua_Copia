"""Canal de salida del correo, compartido por todo lo que le escribe al cliente.

Propósito
---------
Un solo lugar que decida **si** se manda un correo y **por dónde** sale. Lo
usan hoy dos flujos distintos:

* ``flujo_rfq`` — la petición de datos faltantes al comprador (COT-36/59).
* ``decision_pm`` — la declinación cuando el plant manager resuelve que el
  RFQ no es factible (COT-72).

Tener el interruptor duplicado sería peor que la duplicación normal: quien
apagara ``ENVIO_AUTOMATICO`` esperando silencio total podría seguir mandando
declinaciones a clientes reales por la otra rama.

Alcance
-------
* **Sí hace:** resolver el interruptor de envío y elegir el transporte
  (``smtp_sender`` en ``<Local>``, ``graph_sender`` en ``<Token>``).
* **NO hace:** redactar el correo (eso es ``email_templates``, COT-59) ni
  decidir a quién escribirle (eso es de cada flujo).

Funciones públicas
------------------
``envio_habilitado() -> bool``
``enviar(contenido) -> bool``
``nombre_comprador(datos) -> str``
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("cotizador.correo_saliente")

_MODOS_TOKEN = ("graph", "token", "prod")
_MODOS_OUTLOOK = ("outlook", "com", "escritorio")


def _interruptor(nombre: str, por_defecto: bool) -> bool:
    """Lee un interruptor de envío de la configuración o del entorno.

    ``config`` ya lo entrega convertido a bool (COT-56); el resto del cuerpo
    cubre que se inyecte a mano en pruebas o por variable de entorno.
    """
    import app.core.config as config
    valor = getattr(config, nombre, None)
    if isinstance(valor, bool):
        return valor
    if valor is None:
        valor = os.environ.get(nombre)
    if valor is None:
        return por_defecto
    return str(valor).strip().lower() in ("1", "true", "yes", "on")


def envio_habilitado(manual: bool = False) -> bool:
    """
    ¿Sale el correo de verdad?

    Hay DOS interruptores porque son dos decisiones distintas:

    * Lo que el sistema manda SOLO —la petición de datos al comprador y los
      recordatorios— va con ``ENVIO_AUTOMATICO``, apagado por defecto. Es un
      buzón de clientes reales: el robot no escribe por arrastre del cableado.

    * Lo que manda UNA PERSONA pulsando un botón, con el destinatario y las
      condiciones delante —la oferta al aprobar y la declinación al
      declinar— va con ``ENVIO_MANUAL``, encendido por defecto. Ahí ya hay alguien decidiendo; exigirle además encender el
      envío automático significaba que, para que llegara UNA oferta, el robot
      quedaba suelto contestándole a cualquiera.

    Con los dos apagados no sale un solo correo, que es lo que hace falta para
    ensayar el recorrido entero sin molestar a nadie.
    """
    if manual:
        return _interruptor("ENVIO_MANUAL", True)
    return _interruptor("ENVIO_AUTOMATICO", False)


class SinCuentaEmisora(RuntimeError):
    """El modo activo no tiene con qué mandar el correo.

    Es distinto de "el envío está apagado": ahí la decisión es de alguien. Esto
    es que no hay cuenta, y por más que se pulse el botón no va a salir nunca.
    """

    def __init__(self, modo: str, faltan):
        self.modo = modo
        self.faltan = list(faltan)
        super().__init__(
            "El servidor no tiene cuenta para mandar correo en modo %s. "
            "Falta: %s." % (modo.upper(), ", ".join(self.faltan)))


def _puesto(c, *nombres) -> bool:
    """¿Alguno de esos ajustes tiene valor?"""
    return any((getattr(c, n, "") or "").strip() for n in nombres)


def diagnostico_envio() -> dict:
    """¿Puede este proceso mandar un correo, y si no, qué le falta?

    Existe porque el fallo se veía tardísimo y decía lo que no era: el PM
    pulsaba «Enviar oferta», se generaba el PDF, y sólo entonces saltaba «No
    hay cuenta emisora configurada (SMTP_USER / IMAP_USER)» —los nombres de
    SMTP— aunque el modo activo fuera Graph, donde esas dos variables no
    pintan nada. Lo que hace falta saber es: en ESTE modo, ¿con qué cuenta se
    manda, y qué falta para tenerla?

    Devuelve ``{modo, canal, puede, faltan, nota}``. No lanza y no toca la
    red: sólo mira la configuración, así que se puede llamar al pintar la
    pantalla, antes de que nadie pulse nada.
    """
    import app.core.config as config
    c = config.settings
    modo = str(getattr(c, "MAIL_MODE", "imap") or "imap").lower()

    if modo in _MODOS_OUTLOOK:
        # Aquí no hay credenciales que comprobar: manda el Outlook que ya está
        # abierto en esa computadora. Lo que sí se puede decir es que en un
        # servidor Linux no hay tal Outlook, por muy bien puesto que esté.
        import sys
        en_windows = sys.platform == "win32"
        return {
            "modo": modo, "canal": "outlook",
            "puede": en_windows, "faltan": [] if en_windows else ["Outlook"],
            "nota": ("Manda el Outlook de escritorio de esta computadora."
                     if en_windows else
                     "MAIL_MODE=outlook necesita el Outlook de escritorio, y "
                     "este proceso no corre en Windows. En el servidor hay que "
                     "usar graph (o smtp)."),
        }

    if modo in _MODOS_TOKEN:
        faltan = [n for n in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID",
                              "AZURE_CLIENT_SECRET")
                  if not _puesto(c, n)]
        if not _puesto(c, "GRAPH_USER", "IMAP_USER"):
            faltan.append("GRAPH_USER")
        return {"modo": modo, "canal": "graph", "puede": not faltan,
                "faltan": faltan,
                "nota": "La aplicación de Entra ID necesita el permiso "
                        "Mail.Send sobre ese buzón."}

    # Se nombran las dos: el emisor acepta las de SMTP y, si no, las del
    # buzón IMAP —es la misma cuenta—, y con MAIL_MODE=imap lo natural es
    # poner las segundas. Decir sólo "SMTP_USER" manda a crear una variable
    # que no hacía falta.
    faltan = []
    if not _puesto(c, "SMTP_USER", "IMAP_USER"):
        faltan.append("SMTP_USER (o IMAP_USER)")
    if not _puesto(c, "SMTP_PASSWORD", "IMAP_PASSWORD"):
        faltan.append("SMTP_PASSWORD (o IMAP_PASSWORD)")
    return {"modo": modo, "canal": "smtp", "puede": not faltan, "faltan": faltan,
            "nota": "En Microsoft 365 la autenticación básica está retirada: "
                    "SMTP con usuario y contraseña ya no entra. Para mandar "
                    "desde el servidor hay que usar MAIL_MODE=graph."}


def enviar(contenido, rfq_id=None, clase="aviso", por=None) -> bool:
    """Envía el correo por el canal del modo activo: SMTP, Graph u Outlook.

    Y si este proceso NO tiene cuenta emisora, lo deja en la bandeja de salida
    en vez de reventar.

    Por qué el respaldo
    -------------------
    Render no tiene buzón: el de ventas se abre por el Outlook de una
    computadora concreta. Eso ya estaba resuelto para la OFERTA, que se encola
    en `correos_salida` y la aplicación de escritorio despacha en su ciclo.

    Pero la declinación, la petición de datos faltantes y los recordatorios
    llamaban aquí directamente. En Render eso levanta `SinCuentaEmisora`, el
    que llama se lo traga y anota un error, y el correo no sale ni se guarda:
    se pierde. Un RFQ declinado cuyo comprador nunca se entera es peor que uno
    sin declinar, porque en la pantalla pone Declined.

    Encolar en lugar de fallar convierte "se perdió" en "está esperando", y la
    misma computadora que ya manda las ofertas lo manda. El que llama recibe
    ``True``: el correo va a salir, sólo que no desde aquí.

    `getattr(config, ...)` miraba el MÓDULO, donde `MAIL_MODE` no existe: se
    quedaba siempre con "imap" y mandaba por SMTP aunque estuviera configurado
    Graph. El ajuste vive en `config.settings`.
    """
    import app.core.config as config
    modo = str(getattr(config.settings, "MAIL_MODE", "imap") or "imap").lower()

    # Comprobarlo ANTES de abrir nada: así el mensaje nombra el modo activo y
    # las variables de ESE modo, en vez del error de SMTP para todos.
    diag = diagnostico_envio()
    if not diag["puede"]:
        return _encolar_o_fallar(contenido, diag, rfq_id, clase, por)

    if modo in _MODOS_OUTLOOK:
        # Por el Outlook que ya está abierto: mismo remitente y misma firma
        # que si lo hubiera escrito una persona.
        from app.email.factory import EmailProviderFactory
        from app.email.outlook_provider import EnvioDenegado
        proveedor = EmailProviderFactory.get_provider()
        try:
            return proveedor.send_email(
                to=contenido["destinatario"],
                subject=contenido["asunto"],
                body=contenido.get("cuerpo_html") or contenido.get("cuerpo_texto", ""),
                attachments=_adjuntos(contenido),
            )
        except EnvioDenegado as error:
            # Outlook no dejó mandar: el correo no se pierde, espera en la
            # bandeja de salida y lo manda el siguiente ciclo que pueda.
            import app.email.bandeja_salida as bandeja
            cola_id = bandeja.encolar(contenido, rfq_id=rfq_id, clase=clase, por=por)
            log.warning("%s El correo a %s queda en la bandeja de salida (id %s).",
                        error, contenido.get("destinatario"), cola_id)
            return True
    if modo in _MODOS_TOKEN:
        import app.email.graph_sender as graph_sender
        return graph_sender.enviar_correo_graph(contenido)
    import app.email.smtp_sender as smtp_sender
    return smtp_sender.enviar_correo_smtp(contenido)


def _encolar_o_fallar(contenido, diag, rfq_id, clase, por) -> bool:
    """Deja el correo en la bandeja. Si tampoco se puede, entonces sí falla.

    Se lanza `SinCuentaEmisora` sólo cuando el correo NO queda en ningún
    sitio: es la diferencia entre "esto tarda" y "esto se perdió", y quien
    llama necesita poder distinguirlas.
    """
    try:
        import app.email.bandeja_salida as bandeja
        cola_id = bandeja.encolar(contenido, rfq_id=rfq_id, clase=clase, por=por)
    except Exception as error:
        log.error("Sin cuenta emisora y sin bandeja de salida (%s): el correo "
                  "a %s NO sale. %s", error,
                  contenido.get("destinatario"), diag.get("nota") or "")
        raise SinCuentaEmisora(diag["modo"], diag["faltan"]) from error

    log.info("Este proceso no tiene cuenta emisora (%s): el correo a %s queda "
             "en la bandeja de salida (id %s, %s) y lo manda la aplicación de "
             "escritorio en su ciclo.",
             diag["modo"], contenido.get("destinatario"), cola_id, clase)
    return True


def _adjuntos(contenido):
    """Los archivos del correo, leídos a bytes para el proveedor de Outlook.

    Van dos clases en la misma lista: los adjuntos de verdad —el plano, el PDF
    de la oferta— y las imágenes incrustadas de la firma, que se distinguen
    porque llevan ``content_id``. El proveedor las trata distinto: la firma no
    se enseña como archivo, se pinta dentro del mensaje.
    """
    from app.email.base_provider import EmailAttachment
    import os

    fuera = []
    for ruta in (contenido.get("adjuntos") or []):
        try:
            with open(ruta, "rb") as fichero:
                fuera.append(EmailAttachment(filename=os.path.basename(ruta),
                                             content=fichero.read()))
        except OSError as error:
            log.warning("No se pudo adjuntar %s: %s", ruta, error)

    for imagen in (contenido.get("imagenes") or []):
        ruta = imagen.get("ruta")
        if not ruta:
            continue
        try:
            with open(ruta, "rb") as fichero:
                fuera.append(EmailAttachment(filename=os.path.basename(ruta),
                                             content=fichero.read(),
                                             content_id=imagen.get("cid")))
        except OSError as error:
            # Sin logo el correo sale igual: la firma queda en texto.
            log.warning("No se pudo incrustar la imagen %s: %s", ruta, error)
    return fuera


def nombre_comprador(datos) -> str:
    """Nombre de cortesía para el saludo, derivado del correo del remitente."""
    remitente = (datos or {}).get("remitente") or ""
    local = remitente.split("@")[0]
    nombre = local.replace(".", " ").replace("_", " ").strip()
    return nombre.title() or "Customer"
