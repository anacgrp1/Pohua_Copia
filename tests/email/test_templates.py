
import unittest

from app.email.templates import construir_correo

CLAVES_ESPERADAS = {
    "destinatario", "asunto", "cuerpo_html", "cuerpo_texto", "adjuntos",
}


class TestConstruirCorreo(unittest.TestCase):

    # ------------------------------------------------------------------ #
    # TIPO 1 — declinar_rfq
    # ------------------------------------------------------------------ #
    def test_declinar_rfq_completo(self):
        resultado = construir_correo(
            "declinar_rfq",
            {
                "destinatario": "buyer@cliente.com",
                "asunto_original": "RE: RFQ Resorte de compresión",
                "nombre_comprador": "Roberto Méndez",
            },
        )
        self.assertEqual(set(resultado.keys()), CLAVES_ESPERADAS)
        self.assertEqual(resultado["destinatario"], "buyer@cliente.com")
        self.assertEqual(resultado["asunto"], "RE: RFQ Resorte de compresión")
        self.assertIn("Dear Roberto Méndez,", resultado["cuerpo_texto"])
        self.assertIn("not feasible", resultado["cuerpo_texto"])
        self.assertIn("CGR International", resultado["cuerpo_texto"])
        self.assertIn("<p>", resultado["cuerpo_html"])
        self.assertEqual(resultado["adjuntos"], [])

    # ------------------------------------------------------------------ #
    # TIPO 2 — datos_faltantes
    # ------------------------------------------------------------------ #
    def test_datos_faltantes_lista_aparece_en_cuerpo(self):
        campos = ["volumen", "part_number", "material"]
        resultado = construir_correo(
            "datos_faltantes",
            {
                "destinatario": "buyer@cliente.com",
                "asunto_original": "RE: Solicitud de cotización",
                "nombre_comprador": "Roberto Méndez",
                "campos_faltantes": campos,
            },
        )
        for campo in campos:
            self.assertIn(campo, resultado["cuerpo_texto"])
            self.assertIn(campo, resultado["cuerpo_html"])
        self.assertIn("<ul>", resultado["cuerpo_html"])
        self.assertIn("<li>volumen</li>", resultado["cuerpo_html"])
        self.assertEqual(resultado["adjuntos"], [])

    def test_datos_faltantes_lista_vacia_lanza_valueerror(self):
        with self.assertRaises(ValueError):
            construir_correo(
                "datos_faltantes",
                {
                    "destinatario": "buyer@cliente.com",
                    "asunto_original": "RE: Solicitud",
                    "nombre_comprador": "Roberto",
                    "campos_faltantes": [],
                },
            )

    # ------------------------------------------------------------------ #
    # TIPO 3 — validacion_pm
    # ------------------------------------------------------------------ #
    def test_validacion_pm_incluye_key_figures(self):
        resultado = construir_correo(
            "validacion_pm",
            {
                "destinatario": "pm@cgr.com",
                "nombre_pm": "Laura Gómez",
                "nombre_proyecto": "Resorte Norteña 2500",
                "volumen": 2500,
                "tooling_capex": 15000,
                "margen": 18,
            },
        )
        self.assertEqual(
            resultado["asunto"],
            "Validation Required: Commercial Offer - Resorte Norteña 2500",
        )
        cuerpo = resultado["cuerpo_texto"]
        self.assertIn("Hi Laura Gómez,", cuerpo)
        self.assertIn("Volume: 2500 units/year", cuerpo)
        self.assertIn("Tooling/CapEx: 15000 USD", cuerpo)
        self.assertIn("Margin: 18%", cuerpo)
        self.assertIn("<ul>", resultado["cuerpo_html"])

    # ------------------------------------------------------------------ #
    # TIPO 4 — oferta_cliente
    # ------------------------------------------------------------------ #
    def test_oferta_cliente_con_adjuntos(self):
        adjuntos = [
            "C:/cotizaciones/oferta-NRT-2500.pdf",
            "C:/cotizaciones/anexo-tecnico.pdf",
        ]
        resultado = construir_correo(
            "oferta_cliente",
            {
                "destinatario": "buyer@cliente.com",
                "asunto_original": "RE: Solicitud Resorte 316L",
                "nombre_comprador": "Roberto Méndez",
                "nombre_proyecto": "Resorte Norteña 2500",
                "lead_time": "8 weeks",
                "incoterm": "FCA Monterrey",
                "validez_oferta": "30 days",
                "adjuntos": adjuntos,
            },
        )
        self.assertEqual(resultado["adjuntos"], adjuntos)
        cuerpo = resultado["cuerpo_texto"]
        self.assertIn("Lead Time: 8 weeks", cuerpo)
        self.assertIn("Incoterm: FCA Monterrey", cuerpo)
        self.assertIn("Offer Validity: 30 days", cuerpo)
        self.assertIn("Resorte Norteña 2500", cuerpo)

    # ------------------------------------------------------------------ #
    # Errores del dispatcher
    # ------------------------------------------------------------------ #
    def test_tipo_desconocido_lanza_valueerror(self):
        with self.assertRaises(ValueError) as ctx:
            construir_correo("tipo_inexistente", {})
        self.assertIn("tipo_inexistente", str(ctx.exception).lower()
                      .replace("'", ""))

    def test_param_requerido_faltante_lanza_valueerror(self):
        # Falta 'nombre_comprador'.
        with self.assertRaises(ValueError) as ctx:
            construir_correo(
                "declinar_rfq",
                {
                    "destinatario": "buyer@cliente.com",
                    "asunto_original": "RE: RFQ",
                },
            )
        self.assertIn("nombre_comprador", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
