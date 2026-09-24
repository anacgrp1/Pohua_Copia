# -*- coding: utf-8 -*-
"""La hoja de Pohua recibe el catálogo de Neon, y el cargador lo deja entero.

Por qué existen estas pruebas
-----------------------------
El 004-222 salía a $1.234 en Pohua y a $0.3946 en la calculadora de la planta.
Era el mismo programa: la diferencia estaba en las bases que cada uno tenía
delante.

La hoja de Pohua lleva el SEED vacío —el catálogo no se versiona— y sólo
recibía de Neon los clientes. Máquinas, precios de alambre, cajas, recargos y
subcontratistas se quedaban como estaban en el documento: vacíos. Y la
migración `taller2026` de la propia hoja reemplazaba las máquinas por las de
su SEED al abrir, o sea, por nada.

Y el cargador que llena Neon tenía dos fallos que lo dejaban a medias: iba en
autocommit —`--seco` escribía y un error no deshacía nada— y reventaba en los
servicios de subcontrato sin fecha, justo antes de cargar las máquinas y los
parámetros.
"""

import inspect
from datetime import date

import pytest

from pricing import proyeccion_hoja


# --------------------------------------------------------------------------- #
# Una base de mentira: devuelve filas según lo que se le pregunte
# --------------------------------------------------------------------------- #

MAQUINA_W11A = ("W11A", "TORIN (FENN) W11A", "COILER", 3.0, 1500, 150000.0, 40.0,
                7, 1.0, 1920, 0.8, None, 15.0, 15.0, 0.381, 1.829, 39.67,
                True, True, False, "Compression, Tension", None, 2, 5.0, False)
MAQUINA_GRINDER = ("GRINDER-A", "Grinder A", "SECONDARY", 1.0, 500, 150000.0, 27.0,
                   7, 1.0, 1920, 0.6, None, 15.0, 15.0, None, None, None,
                   None, None, None, None, None, None, 5.0, None)


