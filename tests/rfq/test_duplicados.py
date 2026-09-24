"""El control de duplicados mira en dos sitios y con todas las claves.

Un pedido que ya tenía dictamen se volvió a cotizar como RFQ nuevo: el correo
seguía sin leer en Outlook y la única comprobación —``correos_procesados`` por
Message-ID, apuntado DESPUÉS de procesar— no lo encontró. Estas pruebas fijan
las tres defensas: se buscan todas las claves, se mira también ``rfqs`` y se
apunta cada clave.
"""
import unittest
from contextlib import contextmanager
from unittest import mock

import app.persistence.duplicates as duplicates


class CursorFalso:
    def __init__(self, resultado=(0,), fila=(1,)):
        self.ejecutados = []
        self._resultado = resultado
        self._fila = fila

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.ejecutados.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self._resultado if "SELECT" in self.ejecutados[-1][0] else self._fila


def _conexion(cursor):
    @contextmanager
    def fabrica():
        conn = mock.MagicMock()
        conn.cursor.return_value = cursor
        yield conn
    return fabrica


class TestEsDuplicado(unittest.TestCase):

    def test_busca_todas_las_claves_en_procesados_y_en_rfqs(self):
        cur = CursorFalso(resultado=(1,))
        with mock.patch.object(duplicates, "conexion_bd", _conexion(cur)):
            self.assertTrue(duplicates.es_duplicado("<m@x>", otras_claves=["ENTRY"]))
        sql, params = cur.ejecutados[0]
        self.assertIn("correos_procesados", sql)
        self.assertIn("rfqs", sql)
        self.assertEqual(params["c"], ["<m@x>", "ENTRY"])

    def test_sin_coincidencias_es_nuevo(self):
        cur = CursorFalso(resultado=(0,))
        with mock.patch.object(duplicates, "conexion_bd", _conexion(cur)):
            self.assertFalse(duplicates.es_duplicado("<m@x>", otras_claves=[""]))
        self.assertEqual(cur.ejecutados[0][1]["c"], ["<m@x>"])

    def test_sin_claves_no_consulta(self):
        with mock.patch.object(duplicates, "conexion_bd") as conexion:
            self.assertFalse(duplicates.es_duplicado("", otras_claves=[None]))
        conexion.assert_not_called()


class TestRegistrar(unittest.TestCase):

    def test_el_entry_id_va_en_la_misma_fila(self):
        """Un correo, UNA fila: la pantalla Mail cuenta filas como correos."""
        cur = CursorFalso(fila=(7,))
        correo = {"message_id": "<m@x>", "remitente": "a@b", "asunto": "RFQ", "fecha": ""}
        with mock.patch.object(duplicates, "conexion_bd", _conexion(cur)):
            self.assertTrue(duplicates.registrar_correo(correo, otras_claves=["ENTRY", "<m@x>"]))
        self.assertEqual(len(cur.ejecutados), 1)
        sql, params = cur.ejecutados[0]
        self.assertIn("entry_id", sql)
        self.assertEqual((params[0], params[4]), ("<m@x>", "ENTRY"))

    def test_busca_tambien_por_entry_id(self):
        cur = CursorFalso(resultado=(1,))
        with mock.patch.object(duplicates, "conexion_bd", _conexion(cur)):
            self.assertTrue(duplicates.es_duplicado("<m@x>", otras_claves=["ENTRY"]))
        self.assertIn("entry_id = ANY", cur.ejecutados[0][0])

    def test_olvidar_quita_todas_las_claves(self):
        cur = CursorFalso()
        with mock.patch.object(duplicates, "conexion_bd", _conexion(cur)):
            duplicates.olvidar_correo("<m@x>", otras_claves=["ENTRY"])
        sql, params = cur.ejecutados[0]
        self.assertTrue(sql.startswith("DELETE FROM correos_procesados"))
        self.assertIn("entry_id = ANY", sql)
        self.assertEqual(params, {"c": ["<m@x>", "ENTRY"]})


if __name__ == "__main__":
    unittest.main()
