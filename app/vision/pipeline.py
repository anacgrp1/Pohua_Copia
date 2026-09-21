"""
SUBTAREA 1 [Código - IA]
Pipeline del modelo multimodal de visión (Anthropic Claude) para la
extracción de información de dibujos técnicos de resortes.

Recibe los archivos en BYTES y soporta las extensiones:
    .pdf  -> bloque "document" (Claude lee el PDF de forma nativa)
    .png  -> bloque "image"
    .stp / .step -> STUB (CAD ISO-10303 de texto, no es imagen) -> pendiente

Diseña el PROMPT TÉCNICO enfocado en resortes de compresión, torsión y
extensión, y solicita una respuesta en JSON estricto que luego interpreta
src/spring_extractor.py (Subtarea 2).
"""
import base64
import logging

import app.core.config as config

log = logging.getLogger("cotizador.vision")

# ===== Extensiones soportadas y sus media types =====
# JPEG entra aquí porque el modelo lo lee igual que un PNG y porque los planos
# que llegan por correo vienen tantas veces en .jpg como en .pdf —una foto del
# dibujo, un escaneo—. Quedaban fuera de la lista y se descartaban en silencio:
# el RFQ entraba sin una sola cota y la ficha decía "—" en todo sin explicar
# que el dibujo estaba ahí y ni se había mirado.
EXT_IMAGEN = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
EXT_DOCUMENTO = {".pdf": "application/pdf"}
EXT_CAD_STUB = {".stp", ".step"}            # ISO-10303 (texto), aún no soportado
EXTENSIONES_SOPORTADAS = (".pdf", ".png", ".jpg", ".jpeg", ".stp", ".step")

# Firmas (magic bytes) para detección por contenido cuando falta el nombre
_FIRMA_PNG = b"\x89PNG\r\n\x1a\n"
_FIRMA_JPEG = b"\xff\xd8\xff"
_FIRMA_PDF = b"%PDF"
_FIRMA_STEP = b"ISO-10303-21"


# ============================================================================
# PROMPT TÉCNICO — resortes de compresión, torsión y extensión
# ============================================================================
PROMPT_TECNICO = """\
Eres un ingeniero de manufactura experto en RESORTES metálicos. Analiza el o los
dibujos técnicos adjuntos (planos, vistas, tablas de parámetros y notas) y extrae
TODAS las variables físicas necesarias para COTIZAR la fabricación del resorte.

Clasifica primero el TIPO de resorte:
  - "compresion": espiras separadas que resisten una carga axial de compresión.
  - "torsion": brazos/patas que ejercen par (momento) al girar; mira el ángulo entre brazos.
  - "extension": espiras juntas con ganchos/anillos en los extremos que resisten tracción.
  - "desconocido": si el dibujo no permite determinarlo con seguridad.

Reglas de extracción:
  - Usa SIEMPRE milímetros (mm) para longitudes y diámetros; grados para ángulos.
  - Si un valor aparece con tolerancia (p. ej. 12.5 ±0.1), devuelve el valor nominal en el
    campo numérico y la tolerancia textual en "tolerancias".
  - Extrae el NÚMERO DE PARTE en "num_parte": el identificador comercial de la pieza,
    normalmente en el cuadro de rotulación (title block) del plano, junto al nombre
    de la pieza o del cliente. NO uses el número de plano ni el de revisión.
  - Si un dato NO está en el dibujo, devuelve null. NO inventes valores.
  - Para cada valor, evalúa tu confianza global del 0.0 al 1.0 en "confianza".
  - Anota en "advertencias" cualquier ambigüedad, texto ilegible o supuesto realizado.

Devuelve EXCLUSIVAMENTE un objeto JSON válido (sin markdown, sin ```), con esta forma:
{
  "num_parte": "string|null",
  "tipo_resorte": "compresion|torsion|extension|desconocido",
  "material": "string|null",
  "norma_material": "string|null",
  "diametro_alambre_mm": number|null,
  "diametro_exterior_mm": number|null,
  "diametro_interior_mm": number|null,
  "diametro_medio_mm": number|null,
  "longitud_libre_mm": number|null,
  "longitud_cuerpo_mm": number|null,
  "numero_espiras_totales": number|null,
  "numero_espiras_activas": number|null,
  "paso_mm": number|null,
  "sentido_enrollado": "derecha|izquierda|null",
  "tipo_extremos": "string|null",
  "angulo_brazos_grados": number|null,
  "longitud_gancho_mm": number|null,
  "constante_resorte_N_mm": number|null,
  "acabado": "string|null",
  "tolerancias": "string|null",
  "cantidad": number|null,
  "unidad": "string|null",
  "normas": ["string"],
  "notas": "string|null",
  "confianza": number,
  "advertencias": ["string"]
}
"""


