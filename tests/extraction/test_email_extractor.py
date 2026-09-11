"""COT-66 / COT-67 — Extracción de datos comerciales del cuerpo del correo.

No se llama al modelo real: el cliente de Anthropic se inyecta como doble.
"""
import os
import unittest
from unittest import mock

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

import app.extraction.email_extractor as email_extractor
from app.vision.spring_extractor import ExtraccionError


class FakeBloque:
    def __init__(self, text):
        self.text = text


class FakeRespuesta:
    def __init__(self, texto):
        self.content = [FakeBloque(texto)]
        self.usage = mock.Mock(input_tokens=120, output_tokens=45)


class FakeMessages:
    def __init__(self, texto):
        self._texto = texto
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return FakeRespuesta(self._texto)


class FakeCliente:
    def __init__(self, texto):
        self.messages = FakeMessages(texto)


RESPUESTA_COMPLETA = """
{
  "customer": "Neogen",
  "part_number": "RS-4471",
  "volumen": 5000,
  "material": "SAE 1070",
  "fecha_entrega_requerida": "2026-10-15",
  "moneda": "USD",
  "confianza": {"customer": 0.95, "part_number": 1.0, "volumen": 0.9,
                "material": 0.85, "fecha_entrega_requerida": 0.8, "moneda": 0.9}
}
"""


class TestAnalizarCuerpo(unittest.TestCase):
    """COT-66 — la llamada al modelo."""

    def test_envia_asunto_y_cuerpo_con_el_prompt_de_sistema(self):
        cliente = FakeCliente(RESPUESTA_COMPLETA)
        resultado = email_extractor.analizar_cuerpo(
            "Necesito cotizar 5000 piezas", asunto="RFQ 4471", cliente=cliente)

        enviado = cliente.messages.kwargs
        self.assertIs(enviado["system"], email_extractor.PROMPT_COMERCIAL)
        contenido = enviado["messages"][0]["content"]
        self.assertIn("RFQ 4471", contenido)
        self.assertIn("5000 piezas", contenido)
        self.assertEqual(resultado["uso"]["input_tokens"], 120)

    def test_cuerpo_vacio_no_llama_al_modelo(self):
        with self.assertRaises(ExtraccionError):
            email_extractor.analizar_cuerpo("   ")


class TestInterpretar(unittest.TestCase):
    """COT-67 — mapeo de campos y rangos de confianza."""

    def test_campos_sobre_el_umbral_quedan_listos(self):
        r = email_extractor.interpretar(RESPUESTA_COMPLETA, umbral=0.7)

        self.assertEqual(r["campos"]["customer"], "Neogen")
        self.assertEqual(r["campos"]["part_number"], "RS-4471")
        self.assertEqual(r["campos"]["volumen"], 5000)
        self.assertEqual(r["campos"]["material"], "SAE 1070")
        self.assertEqual(r["campos"]["moneda"], "USD")
        self.assertFalse(r["requiere_revision"])
        self.assertEqual(r["en_revision"], {})

    def test_campo_dudoso_no_se_usa_ni_se_descarta(self):
        respuesta = """
        {"customer": "Neogen", "material": "acero?",
         "confianza": {"customer": 0.95, "material": 0.4}}
        """
        r = email_extractor.interpretar(respuesta, umbral=0.7)

        self.assertIn("customer", r["campos"])
        self.assertNotIn("material", r["campos"])          # no se usa
        self.assertEqual(r["en_revision"]["material"]["valor"], "acero?")
        self.assertAlmostEqual(r["en_revision"]["material"]["confianza"], 0.4)
        self.assertTrue(r["requiere_revision"])

    def test_campo_sin_confianza_declarada_va_a_revision(self):
        # Sin score explícito la confianza es 0.0: nunca se acepta a ciegas.
        r = email_extractor.interpretar('{"customer": "Neogen"}', umbral=0.7)
        self.assertNotIn("customer", r["campos"])
        self.assertIn("customer", r["en_revision"])

    def test_normaliza_volumen_con_formato_libre(self):
        respuesta = ('{"volumen": "5,000 pzas anuales", '
                     '"confianza": {"volumen": 0.9}}')
        r = email_extractor.interpretar(respuesta, umbral=0.7)
        self.assertEqual(r["campos"]["volumen"], 5000)

    def test_volumen_no_numerico_se_omite(self):
        respuesta = ('{"volumen": "por definir", '
                     '"confianza": {"volumen": 0.9}}')
        r = email_extractor.interpretar(respuesta, umbral=0.7)
        self.assertNotIn("volumen", r["campos"])
        self.assertNotIn("volumen", r["en_revision"])

    def test_ignora_campos_fuera_del_esquema(self):
        respuesta = ('{"customer": "Neogen", "color_favorito": "azul", '
                     '"confianza": {"customer": 0.9, "color_favorito": 1.0}}')
        r = email_extractor.interpretar(respuesta, umbral=0.7)
        self.assertNotIn("color_favorito", r["campos"])
        self.assertNotIn("color_favorito", r["en_revision"])

    def test_valores_vacios_no_cuentan_como_extraidos(self):
        respuesta = ('{"customer": "", "material": null, "escalones_cantidad": [], '
                     '"confianza": {"customer": 1.0, "material": 1.0}}')
        r = email_extractor.interpretar(respuesta, umbral=0.7)
        self.assertEqual(r["campos"], {})
        self.assertEqual(r["en_revision"], {})

    def test_json_dentro_de_fences_se_recupera(self):
        respuesta = ('Claro, aquí tienes:\n```json\n'
                     '{"customer": "Neogen", "confianza": {"customer": 0.9}}\n```')
        r = email_extractor.interpretar(respuesta, umbral=0.7)
        self.assertEqual(r["campos"]["customer"], "Neogen")

    def test_respuesta_irrecuperable_lanza(self):
        with self.assertRaises(ExtraccionError):
            email_extractor.interpretar("No encontré datos en el correo.")

    def test_confianza_fuera_de_rango_se_acota(self):
        respuesta = ('{"customer": "Neogen", "part_number": "X", '
                     '"confianza": {"customer": 7, "part_number": -3}}')
        r = email_extractor.interpretar(respuesta, umbral=0.7)
        self.assertEqual(r["confianzas"]["customer"], 1.0)
        self.assertEqual(r["confianzas"]["part_number"], 0.0)


class TestExtraerPipeline(unittest.TestCase):

    def test_pipeline_completo(self):
        cliente = FakeCliente(RESPUESTA_COMPLETA)
        r = email_extractor.extraer(
            "cuerpo del correo", asunto="RFQ", cliente=cliente, umbral=0.7)

        self.assertEqual(r["campos"]["part_number"], "RS-4471")
        self.assertIn("modelo", r)
        self.assertEqual(r["uso"]["output_tokens"], 45)


if __name__ == "__main__":
    unittest.main()
