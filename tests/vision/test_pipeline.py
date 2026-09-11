"""Pruebas de src/pipeline.py (Subtarea 1). No llama a la API de Claude."""
import unittest

import app.vision.pipeline as vp

PNG = b"\x89PNG\r\n\x1a\n" + b"datos de imagen"
PDF = b"%PDF-1.7" + b" datos de pdf"
STEP = b"ISO-10303-21;\nHEADER;\n"


class TestDetectarTipo(unittest.TestCase):
    def test_por_extension(self):
        self.assertEqual(vp.detectar_tipo("plano.png", b""), "imagen")
        self.assertEqual(vp.detectar_tipo("ficha.PDF", b""), "documento")
        self.assertEqual(vp.detectar_tipo("modelo.stp", b""), "cad")
        self.assertEqual(vp.detectar_tipo("modelo.step", b""), "cad")

    def test_por_magic_bytes_sin_nombre(self):
        self.assertEqual(vp.detectar_tipo("", PNG), "imagen")
        self.assertEqual(vp.detectar_tipo("", PDF), "documento")
        self.assertEqual(vp.detectar_tipo("", STEP), "cad")

    def test_formato_no_soportado(self):
        with self.assertRaises(vp.FormatoNoSoportado):
            vp.detectar_tipo("notas.txt", b"texto plano")


class TestConstruirContenido(unittest.TestCase):
    def test_png_y_pdf(self):
        archivos = [
            {"nombre": "p.png", "contenido": PNG},
            {"nombre": "f.pdf", "contenido": PDF},
        ]
        bloques, omitidos = vp.construir_contenido(archivos)
        tipos = [b["type"] for b in bloques]
        self.assertEqual(tipos, ["image", "document", "text"])
        self.assertEqual(omitidos, [])
        # El último bloque es el prompt técnico
        self.assertEqual(bloques[-1]["text"], vp.PROMPT_TECNICO)

    def test_step_se_omite_como_stub(self):
        archivos = [
            {"nombre": "p.png", "contenido": PNG},
            {"nombre": "m.step", "contenido": STEP},
        ]
        bloques, omitidos = vp.construir_contenido(archivos)
        self.assertEqual([b["type"] for b in bloques], ["image", "text"])
        self.assertEqual(len(omitidos), 1)
        self.assertEqual(omitidos[0][0], "m.step")

    def test_solo_step_lanza_error(self):
        with self.assertRaises(vp.FormatoNoSoportado):
            vp.construir_contenido([{"nombre": "m.step", "contenido": STEP}])

    def test_bloque_imagen_es_base64(self):
        import base64
        bloques, _ = vp.construir_contenido([{"nombre": "p.png", "contenido": PNG}])
        img = bloques[0]
        self.assertEqual(img["source"]["media_type"], "image/png")
        # El dato debe decodificar de vuelta al contenido original
        self.assertEqual(base64.standard_b64decode(img["source"]["data"]), PNG)


class TestPromptTecnico(unittest.TestCase):
    def test_menciona_los_tres_tipos(self):
        p = vp.PROMPT_TECNICO.lower()
        self.assertIn("compresion", p)
        self.assertIn("torsion", p)
        self.assertIn("extension", p)

    def test_pide_json(self):
        self.assertIn("JSON", vp.PROMPT_TECNICO)


if __name__ == "__main__":
    unittest.main()
