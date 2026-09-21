"""COT-66 / COT-67 — Extracción de datos comerciales del cuerpo del correo.

Es la **etapa 1** del orden definido en COT-36: leer el cuerpo del correo con
un modelo de lenguaje antes de mirar el dibujo, para que la validación se
haga sobre la fusión de ambas fuentes.

Alcance
-------
* **Sí hace:** llamar al LLM con el cuerpo ya limpio (COT-53), interpretar el
  JSON que devuelve, normalizar los campos y asignar a cada uno su rango de
  confianza (COT-67).
* **NO hace:** leer dibujos (eso es ``vision_pipeline``), decidir si el RFQ
  está completo (``field_validator``), ni notificar al PM (COT-77).

Confianza y revisión
--------------------
El modelo devuelve un score 0-1 por campo. Los campos por debajo de
``config.UMBRAL_CONFIANZA`` **no se descartan ni se usan a ciegas**: se
apartan en ``en_revision`` y el flujo marca el RFQ para que una persona lo
valide. Es la decisión de negocio tomada para COT-61: ante duda, ni inventar
ni pedir de más — que lo vea el PM.

Funciones públicas
------------------
``analizar_cuerpo(texto, asunto=None, cliente=None) -> dict``  (COT-66)
``interpretar(respuesta_texto) -> dict``                        (COT-67)
``extraer(texto, asunto=None, cliente=None) -> dict``           (las dos)
"""
import logging

import app.core.config as config
from app.vision.spring_extractor import ExtraccionError, extraer_json

log = logging.getLogger("cotizador.extractor_correo")

# --------------------------------------------------------------------------- #
# Campos
# --------------------------------------------------------------------------- #

# Obligatorios para dar de alta el RFQ (los que mira field_validator).
CAMPOS_OBLIGATORIOS = ("customer", "part_number", "volumen", "material")

# Comerciales: no bloquean el alta, pero la cotización los va a necesitar.
# Extraerlos en la misma pasada evita una segunda llamada al modelo.
CAMPOS_COMERCIALES = (
    "fecha_entrega_requerida",
    "escalones_cantidad",
    "moneda",
    "incoterm",
    "contacto_nombre",
    "contacto_correo",
    "notas",
)

CAMPOS = CAMPOS_OBLIGATORIOS + CAMPOS_COMERCIALES

# Campos numéricos: se normalizan a número cuando se pueda.
_CAMPOS_NUMERICOS = ("volumen",)

# --------------------------------------------------------------------------- #
# PROMPT — extracción estructurada de datos comerciales (COT-66)
# --------------------------------------------------------------------------- #

PROMPT_COMERCIAL = """\
Eres un asistente de un fabricante de resortes que lee solicitudes de \
cotización (RFQ) enviadas por compradores. Los correos llegan en español o \
en inglés, a veces con la información dispersa entre el saludo, una tabla y \
la firma.

Tu tarea es extraer ÚNICAMENTE los datos comerciales que estén presentes en \
el texto y devolverlos como un objeto JSON.

Campos a extraer:

- customer: nombre de la empresa compradora (no el nombre de la persona).
- part_number: número de parte o código del resorte solicitado.
- volumen: cantidad anual estimada (EAU) o cantidad solicitada, como número.
- material: material o especificación del alambre (p. ej. "SAE 1070", \
"Inox 302", "music wire").
- fecha_entrega_requerida: fecha en formato YYYY-MM-DD si se menciona.
- escalones_cantidad: lista de cantidades si piden precio por volumen \
escalonado (p. ej. [1000, 5000, 10000]).
- moneda: código ISO si se menciona (MXN, USD, EUR).
- incoterm: EXW, FOB, DDP, etc.
- contacto_nombre: nombre de la persona que escribe.
- contacto_correo: su dirección de correo.
- notas: cualquier requisito relevante que no encaje arriba (certificados, \
tolerancias especiales, empaque).

REGLAS ESTRICTAS:

1. No inventes. Si un dato no está en el texto, omite la clave por completo. \
Es preferible un campo ausente a uno adivinado.
2. No deduzcas el material a partir del tipo de resorte, ni el volumen a \
partir de una cantidad de muestras o prototipos.
3. Para cada campo que extraigas, incluye tu confianza en el objeto \
"confianza": un número de 0 a 1 por campo, donde 1 es "el dato está escrito \
literalmente y sin ambigüedad" y 0.5 es "lo estoy infiriendo del contexto".
4. Responde SOLO con el objeto JSON, sin texto antes ni después.

Formato de la respuesta:

{
  "customer": "...",
  "part_number": "...",
  "volumen": 5000,
  "material": "...",
  "confianza": { "customer": 0.9, "part_number": 1.0, "volumen": 0.8, \
"material": 0.6 }
}
"""


def _umbral():
    """Umbral de confianza por debajo del cual un campo va a revisión."""
    return float(getattr(config, "UMBRAL_CONFIANZA", 0.7))


def _modelo():
    """Modelo de lenguaje para la extracción de texto."""
    return getattr(config, "LLM_MODEL", None) or config.VISION_MODEL


def _crear_cliente():
    """Cliente de Anthropic. Import perezoso: sólo se exige al usarse."""
    import anthropic
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


# --------------------------------------------------------------------------- #
# COT-66 — llamada al modelo
# --------------------------------------------------------------------------- #

