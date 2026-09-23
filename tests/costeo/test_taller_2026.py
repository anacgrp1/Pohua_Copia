# -*- coding: utf-8 -*-
"""Los números del taller son los que salen en la pantalla.

El 004-222 se cotizaba a $1.234 la pieza y en la calculadora de la planta a
$0.3946. Las dos aplicaban la misma fórmula: lo que no coincidía eran los
datos de máquina que cada una tenía delante.

Los de Pohua salían de derivarlos del precio de compra —costo/hora = compra /
(años x horas al año)—. Los del taller los contestó una persona en
`ISC Machine Selection Rules DATA REQUEST - FILLED.xlsx`, que es lo que hay en
`pricing/nucleo/taller_2026.json`, y no se parecen:

    TORIN W11A       derivado 11.16 $/h, 600 pzs/h   real 15.00 $/h, 1500 pzs/h
    Grinder A        derivado 11.16 $/h, sin pzs/h   real 15.00 $/h,  500 pzs/h
    Stationary Oven  derivado  8.93 $/h, sin pzs/h   real 10.00 $/h,  400 pzs/h

Y los rangos de alambre cambian quién puede hacer qué. La W11A figuraba sin
rango capturado; el taller dice 0.381 a 1.829 mm. La NUCOIL HX-60 figuraba
desde 1.0 mm y en realidad empieza en 2.997, o sea que ni de lejos podía con
el alambre de 0.991 con el que se la puso a cotizar.

Estas pruebas leen el JSON, no la base: comprueban que el dato de origen es el
que creemos y que el generador de la migración lo traslada entero.
"""

import json
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
DATOS = RAIZ / "pricing" / "nucleo" / "taller_2026.json"
MIGRACION = RAIZ / "sql" / "migrations" / "025_taller_2026.sql"


@pytest.fixture(scope="module")
def taller():
    return json.loads(DATOS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sql():
    return MIGRACION.read_text(encoding="utf-8")


def maquina(taller, nombre):
    for m in taller["coilers"] + taller["secondary"]:
        if m["name"] == nombre:
            return m
    raise AssertionError("no está en el taller: %s" % nombre)


class TestElDatoDeOrigen:
    """Lo que contestó el taller, que es lo que se ve en la pantalla buena."""

    def test_viene_del_libro_del_taller(self, taller):
        assert "DATA REQUEST" in taller["fuente"]

    def test_la_w11a(self, taller):
        m = maquina(taller, "TORIN W11A")
        assert m["machineRateH"] == 15.0
        assert m["pph"] == 1500.0
        assert m["setupH"] == 3.0
        assert m["laborRateH"] == 40.0

    def test_el_grinder_a(self, taller):
        m = maquina(taller, "Grinder A")
        assert (m["machineRateH"], m["pph"], m["setupH"], m["laborRateH"]) == \
               (15.0, 500.0, 1.0, 27.0)

    def test_el_horno(self, taller):
        m = maquina(taller, "Stationary Oven")
        assert (m["machineRateH"], m["pph"], m["setupH"], m["laborRateH"]) == \
               (10.0, 400.0, 3.0, 27.0)

    def test_la_w11a_si_puede_con_el_004_222(self, taller):
        # 0.991 mm de alambre. Ésta es la máquina que dice la calculadora.
        m = maquina(taller, "TORIN W11A")
        assert m["wireMinMm"] <= 0.991 <= m["wireMaxMm"]

    def test_la_hx_60_no_puede_ni_de_lejos(self, taller):
        # Se cotizó en ella. Empieza en 2.997 mm.
        m = maquina(taller, "NUCOIL HX-60")
        assert m["wireMinMm"] > 0.991

    def test_la_w11a_es_la_segunda_en_preferencia(self, taller):
        # La primera (SIMPLEX MC 50) no llega a 0.991, así que gana la W11A.
        orden = taller["preferenceOrder"]["compression"]
        assert orden[:2] == ["SIMPLEX MC 50", "TORIN W11A"]
        assert maquina(taller, "SIMPLEX MC 50")["wireMinMm"] > 0.991

    def test_el_horno_no_va_en_toda_compresion(self, taller):
        # Por eso la ruta sale con dos operaciones y no tres: en la pantalla
        # buena el horno lo puso una persona.
        m = maquina(taller, "Stationary Oven")
        assert "not all compression" in m["appliesWhen"]

    def test_la_escalera_de_operarios(self, taller):
        # Es la que el `ratio` anulaba al mandar el multiplicador de familia.
        escalera = taller["rules"]["operatorLadder"]
        assert [p["machines"] for p in escalera] == [1, 2, 3, 4]


class TestLaMigracionLoTrasladaEntero:

    def test_esta_generada_y_lo_dice(self, sql):
        assert "GENERADO por scripts/generar_taller.py" in sql

    @pytest.mark.parametrize("valor", ["15", "1500", "3", "40"])
    def test_los_numeros_de_la_w11a_estan(self, sql, valor):
        bloque = sql.split("-- TORIN W11A")[1].split("-- ")[0]
        assert re.search(r"\b%s\b" % re.escape(valor), bloque)

    def test_iguala_los_nombres_con_y_sin_fenn(self, sql):
        # El taller escribe "TORIN W11A" y el catálogo "TORIN (FENN) W11A".
        # Sin esto se crearían filas duplicadas que compiten al elegir.
        assert "isc_norm_maquina" in sql
        assert "'(FENN)'" in sql

    def test_carga_el_orden_de_preferencia(self, sql):
        # La migración 013 creó `orden_uso` y nadie lo llenó nunca, así que la
        # consulta ordenaba por costo, que es otra regla y da otra máquina.
        assert "orden_uso" in sql

    def test_cierra_la_tarifa_vieja_en_vez_de_borrarla(self, sql):
        # Las tarifas son un histórico: una cotización de hace un mes se
        # explica con la que estaba vigente entonces.
        assert "vigente_hasta = CURRENT_DATE" in sql

    def test_las_28_maquinas(self, sql, taller):
        esperadas = len(taller["coilers"]) + len(taller["secondary"])
        assert sql.count("UPDATE maquinas SET") == esperadas


class TestLaConsultaUsaLaPreferencia:

    def test_ordena_por_orden_uso_antes_que_por_costo(self):
        import inspect
        from pricing import repository
        sql = repository._SQL_MAQUINA
        assert "m.orden_uso ASC NULLS LAST" in sql
        assert sql.index("orden_uso") < sql.index("t.costo_hora ASC")
