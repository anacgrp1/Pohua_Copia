"""El texto de los correos que salen del flujo de RFQ.

De dónde sale este texto
------------------------
De `docs/Cotizador - texto email & notificaciones.pdf`, el machote que
escribió la empresa. No es una redacción de aquí: cuando el machote cambie,
cambia este módulo y nada más, porque el resto del sistema sólo pide "el
correo de tal tipo" y lo despacha.

Los cinco textos del machote:

    Al CLIENTE
      datos_faltantes        pedirle lo que falta antes de poder cotizar
      declinar_rfq           decirle que no podemos cotizar esta pieza
      oferta_cliente         mandarle la cotización formal (PDF adjunto)

    INTERNOS (al plant manager)
      revision_factibilidad  hace falta dictaminar la factibilidad
      validacion_pm          la cotización está lista y espera visto bueno

Los dos internos son el AVISO DE RESPALDO, no el principal: quien revisa se
entera por la campana de Pohua y por el teléfono, y el correo sólo sale
cuando un caso lleva demasiado tiempo esperando (``app/rfq/recordatorios.py``).
Por eso llevan el enlace al caso: se abre desde el correo y se acabó.

Alcance
-------
* **Sí hace:** rellenar las plantillas y devolver el ``dict`` del correo.
* **NO hace:** enviar nada. Eso es ``app/email/outbound.py``, que además
  decide si el envío está habilitado.

Función pública
---------------
``construir_correo(tipo: str, params: dict) -> dict``
"""

from __future__ import annotations

from html import escape

# --------------------------------------------------------------------------- #
# Firmas
# --------------------------------------------------------------------------- #

# La firma del machote, tal cual: nombre legal de la planta, su dirección y
# los dos sitios. Va en los correos al CLIENTE.
_FIRMA_CLIENTE = (
    "INDUSTRIAL SPRING CORPORATION",
    "1801 Bedford Ave",
    "North Kansas City, MO 64116",
    "www.cgr-international.com",
    "www.isckc.com",
)

_DESPEDIDA = "Best regards,"

_FIRMA_CLIENTE_TEXTO = _DESPEDIDA + "\n\n" + "\n".join(_FIRMA_CLIENTE)
_FIRMA_CLIENTE_HTML = (
    f"<p>{_DESPEDIDA}</p>\n<p>"
    + "<br>".join(escape(linea) for linea in _FIRMA_CLIENTE)
    + "</p>"
)


# --------------------------------------------------------------------------- #
# Lo que se le puede pedir al comprador
# --------------------------------------------------------------------------- #

# El machote enumera cinco cosas y las describe. Aquí está la traducción de
# los nombres internos de los campos —los que usa `field_validator`— a esas
# frases: lo que el comprador lee tiene que decirle QUÉ mandar, no el nombre
# de una columna ("volumen" no significa nada fuera de aquí).
_QUE_FALTA = {
    "tiene_adjunto":  "Technical Drawing: Drawing or schematic file (PDF, PNG, or CAD)",
    "drawing":        "Technical Drawing: Drawing or schematic file (PDF, PNG, or CAD)",
    "plano":          "Technical Drawing: Drawing or schematic file (PDF, PNG, or CAD)",
    "part_number":    "Part Number: Part identifier or drawing reference number",
    "num_parte":      "Part Number: Part identifier or drawing reference number",
    "volumen":        "Volume / EAU: Target batch quantity or Estimated Annual Usage",
    "volume":         "Volume / EAU: Target batch quantity or Estimated Annual Usage",
    "cantidad":       "Volume / EAU: Target batch quantity or Estimated Annual Usage",
    "material":       "Material Specification: Required material grade, alloy, or finish",
    "key_dimensions": "Key Dimensions & Tolerances: Critical dimensional requirements "
                      "or tolerance ranges",
    "dimensiones":    "Key Dimensions & Tolerances: Critical dimensional requirements "
                      "or tolerance ranges",
    "tolerancias":    "Key Dimensions & Tolerances: Critical dimensional requirements "
                      "or tolerance ranges",
    "customer":       "Company Name: The company this quotation should be issued to",
}


