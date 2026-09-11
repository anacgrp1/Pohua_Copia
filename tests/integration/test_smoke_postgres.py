"""Test de humo del DDL contra un PostgreSQL real.

A diferencia del resto de la suite (que usa conexiones falsas), este test
**ejecuta `sql/schema.sql` de verdad** contra un PostgreSQL y verifica que las
tablas quedaron con las columnas esperadas. Cubre lo que los mocks no pueden:
que el DDL sea PostgreSQL válido y cargue limpio.

Se **salta solo** si no hay una base disponible (nadie sin Docker rompe la
suite). Para correrlo:

    make db-up           # levanta PostgreSQL y carga el esquema
    make db-smoke        # o: python -m unittest tests.test_smoke_postgres

Parámetros de conexión desde el entorno (mismos defaults que config.py):
    PG_HOST PG_PORT PG_DATABASE PG_USER PG_PASSWORD
"""

import os
import unittest

try:
    import psycopg2
except ImportError:  # psycopg2 no instalado
    psycopg2 = None

_SQL = os.path.join(os.path.dirname(__file__), "..", "..", "sql")
_SCHEMA = os.path.join(_SQL, "schema.sql")
_MIGRACION_PREP = os.path.join(_SQL, "migrations", "004_prep_base.sql")
_MIGRACION_EXT = os.path.join(_SQL, "migrations", "005_extension_costeo.sql")

# Muestra representativa de las 36 tablas de la extensión de costeo (paso 1).
_TABLAS_EXTENSION = {
    "cotizaciones", "cotizacion_partidas", "cotizacion_escalones", "escalon_ruta",
    "materiales", "material_precios", "aleacion_surcharges", "proveedores",
    "maquinas", "maquina_tarifas", "empaques", "subcontratistas", "param_juegos",
    "param_valores", "ordenes_compra", "usuarios", "roles", "rfq_banderas",
}

_PG = dict(
    host=os.environ.get("PG_HOST", "localhost"),
    port=int(os.environ.get("PG_PORT", "5432")),
    dbname=os.environ.get("PG_DATABASE", "cotizador"),
    user=os.environ.get("PG_USER", "postgres"),
    password=os.environ.get("PG_PASSWORD", ""),
)

# Tablas esperadas tras aplicar schema.sql + migración 004_prep_base.sql.
# Para las nuestras se verifica un subconjunto de columnas que deben existir
# (incluye las que agrega la migración del DER).
_TABLAS_ESPERADAS = {
    "clientes": {
        # base (schema.sql)
        "cliente_id", "razon_social", "rfc", "correo_principal",
        "payment_terms", "estatus", "fecha_registro",
        # migración 004 (DER / costeo)
        "codigo_legado", "condicion_pago_id", "moneda", "actualizado_en",
    },
    "cliente_dominios": {"id", "cliente_id", "dominio", "fecha_registro"},
    "rfqs": {
        # base
        "id", "rfq_id", "version", "cliente_id", "nombre_proyecto",
        "part_number", "volumen", "material", "estado", "message_id",
        "datos_json", "fecha_registro",
        # migración 004
        "resorte_id", "cantidad", "veredicto_sistema", "veredicto_final",
        "score", "notas",
    },
    # Maestro de piezas: lo crea la migración 004.
    "resortes": {
        "resorte_id", "num_parte", "tipo", "diametro_alambre_mm",
        "material", "estatus", "constante_resorte_n_mm",
    },
    # Tabla de Ana: la migración le agrega estas 2 columnas.
    "resortes_cotizacion": {"resorte_id", "modelo_version"},
    # Operativas: sólo se verifica que existan.
    "correos_procesados": None,
    "rfq_historial": None,
}

# Llaves foráneas que cierra la migración 004.
_FKS_ESPERADAS = {"fk_rfqs_resorte", "fk_resortes_cotizacion_resorte", "fk_rfqs_cliente"}


def _pg_disponible() -> bool:
    if psycopg2 is None:
        return False
    try:
        conn = psycopg2.connect(connect_timeout=3, **_PG)
        conn.close()
        return True
    except Exception:
        return False


def _aplicar_ddl(cursor) -> None:
    """Carga esquema + migraciones. Orden: base, paso 0 (DER), paso 1 (extensión).

    Los tres scripts son idempotentes, así que puede llamarlo cualquier clase
    sin depender de que otra haya corrido antes.
    """
    for ruta in (_SCHEMA, _MIGRACION_PREP, _MIGRACION_EXT):
        with open(ruta, encoding="utf-8") as fh:
            cursor.execute(fh.read())


