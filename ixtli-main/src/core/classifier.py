"""
Motor de Clasificación Inteligente (Regex Engine)
Clasifica archivos y correos basándose en asunto, remitente y nombre de adjunto.
"""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ClassificationResult:
    category: str        # Categoría principal (ej: "Facturas")
    subcategory: str     # Subcategoría (ej: "UUID")
    folder_path: str     # Ruta relativa completa (ej: "Facturas/UUID")
    rule_matched: str    # Nombre de la regla que coincidió
    confidence: str      # 'HIGH' | 'MEDIUM' | 'LOW'


# ─────────────────────────────────────────────
#  Patrones de clasificación (orden importa)
# ─────────────────────────────────────────────
CLASSIFICATION_RULES = [
    {
        "name": "UUID_Fiscal",
        "category": "Facturas",
        "subcategory": "UUID",
        "folder_path": "Facturas/UUID",
        "confidence": "HIGH",
        "patterns": [
            re.compile(
                r'[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}'
                r'-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}',
                re.IGNORECASE
            )
        ],
        "fields": ["subject", "filename"],
    },
    {
        "name": "COVE_Aduanal",
        "category": "Facturas",
        "subcategory": "COVE",
        "folder_path": "Facturas/COVE",
        "confidence": "HIGH",
        "patterns": [
            re.compile(r'COVE\d{8}[A-Z0-9]{3,5}', re.IGNORECASE),
            re.compile(r'\bCOVE\b', re.IGNORECASE)
        ],
        "fields": ["subject", "filename", "body"],
    },
    {
        "name": "Factura_General",
        "category": "Facturas",
        "subcategory": "General",
        "folder_path": "Facturas/General",
        "confidence": "MEDIUM",
        "patterns": [
            re.compile(r'\bfactura\b', re.IGNORECASE),
            re.compile(r'\bxml\b', re.IGNORECASE),
        ],
        "fields": ["subject", "body"],
    },
    {
        "name": "Comprobantes_General",
        "category": "Comprobantes",
        "subcategory": "General",
        "folder_path": "Comprobantes/General",
        "confidence": "MEDIUM",
        "patterns": [
            re.compile(r'\bcomprobante\b', re.IGNORECASE),
        ],
        "fields": ["subject", "body"],
    },
    {
        "name": "CGR_Registros",
        "category": "CGR",
        "subcategory": "Registros",
        "folder_path": "CGR/Registros",
        "confidence": "HIGH",
        "patterns": [
            re.compile(r'CGR-\d{4}-\d{3}', re.IGNORECASE)
        ],
        "fields": ["subject", "filename"],
    },
    {
        "name": "FedEx_Logistica",
        "category": "Logistica",
        "subcategory": "FedEx",
        "folder_path": "Logistica/FedEx",
        "confidence": "HIGH",
        "patterns": [
            re.compile(r'\bfedex\b', re.IGNORECASE),
            re.compile(r'\b889\d{9}\b'),          # Guía FedEx 12 dígitos
        ],
        "fields": ["subject", "filename", "sender"],
    },
    {
        "name": "DHL_Logistica",
        "category": "Logistica",
        "subcategory": "DHL",
        "folder_path": "Logistica/DHL",
        "confidence": "HIGH",
        "patterns": [
            re.compile(r'\bdhl\b', re.IGNORECASE),
            re.compile(r'\b736\d{7}\b'),           # Guía DHL 10 dígitos
            re.compile(r'\bPED\d+\b', re.IGNORECASE),  # Prefijo PED
        ],
        "fields": ["subject", "filename", "sender"],
    },
    {
        "name": "DAL_DQ",
        "category": "Logistica",
        "subcategory": "DHL",
        "folder_path": "Logistica/DHL",
        "confidence": "HIGH",
        "patterns": [
            # DQ + alfanuméricos: cubre DQ25I35315, DQ25I31802, DQ25I29987_1, etc.
            re.compile(r'^DQ[A-Z0-9]', re.IGNORECASE),
        ],
        "fields": ["filename"],
    },
    {
        "name": "ArchivoDig_Pedimentos",
        "category": "Pagos",
        "subcategory": "Pedimentos",
        "folder_path": "Pagos/Pedimentos",
        "confidence": "HIGH",
        "patterns": [
            re.compile(r'ArchivoDig', re.IGNORECASE),  # Nombre contiene "ArchivoDig"
        ],
        "fields": ["filename"],
    },
    {
        "name": "Pagos_Pedimentos",
        "category": "Pagos",
        "subcategory": "Pedimentos",
        "folder_path": "Pagos/Pedimentos",
        "confidence": "HIGH",
        "patterns": [
            re.compile(r'envios\.codex@gmail\.com', re.IGNORECASE),
            re.compile(r'Notificaci[oó]n\s+de\s+Pago\s+de\s+Pedimento', re.IGNORECASE),
            re.compile(r'pago\s+de\s+pedimento', re.IGNORECASE),
        ],
        "fields": ["subject", "sender"],
    },
]

DEFAULT_RESULT = ClassificationResult(
    category="Otros",
    subcategory="General",
    folder_path="Otros",
    rule_matched="NONE",
    confidence="LOW",
)


def classify(
    subject: str = "",
    filename: str = "",
    sender: str = "",
    body: str = "",
) -> ClassificationResult:
    """
    Clasifica un adjunto basándose en el asunto,
    nombre, remitente y cuerpo del correo.

    Returns ClassificationResult con la categoría asignada.
    """
    context = {
        "subject": subject or "",
        "filename": filename or "",
        "sender": sender or "",
        "body": body or "",
    }

    for rule in CLASSIFICATION_RULES:
        search_text = " ".join(
            context[f] for f in rule["fields"] if context.get(f)
        )
        for pattern in rule["patterns"]:
            if pattern.search(search_text):
                return ClassificationResult(
                    category=rule["category"],
                    subcategory=rule["subcategory"],
                    folder_path=rule["folder_path"],
                    rule_matched=rule["name"],
                    confidence=rule["confidence"],
                )

    return DEFAULT_RESULT
