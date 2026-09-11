"""Construcción del contenido de correos salientes del flujo de RFQ.

Propósito
---------
Este módulo **construye** el contenido de los correos que el sistema envía
durante el ciclo de cotización: declinaciones, peticiones de datos
faltantes, validaciones internas con el Project Manager y ofertas
formales al cliente. Devuelve la representación completa del correo como
un ``dict`` con destinatario, asunto, cuerpo HTML, cuerpo en texto plano y
lista de adjuntos.

Alcance
-------
* **Sí hace:** rellenar las plantillas de los cuatro tipos de correo con
  los parámetros recibidos y devolver el ``dict`` listo para que un
  remitente lo entregue.
* **NO hace:** enviar correos. El envío real es responsabilidad de
  ``smtp_sender.py`` (**COT-57**) y ``graph_sender.py`` (**COT-58**). Este
  módulo no toca SMTP, ni Microsoft Graph, ni el sistema de archivos.

Función pública
---------------
``construir_correo(tipo: str, params: dict) -> dict``

Actúa como dispatcher: según ``tipo`` invoca a la función privada
correspondiente (``_construir_declinar_rfq``, ``_construir_datos_faltantes``,
``_construir_validacion_pm``, ``_construir_oferta_cliente``).

Tipos soportados
----------------
* ``"declinar_rfq"``     — declinar una solicitud no factible.
* ``"datos_faltantes"``  — pedir datos al comprador.
* ``"validacion_pm"``    — pedir validación interna al PM.
* ``"oferta_cliente"``   — enviar la propuesta comercial formal.
"""

from __future__ import annotations

from html import escape

# --------------------------------------------------------------------------- #
# Firma común
# --------------------------------------------------------------------------- #

_FIRMA_TEXTO = "Best regards,\nCGR International"
_FIRMA_HTML = "<p>Best regards,<br>CGR International</p>"


# --------------------------------------------------------------------------- #
# Helpers internos
# --------------------------------------------------------------------------- #

def _exigir_params(params: dict, requeridos: tuple[str, ...]) -> None:
    """Verifica que ``params`` traiga todos los campos requeridos.

    Un parámetro se considera faltante si no está en el dict o si su valor
    es ``None`` o cadena vacía. Lanza ``ValueError`` indicando cuáles
    faltan.
    """
    faltantes = [
        nombre for nombre in requeridos
        if params.get(nombre) is None or params.get(nombre) == ""
    ]
    if faltantes:
        raise ValueError(
            "Faltan parámetros requeridos: " + ", ".join(faltantes)
        )


def _parrafos_html(parrafos: list[str]) -> str:
    """Convierte una lista de párrafos en texto plano a HTML, escapando."""
    return "\n".join(f"<p>{escape(p)}</p>" for p in parrafos)


def _envoltorio_html(cuerpo_interno: str) -> str:
    """Envuelve el HTML del cuerpo en un documento mínimo."""
    return (
        "<html><body>\n"
        f"{cuerpo_interno}\n"
        f"{_FIRMA_HTML}\n"
        "</body></html>"
    )


# --------------------------------------------------------------------------- #
# TIPO 1: declinar_rfq
# --------------------------------------------------------------------------- #

def _construir_declinar_rfq(params: dict) -> dict:
    """Construye el correo de declinación de un RFQ no factible."""
    _exigir_params(
        params, ("destinatario", "asunto_original", "nombre_comprador")
    )

    nombre = params["nombre_comprador"]

    parrafos = [
        f"Dear {nombre},",
        "Our engineering team reviewed the drawing. Unfortunately, this RFQ "
        "is not feasible for us.",
        "Thank you for considering us and we would be glad to work with you "
        "on other projects.",
    ]

    cuerpo_texto = "\n\n".join(parrafos) + "\n\n" + _FIRMA_TEXTO
    cuerpo_html = _envoltorio_html(_parrafos_html(parrafos))

    return {
        "destinatario": params["destinatario"],
        "asunto": params["asunto_original"],
        "cuerpo_html": cuerpo_html,
        "cuerpo_texto": cuerpo_texto,
        "adjuntos": [],
    }


