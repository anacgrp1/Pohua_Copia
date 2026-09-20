"""COT-58 [Código - <Token>] Envío de correos salientes por Microsoft Graph.

Propósito
---------
Despacha los correos salientes del flujo de RFQ mediante una petición
**HTTP POST al endpoint ``sendMail`` de Microsoft Graph**, para el modo
``<Token>`` (producción, autenticación OAuth2 / Azure AD). Es el gemelo de
``smtp_sender.py`` (COT-57), pero sobre Graph en lugar de SMTP.

Consume el **mismo dict** que produce ``templates.construir_correo``
(COT-59): ``{destinatario, asunto, cuerpo_html, cuerpo_texto, adjuntos}``.
El cuerpo se envía como HTML (con el texto plano como respaldo si no hay
HTML) y los adjuntos se leen del disco y se codifican en base64 dentro del
JSON como ``fileAttachment``.

Alcance
-------
* **Sí hace:** obtener el token de Azure AD (client credentials), construir
  el payload JSON de ``sendMail`` y despacharlo.
* **NO hace:** construir el contenido (COT-59), ni decidir a quién/cuándo se
  envía (flujo COT-36). El envío por SMTP para ``<Local>`` es de
  ``smtp_sender.py`` (COT-57).

Función pública
---------------
``enviar_correo_graph(correo: dict, ...) -> bool``
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
from typing import List, Optional

import requests

import app.core.config as config

log = logging.getLogger("cotizador.graph_sender")

_URL_TOKEN = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_URL_SENDMAIL = "https://graph.microsoft.com/v1.0/users/{usuario}/sendMail"


class GraphSenderError(Exception):
    """Error al construir o despachar un correo por Microsoft Graph."""


# --------------------------------------------------------------------------- #
# Validación de entrada
# --------------------------------------------------------------------------- #

def _validar_correo(correo: dict) -> None:
    """Verifica que el dict traiga lo mínimo para poder enviarse."""
    if not isinstance(correo, dict):
        raise GraphSenderError("El correo debe ser un dict de construir_correo().")
    if not correo.get("destinatario"):
        raise GraphSenderError("El correo no tiene 'destinatario'.")
    if not correo.get("cuerpo_texto") and not correo.get("cuerpo_html"):
        raise GraphSenderError(
            "El correo no tiene cuerpo ('cuerpo_texto' ni 'cuerpo_html')."
        )


# --------------------------------------------------------------------------- #
# Construcción del payload JSON de sendMail
# --------------------------------------------------------------------------- #

def _adjunto_a_fileattachment(ruta: str) -> dict:
    """Lee un archivo del disco y lo convierte en un fileAttachment de Graph.

    Lanza GraphSenderError si la ruta no existe: no despachamos una oferta o
    solicitud sin el plano/cotización que la acompaña.
    """
    if not os.path.isfile(ruta):
        raise GraphSenderError(f"Adjunto no encontrado en disco: {ruta!r}")

    tipo, _ = mimetypes.guess_type(ruta)
    with open(ruta, "rb") as fh:
        contenido = fh.read()

    return {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": os.path.basename(ruta),
        "contentType": tipo or "application/octet-stream",
        "contentBytes": base64.b64encode(contenido).decode("ascii"),
    }


def _imagen_incrustada(imagen: dict) -> dict:
    """El logo de la firma, como adjunto en línea de Graph.

    Es un fileAttachment más, con dos marcas: ``isInline`` y el ``contentId``
    que el HTML busca en ``<img src="cid:...">``. Sin ellas el logo llegaría
    como un archivo suelto y la firma saldría con un hueco.
    """
    adjunto = _adjunto_a_fileattachment(imagen["ruta"])
    adjunto["isInline"] = True
    adjunto["contentId"] = imagen.get("cid") or os.path.basename(imagen["ruta"])
    return adjunto


def construir_payload(correo: dict, guardar_enviados: bool = True) -> dict:
    """Arma el cuerpo JSON de la petición ``sendMail`` a partir del dict COT-59.

    Prefiere el cuerpo HTML; si no hay, usa el texto plano. Los adjuntos se
    leen del disco y se incrustan en base64.
    """
    _validar_correo(correo)

    html = correo.get("cuerpo_html")
    if html:
        cuerpo = {"contentType": "HTML", "content": html}
    else:
        cuerpo = {"contentType": "Text", "content": correo.get("cuerpo_texto", "")}

    adjuntos: List[str] = correo.get("adjuntos") or []
    attachments = [_adjunto_a_fileattachment(ruta) for ruta in adjuntos]
    for imagen in (correo.get("imagenes") or []):
        try:
            attachments.append(_imagen_incrustada(imagen))
        except GraphSenderError as error:
            # Sin logo el correo sale igual; sin el plano, no.
            log.warning("No se pudo incrustar la imagen de la firma: %s", error)

    return {
        "message": {
            "subject": correo.get("asunto", ""),
            "body": cuerpo,
            "toRecipients": [
                {"emailAddress": {"address": correo["destinatario"]}}
            ],
            "attachments": attachments,
        },
        "saveToSentItems": guardar_enviados,
    }


# --------------------------------------------------------------------------- #
# Token de Azure AD
# --------------------------------------------------------------------------- #

def _obtener_token(cliente_http=None) -> str:
    """Obtiene un token de aplicación (client credentials) de Azure AD."""
    tenant = getattr(config, "AZURE_TENANT_ID", None) or getattr(config, "GRAPH_TENANT_ID", None)
    client_id = getattr(config, "AZURE_CLIENT_ID", None) or getattr(config, "GRAPH_CLIENT_ID", None)
    client_secret = (
        getattr(config, "AZURE_CLIENT_SECRET", None)
        or getattr(config, "GRAPH_CLIENT_SECRET", None)
    )

    if not tenant or not client_id or not client_secret:
        raise GraphSenderError(
            "Credenciales de Azure incompletas (AZURE_TENANT_ID / CLIENT_ID / CLIENT_SECRET)."
        )

    http = cliente_http or requests
    respuesta = http.post(
        _URL_TOKEN.format(tenant=tenant),
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    respuesta.raise_for_status()
    return respuesta.json()["access_token"]


def _usuario_emisor() -> Optional[str]:
    return getattr(config, "GRAPH_USER", None) or getattr(config, "IMAP_USER", None)


# --------------------------------------------------------------------------- #
# Envío
# --------------------------------------------------------------------------- #

def enviar_correo_graph(
    correo: dict,
    *,
    token: Optional[str] = None,
    usuario: Optional[str] = None,
    cliente_http=None,
) -> bool:
    """Despacha ``correo`` (dict de COT-59) por Microsoft Graph. True si sale.

    Args:
        correo: dict de ``construir_correo``.
        token: token Bearer ya obtenido. Si es None, se solicita a Azure AD.
        usuario: buzón emisor (UPN). Si es None, se toma de ``GRAPH_USER`` o
            ``IMAP_USER``.
        cliente_http: objeto con ``.post`` (inyección para pruebas). Por
            defecto usa ``requests``.

    Raises:
        GraphSenderError: si faltan datos del correo, configuración, o falla
            la petición.
    """
    payload = construir_payload(correo)

    usuario = usuario or _usuario_emisor()
    if not usuario:
        raise GraphSenderError(
            "No hay buzón emisor configurado (GRAPH_USER / IMAP_USER)."
        )

    http = cliente_http or requests
    if token is None:
        token = _obtener_token(cliente_http=http)

    destinatario = correo["destinatario"]
    url = _URL_SENDMAIL.format(usuario=usuario)

    log.info("Enviando correo por Graph a %s (buzón %s)...", destinatario, usuario)
    try:
        respuesta = http.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        respuesta.raise_for_status()
    except requests.RequestException as error:
        raise GraphSenderError(
            f"Fallo en la petición a Graph al enviar a {destinatario}: {error}"
        ) from error

    log.info("Correo enviado exitosamente vía Graph a %s.", destinatario)
    return True