def _pedido(campo: str) -> str:
    """La frase del machote para un campo, o el campo tal cual si es otro.

    Lo desconocido no se descarta ni se inventa: se enseña con el nombre que
    venga, en mayúscula inicial. Un campo nuevo del validador aparecerá feo
    antes que desaparecer sin que nadie se entere.
    """
    clave = str(campo or "").strip()
    frase = _QUE_FALTA.get(clave.lower())
    if frase:
        return frase
    return clave.replace("_", " ").strip().capitalize() or clave


def _sin_repetir(campos) -> list:
    """Las frases de los campos que faltan, sin duplicados y en orden.

    Varios campos internos caen en la misma frase del machote —tolerancias y
    dimensiones son una sola línea— y repetirla haría dudar de si son dos
    cosas distintas.
    """
    vistas, fuera = set(), []
    for campo in campos:
        frase = _pedido(campo)
        if frase in vistas:
            continue
        vistas.add(frase)
        fuera.append(frase)
    return fuera


# --------------------------------------------------------------------------- #
# Helpers internos
# --------------------------------------------------------------------------- #

def _exigir_params(params: dict, requeridos: tuple) -> None:
    """Verifica que ``params`` traiga todos los campos requeridos."""
    faltantes = [
        nombre for nombre in requeridos
        if params.get(nombre) is None or params.get(nombre) == ""
    ]
    if faltantes:
        raise ValueError("Faltan parámetros requeridos: " + ", ".join(faltantes))


def _parrafos_html(parrafos: list) -> str:
    return "\n".join(f"<p>{escape(p)}</p>" for p in parrafos)


def _lista_html(puntos: list) -> str:
    return ("<ul>\n"
            + "\n".join(f"  <li>{escape(p)}</li>" for p in puntos)
            + "\n</ul>")


def _lista_texto(puntos: list) -> str:
    return "\n".join(f"  • {p}" for p in puntos)


def _documento(cuerpo_interno: str, firma_html: str = "") -> str:
    """Envuelve el HTML del cuerpo en un documento mínimo."""
    partes = ["<html><body>", cuerpo_interno]
    if firma_html:
        partes.append(firma_html)
    partes.append("</body></html>")
    return "\n".join(partes)


def _correo_cliente(destinatario, asunto, intro, puntos, cierre, adjuntos=None) -> dict:
    """Arma un correo al cliente: párrafos, lista opcional y la firma de ISC."""
    texto = "\n\n".join(intro)
    if puntos:
        texto += "\n\n" + _lista_texto(puntos)
    if cierre:
        texto += "\n\n" + "\n\n".join(cierre)
    texto += "\n\n" + _FIRMA_CLIENTE_TEXTO

    html = _parrafos_html(intro)
    if puntos:
        html += "\n" + _lista_html(puntos)
    if cierre:
        html += "\n" + _parrafos_html(cierre)

    return {
        "destinatario": destinatario,
        "asunto": asunto,
        "cuerpo_html": _documento(html, _FIRMA_CLIENTE_HTML),
        "cuerpo_texto": texto,
        "adjuntos": list(adjuntos or []),
    }


def _enlace_html(enlace: str) -> str:
    """El enlace del correo interno, pinchable y visible a la vez.

    Se enseña la dirección completa además de enlazarla: un correo interno se
    reenvía, se abre en clientes que no pintan HTML, y una palabra "aquí" que
    no se puede copiar no sirve de nada.
    """
    seguro = escape(enlace, quote=True)
    return f'<p><a href="{seguro}">{escape(enlace)}</a></p>'


# --------------------------------------------------------------------------- #
# AL CLIENTE 1: datos_faltantes
# --------------------------------------------------------------------------- #