# --------------------------------------------------------------------------- #
# TIPO 2: datos_faltantes
# --------------------------------------------------------------------------- #

def _construir_datos_faltantes(params: dict) -> dict:
    """Construye el correo solicitando los datos que faltan al comprador."""
    _exigir_params(
        params,
        ("destinatario", "asunto_original", "nombre_comprador", "campos_faltantes"),
    )

    campos = params["campos_faltantes"]
    if not isinstance(campos, list) or len(campos) == 0:
        raise ValueError(
            "campos_faltantes debe ser una lista no vacía de nombres de campos"
        )

    nombre = params["nombre_comprador"]

    intro = [
        f"Dear {nombre},",
        "Thank you very much for considering us for this project. We "
        "appreciate the opportunity to participate and collaborate with you.",
        "In order to proceed with an accurate commercial proposal and meet "
        "your timeline, could you please provide us with the following "
        "missing information?",
    ]
    cierre = [
        "As soon as we receive these details, our team will immediately "
        "trigger the quoting process.",
        "Thank you again for your trust. We look forward to hearing from you.",
    ]

    # --- Texto plano ---
    lista_texto = "\n".join(f"• {c}" for c in campos)
    cuerpo_texto = (
        "\n\n".join(intro)
        + "\n\n" + lista_texto + "\n\n"
        + "\n\n".join(cierre)
        + "\n\n" + _FIRMA_TEXTO
    )

    # --- HTML ---
    lista_html = "<ul>\n" + "\n".join(
        f"  <li>{escape(c)}</li>" for c in campos
    ) + "\n</ul>"
    cuerpo_html = _envoltorio_html(
        _parrafos_html(intro) + "\n" + lista_html + "\n" + _parrafos_html(cierre)
    )

    return {
        "destinatario": params["destinatario"],
        "asunto": params["asunto_original"],
        "cuerpo_html": cuerpo_html,
        "cuerpo_texto": cuerpo_texto,
        "adjuntos": [],
    }


# --------------------------------------------------------------------------- #
# TIPO 3: validacion_pm
# --------------------------------------------------------------------------- #

def _construir_validacion_pm(params: dict) -> dict:
    """Construye el correo interno de validación de oferta para el PM."""
    _exigir_params(
        params,
        ("destinatario", "nombre_pm", "nombre_proyecto", "volumen",
         "tooling_capex", "margen"),
    )

    nombre_pm = params["nombre_pm"]
    nombre_proyecto = params["nombre_proyecto"]
    volumen = params["volumen"]
    tooling_capex = params["tooling_capex"]
    margen = params["margen"]

    asunto = f"Validation Required: Commercial Offer - {nombre_proyecto}"

    intro = [
        f"Hi {nombre_pm},",
        f"The commercial offer for {nombre_proyecto} is ready for your "
        "review and approval before submission to the customer.",
        "Key Figures:",
    ]
    cierre = [
        "Attached to this email you will find the complete breakdown for "
        "your review. I look forward to your comments or approval to proceed "
        "with the submission.",
        "Thank you for your support.",
    ]
    figuras = [
        f"Volume: {volumen} units/year",
        f"Tooling/CapEx: {tooling_capex} USD",
        f"Margin: {margen}%",
    ]

    # --- Texto plano ---
    lista_texto = "\n".join(f"• {f}" for f in figuras)
    cuerpo_texto = (
        "\n\n".join(intro)
        + "\n" + lista_texto + "\n\n"
        + "\n\n".join(cierre)
        + "\n\n" + _FIRMA_TEXTO
    )

    # --- HTML ---
    lista_html = "<ul>\n" + "\n".join(
        f"  <li>{escape(f)}</li>" for f in figuras
    ) + "\n</ul>"
    cuerpo_html = _envoltorio_html(
        _parrafos_html(intro) + "\n" + lista_html + "\n" + _parrafos_html(cierre)
    )

    return {
        "destinatario": params["destinatario"],
        "asunto": asunto,
        "cuerpo_html": cuerpo_html,
        "cuerpo_texto": cuerpo_texto,
        "adjuntos": [],
    }


