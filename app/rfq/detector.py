"""
Detección de patrones clave de RFQ (RFQ, Cotización, Quote, Resorte)
en el asunto y el cuerpo usando expresiones regulares.
"""
import re

# ===== Patrones clave (insensibles a mayúsculas y acentos comunes) =====
PATRONES_RFQ = [
    re.compile(r"\bRFQ\b", re.IGNORECASE),
    re.compile(r"\bcotizaci[oó]n(es)?\b", re.IGNORECASE),
    re.compile(r"\bcotizar\b", re.IGNORECASE),
    re.compile(r"\bquote\b", re.IGNORECASE),
    re.compile(r"\bquotation\b", re.IGNORECASE),
    re.compile(r"\bresortes?\b", re.IGNORECASE),
]

# ID de RFQ en el asunto, ej: "RFQ-2024-001", "RFQ #123", "RFQ 456"
PATRON_ID_RFQ = re.compile(r"\bRFQ[\s#:-]*([A-Z0-9][A-Z0-9-]*\d)", re.IGNORECASE)


def encontrar_patrones(asunto, cuerpo=""):
    """
    Busca los patrones clave en asunto y cuerpo.
    Retorna la lista de coincidencias encontradas (vacía si no hay).
    """
    texto = f"{asunto or ''}\n{cuerpo or ''}"
    encontrados = []
    for patron in PATRONES_RFQ:
        m = patron.search(texto)
        if m:
            encontrados.append(m.group(0))
    return encontrados


def es_rfq(asunto, cuerpo=""):
    """True si el correo contiene al menos un patrón clave de RFQ."""
    return len(encontrar_patrones(asunto, cuerpo)) > 0


def extraer_id_rfq(asunto):
    """
    Extrae el ID del RFQ del asunto si existe.
    Ej: "RE: RFQ-2024-001 Resortes" -> "2024-001"
    Retorna None si no se encuentra.
    """
    m = PATRON_ID_RFQ.search(asunto or "")
    return m.group(1).upper() if m else None


if __name__ == "__main__":
    pruebas = [
        ("RFQ-2024-001 Resortes de compresión", "Favor de cotizar 500 pzas"),
        ("Solicitud de cotización", "Necesitamos quote para resorte de torsión"),
        ("Newsletter junio", "Ofertas de verano"),
    ]
    for asunto, cuerpo in pruebas:
        print(f"{asunto!r} -> es_rfq={es_rfq(asunto, cuerpo)}, "
              f"patrones={encontrar_patrones(asunto, cuerpo)}, "
              f"id={extraer_id_rfq(asunto)}")
