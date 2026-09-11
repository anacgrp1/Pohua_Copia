
import unittest

from app.shared.field_validator import CAMPOS_SOLO_CORREO, validar_campos_rfq


def _rfq_completo() -> dict:
    """Devuelve un dict con todos los campos obligatorios presentes y válidos."""
    return {
        "tiene_adjunto": True,
        "customer": "Industrias Norteña S.A. de C.V.",
        "volumen": 2500,
        "part_number": "RC-12.5-45-316L",
        "material": "Acero inoxidable 316L",
    }


class TestValidarCamposRfq(unittest.TestCase):

    def test_dict_completo(self):
        """Todos los campos presentes → válido y sin faltantes."""
        resultado = validar_campos_rfq(_rfq_completo())
        self.assertTrue(resultado["es_valido"])
        self.assertEqual(resultado["campos_faltantes"], [])

    def test_sin_adjunto(self):
        """tiene_adjunto = False → inválido, adjunto en la lista."""
        data = _rfq_completo()
        data["tiene_adjunto"] = False
        resultado = validar_campos_rfq(data)
        self.assertFalse(resultado["es_valido"])
        self.assertIn("tiene_adjunto", resultado["campos_faltantes"])

    def test_sin_customer(self):
        """customer ausente → inválido, customer en la lista."""
        data = _rfq_completo()
        del data["customer"]
        resultado = validar_campos_rfq(data)
        self.assertFalse(resultado["es_valido"])
        self.assertIn("customer", resultado["campos_faltantes"])

    def test_sin_volumen(self):
        """volumen ausente → inválido, volumen en la lista."""
        data = _rfq_completo()
        del data["volumen"]
        resultado = validar_campos_rfq(data)
        self.assertFalse(resultado["es_valido"])
        self.assertIn("volumen", resultado["campos_faltantes"])

    def test_sin_part_number(self):
        """part_number ausente → inválido, part_number en la lista."""
        data = _rfq_completo()
        del data["part_number"]
        resultado = validar_campos_rfq(data)
        self.assertFalse(resultado["es_valido"])
        self.assertIn("part_number", resultado["campos_faltantes"])

    def test_sin_material(self):
        """material ausente → inválido, material en la lista."""
        data = _rfq_completo()
        del data["material"]
        resultado = validar_campos_rfq(data)
        self.assertFalse(resultado["es_valido"])
        self.assertIn("material", resultado["campos_faltantes"])

    def test_varios_campos_faltantes(self):
        """Varias ausencias a la vez → todas aparecen en campos_faltantes."""
        data = {"tiene_adjunto": False, "volumen": None}
        # Faltan: tiene_adjunto (no es True), customer (no existe),
        # volumen (None), part_number (no existe), material (no existe).
        resultado = validar_campos_rfq(data)
        self.assertFalse(resultado["es_valido"])
        for campo in ("tiene_adjunto", "customer", "volumen", "part_number", "material"):
            self.assertIn(campo, resultado["campos_faltantes"])

    def test_campos_presentes_pero_vacios(self):
        """Cadenas vacías y None se tratan como ausentes."""
        data = {
            "tiene_adjunto": True,
            "customer": "",
            "volumen": "",
            "part_number": None,
            "material": "",
        }
        resultado = validar_campos_rfq(data)
        self.assertFalse(resultado["es_valido"])
        self.assertIn("customer", resultado["campos_faltantes"])
        self.assertIn("volumen", resultado["campos_faltantes"])
        self.assertIn("part_number", resultado["campos_faltantes"])
        self.assertIn("material", resultado["campos_faltantes"])
        self.assertNotIn("tiene_adjunto", resultado["campos_faltantes"])

    # ------------------------------------------------------------------ #
    # Validación por subconjunto (campos_requeridos)
    # ------------------------------------------------------------------ #
    def test_validacion_temprana_solo_correo_valida(self):
        """Con CAMPOS_SOLO_CORREO no exige part_number ni material."""
        data = {
            "tiene_adjunto": True,
            "customer": "ACME",
            "volumen": 1000,
            # sin part_number ni material: aún no se leyó el dibujo
        }
        resultado = validar_campos_rfq(data, campos_requeridos=CAMPOS_SOLO_CORREO)
        self.assertTrue(resultado["es_valido"])
        self.assertEqual(resultado["campos_faltantes"], [])

    def test_validacion_temprana_detecta_faltante_de_correo(self):
        """La validación temprana sí frena si falta un dato de sólo-correo."""
        data = {"tiene_adjunto": True, "customer": "", "volumen": 1000}
        resultado = validar_campos_rfq(data, campos_requeridos=CAMPOS_SOLO_CORREO)
        self.assertFalse(resultado["es_valido"])
        self.assertIn("customer", resultado["campos_faltantes"])


if __name__ == "__main__":
    unittest.main()
