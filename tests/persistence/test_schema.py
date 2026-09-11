"""Verificación del esquema: sustituye al DDL embebido en los módulos.

El punto de estos tests es que la ausencia de una tabla falle **fuerte y
claro**, en vez de que el módulo la cree en silencio con la forma anterior a
la migración 004.
"""
import os
import unittest
from unittest import mock

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

import app.persistence.schema as schema


class FakeCursor:
    def __init__(self, presentes):
        self._presentes = presentes
        self.sql = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params

    def fetchall(self):
        pedidas = (self.params or [[]])[0]
        return [(t,) for t in pedidas if t in self._presentes]


class FakeConn:
    def __init__(self, presentes):
        self._cursor = FakeCursor(presentes)
        self.cerrada = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.cerrada = True


class TestVerificarTablas(unittest.TestCase):

    def test_todas_presentes_no_lanza(self):
        conn = FakeConn({"clientes", "cliente_dominios"})
        schema.verificar_tablas(("clientes", "cliente_dominios"), conexion=conn)

    def test_tabla_ausente_lanza_con_nombre_y_remedio(self):
        conn = FakeConn({"clientes"})
        with self.assertRaises(schema.EsquemaIncompletoError) as ctx:
            schema.verificar_tablas(("clientes", "cliente_dominios"), conexion=conn)

        mensaje = str(ctx.exception)
        self.assertIn("cliente_dominios", mensaje)
        self.assertNotIn("clientes,", mensaje)   # la que sí está no se reporta
        self.assertIn("make db-up", mensaje)     # dice qué correr

    def test_base_vacia_reporta_todas(self):
        conn = FakeConn(set())
        with self.assertRaises(schema.EsquemaIncompletoError) as ctx:
            schema.verificar_tablas(("rfqs", "rfq_historial"), conexion=conn)

        self.assertIn("rfqs", str(ctx.exception))
        self.assertIn("rfq_historial", str(ctx.exception))

    def test_lista_vacia_no_consulta(self):
        conn = FakeConn(set())
        self.assertEqual(schema.tablas_faltantes((), conexion=conn), [])
        self.assertIsNone(conn._cursor.sql)

    def test_conexion_inyectada_no_se_cierra(self):
        conn = FakeConn({"rfqs"})
        schema.verificar_tablas(("rfqs",), conexion=conn)
        self.assertFalse(conn.cerrada)


class TestModulosYaNoCreanTablas(unittest.TestCase):
    """Los cinco módulos delegan en schema en vez de ejecutar DDL."""

    CASOS = [
        ("app.persistence.duplicates", "inicializar_bd", ("correos_procesados",)),
        ("app.rfq.thread_validator", "inicializar_historial", ("rfq_historial",)),
        ("app.persistence.spring_repository", "inicializar_bd", ("resortes_cotizacion",)),
        ("app.rfq.repository", "inicializar_bd", ("rfqs",)),
        ("app.clients.mapper", "inicializar_bd", ("clientes", "cliente_dominios")),
    ]

    def test_cada_modulo_verifica_sus_tablas(self):
        import importlib

        for nombre_modulo, nombre_funcion, tablas in self.CASOS:
            with self.subTest(modulo=nombre_modulo):
                modulo = importlib.import_module(nombre_modulo)
                with mock.patch.object(schema, "verificar_tablas") as verificar:
                    getattr(modulo, nombre_funcion)()
                verificar.assert_called_once_with(tablas)


if __name__ == "__main__":
    unittest.main()
