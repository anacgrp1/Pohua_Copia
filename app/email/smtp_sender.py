"""COT-57 [Código - <Local>] Envío de correos salientes por SMTP clásico.

Propósito
---------
Despacha por **SMTP estándar (puerto 587 + STARTTLS)** los correos salientes
del flujo de RFQ construidos por ``templates.construir_correo`` (COT-59).
Usa exclusivamente librerías nativas: ``smtplib`` y ``email.mime``.

A diferencia del ``send_email`` primitivo de los proveedores (que sólo manda
texto plano y recibe adjuntos como bytes en memoria), este módulo:

* arma un cuerpo **multipart/alternative** con la versión HTML y la de texto
  plano (fallback), para que el cliente de correo renderice el HTML;
* lee los **adjuntos desde el disco** a partir de sus rutas (los planos y la
  cotización que entrega COT-59 en ``correo["adjuntos"]``);
* se integra con la configuración central (``config.settings``).

Alcance
-------
* **Sí hace:** construir el mensaje MIME y despacharlo por SMTP.
* **NO hace:** construir el contenido (eso es COT-59), ni decidir a quién se
  envía o cuándo (eso lo decide el flujo, COT-36). El envío por Microsoft
  Graph para el modo ``<Token>`` es responsabilidad de ``graph_sender.py``
  (COT-58).

Función pública
---------------
``enviar_correo_smtp(correo: dict, ...) -> bool``

``correo`` es el dict de ``construir_correo``:
``{destinatario, asunto, cuerpo_html, cuerpo_texto, adjuntos}``.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

import app.core.config as config

log = logging.getLogger("cotizador.smtp_sender")


class SmtpSenderError(Exception):
    """Error al construir o despachar un correo por SMTP."""


# --------------------------------------------------------------------------- #
# Validación de entrada
# --------------------------------------------------------------------------- #

def _validar_correo(correo: dict) -> None:
    """Verifica que el dict traiga lo mínimo para poder enviarse."""
    if not isinstance(correo, dict):
        raise SmtpSenderError("El correo debe ser un dict de construir_correo().")

    if not correo.get("destinatario"):
        raise SmtpSenderError("El correo no tiene 'destinatario'.")

    if not correo.get("cuerpo_texto") and not correo.get("cuerpo_html"):
        raise SmtpSenderError(
            "El correo no tiene cuerpo ('cuerpo_texto' ni 'cuerpo_html')."
        )


# --------------------------------------------------------------------------- #
# Construcción del mensaje MIME
# --------------------------------------------------------------------------- #

def _adjuntar_archivo(mensaje: MIMEMultipart, ruta: str) -> None:
    """Lee un archivo del disco y lo adjunta al mensaje.

    Lanza SmtpSenderError si la ruta no existe: no queremos despachar una
    oferta o una solicitud sin el plano/cotización que la acompaña.
    """
    if not os.path.isfile(ruta):
        raise SmtpSenderError(f"Adjunto no encontrado en disco: {ruta!r}")

    tipo, _ = mimetypes.guess_type(ruta)
    maintype, subtype = (tipo.split("/", 1) if tipo else ("application", "octet-stream"))

    with open(ruta, "rb") as fh:
        datos = fh.read()

    parte = MIMEApplication(datos, _subtype=subtype)
    # Reajusta el Content-Type si el maintype no es 'application'
    if maintype != "application":
        parte.replace_header("Content-Type", f"{maintype}/{subtype}")
    parte.add_header(
        "Content-Disposition", "attachment", filename=os.path.basename(ruta)
    )
    mensaje.attach(parte)


def _cuerpo_alternativo(correo: dict) -> MIMEMultipart:
    """Construye el bloque multipart/alternative (texto + HTML)."""
    alternativa = MIMEMultipart("alternative")
    texto = correo.get("cuerpo_texto")
    html = correo.get("cuerpo_html")

    # Orden recomendado: primero texto plano, luego HTML (el cliente muestra
    # la última parte que sepa renderizar).
    if texto:
        alternativa.attach(MIMEText(texto, "plain", "utf-8"))
    if html:
        alternativa.attach(MIMEText(html, "html", "utf-8"))
    return alternativa


def construir_mensaje(correo: dict, remitente: str) -> MIMEMultipart:
    """Arma el objeto MIME completo a partir del dict de COT-59.

    Estructura resultante:
      - sin adjuntos: multipart/alternative (texto + HTML)
      - con adjuntos: multipart/mixed [ alternative(texto+HTML), adjunto... ]
    """
    _validar_correo(correo)

    adjuntos: List[str] = correo.get("adjuntos") or []
    alternativa = _cuerpo_alternativo(correo)

    if adjuntos:
        raiz = MIMEMultipart("mixed")
        raiz.attach(alternativa)
        for ruta in adjuntos:
            _adjuntar_archivo(raiz, ruta)
    else:
        raiz = alternativa

    raiz["Subject"] = correo.get("asunto", "")
    raiz["From"] = remitente
    raiz["To"] = correo["destinatario"]
    return raiz


# --------------------------------------------------------------------------- #
# Resolución de credenciales / servidor
# --------------------------------------------------------------------------- #

def _remitente_por_defecto() -> Optional[str]:
    """Cuenta emisora: SMTP_USER si existe, si no IMAP_USER (misma cuenta)."""
    return getattr(config, "SMTP_USER", None) or getattr(config, "IMAP_USER", None)


def _password_por_defecto() -> Optional[str]:
    return getattr(config, "SMTP_PASSWORD", None) or getattr(config, "IMAP_PASSWORD", None)


# --------------------------------------------------------------------------- #
# Envío
# --------------------------------------------------------------------------- #

def enviar_correo_smtp(
    correo: dict,
    *,
    remitente: Optional[str] = None,
    password: Optional[str] = None,
    cliente_smtp=None,
) -> bool:
    """Despacha ``correo`` (dict de COT-59) por SMTP y devuelve True si sale.

    Args:
        correo: dict de ``construir_correo``.
        remitente: cuenta emisora. Si es None, se toma de la configuración
            (``SMTP_USER`` o ``IMAP_USER``).
        password: contraseña de la cuenta emisora. Si es None, se toma de la
            configuración (``SMTP_PASSWORD`` o ``IMAP_PASSWORD``).
        cliente_smtp: cliente SMTP ya conectado (inyección para pruebas). Si
            se provee, se usa tal cual (sin STARTTLS/login) y no se cierra.

    Raises:
        SmtpSenderError: si faltan datos del correo, credenciales, o falla el
            despacho.
    """
    remitente = remitente or _remitente_por_defecto()
    if not remitente:
        raise SmtpSenderError(
            "No hay cuenta emisora configurada (SMTP_USER / IMAP_USER)."
        )

    mensaje = construir_mensaje(correo, remitente)
    destinatario = correo["destinatario"]

    # --- Cliente inyectado (pruebas / reuso): sólo despachar ---
    if cliente_smtp is not None:
        cliente_smtp.sendmail(remitente, [destinatario], mensaje.as_string())
        log.info("Correo despachado por cliente SMTP inyectado a %s.", destinatario)
        return True

    # --- Envío real ---
    password = password or _password_por_defecto()
    if not password:
        raise SmtpSenderError(
            "No hay contraseña configurada (SMTP_PASSWORD / IMAP_PASSWORD)."
        )

    servidor = getattr(config, "SMTP_SERVER", None) or "smtp.office365.com"
    puerto = getattr(config, "SMTP_PORT", None) or 587
    usar_tls = getattr(config, "SMTP_USE_TLS", True)

    log.info("Enviando correo a %s vía %s:%s...", destinatario, servidor, puerto)
    try:
        with smtplib.SMTP(servidor, puerto, timeout=30) as cliente:
            if usar_tls:
                cliente.starttls()
            cliente.login(remitente, password)
            cliente.sendmail(remitente, [destinatario], mensaje.as_string())
        log.info("Correo enviado exitosamente a %s.", destinatario)
        return True
    except smtplib.SMTPException as error:
        raise SmtpSenderError(f"Fallo SMTP al enviar a {destinatario}: {error}") from error
    except OSError as error:  # red / socket / timeout
        raise SmtpSenderError(f"Fallo de red al enviar a {destinatario}: {error}") from error