@unittest.skipUnless(
    _pg_disponible(),
    "PostgreSQL no disponible (levántalo con 'make db-up'); test de humo omitido.",
)
class TestSmokePostgres(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conn = psycopg2.connect(**_PG)
        cls.conn.autocommit = True
        with cls.conn.cursor() as cur:
            _aplicar_ddl(cur)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def _columnas(self, tabla):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s;",
                (tabla,),
            )
            return {r[0] for r in cur.fetchall()}

    def test_todas_las_tablas_existen(self):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public';"
            )
            existentes = {r[0] for r in cur.fetchall()}
        for tabla in _TABLAS_ESPERADAS:
            self.assertIn(tabla, existentes, f"Falta la tabla {tabla}")

    def test_columnas_esperadas(self):
        for tabla, columnas in _TABLAS_ESPERADAS.items():
            if columnas is None:
                continue
            reales = self._columnas(tabla)
            faltantes = columnas - reales
            self.assertFalse(
                faltantes, f"{tabla}: faltan columnas {faltantes}"
            )

    def test_constraints_clave(self):
        # rfc UNIQUE y dominio UNIQUE deben existir.
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.table_constraints "
                "WHERE table_schema='public' AND constraint_type='UNIQUE' "
                "AND table_name IN ('clientes','cliente_dominios');"
            )
            n = cur.fetchone()[0]
        self.assertGreaterEqual(n, 2, "Faltan restricciones UNIQUE esperadas")

    def test_fks_de_la_migracion(self):
        # La migración 004 cierra 3 FKs (resortes y cliente).
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT conname FROM pg_constraint WHERE contype = 'f' "
                "AND conname = ANY(%s);",
                (list(_FKS_ESPERADAS),),
            )
            reales = {r[0] for r in cur.fetchall()}
        faltantes = _FKS_ESPERADAS - reales
        self.assertFalse(faltantes, f"Faltan llaves foráneas: {faltantes}")

    def test_extension_costeo(self):
        # El paso 1 agrega 36 tablas de costeo → el total debe ser >= 43.
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
            )
            existentes = {r[0] for r in cur.fetchall()}
        faltantes = _TABLAS_EXTENSION - existentes
        self.assertFalse(faltantes, f"Faltan tablas de la extensión: {faltantes}")
        self.assertGreaterEqual(
            len(existentes), 43,
            f"Se esperaban >= 43 tablas; hay {len(existentes)}",
        )


