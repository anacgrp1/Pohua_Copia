"""PDF Generator — creates Quotation PDFs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

try:
    from weasyprint import HTML  # type: ignore
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False

from jinja2 import Environment, FileSystemLoader

log = logging.getLogger("cotizador.pdf.generator")

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
ASSETS_DIR = Path(__file__).resolve().parent.parent / "frontend" / "assets"

jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


def generar_cotizacion_pdf(rfq_datos: Dict[str, Any], precio_datos: Dict[str, Any]) -> bytes:
    """Generates a quotation PDF and returns it as bytes."""

    if not WEASYPRINT_AVAILABLE:
        raise RuntimeError("weasyprint is not installed. PDF generation disabled.")

    template = jinja_env.get_template("quotation.html")

    # Path to local logo for Weasyprint to embed
    logo_path = ASSETS_DIR / "logo.png"
    logo_uri = logo_path.as_uri() if logo_path.exists() else ""

    html_content = template.render(
        rfq=rfq_datos,
        precio=precio_datos,
        logo_uri=logo_uri
    )

    pdf_bytes = HTML(string=html_content).write_pdf()
    return pdf_bytes
