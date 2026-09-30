"""Lectura del catálogo de costeo.

Lo que de verdad se protege aquí: que cuando falte un dato en la base, el
módulo lo DIGA en vez de rellenarlo con una constante. Antes el adaptador
sustituía silenciosamente el precio del alambre por 2.50 USD/lb.
"""

import os
import unittest

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

from datetime import date  # noqa: E402

from pricing import repository  # noqa: E402


class FakeCursor:
    """Cursor falso: entrega los resultados en el orden en que se piden."""

    def __init__(self, resultados):
        self._resultados = list(resultados)
        self.ejecutados = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.ejecutados.append((sql, params))

    def fetchone(self):
        return self._resultados.pop(0) if self._resultados else None

    def fetchall(self):
        return self._resultados.pop(0) if self._resultados else []


class FakeConn:
    def __init__(self, resultados):
        self.cursor_obj = FakeCursor(resultados)

    def cursor(self):
        return self.cursor_obj

    def close(self):
        pass


# Fila de maquinas tal y como la devuelve _SQL_MAQUINA:
# id, codigo, nombre, familia, horas_setup, pph, horas_labor, multiplicador,
# costo_hora, ccv_objetivo_h
_MAQUINA = (7, "NUCO2", "NUCOIL CSF-200", "COILER", 6.0, 327, 40.0, 1.0, 14.881, 44.643)

# Fila de materiales: id, codigo, nombre, lleva_surcharge, precio_lb,
# diam_pulg, fecha_cotizado
_MATERIAL = (3, "MW", "Music Wire", False, 2.55, 0.0625, date(2026, 7, 1))
_MATERIAL_SIN_PRECIO = (3, "MW", "Music Wire", False, None, None, None)

# Fila de empaques: codigo, descripcion, precio, piezas_por_caja
_EMPAQUE = ("COR100803", "10 X 8 X 3 BOX", 0.63, 1000)


class TestParametros(unittest.TestCase):

    def test_gana_el_juego_mas_reciente(self):
        """La consulta viene ordenada por vigente_desde DESC; al escribir en
        orden inverso, el más reciente sobrescribe al viejo."""
        conn = FakeConn([[("matMk", 8), ("matMk", 6)]])  # [0] reciente, [1] viejo
        self.assertEqual(repository.parametros_vigentes(conexion=conn)["matMk"], 8)

    def test_sin_juego_vigente_devuelve_vacio(self):
        self.assertEqual(repository.parametros_vigentes(conexion=FakeConn([[]])), {})


class TestMaquina(unittest.TestCase):

    def test_devuelve_la_maquina_con_su_tarifa(self):
        maquina = repository.elegir_maquina("compresion", 1.6, 12.0,
                                            conexion=FakeConn([_MAQUINA]))
        self.assertEqual(maquina["nombre"], "NUCOIL CSF-200")
        self.assertEqual(maquina["horas_setup"], 6.0)
        self.assertEqual(maquina["costo_hora"], 14.881)

    def test_sin_maquina_capaz_devuelve_none(self):
        self.assertIsNone(repository.elegir_maquina("torsion", 9.9,
                                                    conexion=FakeConn([None])))

    def test_el_tipo_elige_la_columna_de_capacidad(self):
        for tipo, columna in [("compresion", "hace_compresion"),
                              ("extension", "hace_extension"),
                              ("torsion", "hace_torsion")]:
            with self.subTest(tipo=tipo):
                conn = FakeConn([_MAQUINA])
                repository.elegir_maquina(tipo, 1.6, conexion=conn)
                sql = conn.cursor_obj.ejecutados[0][0]
                self.assertIn(f"c.{columna}", sql)

    def test_un_rango_de_alambre_sin_capturar_no_hace_capaz_a_una_maquina(self):
        # INT-9084602A: 15.875 mm. Ninguna bobinadora real lo admite, y una
        # fila sin capacidades ganaba por "no se sabe". Ya no.
        conn = FakeConn([None])
        self.assertIsNone(repository.elegir_maquina("compresion", 15.875, 127.0,
                                                    conexion=conn))
        sql = conn.cursor_obj.ejecutados[0][0]
        self.assertIn("c.alambre_min_mm IS NOT NULL", sql)
        self.assertIn("c.alambre_max_mm IS NOT NULL", sql)
        self.assertNotIn("c.alambre_max_mm IS NULL OR", sql)

    def test_un_tipo_desconocido_no_revienta(self):
        conn = FakeConn([_MAQUINA])
        maquina = repository.elegir_maquina("lo-que-sea", 1.6, conexion=conn)
        self.assertIsNotNone(maquina)
        self.assertIn("c.hace_compresion", conn.cursor_obj.ejecutados[0][0])