# ============================================================================
# Excepciones
# ============================================================================
class VisionPipelineError(Exception):
    """Error general del pipeline de visión."""


class FormatoNoSoportado(VisionPipelineError):
    """La extensión/contenido del archivo no está dentro de los soportados."""


class FormatoPendiente(VisionPipelineError):
    """Formato reconocido pero aún no implementado (STEP/CAD)."""


# ============================================================================
# Detección de tipo de archivo
# ============================================================================
def _extension(nombre):
    """Devuelve la extensión en minúsculas (con punto) a partir del nombre."""
    if not nombre or "." not in nombre:
        return ""
    return "." + nombre.rsplit(".", 1)[1].lower()


def detectar_tipo(nombre="", contenido=b""):
    """
    Determina la categoría del archivo: "imagen", "documento" o "cad".
    Usa primero la extensión del nombre y, como respaldo, las firmas
    (magic bytes) del contenido. Lanza FormatoNoSoportado si no aplica.
    """
    ext = _extension(nombre)
    if ext in EXT_IMAGEN:
        return "imagen"
    if ext in EXT_DOCUMENTO:
        return "documento"
    if ext in EXT_CAD_STUB:
        return "cad"

    # Respaldo por contenido (magic bytes) cuando no hay extensión fiable
    cabecera = contenido[:16] if contenido else b""
    if cabecera.startswith(_FIRMA_PNG) or cabecera.startswith(_FIRMA_JPEG):
        return "imagen"
    if cabecera.startswith(_FIRMA_PDF):
        return "documento"
    if _FIRMA_STEP in cabecera or contenido[:512].lstrip().startswith(_FIRMA_STEP):
        return "cad"

    raise FormatoNoSoportado(
        f"Formato no soportado: nombre={nombre!r}. "
        f"Soportados: {', '.join(EXTENSIONES_SOPORTADAS)}"
    )


def _media_type(nombre, categoria):
    """Resuelve el media_type para imagen/documento."""
    ext = _extension(nombre)
    if categoria == "imagen":
        return EXT_IMAGEN.get(ext, "image/png")
    if categoria == "documento":
        return EXT_DOCUMENTO.get(ext, "application/pdf")
    return None


# ============================================================================
# Construcción de bloques de contenido para la Messages API
# ============================================================================
def _bloque_imagen(contenido, media_type):
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.standard_b64encode(contenido).decode("ascii"),
        },
    }


def _bloque_documento(contenido, media_type):
    return {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.standard_b64encode(contenido).decode("ascii"),
        },
    }


def _bloque_cad_stub(nombre):
    """
    STEP/STP (.stp/.step) son CAD de texto ISO-10303, no imágenes: un modelo
    de visión no los interpreta directamente.

    TODO (extensión futura): renderizar el sólido a imagen con un kernel CAD
    (OpenCASCADE / cadquery) o parsear la geometría B-rep, y luego reanudar
    el flujo de visión. Por ahora se omite explícitamente.
    """
    log.warning("Formato CAD pendiente, archivo omitido del análisis: %s", nombre)
    raise FormatoPendiente(
        f"STEP/STP aún no soportado (stub): {nombre!r}. "
        "Pendiente renderizar CAD a imagen antes de la visión."
    )


