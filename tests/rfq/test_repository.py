import os
import unittest

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

from app.rfq.repository import ESTADO_NEW, guardar_rfq, guardar_veredicto, guardar_veredicto_final


class FakeCursor:
    """Cursor falso: devuelve resultados de fetchone en orden (cola)."""

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
        return self._resultados.pop(0)


class FakeConn:
    def __init__(self, resultados):
        self.cursor_obj = FakeCursor(resultados)
        self.commits = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def close(self):
        pass


_DATOS = {
    "cliente_id": "CLI-001",
    "nombre_proyecto": "Resorte Norteña 2500",
    "part_number": "RC-12.5-45-316L",
    "volumen": 2500,
    "material": "Acero inoxidable 316L",
    "message_id": "<abc@cliente.com>",
}


class TestGuardarRfq(unittest.TestCase):

    def test_rfq_nuevo_version_1_estado_new(self):
        # _siguiente_version → 1 ; INSERT RETURNING → (10, 1)
        conn = FakeConn([(1,), (10, 1)])
        resultado = guardar_rfq("RFQ-2026-001", _DATOS, conexion=conn)
        self.assertEqual(resultado["version"], 1)
        self.assertEqual(resultado["estado"], ESTADO_NEW)
        self.assertFalse(resultado["es_seguimiento"])
        self.assertEqual(resultado["id"], 10)

    def test_seguimiento_crea_nueva_version(self):
        # Ya existe v1 y v2 → siguiente = 3 ; INSERT RETURNING → (11, 3)
        conn = FakeConn([(3,), (11, 3)])
        resultado = guardar_rfq(
            "RFQ-2026-001", _DATOS, es_seguimiento=True, conexion=conn
        )
        self.assertEqual(resultado["version"], 3)
        self.assertTrue(resultado["es_seguimiento"])
        self.assertEqual(resultado["estado"], ESTADO_NEW)

    def test_version_mayor_a_1_se_marca_seguimiento(self):
        """Aunque no se pase es_seguimiento, si ya existían versiones, lo es."""
        conn = FakeConn([(2,), (12, 2)])
        resultado = guardar_rfq("RFQ-2026-001", _DATOS, conexion=conn)
        self.assertEqual(resultado["version"], 2)
        self.assertTrue(resultado["es_seguimiento"])

    def test_insert_usa_estado_new_y_rfq_id(self):
        conn = FakeConn([(1,), (13, 1)])
        guardar_rfq("RFQ-2026-002", _DATOS, conexion=conn)
        # El segundo execute es el INSERT; sus params incluyen rfq_id y estado.
        sql_insert, params = conn.cursor_obj.ejecutados[1]
        self.assertIn("INSERT INTO rfqs", sql_insert)
        self.assertEqual(params[0], "RFQ-2026-002")   # rfq_id
        self.assertIn(ESTADO_NEW, params)             # estado 'New'

    def test_rfq_id_vacio_lanza_error(self):
        with self.assertRaises(ValueError):
            guardar_rfq("", _DATOS, conexion=FakeConn([(1,), (1, 1)]))


_VEREDICTO = {
    "veredicto": "requires review",
    "score": 61,
    "banda": "Engineering review",
    "reglas_version": "0.2",
    "tipo_resorte": "compresion",
    "motivos": [
        {"codigo": "fuera_de_rango", "nivel": "crit", "campo": "diametro_alambre_mm",
         "valor": 25.0, "limite": "0.2–12 mm",
         "texto": "Diámetro de alambre fuera de rango: 25 mm (fabricable 0.2–12 mm)."},
        {"codigo": "confianza_baja", "nivel": "warn", "campo": "confianza",
         "valor": 0.4, "limite": 0.7,
         "texto": "La extracción del plano quedó en 0.4 de confianza."},
    ],
}