class TestMaterial(unittest.TestCase):

    def test_devuelve_precio_y_fecha(self):
        material = repository.precio_material("MW", 0.063,
                                              conexion=FakeConn([_MATERIAL]))
        self.assertEqual(material["precio_lb"], 2.55)
        self.assertEqual(material["fecha_cotizado"], "2026-07-01")
        self.assertEqual(material["surcharge_lb"], 0.0)

    def test_material_inexistente(self):
        self.assertIsNone(repository.precio_material("XXX", 0.063,
                                                     conexion=FakeConn([None])))

    def test_material_sin_precio_devuelve_precio_none(self):
        """Existe en el catálogo pero nadie capturó su precio: no se inventa."""
        material = repository.precio_material("MW", 0.063,
                                              conexion=FakeConn([_MATERIAL_SIN_PRECIO]))
        self.assertIsNotNone(material)
        self.assertIsNone(material["precio_lb"])

    def test_inoxidable_suma_el_surcharge_vigente(self):
        inox = (5, "SS", "Stainless 302/304", True, 4.10, 0.0625, date(2026, 7, 1))
        material = repository.precio_material("SS", 0.063,
                                              conexion=FakeConn([inox, (1.25,)]))
        self.assertEqual(material["surcharge_lb"], 1.25)

    def test_codigo_vacio_no_consulta(self):
        self.assertIsNone(repository.precio_material("", 0.063, conexion=FakeConn([])))


class TestCargarCatalogo(unittest.TestCase):
    """El contrato importante: qué se reporta como faltante."""

    def _conn(self, params=None, maquina=_MAQUINA, material=_MATERIAL,
              empaque=_EMPAQUE):
        return FakeConn([params if params is not None else [("matMk", 6)],
                         maquina, material, empaque])

    def test_catalogo_completo(self):
        cat = repository.cargar_catalogo("compresion", "MW", 1.6, 12.0,
                                         conexion=self._conn())
        self.assertTrue(cat.completo, cat.faltantes)
        self.assertEqual(cat.faltantes, [])
        self.assertIn("NUCOIL CSF-200", cat.origen["maquina"])
        self.assertIn("2.55", cat.origen["material"])

    def test_sin_precio_de_material_lo_reporta(self):
        cat = repository.cargar_catalogo("compresion", "MW", 1.6, 12.0,
                                         conexion=self._conn(material=_MATERIAL_SIN_PRECIO))
        self.assertFalse(cat.completo)
        self.assertTrue(any("no tiene precio" in f for f in cat.faltantes), cat.faltantes)

    def test_sin_maquina_lo_reporta(self):
        cat = repository.cargar_catalogo("torsion", "MW", 1.6, 12.0,
                                         conexion=self._conn(maquina=None))
        self.assertFalse(cat.completo)
        self.assertTrue(any("Ninguna máquina" in f for f in cat.faltantes), cat.faltantes)

    def test_sin_parametros_vigentes_lo_reporta(self):
        cat = repository.cargar_catalogo("compresion", "MW", 1.6, 12.0,
                                         conexion=self._conn(params=[]))
        self.assertFalse(cat.completo)
        self.assertTrue(any("param_juegos" in f for f in cat.faltantes), cat.faltantes)

    def test_sin_material_indicado_lo_reporta(self):
        conn = FakeConn([[("matMk", 6)], _MAQUINA, _EMPAQUE])
        cat = repository.cargar_catalogo("compresion", None, 1.6, 12.0, conexion=conn)
        self.assertFalse(cat.completo)
        self.assertTrue(any("No se indicó material" in f for f in cat.faltantes), cat.faltantes)

    def test_sin_diametro_lo_reporta(self):
        cat = repository.cargar_catalogo("compresion", "MW", None, None,
                                         conexion=self._conn())
        self.assertFalse(cat.completo)
        self.assertTrue(any("diámetro de alambre" in f for f in cat.faltantes), cat.faltantes)

    def test_un_error_de_base_no_tumba_la_carga(self):
        """Si la consulta revienta se anota como faltante y se sigue: la ruta
        HTTP debe poder decir qué pasó, no devolver un 500 opaco."""
        class ConnQueTruena:
            def cursor(self):
                raise RuntimeError("la base se cayó")
            def close(self):
                pass

        cat = repository.cargar_catalogo("compresion", "MW", 1.6, 12.0,
                                         conexion=ConnQueTruena())
        self.assertFalse(cat.completo)
        self.assertTrue(cat.faltantes)


if __name__ == "__main__":
    unittest.main()
