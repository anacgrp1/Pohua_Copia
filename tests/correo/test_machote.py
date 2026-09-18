"""Los cinco textos del machote, palabra por palabra donde importa.

El machote es `docs/Cotizador - texto email & notificaciones.pdf`. Lo que se
comprueba aquí no es el estilo: es que no se pierda ninguna de las frases que
la empresa decidió que dijera cada correo, que la firma sea la de la planta y
que los asuntos de los internos sean los que se buscan en la bandeja.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

import app.email.templates as templates

FIRMA = ["INDUSTRIAL SPRING CORPORATION", "1801 Bedford Ave",
         "North Kansas City, MO 64116", "www.cgr-international.com",
         "www.isckc.com"]


class TestAlCliente(unittest.TestCase):

    def test_datos_faltantes(self):
        c = templates.construir_correo("datos_faltantes", {
            "destinatario": "roberto@neogen.com",
            "asunto_original": "RFQ 4500",
            "nombre_comprador": "Roberto Perez",
            "campos_faltantes": ["tiene_adjunto", "volumen", "material"],
        })
        cuerpo = c["cuerpo_texto"]
        self.assertEqual(c["asunto"], "RFQ 4500")          # se responde en su hilo
        self.assertIn("Dear Roberto Perez,", cuerpo)
        self.assertIn("Thank you for considering us for this project.", cuerpo)
        self.assertIn("we need the following missing details:", cuerpo)
        self.assertIn("Please provide this information by replying to this email.",
                      cuerpo)
        # Lo que se pide se dice como en el machote, no con el nombre interno.
        self.assertIn("Technical Drawing: Drawing or schematic file (PDF, PNG, or CAD)",
                      cuerpo)
        self.assertIn("Volume / EAU: Target batch quantity or Estimated Annual Usage",
                      cuerpo)
        self.assertNotIn("tiene_adjunto", cuerpo)
        self.assertNotIn("volumen", cuerpo)

    def test_lo_que_cae_en_la_misma_linea_no_se_repite(self):
        c = templates.construir_correo("datos_faltantes", {
            "destinatario": "x@y.com", "asunto_original": "RFQ",
            "nombre_comprador": "Ana",
            "campos_faltantes": ["tolerancias", "key_dimensions", "dimensiones"],
        })
        self.assertEqual(c["cuerpo_texto"].count("Key Dimensions & Tolerances"), 1)

    def test_un_campo_que_no_conoce_sale_igual(self):
        c = templates.construir_correo("datos_faltantes", {
            "destinatario": "x@y.com", "asunto_original": "RFQ",
            "nombre_comprador": "Ana", "campos_faltantes": ["plazo_entrega"],
        })
        self.assertIn("Plazo entrega", c["cuerpo_texto"])

    def test_sin_campos_no_hay_correo(self):
        with self.assertRaises(ValueError):
            templates.construir_correo("datos_faltantes", {
                "destinatario": "x@y.com", "asunto_original": "RFQ",
                "nombre_comprador": "Ana", "campos_faltantes": []})

    def test_declinar(self):
        c = templates.construir_correo("declinar_rfq", {
            "destinatario": "x@y.com", "asunto_original": "Re: RFQ 4500",
            "nombre_comprador": "Ana"})
        cuerpo = c["cuerpo_texto"]
        self.assertIn("we regret to inform you that we are unable to quote this "
                      "project", cuerpo)
        self.assertIn("fall outside our current manufacturing capabilities", cuerpo)
        self.assertIn("please let us know if we can assist with future projects",
                      cuerpo)
        self.assertEqual(c["adjuntos"], [])

    def test_oferta(self):
        c = templates.construir_correo("oferta_cliente", {
            "destinatario": "x@y.com", "asunto_original": "Re: RFQ 4500",
            "nombre_comprador": "Ana", "lead_time": "45 working days",
            "incoterm": "FCA North Kansas City", "validez_oferta": "30 days",
            "adjuntos": ["/tmp/COT-75.pdf"]})
        cuerpo = c["cuerpo_texto"]
        self.assertIn("please find attached our formal quotation for your review",
                      cuerpo)
        self.assertIn("Do not hesitate to reach out", cuerpo)
        # Las tres condiciones se quedan en el cuerpo (decisión de Ana).
        self.assertIn("Lead Time: 45 working days", cuerpo)
        self.assertIn("Incoterm: FCA North Kansas City", cuerpo)
        self.assertIn("Offer Validity: 30 days", cuerpo)
        self.assertEqual(c["adjuntos"], ["/tmp/COT-75.pdf"])

    def test_todos_llevan_la_firma_de_la_planta(self):
        correos = [
            templates.construir_correo("declinar_rfq", {
                "destinatario": "x@y.com", "asunto_original": "R", "nombre_comprador": "A"}),
            templates.construir_correo("datos_faltantes", {
                "destinatario": "x@y.com", "asunto_original": "R", "nombre_comprador": "A",
                "campos_faltantes": ["material"]}),
            templates.construir_correo("oferta_cliente", {
                "destinatario": "x@y.com", "asunto_original": "R", "nombre_comprador": "A",
                "lead_time": "1", "incoterm": "2", "validez_oferta": "3"}),
        ]
        for c in correos:
            for linea in FIRMA:
                self.assertIn(linea, c["cuerpo_texto"])
                self.assertIn(linea, c["cuerpo_html"])
            self.assertIn("Best regards,", c["cuerpo_texto"])


class TestInternos(unittest.TestCase):
    """Los dos que llegan a quien dictamina. Llevan enlace y NO llevan firma."""

    BASE = {"destinatario": "pm@isc.com", "nombre_pm": "Miguel",
            "cliente": "Neogen", "enlace": "https://pohua.example/#/rfq/COT-75"}

    def test_revision_de_factibilidad(self):
        c = templates.construir_correo("revision_factibilidad", dict(self.BASE))
        self.assertEqual(c["asunto"], "Feasibility review required – Neogen")
        cuerpo = c["cuerpo_texto"]
        self.assertIn("Hi Miguel,", cuerpo)
        self.assertIn("A feasibility review is required for a new quote request "
                      "from Neogen", cuerpo)
        self.assertIn("https://pohua.example/#/rfq/COT-75", cuerpo)
        # La línea que evita que alguien conteste creyendo que ya se contestó.
        self.assertIn("(Note: No email has been sent to the client yet).", cuerpo)
        self.assertNotIn("INDUSTRIAL SPRING CORPORATION", cuerpo)
        self.assertIn('href="https://pohua.example/#/rfq/COT-75"', c["cuerpo_html"])

    def test_validacion(self):
        c = templates.construir_correo("validacion_pm", dict(self.BASE))
        self.assertEqual(c["asunto"], "Quote validation required – Neogen")
        cuerpo = c["cuerpo_texto"]
        self.assertIn("A new quote for Neogen is ready and requires your review "
                      "and approval", cuerpo)
        self.assertIn("https://pohua.example/#/rfq/COT-75", cuerpo)
        self.assertTrue(cuerpo.rstrip().endswith("Thank you,"))

    def test_sin_enlace_no_se_construye(self):
        for tipo in ("revision_factibilidad", "validacion_pm"):
            params = dict(self.BASE)
            params["enlace"] = ""
            with self.assertRaises(ValueError):
                templates.construir_correo(tipo, params)


class TestAvisosDeLaCampana(unittest.TestCase):
    """El mismo texto, dicho por el otro canal."""

    def test_textos(self):
        self.assertEqual(templates.aviso_revision_factibilidad("Neogen"),
                         "Feasibility review required – Neogen")
        self.assertEqual(templates.aviso_validacion("Neogen"),
                         "Quote validation required – Neogen")

    def test_sin_cliente_no_queda_colgando(self):
        self.assertTrue(templates.aviso_validacion("").endswith("—"))


class TestDispatcher(unittest.TestCase):

    def test_tipo_desconocido(self):
        with self.assertRaises(ValueError) as caja:
            templates.construir_correo("lo_que_sea", {})
        self.assertIn("revision_factibilidad", str(caja.exception))


if __name__ == "__main__":
    unittest.main()
