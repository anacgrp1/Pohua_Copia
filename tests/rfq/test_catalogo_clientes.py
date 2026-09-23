# -*- coding: utf-8 -*-
"""Un solo catálogo de clientes, no dos.

Por qué existe
--------------
Había dos, y ninguno lo sabía. La tabla ``clientes`` —razón social, términos
de pago, RFC— y una copia recortada dentro del documento de la calculadora
(``dbs.customers``), que se llenaba a mano o copiando del primero cuando
alguien tropezaba con el hueco.

Dos copias de lo mismo divergen SIEMPRE: la segunda sólo se actualiza si
alguien pasa por el sitio exacto que la actualiza. Lo que se veía era un
cliente que Pohua conocía perfectamente apareciendo sin resolver en la hoja,
con "Customer" en blanco — y sin cliente una cotización no se puede ni numerar
ni aprobar.

Ahora la tabla manda y ``dbs.customers`` es una proyección suya, armada al
servir. Estas pruebas fijan las dos direcciones y, sobre todo, los casos en
los que NO hay que pisar nada: dejar la hoja sin catálogo es peor que dejarla
con uno viejo.

Se usa sqlite en memoria imitando el contrato de psycopg2 (cursor/execute/
fetchall) en vez de hablar con Neon: lo que se prueba es la lógica, y la
base de producción no es un banco de pruebas.
"""

import sqlite3

import pytest

import app.clients.catalogo_hoja as catalogo


class Conexion:
    """Lo justo de la interfaz de psycopg2 que usa el módulo."""

    def __init__(self, filas=(), rota=False):
        self.rota = rota
        self.db = sqlite3.connect(":memory:")
        self.db.execute("""CREATE TABLE clientes (
            cliente_id TEXT PRIMARY KEY, razon_social TEXT,
            payment_terms TEXT, origen_datos TEXT,
            estatus TEXT NOT NULL DEFAULT 'Activo')""")
        for fila in filas:
            self.db.execute(
                "INSERT INTO clientes (cliente_id, razon_social, payment_terms,"
                " estatus) VALUES (?,?,?,?)", fila)
        self.db.commit()

    def cursor(self):
        if self.rota:
            raise RuntimeError("la base no contesta")
        return _Cursor(self.db)

    def clientes(self):
        return self.db.execute(
            "SELECT cliente_id, razon_social, payment_terms, origen_datos"
            " FROM clientes ORDER BY cliente_id").fetchall()


class _Cursor:
    def __init__(self, db):
        self.db = db
        self.cur = db.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        # El módulo escribe SQL de Postgres; aquí sólo hay que traducir el
        # marcador de parámetro y el ON CONFLICT.
        sql = sql.replace("%s", "?").replace("ON CONFLICT (cliente_id) DO NOTHING",
                                             "")
        if sql.strip().upper().startswith("INSERT"):
            sql = sql.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)
        self.cur.execute(sql, params)
        return self

    def fetchall(self):
        return self.cur.fetchall()


TRES = [("CGRMX", "CGR Mexico", "Net 30", "Activo"),
        ("ACME", "Acme Springs", "Net 60", "Activo"),
        ("VIEJO", "Cliente Viejo", "Net 30", "Inactivo")]


class TestLaTablaManda:

    def test_la_hoja_recibe_los_clientes_de_la_tabla(self):
        doc = {"dbs": {"customers": []}}
        assert catalogo.aplicar(doc, Conexion(TRES)) is True
        codigos = [c["code"] for c in doc["dbs"]["customers"]]
        assert codigos == ["ACME", "CGRMX"]          # ordenados, sin el inactivo

    def test_con_la_forma_exacta_que_espera_la_hoja(self):
        # `fillCustomers()` del núcleo lee estas tres claves. Si cambian, la
        # hoja se queda sin catálogo sin decir nada.
        doc = {"dbs": {}}
        catalogo.aplicar(doc, Conexion(TRES))
        for c in doc["dbs"]["customers"]:
            assert set(c) == {"code", "name", "terms"}

    def test_los_términos_de_pago_viajan(self):
        doc = {"dbs": {}}
        catalogo.aplicar(doc, Conexion(TRES))
        acme = next(c for c in doc["dbs"]["customers"] if c["code"] == "ACME")
        assert acme["terms"] == "Net 60"

    def test_pisa_la_copia_vieja_del_blob(self):
        # Este es el fallo entero, en una prueba: el blob dice una cosa, la
        # tabla otra, y la que se ve tiene que ser la de la tabla.
        doc = {"dbs": {"customers": [{"code": "VIEJO", "name": "Lo de antes",
                                      "terms": "Net 15"}]}}
        catalogo.aplicar(doc, Conexion(TRES))
        assert [c["code"] for c in doc["dbs"]["customers"]] == ["ACME", "CGRMX"]

    def test_un_cliente_sin_términos_recibe_los_de_siempre(self):
        doc = {"dbs": {}}
        catalogo.aplicar(doc, Conexion([("X", "Equis", None, "Activo")]))
        assert doc["dbs"]["customers"][0]["terms"] == "Net 30"


