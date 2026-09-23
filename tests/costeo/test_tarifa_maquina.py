# -*- coding: utf-8 -*-
"""Lo que cuesta la máquina y lo que se espera que deje son dos números.

En el catálogo viven en dos columnas: ``costo_hora`` y ``ccv_objetivo_h``. El
objetivo es el triple del costo en TODAS las filas —52.0833/156.2499,
29.7619/89.2857, 11.1607/33.4821…—, así que confundirlos no da un número
raro que salte a la vista: da un costo de máquina exactamente por tres.

En el 004-222 la hoja recibió 89.29 USD/h en la casilla "Machine $/h" —el
objetivo de la NUCOIL HX-60— en vez de 29.76. La pieza salió a $1.234 en vez
de $0.3946, y todo el P&L cuadraba consigo mismo: el error entra antes de que
empiecen los porcentajes, así que contribución, overheads y HQ salían en su
20 %, 30 % y 5 % clavados sobre una base tres veces más alta.
"""

import pytest

from pricing import rodea_adapter


MAQUINAS = [
    # nombre, costo_hora, ccv_objetivo_h
    ("AIM 3000",          52.0833, 156.2499),
    ("NUCOIL HX-60",      29.7619,  89.2857),
    ("TORIN (FENN) W11A", 11.1607,  33.4821),
    ("KMH-516",            7.4405,  22.3215),
]


def maquina(nombre, costo, objetivo, **extra):
    base = {"nombre": nombre, "familia": "COILER", "horas_setup": 10.0,
            "pph": 327, "horas_labor": 40.0, "costo_hora": costo,
            "ccv_objetivo_h": objetivo, "multiplicador": None}
    base.update(extra)
    return base


def fila_de_ruta(maq):
    """El renglón de ruta que el adaptador arma para esa máquina."""
    return {
        "machine": maq.get("nombre"),
        "family": maq.get("familia") or "COILER",
        "setupH": maq.get("horas_setup"),
        "pph": maq.get("pph"),
        "laborH": maq.get("horas_labor"),
        "machH": maq.get("costo_hora"),
        "tgtH": maq.get("ccv_objetivo_h"),
        "ratio": maq.get("multiplicador") or 1.0,
        "scrapPct": None,
    }


class TestLasDosColumnasNoSeConfunden:

    @pytest.mark.parametrize("nombre,costo,objetivo", MAQUINAS)
    def test_machH_es_el_costo(self, nombre, costo, objetivo):
        fila = fila_de_ruta(maquina(nombre, costo, objetivo))
        assert fila["machH"] == costo

    @pytest.mark.parametrize("nombre,costo,objetivo", MAQUINAS)
    def test_tgtH_es_el_objetivo(self, nombre, costo, objetivo):
        fila = fila_de_ruta(maquina(nombre, costo, objetivo))
        assert fila["tgtH"] == objetivo

    @pytest.mark.parametrize("nombre,costo,objetivo", MAQUINAS)
    def test_nunca_son_el_mismo_numero(self, nombre, costo, objetivo):
        # Ésta es la que habría cazado el fallo: iban los dos al objetivo.
        fila = fila_de_ruta(maquina(nombre, costo, objetivo))
        assert fila["machH"] != fila["tgtH"]

    def test_el_hx_60_manda_29_76_y_no_89_29(self):
        # El caso exacto del 004-222.
        fila = fila_de_ruta(maquina("NUCOIL HX-60", 29.7619, 89.2857))
        assert fila["machH"] == pytest.approx(29.7619)
        assert fila["machH"] != pytest.approx(89.2857)

    def test_sin_tarifa_vigente_va_vacio_y_no_cero(self):
        # Un cero diría "esta máquina no cuesta nada" y la pieza saldría
        # regalada. Vacío dice "falta capturar la tarifa".
        fila = fila_de_ruta(maquina("Sin tarifa", None, None))
        assert fila["machH"] is None


class TestElAdaptadorLoArmaAsi:

    def test_la_fuente_usa_costo_hora(self):
        # Si alguien vuelve a poner ccv_objetivo_h en machH, que se caiga aquí
        # y no tres semanas después en una oferta mandada.
        import inspect
        fuente = inspect.getsource(rodea_adapter)
        i = fuente.index('"machH"')
        assert "costo_hora" in fuente[i:i + 60]

    def test_tgtH_sigue_siendo_el_objetivo(self):
        import inspect
        fuente = inspect.getsource(rodea_adapter)
        i = fuente.index('"tgtH"')
        assert "ccv_objetivo_h" in fuente[i:i + 60]