def construir_contenido(archivos):
    """
    Construye la lista de bloques de contenido para el mensaje del usuario.

    archivos: lista de dicts {"nombre": str, "contenido": bytes}.

    Devuelve (bloques, omitidos):
      - bloques: [ {imagen/documento}..., {texto: PROMPT_TECNICO} ]
      - omitidos: lista de (nombre, motivo) de archivos no incluidos (p. ej. STEP)
    El prompt de texto se coloca al final para que el modelo ya tenga el
    contexto visual cargado al leer las instrucciones.
    """
    bloques = []
    omitidos = []

    for archivo in archivos:
        nombre = archivo.get("nombre", "")
        contenido = archivo.get("contenido", b"") or b""
        try:
            categoria = detectar_tipo(nombre, contenido)
            if categoria == "imagen":
                bloques.append(_bloque_imagen(contenido, _media_type(nombre, "imagen")))
            elif categoria == "documento":
                bloques.append(_bloque_documento(contenido, _media_type(nombre, "documento")))
            elif categoria == "cad":
                _bloque_cad_stub(nombre)        # lanza FormatoPendiente
        except (FormatoNoSoportado, FormatoPendiente) as error:
            omitidos.append((nombre, str(error)))

    if not bloques:
        raise FormatoNoSoportado(
            "Ningún archivo soportado para visión "
            f"(omitidos: {[n for n, _ in omitidos]})."
        )

    bloques.append({"type": "text", "text": PROMPT_TECNICO})
    return bloques, omitidos


# ============================================================================
# Cliente y llamada al modelo
# ============================================================================
def _crear_cliente():
    """
    Crea el cliente de Anthropic. Import perezoso para que el módulo se pueda
    importar (y testear la construcción de bloques) sin el SDK instalado.
    """
    if not config.settings.ANTHROPIC_API_KEY:
        raise VisionPipelineError("Falta ANTHROPIC_API_KEY en el entorno (.env).")
    try:
        import anthropic
    except ImportError as error:
        raise VisionPipelineError(
            "El paquete 'anthropic' no está instalado. Ejecuta: pip install anthropic"
        ) from error
    return anthropic.Anthropic(api_key=config.settings.ANTHROPIC_API_KEY)


def analizar_dibujos(archivos, cliente=None):
    """
    Punto de entrada del pipeline (Subtarea 1).

    Recibe los archivos en bytes, construye el contenido multimodal, llama al
    modelo de visión y devuelve un dict:
        {
          "texto": <respuesta cruda del modelo, JSON en texto>,
          "omitidos": [(nombre, motivo), ...],
          "modelo": <nombre del modelo>,
          "uso": {input_tokens, output_tokens}  # si está disponible
        }
    El texto se entrega tal cual al extractor (src/spring_extractor.py).
    """
    bloques, omitidos = construir_contenido(archivos)
    cliente = cliente or _crear_cliente()

    log.info("Analizando %d bloque(s) de dibujo con %s (omitidos: %d)...",
             len(bloques) - 1, config.settings.VISION_MODEL, len(omitidos))

    # La temperatura va sólo si está configurada Y el modelo la acepta: los
    # modelos recientes la rechazan con un 400 y tumban la lectura entera.
    import app.core.modelo as modelo
    respuesta = modelo.crear_mensaje(
        cliente,
        model=config.settings.VISION_MODEL,
        max_tokens=config.settings.VISION_MAX_TOKENS,
        messages=[{"role": "user", "content": bloques}],
        **modelo.parametros_de_muestreo(
            getattr(config.settings, "VISION_TEMPERATURE", None)),
    )

    # Concatena los bloques de texto de la respuesta
    texto = "".join(
        getattr(parte, "text", "") for parte in respuesta.content
        if getattr(parte, "type", "") == "text"
    )

    uso = {}
    if getattr(respuesta, "usage", None):
        uso = {
            "input_tokens": getattr(respuesta.usage, "input_tokens", None),
            "output_tokens": getattr(respuesta.usage, "output_tokens", None),
        }

    return {
        "texto": texto,
        "omitidos": omitidos,
        "modelo": config.settings.VISION_MODEL,
        "uso": uso,
    }


if __name__ == "__main__":
    # Demo offline: solo construcción de bloques (no llama a la API).
    from app.core.logging import configure_logging
    configure_logging()
    png_falso = _FIRMA_PNG + b"contenido de imagen de prueba"
    pdf_falso = _FIRMA_PDF + b"-1.7 contenido de pdf de prueba"
    step_falso = b"ISO-10303-21;\nHEADER;\n..."

    ejemplos = [
        {"nombre": "plano_resorte.png", "contenido": png_falso},
        {"nombre": "ficha.pdf", "contenido": pdf_falso},
        {"nombre": "modelo.step", "contenido": step_falso},
    ]
    bloques, omitidos = construir_contenido(ejemplos)
    print(f"Bloques construidos: {[b['type'] for b in bloques]}")
    print(f"Omitidos (STEP stub): {omitidos}")