def _construir_datos_faltantes(params: dict) -> dict:
    """Pide lo que falta para poder cotizar. Machote: REQUEST DATA EMAIL."""
    _exigir_params(
        params,
        ("destinatario", "asunto_original", "nombre_comprador", "campos_faltantes"),
    )

    campos = params["campos_faltantes"]
    if not isinstance(campos, list) or len(campos) == 0:
        raise ValueError(
            "campos_faltantes debe ser una lista no vacía de nombres de campos")

    intro = [
        f"Dear {params['nombre_comprador']},",
        "Thank you for considering us for this project.",
        "We have received your request and started reviewing the specifications.",
        "To prepare an accurate quotation for you, we need the following "
        "missing details:",
    ]
    cierre = [
        "Please provide this information by replying to this email. As soon as "
        "we receive it, we will proceed with your quote.",
    ]

    return _correo_cliente(
        params["destinatario"], params["asunto_original"],
        intro, _sin_repetir(campos), cierre)


# --------------------------------------------------------------------------- #
# AL CLIENTE 2: declinar_rfq
# --------------------------------------------------------------------------- #

def _construir_declinar_rfq(params: dict) -> dict:
    """Declina la solicitud. Machote: NOT FEASIBLE - DECLINE EMAIL."""
    _exigir_params(params, ("destinatario", "asunto_original", "nombre_comprador"))

    intro = [
        f"Dear {params['nombre_comprador']},",
        "Thank you for reaching out and sharing your request with us.",
        "After reviewing your technical specifications, we regret to inform you "
        "that we are unable to quote this project, as the required parameters "
        "fall outside our current manufacturing capabilities.",
        "Thank you for considering us, and please let us know if we can assist "
        "with future projects.",
    ]

    return _correo_cliente(
        params["destinatario"], params["asunto_original"], intro, [], [])


# --------------------------------------------------------------------------- #
# AL CLIENTE 3: oferta_cliente
# --------------------------------------------------------------------------- #

def _construir_oferta_cliente(params: dict) -> dict:
    """Manda la cotización formal. Machote: SEND OFFER, con el PDF adjunto.

    El machote deja el cuerpo corto y remite al PDF. Se conservan las tres
    condiciones comerciales —plazo, incoterm y validez— porque son lo que se
    contesta sin abrir el adjunto, y porque una oferta sin validez a la vista
    se responde tarde.
    """
    _exigir_params(
        params,
        ("destinatario", "asunto_original", "nombre_comprador",
         "lead_time", "incoterm", "validez_oferta"),
    )

    adjuntos = params.get("adjuntos") or []
    if not isinstance(adjuntos, list):
        raise ValueError("adjuntos debe ser una lista de rutas de archivos")

    intro = [
        f"Dear {params['nombre_comprador']},",
        "Following the review of your technical specifications, please find "
        "attached our formal quotation for your review.",
    ]
    condiciones = [
        f"Lead Time: {params['lead_time']}",
        f"Incoterm: {params['incoterm']}",
        f"Offer Validity: {params['validez_oferta']}",
    ]
    cierre = [
        "Do not hesitate to reach out if you have any questions or require any "
        "adjustments. We look forward to working with you.",
    ]

    return _correo_cliente(
        params["destinatario"], params["asunto_original"],
        intro, condiciones, cierre, adjuntos)


# --------------------------------------------------------------------------- #
# INTERNO 1: revision_factibilidad
# --------------------------------------------------------------------------- #

