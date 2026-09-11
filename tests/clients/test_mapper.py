import os
import unittest

# config valida credenciales al importarse; valores dummy ANTES del import.
os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

from app.clients.mapper import (
    buscar_cliente_por_dominio,
    extraer_dominio,
    mapear_cliente,
)

# --------------------------------------------------------------------------- #
# Dobles de prueba para psycopg2 (sin BD real)
# --------------------------------------------------------------------------- #

class FakeCursor:
    def __init__(self, fila):
        self._fila = fila
        self.sql = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params

    def fetchone(self):
        return self._fila


class FakeConn:
    """Conexión falsa que devuelve una fila predeterminada."""

    def __init__(self, fila):
        self._fila = fila
        self.cursor_usado = None

    def cursor(self):
        self.cursor_usado = FakeCursor(self._fila)
        return self.cursor_usado

    def close(self):
        pass


# Fila del JOIN cliente_dominios → clientes, en el orden que devuelve la query:
# 0: cd.dominio        1: c.cliente_id      2: c.razon_social   3: c.rfc
# 4: c.correo_principal 5: c.payment_terms  6: c.estatus
_FILA_CLIENTE = ("industriasnortena.com.mx", "CLI-001", "Industrias Norteña",
                 "RFC-123", "compras@industriasnortena.com.mx", "Net 30", "Activo")


class TestExtraerDominio(unittest.TestCase):

    def test_con_nombre_y_direccion(self):
        self.assertEqual(
            extraer_dominio("Roberto Méndez <rmendez@industriasnortena.com.mx>"),
            "industriasnortena.com.mx",
        )

    def test_direccion_simple(self):
        self.assertEqual(
            extraer_dominio("rmendez@Industrias.COM"), "industrias.com"
        )

    def test_sin_arroba_devuelve_none(self):
        self.assertIsNone(extraer_dominio("texto sin correo"))

    def test_vacio_o_none(self):
        self.assertIsNone(extraer_dominio(""))
        self.assertIsNone(extraer_dominio(None))

    def test_dominio_sin_punto_invalido(self):
        self.assertIsNone(extraer_dominio("user@localhost"))


class TestBuscarClientePorDominio(unittest.TestCase):

    def test_cliente_encontrado(self):
        conn = FakeConn(_FILA_CLIENTE)
        cliente = buscar_cliente_por_dominio(
            "industriasnortena.com.mx", conexion=conn
        )
        self.assertIsNotNone(cliente)
        self.assertEqual(cliente["cliente_id"], "CLI-001")
        self.assertEqual(cliente["razon_social"], "Industrias Norteña")
        self.assertEqual(cliente["dominio"], "industriasnortena.com.mx")
        self.assertEqual(cliente["rfc"], "RFC-123")
        self.assertEqual(cliente["correo_principal"],
                         "compras@industriasnortena.com.mx")
        self.assertEqual(cliente["payment_terms"], "Net 30")
        self.assertEqual(cliente["estatus"], "Activo")

    def test_query_usa_dominio_en_minusculas(self):
        conn = FakeConn(_FILA_CLIENTE)
        buscar_cliente_por_dominio("Industrias.COM", conexion=conn)
        # El parámetro pasado a la query debe ir en minúsculas.
        self.assertEqual(conn.cursor_usado.params, ("industrias.com",))

    def test_cliente_no_encontrado(self):
        conn = FakeConn(None)  # la query no devuelve fila
        self.assertIsNone(
            buscar_cliente_por_dominio("desconocido.com", conexion=conn)
        )

    def test_dominio_none_devuelve_none(self):
        # No debe siquiera tocar la BD.
        self.assertIsNone(buscar_cliente_por_dominio(None, conexion=FakeConn(None)))


class TestMapearCliente(unittest.TestCase):

    def test_remitente_completo_mapea(self):
        conn = FakeConn(_FILA_CLIENTE)
        cliente = mapear_cliente(
            "Roberto <rmendez@industriasnortena.com.mx>", conexion=conn
        )
        self.assertIsNotNone(cliente)
        self.assertEqual(cliente["cliente_id"], "CLI-001")

    def test_remitente_sin_dominio_no_mapea(self):
        # No hay dominio válido → None sin tocar la BD.
        self.assertIsNone(mapear_cliente("basura", conexion=FakeConn(_FILA_CLIENTE)))

    def test_dominio_valido_pero_sin_cliente(self):
        conn = FakeConn(None)
        self.assertIsNone(
            mapear_cliente("x@empresa-nueva.com", conexion=conn)
        )


if __name__ == "__main__":
    unittest.main()