def analizar_cuerpo(texto, asunto=None, cliente=None):
    """Envía el cuerpo del correo al LLM y devuelve su respuesta cruda.

    Args:
        texto: cuerpo del correo ya limpio (salida de ``html_cleaner``).
        asunto: asunto del correo; suele traer el part number o el cliente.
        cliente: cliente de Anthropic ya creado (inyección para pruebas).

    Returns:
        ``{"texto": <respuesta cruda>, "modelo": str, "uso": {...}}``.

    Raises:
        ExtraccionError: si no hay nada que analizar.
    """
    if not texto or not texto.strip():
        raise ExtraccionError("Cuerpo del correo vacío; nada que extraer.")

    encabezado = f"ASUNTO: {asunto}\n\n" if asunto else ""
    contenido = f"{encabezado}CUERPO DEL CORREO:\n{texto}"

    cliente = cliente or _crear_cliente()
    modelo = _modelo()
    log.info("Analizando el cuerpo del correo con %s (%d caracteres)...",
             modelo, len(texto))

    # La temperatura, sólo si está configurada y el modelo la acepta. Mandarla
    # a un modelo reciente devuelve un 400 y se lleva por delante la
    # extracción entera: el RFQ entra sin cliente, sin cantidades y sin
    # material, y parece que el correo venía vacío.
    import app.core.modelo as modelo_api
    respuesta = modelo_api.crear_mensaje(
        cliente,
        model=modelo,
        max_tokens=getattr(config, "VISION_MAX_TOKENS", 2048),
        system=PROMPT_COMERCIAL,
        messages=[{"role": "user", "content": contenido}],
        **modelo_api.parametros_de_muestreo(
            getattr(config, "VISION_TEMPERATURE", None)),
    )

    partes = [b.text for b in respuesta.content if getattr(b, "text", None)]
    uso = getattr(respuesta, "usage", None)

    return {
        "texto": "\n".join(partes),
        "modelo": modelo,
        "uso": {
            "input_tokens": getattr(uso, "input_tokens", None),
            "output_tokens": getattr(uso, "output_tokens", None),
        } if uso else {},
    }


# --------------------------------------------------------------------------- #
# COT-67 — interpretación de la respuesta
# --------------------------------------------------------------------------- #

def _a_numero(valor):
    """Convierte a número tolerando '5,000', '5000 pzas' o '~5000'."""
    if isinstance(valor, (int, float)):
        return valor
    if not isinstance(valor, str):
        return None
    limpio = "".join(c for c in valor if c.isdigit() or c in ".-")
    if not limpio or limpio in (".", "-"):
        return None
    try:
        numero = float(limpio)
    except ValueError:
        return None
    return int(numero) if numero.is_integer() else numero


def _a_confianza(valor):
    """Normaliza la confianza a un float 0-1; lo no interpretable es 0.0."""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, numero))


def interpretar(respuesta_texto, umbral=None):
    """Procesa la respuesta del LLM y reparte los campos por confianza.

    Returns:
        dict con:
          * ``campos``: los que superan el umbral, listos para usar.
          * ``en_revision``: ``{campo: {"valor":…, "confianza":…}}`` de los
            que no lo superan. No se usan ni se declaran faltantes.
          * ``confianzas``: score de cada campo extraído.
          * ``requiere_revision``: True si algún campo quedó por debajo.
          * ``umbral``: el umbral aplicado, para dejar traza.

    Raises:
        ExtraccionError: si la respuesta no contiene un JSON recuperable.
    """
    umbral = _umbral() if umbral is None else umbral
    crudo = extraer_json(respuesta_texto)
    if not isinstance(crudo, dict):
        raise ExtraccionError("El modelo no devolvió un objeto JSON.")

    scores = crudo.get("confianza") or {}
    if not isinstance(scores, dict):
        scores = {}

    campos, en_revision, confianzas = {}, {}, {}

    for campo in CAMPOS:
        if campo not in crudo:
            continue

        valor = crudo[campo]
        if valor is None or valor == "" or valor == []:
            continue

        if campo in _CAMPOS_NUMERICOS:
            convertido = _a_numero(valor)
            if convertido is None:
                log.warning("Campo %r no numérico (%r); se omite.", campo, valor)
                continue
            valor = convertido

        confianza = _a_confianza(scores.get(campo, 0.0))
        confianzas[campo] = confianza

        if confianza < umbral:
            en_revision[campo] = {"valor": valor, "confianza": confianza}
        else:
            campos[campo] = valor

    if en_revision:
        log.info("Campos por debajo del umbral %.2f, a revisión del PM: %s",
                 umbral, ", ".join(sorted(en_revision)))

    return {
        "campos": campos,
        "en_revision": en_revision,
        "confianzas": confianzas,
        "requiere_revision": bool(en_revision),
        "umbral": umbral,
    }


def extraer(texto, asunto=None, cliente=None, umbral=None):
    """Pipeline completo: cuerpo del correo → campos comerciales."""
    analisis = analizar_cuerpo(texto, asunto=asunto, cliente=cliente)
    resultado = interpretar(analisis["texto"], umbral=umbral)
    resultado["modelo"] = analisis["modelo"]
    resultado["uso"] = analisis.get("uso", {})
    return resultado