class TestGuardarVeredicto(unittest.TestCase):
    """COT-72 — el veredicto del sistema y sus motivos, ya en la BD.

    Secuencia de sentencias que ejercen estos tests (`cursor.ejecutados`):
      [0] SELECT de la fila a marcar
          - sin `version`: `_ultima_version_id` → (id, version, estado,
            datos_json, notas)
          - con `version`: (id, version, datos_json)
      [1] UPDATE rfqs → params (veredicto, notas, datos_json[, score], id)
      [2] DELETE FROM rfq_banderas
      [3+] un INSERT INTO rfq_banderas por motivo
    """

    def test_marca_el_rfq_y_devuelve_la_version(self):
        # SELECT última versión: (id, version, estado, datos_json, notas)
        conn = FakeConn([(10, 2, "New", None, None)])
        resultado = guardar_veredicto("RFQ-2026-001", _VEREDICTO, conexion=conn)
        self.assertEqual(resultado["id"], 10)
        self.assertEqual(resultado["version"], 2)
        self.assertEqual(resultado["veredicto"], "requires review")
        self.assertEqual(resultado["banderas"], 2)

    def test_el_update_escribe_veredicto_notas_y_datos_json(self):
        conn = FakeConn([(10, 1, "New", None, None)])
        guardar_veredicto("RFQ-2026-001", _VEREDICTO, conexion=conn)
        sql, params = conn.cursor_obj.ejecutados[1]     # [0] es el SELECT
        self.assertIn("UPDATE rfqs", sql)
        self.assertIn("veredicto_sistema", sql)
        # params: 0 veredicto, 1 notas, 2 datos_json, 3 score, 4 id
        self.assertEqual(params[0], "requires review")
        self.assertIn("fuera de rango", params[1])          # notas legibles
        self.assertIn('"factibilidad"', params[2])          # fragmento jsonb
        self.assertEqual(params[3], 61)                     # score 0-100

    def test_el_score_se_guarda_y_se_devuelve(self):
        # Mismo modelo que los históricos de ISC: las filas son comparables.
        conn = FakeConn([(10, 1, "New", None, None)])
        resultado = guardar_veredicto("RFQ-2026-001", _VEREDICTO, conexion=conn)
        self.assertEqual(resultado["score"], 61)
        self.assertIn("score", conn.cursor_obj.ejecutados[1][0])

    def test_sin_score_no_borra_el_que_haya(self):
        # Unas directrices sin modelo de puntuación no deben limpiar la columna:
        # el UPDATE ni siquiera menciona `score`.
        conn = FakeConn([(10, 1, "New", None, None)])
        guardar_veredicto("RFQ-2026-001", {"veredicto": "feasible", "motivos": []},
                          conexion=conn)
        sql, params = conn.cursor_obj.ejecutados[1]
        self.assertNotIn("score", sql)
        # params: 0 veredicto, 1 notas, 2 datos_json, 3 id (sin score en medio)
        self.assertEqual(len(params), 4)
        self.assertEqual(params[3], 10)

    def test_una_bandera_por_motivo(self):
        conn = FakeConn([(10, 1, "New", None, None)])
        guardar_veredicto("RFQ-2026-001", _VEREDICTO, conexion=conn)
        inserts = [(sql, params) for sql, params in conn.cursor_obj.ejecutados
                   if "INSERT INTO rfq_banderas" in sql]
        self.assertEqual(len(inserts), 2)
        self.assertEqual(inserts[0][1][0], 10)             # rfq_version_id
        self.assertEqual(inserts[0][1][1], "crit")
        self.assertEqual(inserts[1][1][1], "warn")

    def test_limpia_las_banderas_previas(self):
        # Re-evaluar un RFQ no debe acumular motivos viejos.
        conn = FakeConn([(10, 1, "New", None, None)])
        guardar_veredicto("RFQ-2026-001", _VEREDICTO, conexion=conn)
        borrados = [params for sql, params in conn.cursor_obj.ejecutados
                    if "DELETE FROM rfq_banderas" in sql]
        self.assertEqual(borrados, [(10,)])

    def test_veredicto_factible_sin_motivos(self):
        conn = FakeConn([(10, 1, "New", None, None)])
        resultado = guardar_veredicto(
            "RFQ-2026-001", {"veredicto": "feasible", "motivos": []}, conexion=conn)
        self.assertEqual(resultado["banderas"], 0)
        # notas (params[1] del UPDATE) en NULL
        self.assertIsNone(conn.cursor_obj.ejecutados[1][1][1])

    def test_version_explicita_se_respeta(self):
        # SELECT con versión explícita: (id, version, datos_json)
        conn = FakeConn([(10, 3, None)])
        resultado = guardar_veredicto(
            "RFQ-2026-001", _VEREDICTO, version=3, conexion=conn)
        sql, params = conn.cursor_obj.ejecutados[0]
        self.assertIn("version = %s", sql)
        self.assertEqual(params, ("RFQ-2026-001", 3))
        self.assertEqual(resultado["version"], 3)
        # y el UPDATE cae sobre el id de esa versión
        self.assertEqual(conn.cursor_obj.ejecutados[1][1][-1], 10)

    def test_sin_version_marca_la_ultima(self):
        # SELECT última versión: (id, version, estado, datos_json, notas)
        conn = FakeConn([(10, 5, "New", None, None)])
        resultado = guardar_veredicto("RFQ-2026-001", _VEREDICTO, conexion=conn)
        sql, params = conn.cursor_obj.ejecutados[0]
        self.assertEqual(params, ("RFQ-2026-001",))     # no se filtra por versión
        self.assertIn("ORDER BY version DESC", sql)
        self.assertIn("LIMIT 1", sql)
        self.assertEqual(resultado["version"], 5)

    def test_nivel_invalido_no_toca_la_bd(self):
        # rfq_banderas.nivel tiene CHECK: se valida antes de escribir nada,
        # para no dejar el RFQ marcado y las banderas a medias.
        malo = dict(_VEREDICTO, motivos=[{"nivel": "grave", "texto": "x"}])
        conn = FakeConn([(10, 1)])
        with self.assertRaises(ValueError):
            guardar_veredicto("RFQ-2026-001", malo, conexion=conn)
        self.assertEqual(conn.cursor_obj.ejecutados, [])

    def test_rfq_inexistente(self):
        conn = FakeConn([None])            # el UPDATE no encontró la fila
        with self.assertRaises(ValueError):
            guardar_veredicto("RFQ-FANTASMA", _VEREDICTO, conexion=conn)

    def test_sin_veredicto(self):
        with self.assertRaises(ValueError):
            guardar_veredicto("RFQ-2026-001", {"motivos": []},
                              conexion=FakeConn([(10, 1)]))

    def test_rfq_id_vacio(self):
        with self.assertRaises(ValueError):
            guardar_veredicto("", _VEREDICTO, conexion=FakeConn([(10, 1)]))

    def test_motivo_sin_texto_igual_deja_titulo(self):
        # rfq_banderas.titulo es NOT NULL.
        sin_texto = dict(_VEREDICTO, motivos=[{"nivel": "info", "codigo": "dato_ausente"}])
        conn = FakeConn([(10, 1, "New", None, None)])
        guardar_veredicto("RFQ-2026-001", sin_texto, conexion=conn)
        insert = [params for sql, params in conn.cursor_obj.ejecutados
                  if "INSERT INTO rfq_banderas" in sql][0]
        self.assertEqual(insert[2], "dato_ausente")

    def test_conexion_inyectada_no_hace_commit(self):
        conn = FakeConn([(10, 1, "New", None, None)])
        guardar_veredicto("RFQ-2026-001", _VEREDICTO, conexion=conn)
        self.assertEqual(conn.commits, 0)


