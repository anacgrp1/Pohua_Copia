"""Limpieza del cuerpo HTML de correos entrantes (Outlook).

Propósito
---------
Este módulo recibe el cuerpo HTML de un correo (``body_html``) y devuelve
texto plano legible, listo para ser procesado por las etapas siguientes del
pipeline de RFQ (extracción de campos, clasificación, generación de
cotización). Es el primer paso del análisis: convierte HTML rico —con tags,
estilos en línea, scripts, tablas, listas y firmas— en texto crudo
manejable.

Función principal
-----------------
``limpiar_html(body_html: str | None) -> str``

* **Entrada:** un ``str`` con el HTML del correo (el campo ``body_html`` tal
  como lo entrega Outlook / Microsoft Graph). También acepta ``None`` o
  cadena vacía sin lanzar excepción.
* **Salida:** un ``str`` con el texto extraído del HTML, sin tags, sin
  estilos CSS, sin scripts, sin markup y sin líneas vacías duplicadas. Si
  la entrada está vacía o es inválida, devuelve cadena vacía.

Fuera de alcance (NO es responsabilidad de este módulo)
-------------------------------------------------------
Este módulo **no extrae metadatos del correo**: asunto, remitente,
destinatarios, fecha, adjuntos, ``message_id``, etc. Esos datos son
provistos por la dataclass ``EmailMessage`` que construye el módulo de
proveedores de correo (tarea **COT-46**, a cargo de **Ana Ramírez**). El
contrato de integración es:

    email_msg: EmailMessage = provider.get_message(...)   # COT-46
    texto: str = limpiar_html(email_msg.body_html)        # COT-53 (este módulo)

Tampoco hace análisis semántico, detección de idioma, ni parsing de
adjuntos: solo entrega texto plano limpio.

Dependencias
------------
* ``beautifulsoup4`` — parsing y manipulación del árbol HTML.
* ``lxml`` — parser rápido y tolerante a HTML malformado (con respaldo
  automático a ``html.parser`` de la stdlib si ``lxml`` no estuviera
  disponible en el entorno).
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Tags cuyo contenido no es texto legible y debe descartarse por completo.
_TAGS_NO_VISIBLES = ("script", "style", "head", "title", "meta", "link", "noscript")

# Elementos de bloque: tras su texto debe insertarse un salto de línea. Los
# elementos inline (b, i, span, a, ...) no rompen la frase.
_TAGS_BLOQUE = (
    "p", "div", "br", "li", "tr", "table", "ul", "ol", "blockquote", "pre",
    "h1", "h2", "h3", "h4", "h5", "h6", "header", "footer", "section", "article",
)

# Colapsa 3 o más saltos de línea (con posibles espacios intermedios) en
# como máximo una línea en blanco, evitando líneas vacías duplicadas.
_RE_LINEAS_VACIAS = re.compile(r"\n\s*\n\s*\n+")

# Espacios/tabs repetidos dentro de una misma línea.
_RE_ESPACIOS = re.compile(r"[ \t]+")


def limpiar_html(body_html: str | None, parser: str = "lxml") -> str:
    """Convierte un string HTML en texto plano legible.

    Args:
        body_html: Contenido HTML del correo (``body_html`` de Outlook).
            Puede ser ``None`` o vacío.
        parser: Parser de BeautifulSoup a usar. Por defecto ``"lxml"``;
            si no está disponible se hace fallback a ``"html.parser"``
            (incluido en la stdlib).

    Returns:
        Texto limpio sin markup, sin líneas vacías duplicadas y sin espacios
        sobrantes. Devuelve cadena vacía si la entrada está vacía o no se
        pudo extraer texto.
    """
    # --- Validación / manejo de HTML vacío -------------------------------
    if not body_html or not body_html.strip():
        logger.debug("limpiar_html recibió un HTML vacío o nulo.")
        return ""

    if not isinstance(body_html, str):
        # Defensa ante inputs inesperados (p. ej. bytes o None disfrazado).
        logger.warning(
            "limpiar_html esperaba str y recibió %s; se intenta convertir.",
            type(body_html).__name__,
        )
        body_html = str(body_html)

    # --- Parseo robusto ante HTML malformado -----------------------------
    soup = _parsear(body_html, parser)
    if soup is None:
        return ""

    # Eliminar tags no visibles junto con su contenido.
    for elemento in soup(_TAGS_NO_VISIBLES):
        elemento.decompose()

    # Marcar el fin de cada elemento de bloque con un salto de línea para que
    # el texto inline (b, i, span...) no se fragmente, pero los bloques sí se
    # separen en líneas distintas.
    for elemento in soup.find_all(_TAGS_BLOQUE):
        if elemento.name == "br":
            elemento.replace_with("\n")
        else:
            elemento.append("\n")

    # Extraer texto sin separador adicional (los saltos ya están insertados).
    texto = soup.get_text()

    return _normalizar(texto)


def _parsear(body_html: str, parser: str) -> BeautifulSoup | None:
    """Parsea el HTML tolerando errores y con fallback de parser."""
    try:
        return BeautifulSoup(body_html, parser)
    except Exception:  # noqa: BLE001 - incluye FeatureNotFound y errores de lxml
        logger.warning(
            "Falló el parser '%s'; usando 'html.parser' como respaldo.",
            parser,
            exc_info=True,
        )
        try:
            return BeautifulSoup(body_html, "html.parser")
        except Exception:  # noqa: BLE001
            logger.error("No se pudo parsear el HTML del correo.", exc_info=True)
            return None


def _normalizar(texto: str) -> str:
    """Normaliza espacios y elimina líneas vacías duplicadas."""
    if not texto:
        return ""

    # Normalizar saltos de línea de Windows/Mac y espacios duros (&nbsp;).
    texto = texto.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")

    # Limpiar espacios repetidos y recortar cada línea.
    lineas = (_RE_ESPACIOS.sub(" ", linea).strip() for linea in texto.split("\n"))
    texto = "\n".join(lineas)

    # Colapsar líneas vacías duplicadas a una sola línea en blanco.
    texto = _RE_LINEAS_VACIAS.sub("\n\n", texto)

    return texto.strip()
