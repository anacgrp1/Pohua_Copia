"""Generación del PDF de cotización.

El test que de verdad importaba faltar: que ``import pdf.generator`` funcione.
El módulo importa jinja2 a nivel de módulo y jinja2 no estaba en
requirements.txt, así que en un entorno limpio esto reventaba con ImportError
y nadie se enteraba porque no había ningún test que lo importara.
"""

import os
import unittest
from unittest import mock

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")


class TestImportable(unittest.TestCase):

    def test_el_modulo_se_puede_importar(self):
        import pdf.generator  # noqa: F401

    def test_la_plantilla_existe(self):
        import pdf.generator as generator
        self.assertTrue((generator.TEMPLATES_DIR / "quotation.html").is_file())


class TestGeneracion(unittest.TestCase):

    def setUp(self):
        import pdf.generator as generator
        self.generator = generator
        self.rfq = {"rfq_id": "RFQ-2026-0042", "cliente_id": "CLI-001",
                    "nombre_proyecto": "Resorte Norteña 2500",
                    "part_number": "RC-12.5-45", "material": "MW",
                    "volumen": 5000, "fecha_registro": "2026-09-02",
                    "desc": "Resorte de compresión"}
        self.precio = {"precio_unitario_usd": 0.6451, "tooling_usd": 1250.0,
                       "lead_time_weeks": 8, "moneda": "USD", "notas": None}

    def test_sin_weasyprint_el_error_lo_dice(self):
        with mock.patch.object(self.generator, "WEASYPRINT_AVAILABLE", False):
            with self.assertRaises(RuntimeError) as ctx:
                self.generator.generar_cotizacion_pdf(self.rfq, self.precio)
        self.assertIn("weasyprint", str(ctx.exception).lower())

    def test_la_plantilla_se_renderiza_con_los_datos(self):
        """Se comprueba el renderizado del HTML sin depender de que las
        librerías nativas de WeasyPrint estén instaladas."""
        plantilla = self.generator.jinja_env.get_template("quotation.html")
        html = plantilla.render(rfq=self.rfq, precio=self.precio, logo_uri="")
        self.assertIn("RFQ-2026-0042", html)
        self.assertIn("0.6451", html)
        self.assertIn("8 Semanas", html)

    def test_la_plantilla_aguanta_valores_ausentes(self):
        """Desde que el costeo no inventa datos, precio_unitario_usd,
        tooling_usd y lead_time_weeks pueden venir en None. El filtro format()
        sobre None lanzaba UndefinedError y tumbaba la generación del PDF."""
        plantilla = self.generator.jinja_env.get_template("quotation.html")
        html = plantilla.render(
            rfq=self.rfq,
            precio={"precio_unitario_usd": None, "tooling_usd": None,
                    "lead_time_weeks": None, "moneda": "USD", "notas": None},
            logo_uri="")
        self.assertIn("Por confirmar", html)      # plazo de entrega
        self.assertIn("Por determinar", html)     # precio unitario
        self.assertIn("Sin herramental", html)
        self.assertNotIn("None", html)


if __name__ == "__main__":
    unittest.main()