class TestGuardarVeredictoFinal(unittest.TestCase):
    """COT-72 — el dictamen del plant manager sobre `rfqs.veredicto_final`.

    Secuencia de sentencias (`cursor.ejecutados`):
      [0] SELECT de la fila a dictaminar (columnas según el camino, ver abajo)
      [1] UPDATE rfqs → params (veredicto_final, estado, notas, id)
    """

    def _conn(self, datos_json=None, estado="Declined", notas=None):
        # Sin versión → `_ultima_version_id`:
        # (id, version, estado, datos_json, notas)
        return FakeConn([(10, 1, estado, datos_json, notas)])

    def _conn_version(self, version=4, datos_json=None, estado="Declined",
                      notas=None):
        # Con versión explícita el SELECT lee otro orden:
        # (id, version, estado, notas, datos_json)
        return FakeConn([(10, version, estado, notas, datos_json)])

    def test_registra_veredicto_estado_y_devuelve_los_datos(self):
        conn = self._conn({"remitente": "r@cliente.com"})
        resultado = guardar_veredicto_final(
            "RFQ-2026-001", "not feasible", estado="Declined", conexion=conn)
        self.assertEqual(resultado["veredicto_final"], "not feasible")
        self.assertEqual(resultado["estado"], "Declined")
        self.assertEqual(resultado["datos"]["remitente"], "r@cliente.com")

    def test_no_pisa_el_veredicto_del_sistema(self):
        # Comparar lo que dijo el motor con lo que resolvió la persona es lo
        # que después permite ajustar las directrices.
        conn = self._conn()
        guardar_veredicto_final("RFQ-2026-001", "feasible", conexion=conn)
        sql = conn.cursor_obj.ejecutados[1][0]      # [0] es el SELECT
        self.assertIn("veredicto_final", sql)
        self.assertNotIn("veredicto_sistema", sql)

    def test_sin_estado_no_lo_cambia(self):
        conn = self._conn(estado="RequiresReview")
        guardar_veredicto_final("RFQ-2026-001", "feasible", conexion=conn)
        params = conn.cursor_obj.ejecutados[1][1]
        # params: 0 veredicto_final, 1 estado, 2 notas, 3 id
        self.assertEqual(params[1], "RequiresReview")   # se reescribe el actual

    def test_la_nota_se_anexa_no_sustituye(self):
        # `notas` ya trae los motivos del motor.
        conn = self._conn(notas="[crit] Diámetro fuera de rango.")
        guardar_veredicto_final(
            "RFQ-2026-001", "not feasible", nota="[PM: ing.lopez] fuera de capacidad",
            conexion=conn)
        params = conn.cursor_obj.ejecutados[1][1]
        self.assertEqual(
            params[2],
            "[crit] Diámetro fuera de rango.\n[PM: ing.lopez] fuera de capacidad")

    def test_sin_nota_no_toca_notas(self):
        conn = self._conn(notas="[crit] Diámetro fuera de rango.")
        guardar_veredicto_final("RFQ-2026-001", "feasible", conexion=conn)
        params = conn.cursor_obj.ejecutados[1][1]
        self.assertEqual(params[2], "[crit] Diámetro fuera de rango.")

    def test_datos_json_como_texto_se_convierte(self):
        conn = self._conn('{"remitente": "r@cliente.com"}')
        resultado = guardar_veredicto_final(
            "RFQ-2026-001", "not feasible", conexion=conn)
        self.assertEqual(resultado["datos"]["remitente"], "r@cliente.com")

    def test_datos_json_vacio_o_roto(self):
        for crudo in (None, "", "{no es json", "[1,2]"):
            with self.subTest(crudo=crudo):
                resultado = guardar_veredicto_final(
                    "RFQ-2026-001", "feasible", conexion=self._conn(crudo))
                self.assertEqual(resultado["datos"], {})

    def test_version_explicita(self):
        conn = self._conn_version(version=4)
        resultado = guardar_veredicto_final(
            "RFQ-2026-001", "feasible", version=4, conexion=conn)
        sql, params = conn.cursor_obj.ejecutados[0]
        self.assertIn("version = %s", sql)
        self.assertEqual(params, ("RFQ-2026-001", 4))
        self.assertEqual(resultado["version"], 4)

    def test_rfq_inexistente(self):
        with self.assertRaises(ValueError):
            guardar_veredicto_final(
                "RFQ-FANTASMA", "feasible", conexion=FakeConn([None]))

    def test_veredicto_vacio(self):
        with self.assertRaises(ValueError):
            guardar_veredicto_final("RFQ-2026-001", "", conexion=self._conn())

    def test_rfq_id_vacio(self):
        with self.assertRaises(ValueError):
            guardar_veredicto_final("", "feasible", conexion=self._conn())


if __name__ == "__main__":
    unittest.main()