@unittest.skipUnless(
    _pg_disponible(),
    "PostgreSQL no disponible (levántalo con 'make db-up'); test de humo omitido.",
)
class TestVeredictoFactibilidadPostgres(unittest.TestCase):
    """COT-72 — el veredicto del sistema, escrito de verdad.

    El resto de la suite prueba ``guardar_veredicto`` con una conexión falsa:
    verifica la lógica, pero no que el SQL corra. Aquí se ejecuta contra
    PostgreSQL, que es donde se descubre si ``datos_json || '...'::jsonb``
    funciona sobre la columna real y si el CHECK de ``rfq_banderas.nivel``
    acepta los niveles que emite el motor.

    Todo ocurre dentro de una transacción que se revierte: no deja filas.
    """

    RFQ_ID = "RFQ-SMOKE-FACT"

    VEREDICTO = {
        "veredicto": "requires review",
        "score": 61,
        "banda": "Engineering review",
        "reglas_version": "0.2",
        "tipo_resorte": "compresion",
        "motivos": [
            {"codigo": "fuera_de_rango", "nivel": "crit",
             "campo": "diametro_alambre_mm", "valor": 25.0,
             "limite": "0.2–12 mm", "texto": "Diámetro de alambre fuera de rango."},
            {"codigo": "dato_ausente", "nivel": "warn",
             "campo": "longitud_libre_mm", "valor": None, "limite": None,
             "texto": "Falta longitud libre para dictaminar."},
        ],
    }

    @classmethod
    def setUpClass(cls):
        conn = psycopg2.connect(**_PG)
        conn.autocommit = True
        with conn.cursor() as cur:
            _aplicar_ddl(cur)
        conn.close()

    def setUp(self):
        self.conn = psycopg2.connect(**_PG)   # sin autocommit: se revierte al final

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def _dar_de_alta(self):
        import app.rfq.repository as repository
        return repository.guardar_rfq(
            self.RFQ_ID,
            {"cliente_id": None, "part_number": "RS-9", "volumen": 5000,
             "material": "Acero inoxidable AISI 302"},
            conexion=self.conn,
        )

    def test_veredicto_y_banderas_quedan_escritos(self):
        import app.rfq.repository as repository
        registro = self._dar_de_alta()
        resultado = repository.guardar_veredicto(
            self.RFQ_ID, self.VEREDICTO,
            version=registro["version"], conexion=self.conn)

        self.assertEqual(resultado["id"], registro["id"])
        self.assertEqual(resultado["banderas"], 2)

        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT veredicto_sistema, veredicto_final, score, notas, "
                "       datos_json->'factibilidad'->>'reglas_version' "
                "  FROM rfqs WHERE id = %s;",
                (registro["id"],),
            )
            sistema, final, score, notas, version_reglas = cur.fetchone()

        # Los valores esperados se leen del propio VEREDICTO: así una versión
        # nueva de las directrices no deja este test desfasado.
        self.assertEqual(sistema, self.VEREDICTO["veredicto"])
        self.assertIsNone(final, "veredicto_final lo escribe el PM, no el sistema")
        self.assertEqual(float(score), float(self.VEREDICTO["score"]))  # numeric(6,2)
        self.assertIn("Diámetro de alambre", notas)
        self.assertEqual(version_reglas, self.VEREDICTO["reglas_version"])

        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT nivel, titulo FROM rfq_banderas "
                " WHERE rfq_version_id = %s ORDER BY id;",
                (registro["id"],),
            )
            banderas = cur.fetchall()

        self.assertEqual([nivel for nivel, _ in banderas], ["crit", "warn"])

    def test_reevaluar_no_acumula_banderas(self):
        import app.rfq.repository as repository
        registro = self._dar_de_alta()
        for _ in range(2):
            repository.guardar_veredicto(
                self.RFQ_ID, self.VEREDICTO,
                version=registro["version"], conexion=self.conn)

        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM rfq_banderas WHERE rfq_version_id = %s;",
                (registro["id"],),
            )
            self.assertEqual(cur.fetchone()[0], 2)

    def test_dictamen_del_pm_sobre_el_veredicto_del_sistema(self):
        # El circuito completo: motor marca, PM resuelve, ambos veredictos
        # conviven y la nota del PM se anexa a los motivos del motor.
        import app.rfq.repository as repository
        registro = self._dar_de_alta()
        repository.guardar_veredicto(
            self.RFQ_ID, self.VEREDICTO,
            version=registro["version"], conexion=self.conn)

        final = repository.guardar_veredicto_final(
            self.RFQ_ID, "not feasible", version=registro["version"],
            nota="[PM: ing.lopez] fuera de capacidad",
            estado=repository.ESTADO_DECLINADO, conexion=self.conn)

        self.assertEqual(final["estado"], "Declined")
        self.assertEqual(final["datos"]["part_number"], "RS-9")

        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT veredicto_sistema, veredicto_final, notas "
                "  FROM rfqs WHERE id = %s;",
                (registro["id"],),
            )
            sistema, final_bd, notas = cur.fetchone()

        self.assertEqual(sistema, self.VEREDICTO["veredicto"])
        self.assertEqual(final_bd, "not feasible")
        self.assertIn("Diámetro de alambre", notas)      # motivo del motor
        self.assertIn("ing.lopez", notas)                # nota del PM, anexada

    def test_datos_json_conserva_lo_que_ya_tenia(self):
        # El fragmento se fusiona con `||`; no debe pisar el dict del RFQ.
        import app.rfq.repository as repository
        registro = self._dar_de_alta()
        repository.guardar_veredicto(
            self.RFQ_ID, self.VEREDICTO,
            version=registro["version"], conexion=self.conn)

        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT datos_json->>'part_number', "
                "       datos_json->'factibilidad'->>'veredicto' "
                "  FROM rfqs WHERE id = %s;",
                (registro["id"],),
            )
            part_number, veredicto = cur.fetchone()

        self.assertEqual(part_number, "RS-9")
        self.assertEqual(veredicto, self.VEREDICTO["veredicto"])


if __name__ == "__main__":
    unittest.main()