class Cursor:
    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.ultimo = ""
        self.connection = self

    def execute(self, sql, params=None):
        self.ultimo = sql

    def fetchall(self):
        for clave, filas in self.respuestas.items():
            if clave in self.ultimo:
                return filas
        return []

    def fetchone(self):
        if "information_schema" in self.ultimo:
            return (3,) if "maquinas" in self.ultimo or "capacidades" in self.ultimo else (1,)
        return None

    def rollback(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Conexion:
    def __init__(self, respuestas):
        self.respuestas = respuestas

    def cursor(self):
        return Cursor(self.respuestas)

    def rollback(self):
        pass


RESPUESTAS = {
    "FROM maquinas m": [MAQUINA_W11A, MAQUINA_GRINDER],
    "FROM material_precios p": [
        ("MW", 1, 0.039, 1.8, 150.0, date(2026, 1, 7), "calculadora V7", "INTER")],
    "FROM empaques e": [
        ("COR11050", "11-1/4X8-3/4X12 RSC STK CTN", "SIP", 0.83, "EACH", None)],
    "FROM aleacion_surcharges a": [],
    "FROM subcontratistas s": [],
}


@pytest.fixture
def sin_parametros(monkeypatch):
    from pricing import repository
    monkeypatch.setattr(repository, "parametros_vigentes",
                        lambda conexion=None, en_fecha=None: {})


class TestLaHojaRecibeElCatalogo:

    def test_llegan_las_maquinas_con_sus_numeros(self, sin_parametros):
        doc = {"dbs": {"machines": []}}
        proyeccion_hoja.aplicar(doc, Conexion(RESPUESTAS))
        w = next(m for m in doc["dbs"]["machines"] if m["name"] == "TORIN (FENN) W11A")
        # Los de la pantalla buena.
        assert (w["setupH"], w["pph"], w["costRateH"], w["laborH"]) == (3.0, 1500.0, 15.0, 40.0)
        assert (w["wireMinMm"], w["wireMaxMm"]) == (0.381, 1.829)
        assert w["family"] == "COILER" and w["m1"] == "W11A"

    def test_la_forma_es_la_que_lee_la_hoja(self, sin_parametros):
        # Los nombres son los del SEED de la calculadora; si cambian aquí sin
        # cambiar allí, la hoja lee undefined y no dice nada.
        doc = {"dbs": {}}
        proyeccion_hoja.aplicar(doc, Conexion(RESPUESTAS))
        m = doc["dbs"]["machines"][0]
        for campo in ("family", "name", "m1", "setupH", "pph", "laborH",
                      "costRateH", "ccvTargetH", "wireMinMm", "wireMaxMm",
                      "odMaxMm", "capC", "capE", "capT"):
            assert campo in m

    def test_llega_el_precio_del_calibre(self, sin_parametros):
        doc = {"dbs": {}}
        proyeccion_hoja.aplicar(doc, Conexion(RESPUESTAS))
        p = doc["dbs"]["materialPrices"][0]
        assert (p["code"], p["dia"], p["latest"]) == ("MW", 0.039, 1.8)
        assert p["date"] == "2026-01-07"

    def test_llega_la_caja_con_su_precio(self, sin_parametros):
        # El motor calcula el empaque como precio / piezas por caja buscando la
        # caja en esta lista. Sin ella, el empaque daba cero.
        doc = {"dbs": {}}
        proyeccion_hoja.aplicar(doc, Conexion(RESPUESTAS))
        c = doc["dbs"]["packing"][0]
        assert (c["id"], c["price"]) == ("COR11050", 0.83)

    def test_una_tabla_vacia_no_pisa_lo_que_habia(self, sin_parametros):
        # Un catálogo vacío para todo el mundo es peor que uno un poco viejo.
        viejo = [{"alloy": "302 / 304", "code": "SS", "perLb": 1.3}]
        doc = {"dbs": {"surcharges": list(viejo)}}
        proyeccion_hoja.aplicar(doc, Conexion(RESPUESTAS))
        assert doc["dbs"]["surcharges"] == viejo

    def test_si_la_base_falla_la_hoja_sigue_abriendo(self, sin_parametros):
        class Rota(Conexion):
            def cursor(self):
                raise RuntimeError("la base no contesta")
        doc = {"dbs": {"machines": [{"name": "la de antes"}]}}
        proyeccion_hoja.aplicar(doc, Rota({}))
        assert doc["dbs"]["machines"] == [{"name": "la de antes"}]


class TestLaHojaNoVuelveABorrarlas:
    """Su SEED va vacío: las migraciones que lo copian no pueden correr."""

    def test_marca_la_migracion_que_borraba_las_maquinas(self, sin_parametros):
        doc = {"dbs": {}, "migrations": {}}
        proyeccion_hoja.aplicar(doc, Conexion(RESPUESTAS))
        assert doc["migrations"]["taller2026"] is True
        assert doc["migrations"]["camposNuevos202609"] is True

    def test_no_le_pregunta_si_actualizar_a_la_semilla(self, sin_parametros):
        # Contestar que sí con la semilla vacía borraría todas las bases.
        doc = {"dbs": {}, "migrations": {"seedPendiente": {"machines": 30}}}
        proyeccion_hoja.aplicar(doc, Conexion(RESPUESTAS))
        assert "seedPendiente" not in doc["migrations"]

    def test_la_version_es_la_del_html_que_se_sirve(self, sin_parametros):
        doc = {"dbs": {}, "migrations": {}}
        proyeccion_hoja.aplicar(doc, Conexion(RESPUESTAS))
        v = proyeccion_hoja.version_semilla()
        assert v and doc["migrations"]["seedVersion"] == v

    def test_sin_maquinas_en_neon_no_se_marca(self, sin_parametros):
        vacias = dict(RESPUESTAS, **{"FROM maquinas m": []})
        doc = {"dbs": {}, "migrations": {}}
        proyeccion_hoja.aplicar(doc, Conexion(vacias))
        assert "taller2026" not in doc["migrations"]


class TestLosParametros:

    def test_los_del_juego_vigente_mandan(self, monkeypatch):
        # Si la hoja usara otros, el precio de la hoja y el de la oferta
        # serían dos distintos.
        from pricing import repository
        monkeypatch.setattr(repository, "parametros_vigentes",
                            lambda conexion=None, en_fecha=None:
                            {"ohLadder": [30, 30, 30, 30], "floorBase": 800})
        doc = {"dbs": {}, "params": {"ohLadder": [12, 16, 20, 24], "hq": 5}}
        proyeccion_hoja.aplicar(doc, Conexion(RESPUESTAS))
        assert doc["params"]["ohLadder"] == [30, 30, 30, 30]
        assert doc["params"]["floorBase"] == 800
        assert doc["params"]["hq"] == 5          # lo demás se queda


class TestSeSirveConElDocumento:

    def test_la_ruta_lo_aplica(self):
        import api.routes.nube as nube
        fuente = inspect.getsource(nube.leer_estado)
        assert "proyeccion.aplicar" in fuente
        # Después de los clientes, sobre el mismo documento.
        assert fuente.index("catalogo.aplicar") < fuente.index("proyeccion.aplicar")


# --------------------------------------------------------------------------- #
# El cargador
# --------------------------------------------------------------------------- #

class TestElCargador:

    @staticmethod
    @pytest.fixture(scope="class")
    def fuente():
        from pathlib import Path
        ruta = Path(__file__).resolve().parents[2] / "scripts" / "cargar_catalogo.py"
        return ruta.read_text(encoding="utf-8")

    def test_va_en_una_sola_transaccion(self, fuente):
        # conectar_bd() devuelve la conexión en autocommit: sin esto, --seco
        # escribía y un error a mitad de carga no deshacía nada.
        i = fuente.index("conn = duplicates.conectar_bd()")
        assert "conn.autocommit = False" in fuente[i:i + 1500]

    def test_una_tarifa_de_hoy_se_corrige_en_su_sitio(self, fuente):
        # Cerrarla con fecha de hoy la dejaba con vigente_hasta = vigente_desde,
        # que la base prohíbe. Pasaba al correr el cargador dos veces el mismo día.
        assert "vigente_desde = CURRENT_DATE" in fuente
        assert "vigente_desde < CURRENT_DATE" in fuente

    def test_un_servicio_sin_fecha_entra_con_la_de_la_validacion(self, monkeypatch):
        import importlib.util
        from pathlib import Path
        ruta = Path(__file__).resolve().parents[2] / "scripts" / "cargar_catalogo.py"
        spec = importlib.util.spec_from_file_location("cargar_catalogo", ruta)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        avisos = []
        monkeypatch.setattr(mod, "avisar", avisos.append)

        con = mod._vigencia_servicio({"vigente_desde": "2025-09-12",
                                      "etiqueta": "Passivate"})
        sin = mod._vigencia_servicio({"vigente_desde": "", "etiqueta": "Zinc & Clear",
                                      "subcontratista_nombre": "Commercial Plating"})
        assert con == "2025-09-12"
        assert sin == mod.FECHA_VALIDACION
        # Y se dice: no es una fecha que viniera en el extracto.
        assert len(avisos) == 1 and "Zinc & Clear" in avisos[0]