class TestCuandoNoHayQuePisarNada:
    """Quedarse sin catálogo es peor que tener uno viejo."""

    def test_si_la_base_no_contesta_se_deja_lo_que_había(self):
        antes = [{"code": "CGRMX", "name": "CGR Mexico", "terms": "Net 30"}]
        doc = {"dbs": {"customers": list(antes)}}
        assert catalogo.aplicar(doc, Conexion(rota=True)) is False
        assert doc["dbs"]["customers"] == antes

    def test_si_la_tabla_está_vacía_y_la_hoja_no_se_deja_la_hoja(self):
        # El primer día, antes de registrar ningún dominio. Vaciar la hoja
        # dejaría sin poder cotizar a quien ya tenía sus clientes puestos.
        antes = [{"code": "CGRMX", "name": "CGR Mexico", "terms": "Net 30"}]
        doc = {"dbs": {"customers": list(antes)}}
        assert catalogo.aplicar(doc, Conexion([])) is False
        assert doc["dbs"]["customers"] == antes

    def test_un_documento_que_no_es_un_objeto_no_revienta(self):
        assert catalogo.aplicar(None, Conexion(TRES)) is False
        assert catalogo.aplicar([1, 2, 3], Conexion(TRES)) is False

    def test_un_documento_sin_dbs_se_le_pone(self):
        doc = {}
        assert catalogo.aplicar(doc, Conexion(TRES)) is True
        assert len(doc["dbs"]["customers"]) == 2


class TestElOtroSentido:

    def test_un_cliente_nuevo_de_la_hoja_sube_a_la_tabla(self):
        conn = Conexion(TRES)
        doc = {"dbs": {"customers": [
            {"code": "CGRMX", "name": "CGR Mexico", "terms": "Net 30"},
            {"code": "NUEVO", "name": "Resortes Nuevos", "terms": "Net 45"}]}}
        assert catalogo.recoger(doc, conn) == 1
        fila = [c for c in conn.clientes() if c[0] == "NUEVO"][0]
        assert fila[1] == "Resortes Nuevos"
        assert fila[2] == "Net 45"
        # Queda marcado de dónde salió: no es lo mismo un cliente verificado
        # que uno tecleado a vuelapluma en la hoja.
        assert fila[3] == "calculadora"

    def test_los_que_ya_están_no_se_duplican(self):
        conn = Conexion(TRES)
        doc = {"dbs": {"customers": [{"code": "CGRMX", "name": "Otro nombre",
                                      "terms": "Net 90"}]}}
        assert catalogo.recoger(doc, conn) == 0
        # Y no se pisan: la tabla es la buena, la hoja no la corrige.
        assert [c for c in conn.clientes() if c[0] == "CGRMX"][0][1] == "CGR Mexico"

    def test_sin_clientes_en_la_hoja_no_hace_nada(self):
        assert catalogo.recoger({"dbs": {"customers": []}}, Conexion(TRES)) == 0
        assert catalogo.recoger({}, Conexion(TRES)) == 0

    def test_la_basura_se_ignora_sin_romper_el_guardado(self):
        conn = Conexion(TRES)
        doc = {"dbs": {"customers": ["texto suelto", None, {"name": "sin código"},
                                     {"code": "   "}]}}
        assert catalogo.recoger(doc, conn) == 0

    def test_si_la_base_falla_el_guardado_no_se_cae(self):
        # Perder un alta es malo; perder el guardado entero de la calculadora
        # es mucho peor.
        doc = {"dbs": {"customers": [{"code": "NUEVO", "name": "X"}]}}
        assert catalogo.recoger(doc, Conexion(rota=True)) == 0


class TestElCodigo:

    def test_se_usa_el_cliente_id_de_pohua(self):
        # Para que el RFQ y la hoja nombren al cliente igual.
        assert catalogo._codigo("CGRMX", "CGR Mexico") == "CGRMX"

    def test_sin_cliente_id_se_apaña_con_la_razón_social(self):
        assert catalogo._codigo("", "Resortes del Bajío, S.A.") == "RESORTES"

    def test_sin_nada_no_devuelve_vacío(self):
        # Un código vacío rompería `codigoDeCliente()` en la hoja.
        assert catalogo._codigo("", "") == "CLIENTE"
