"""Pruebas de src/spring_extractor.py (Subtarea 2). Sin llamadas a la API."""
import unittest

import app.vision.spring_extractor as ext


class TestExtraerJson(unittest.TestCase):
    def test_json_puro(self):
        self.assertEqual(ext.extraer_json('{"a": 1}'), {"a": 1})

    def test_json_con_fences(self):
        texto = 'Aquí tienes:\n```json\n{"tipo_resorte": "compresion"}\n```'
        self.assertEqual(ext.extraer_json(texto)["tipo_resorte"], "compresion")

    def test_json_con_preambulo(self):
        texto = 'Análisis del plano: {"material": "acero", "cantidad": 10} fin.'
        datos = ext.extraer_json(texto)
        self.assertEqual(datos["material"], "acero")
        self.assertEqual(datos["cantidad"], 10)

    def test_objeto_anidado(self):
        texto = 'x {"a": {"b": 2}, "c": [1,2]} y'
        self.assertEqual(ext.extraer_json(texto), {"a": {"b": 2}, "c": [1, 2]})

    def test_vacio_lanza_error(self):
        with self.assertRaises(ext.ExtraccionError):
            ext.extraer_json("   ")

    def test_sin_json_lanza_error(self):
        with self.assertRaises(ext.ExtraccionError):
            ext.extraer_json("No hay datos estructurados aquí.")


class TestConversiones(unittest.TestCase):
    def test_a_float_con_unidad(self):
        self.assertEqual(ext._a_float("12.5 mm"), 12.5)

    def test_a_float_coma_decimal(self):
        self.assertEqual(ext._a_float("12,5"), 12.5)

    def test_a_float_entero(self):
        self.assertEqual(ext._a_float(8), 8.0)

    def test_a_float_nulos(self):
        self.assertIsNone(ext._a_float(None))
        self.assertIsNone(ext._a_float(""))
        self.assertIsNone(ext._a_float("sin dato"))

    def test_a_float_bool_es_none(self):
        self.assertIsNone(ext._a_float(True))

    def test_normalizar_tipo(self):
        self.assertEqual(ext._normalizar_tipo("Compresión"), "compresion")
        self.assertEqual(ext._normalizar_tipo("TORSION"), "torsion")
        self.assertEqual(ext._normalizar_tipo("extensión"), "extension")
        self.assertEqual(ext._normalizar_tipo("tracción"), "extension")
        self.assertEqual(ext._normalizar_tipo("otra cosa"), "desconocido")
        self.assertEqual(ext._normalizar_tipo(None), "desconocido")

    def test_confianza_acotada(self):
        self.assertEqual(ext._a_confianza(1.5), 1.0)
        self.assertEqual(ext._a_confianza(-0.2), 0.0)
        self.assertEqual(ext._a_confianza("0.7"), 0.7)
        self.assertEqual(ext._a_confianza(None), 0.0)

    def test_a_lista(self):
        self.assertEqual(ext._a_lista("ASTM A228"), ["ASTM A228"])
        self.assertEqual(ext._a_lista(["a", "b"]), ["a", "b"])
        self.assertEqual(ext._a_lista(None), [])


class TestNormalizarEInterpretar(unittest.TestCase):
    def test_resorte_completo_listo_para_cotizar(self):
        crudo = {
            "tipo_resorte": "Compresión",
            "material": "Acero ASTM A228",
            "diametro_alambre_mm": "1.2 mm",
            "diametro_exterior_mm": 12.5,
            "longitud_libre_mm": "40,0",
            "cantidad": 500,
            "unidad": "piezas",
            "confianza": 0.9,
        }
        r = ext.normalizar(crudo)
        self.assertEqual(r.tipo_resorte, "compresion")
        self.assertEqual(r.diametro_alambre_mm, 1.2)
        self.assertEqual(r.longitud_libre_mm, 40.0)
        self.assertTrue(r.listo_para_cotizar)
        self.assertEqual(r.faltantes(), [])

    def test_diametro_medio_derivado(self):
        # medio = exterior - alambre = 12.5 - 1.2 = 11.3
        r = ext.normalizar({
            "tipo_resorte": "compresion",
            "diametro_exterior_mm": 12.5,
            "diametro_alambre_mm": 1.2,
        })
        self.assertAlmostEqual(r.diametro_medio_mm, 11.3, places=3)

    def test_faltantes_marca_no_listo(self):
        # Sin material ni cantidad -> no listo para cotizar
        datos = ext.interpretar('{"tipo_resorte": "torsion", "diametro_alambre_mm": 2.0}')
        self.assertFalse(datos["listo_para_cotizar"])
        self.assertIn("material", datos["faltantes"])
        self.assertIn("cantidad", datos["faltantes"])
        self.assertNotIn("tipo_resorte", datos["faltantes"])

    def test_interpretar_devuelve_dict_serializable(self):
        import json
        datos = ext.interpretar('{"tipo_resorte": "extension", "material": "inox",'
                                ' "diametro_alambre_mm": 1.0, "cantidad": 100}')
        # Debe ser serializable y contener las claves de control
        json.dumps(datos)
        self.assertIn("listo_para_cotizar", datos)
        self.assertIn("faltantes", datos)
        self.assertTrue(datos["listo_para_cotizar"])


if __name__ == "__main__":
    unittest.main()