# --------------------------------------------------------------------------- #
# TIPO 4: oferta_cliente
# --------------------------------------------------------------------------- #

def _construir_oferta_cliente(params: dict) -> dict:
    """Construye la propuesta comercial formal al cliente."""
    _exigir_params(
        params,
        ("destinatario", "asunto_original", "nombre_comprador",
         "nombre_proyecto", "lead_time", "incoterm", "validez_oferta"),
    )

    nombre = params["nombre_comprador"]
    nombre_proyecto = params["nombre_proyecto"]
    lead_time = params["lead_time"]
    incoterm = params["incoterm"]
    validez = params["validez_oferta"]

    # adjuntos es opcional (lista, puede ser vacía); si viene None lo
    # tratamos como [].
    adjuntos = params.get("adjuntos") or []
    if not isinstance(adjuntos, list):
        raise ValueError("adjuntos debe ser una lista de rutas de archivos")

    intro = [
        f"Dear {nombre},",
        f"Following up on your request, we are pleased to submit our "
        f"official commercial proposal for the {nombre_proyecto} project.",
        "Attached to this email, you will find our detailed quotation, "
        "which has been structured to meet all the technical and quality "
        "requirements specified by your team.",
        "Key highlights of our proposal:",
    ]
    cierre = [
        "We are very excited about the prospect of partnering with you on "
        "this business. Please let us know if you would like to schedule a "
        "review meeting to go over the details.",
        "Thank you for the opportunity. We look forward to your feedback.",
    ]
    highlights = [
        f"Lead Time: {lead_time}",
        f"Incoterm: {incoterm}",
        f"Offer Validity: {validez}",
    ]

    # --- Texto plano ---
    lista_texto = "\n".join(f"• {h}" for h in highlights)
    cuerpo_texto = (
        "\n\n".join(intro)
        + "\n" + lista_texto + "\n\n"
        + "\n\n".join(cierre)
        + "\n\n" + _FIRMA_TEXTO
    )

    # --- HTML ---
    lista_html = "<ul>\n" + "\n".join(
        f"  <li>{escape(h)}</li>" for h in highlights
    ) + "\n</ul>"
    cuerpo_html = _envoltorio_html(
        _parrafos_html(intro) + "\n" + lista_html + "\n" + _parrafos_html(cierre)
    )

    return {
        "destinatario": params["destinatario"],
        "asunto": params["asunto_original"],
        "cuerpo_html": cuerpo_html,
        "cuerpo_texto": cuerpo_texto,
        "adjuntos": list(adjuntos),
    }


# --------------------------------------------------------------------------- #
# Dispatcher público
# --------------------------------------------------------------------------- #

_CONSTRUCTORES = {
    "declinar_rfq": _construir_declinar_rfq,
    "datos_faltantes": _construir_datos_faltantes,
    "validacion_pm": _construir_validacion_pm,
    "oferta_cliente": _construir_oferta_cliente,
}


def construir_correo(tipo: str, params: dict) -> dict:
    """Construye el contenido de un correo saliente.

    Args:
        tipo: identificador del tipo de correo. Uno de:
            ``"declinar_rfq"``, ``"datos_faltantes"``,
            ``"validacion_pm"``, ``"oferta_cliente"``.
        params: parámetros específicos del tipo (ver docstring de cada
            constructor interno para el detalle de campos requeridos).

    Returns:
        ``dict`` con las claves ``destinatario``, ``asunto``,
        ``cuerpo_html``, ``cuerpo_texto`` y ``adjuntos``.

    Raises:
        ValueError: si ``tipo`` no es uno de los soportados, o si faltan
            parámetros requeridos.
    """
    constructor = _CONSTRUCTORES.get(tipo)
    if constructor is None:
        soportados = ", ".join(sorted(_CONSTRUCTORES))
        raise ValueError(
            f"Tipo de correo desconocido: {tipo!r}. Tipos soportados: {soportados}"
        )
    return constructor(params)