def _construir_revision_factibilidad(params: dict) -> dict:
    """Pide dictamen de factibilidad. Machote: NOT FEASIBLE REVIEW (RODEA).

    La última línea —que al cliente todavía no se le ha escrito— no es un
    adorno: es lo que evita que alguien conteste por su cuenta creyendo que el
    sistema ya dijo algo.
    """
    _exigir_params(params, ("destinatario", "nombre_pm", "cliente", "enlace"))

    cliente = params["cliente"]
    parrafos = [
        f"Hi {params['nombre_pm']},",
        f"A feasibility review is required for a new quote request from "
        f"{cliente} before any reply can be sent to the client.",
        "Please access the case details, drawing, and technical flags using the "
        "link below to decide whether to proceed or decline:",
    ]
    nota = "(Note: No email has been sent to the client yet)."
    enlace = params["enlace"]

    texto = "\n\n".join(parrafos) + "\n\n" + enlace + "\n\n" + nota
    html = _documento(_parrafos_html(parrafos) + "\n" + _enlace_html(enlace)
                      + "\n" + _parrafos_html([nota]))

    return {
        "destinatario": params["destinatario"],
        "asunto": f"Feasibility review required – {cliente}",
        "cuerpo_html": html,
        "cuerpo_texto": texto,
        "adjuntos": [],
    }


# --------------------------------------------------------------------------- #
# INTERNO 2: validacion_pm
# --------------------------------------------------------------------------- #

def _construir_validacion_pm(params: dict) -> dict:
    """Pide el visto bueno de la cotización. Machote: VALIDATION EMAIL (RODEA)."""
    _exigir_params(params, ("destinatario", "nombre_pm", "cliente", "enlace"))

    cliente = params["cliente"]
    parrafos = [
        f"Hi {params['nombre_pm']},",
        f"A new quote for {cliente} is ready and requires your review and "
        "approval before the final offer is sent to the customer.",
        "Please access the full details, drawings, and cost breakdown using the "
        "link below:",
    ]
    cierre = "Thank you,"
    enlace = params["enlace"]

    texto = "\n\n".join(parrafos) + "\n\n" + enlace + "\n\n" + cierre
    html = _documento(_parrafos_html(parrafos) + "\n" + _enlace_html(enlace)
                      + "\n" + _parrafos_html([cierre]))

    return {
        "destinatario": params["destinatario"],
        "asunto": f"Quote validation required – {cliente}",
        "cuerpo_html": html,
        "cuerpo_texto": texto,
        "adjuntos": [],
    }


# --------------------------------------------------------------------------- #
# Los textos de la campana
# --------------------------------------------------------------------------- #

# El machote también dice qué tiene que decir el aviso DENTRO de la
# aplicación. Vive aquí, junto a los correos, porque es el mismo texto dicho
# por el otro canal y se cambia en el mismo sitio.
def aviso_revision_factibilidad(cliente: str) -> str:
    return f"Feasibility review required – {cliente or '—'}"


def aviso_validacion(cliente: str) -> str:
    return f"Quote validation required – {cliente or '—'}"


# --------------------------------------------------------------------------- #
# Dispatcher público
# --------------------------------------------------------------------------- #

_CONSTRUCTORES = {
    "datos_faltantes": _construir_datos_faltantes,
    "declinar_rfq": _construir_declinar_rfq,
    "oferta_cliente": _construir_oferta_cliente,
    "revision_factibilidad": _construir_revision_factibilidad,
    "validacion_pm": _construir_validacion_pm,
}


def construir_correo(tipo: str, params: dict) -> dict:
    """Construye el contenido de un correo saliente.

    Args:
        tipo: ``"datos_faltantes"``, ``"declinar_rfq"``, ``"oferta_cliente"``,
            ``"revision_factibilidad"`` o ``"validacion_pm"``.
        params: los parámetros de ese tipo (ver cada constructor).

    Returns:
        ``dict`` con ``destinatario``, ``asunto``, ``cuerpo_html``,
        ``cuerpo_texto`` y ``adjuntos``.

    Raises:
        ValueError: tipo desconocido o parámetros incompletos.
    """
    constructor = _CONSTRUCTORES.get(tipo)
    if constructor is None:
        soportados = ", ".join(sorted(_CONSTRUCTORES))
        raise ValueError(
            f"Tipo de correo desconocido: {tipo!r}. Tipos soportados: {soportados}")
    return constructor(params)
