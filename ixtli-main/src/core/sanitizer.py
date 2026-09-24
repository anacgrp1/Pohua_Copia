"""
Sanitizador de nombres de archivo.
Elimina caracteres inválidos para el sistema de archivos de Windows.
"""
import re
import unicodedata


# Caracteres prohibidos en Windows
_WINDOWS_FORBIDDEN = re.compile(r'[\\/:*?"<>|]')
# Espacios múltiples
_MULTI_SPACE = re.compile(r'\s+')
# Nombres reservados de Windows
_WINDOWS_RESERVED = re.compile(
    r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)',
    re.IGNORECASE
)
MAX_FILENAME_LENGTH = 200


def sanitize(name: str, replacement: str = "_") -> str:
    """
    Sanitiza un nombre de archivo para Windows:
    - Elimina caracteres prohibidos
    - Reemplaza espacios múltiples
    - Trunca a MAX_FILENAME_LENGTH caracteres
    - Añade prefijo si es nombre reservado

    Args:
        name: Nombre original del archivo (sin extensión o con extensión).
        replacement: Carácter de reemplazo para los prohibidos.

    Returns:
        Nombre de archivo limpio y seguro.
    """
    if not name:
        return "sin_nombre"

    # Normalizar unicode (NFD → NFC)
    name = unicodedata.normalize("NFC", name)

    # Reemplazar caracteres prohibidos
    name = _WINDOWS_FORBIDDEN.sub(replacement, name)

    # Colapsar espacios
    name = _MULTI_SPACE.sub(" ", name).strip()

    # Si es nombre reservado, añadir prefijo
    if _WINDOWS_RESERVED.match(name):
        name = f"__{name}"

    # Truncar preservando la extensión
    if "." in name:
        stem, _, ext = name.rpartition(".")
        max_stem = MAX_FILENAME_LENGTH - len(ext) - 1
        name = f"{stem[:max_stem]}.{ext}"
    else:
        name = name[:MAX_FILENAME_LENGTH]

    return name or "sin_nombre"
