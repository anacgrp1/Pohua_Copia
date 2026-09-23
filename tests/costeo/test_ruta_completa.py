# -*- coding: utf-8 -*-
"""La ruta que sale del adaptador: la bobinadora Y lo que va después.

El 004-222 salió cotizado con UNA operación cuando lleva tres. No fue un fallo
del adaptador: `pricing/nucleo/reglas.js` eran diez bytes —la línea
``// reglas``— así que las reglas del taller, que son las que deciden el
esmerilado y el horno, no existían. El fichero estaba, el diagnóstico decía
"núcleo presente", y dentro no había nada.

El número de operaciones no es cosmético: alimenta la escalera de overheads y
el suelo de ISC, que es 800 + 200 por cada operación de más. Faltaba costo por
tres caminos a la vez.
"""

import pytest

from pricing import nucleo, reglas
from pricing.rodea_adapter import _fuera_de_capacidad, _transporte, TRANSPORTE_POR_DEFECTO


class Catalogo:
    """Lo justo para recoger los `faltantes`."""
    def __init__(self):
        self.faltantes = []


class TestLasReglasDelTallerContestan:

    def test_estan_disponibles(self):
        # Si esto falla, el núcleo volvió a quedarse hueco.
        assert reglas.disponible(), (
            "las reglas del taller no responden: sin ellas la ruta sale con "
            "una sola operación y nadie se entera")

    def test_extremos_ground_piden_esmerilado(self):
        ops = reglas.operaciones_secundarias(
            "Compression Spring", tipo_extremos="Squared & Ground",
            material_codigo="MW")
        assert [o["m"] for o in ops] == ["Grinder A"]

    def test_extremos_sin_esmerilar_no_lo_piden(self):
        ops = reglas.operaciones_secundarias(
            "Compression Spring", tipo_extremos="Closed", material_codigo="MW")
        assert ops == []

    def test_el_17_7_pide_horno(self):
        ops = reglas.operaciones_secundarias(
            "Compression Spring", tipo_extremos="Closed",
            material_codigo="SS177")
        assert "Stationary Oven" in [o["m"] for o in ops]

    def test_extension_pide_ganchos(self):
        ops = reglas.operaciones_secundarias("Tension Spring",
                                             material_codigo="MW")
        assert "Looping / Hooks" in [o["m"] for o in ops]

    def test_lista_vacia_y_None_no_son_lo_mismo(self):
        # Vacía = "el plano no pide ninguna". None = "no pudimos preguntar".
        # Confundirlas es cotizar media ruta creyendo que está entera.
        ops = reglas.operaciones_secundarias(
            "Compression Spring", tipo_extremos="Closed", material_codigo="MW")
        assert ops == [] and ops is not None


class TestElNucleoNoPuedeVolverAQuedarseHueco:

    @pytest.mark.parametrize("pieza", ["motor", "reglas", "resortes"])
    def test_ninguna_pieza_va_hueca(self, pieza):
        assert not nucleo.es_hueco(pieza)

    def test_con_las_reglas_huecas_no_se_pregunta(self, monkeypatch):
        # Y sobre todo: no se inventa una respuesta.
        monkeypatch.setattr(nucleo, "es_hueco", lambda p: True)
        assert reglas.disponible() is False
        assert reglas.operaciones_secundarias("Compression Spring") is None


class TestLaMaquinaQueNoPuede:
    """El 004-222 se costeó en una máquina que no corre ese alambre."""

    HX60 = {"alambre_min_mm": 1.0, "alambre_max_mm": 6.0, "od_max_mm": 90.0}

    def test_el_caso_real(self):
        motivo = _fuera_de_capacidad(self.HX60, 0.991, 12.129)
        assert motivo and "desde 1 mm" in motivo and "0.991" in motivo

    def test_un_alambre_que_si_puede_no_avisa(self):
        assert _fuera_de_capacidad(self.HX60, 2.0, 12.129) is None

    def test_el_od_tambien_se_mira(self):
        assert _fuera_de_capacidad(self.HX60, 2.0, 120.0)

    def test_un_limite_sin_capturar_no_descarta(self):
        # "No lo sabemos" no es "no tiene límite", pero tampoco es "no puede":
        # inventarse cualquiera de las dos cosas es el error que esto evita.
        vacio = {"alambre_min_mm": None, "alambre_max_mm": None, "od_max_mm": None}
        assert _fuera_de_capacidad(vacio, 0.991, 12.129) is None


class TestElTransporteNoSeCaeACero:

    def test_el_del_catalogo_manda(self):
        cat = Catalogo()
        assert _transporte({"transpPerLb": 0.42}, cat) == 0.42
        assert cat.faltantes == []

    def test_sin_el_se_usa_la_constante_y_se_dice(self):
        # `or 0` convertía "el catálogo no lo tiene" en "cuesta cero", y el
        # transporte es alrededor del 7 % del material.
        cat = Catalogo()
        assert _transporte({}, cat) == TRANSPORTE_POR_DEFECTO
        assert len(cat.faltantes) == 1
        assert "transporte" in cat.faltantes[0]

    def test_un_cero_explicito_se_respeta(self):
        cat = Catalogo()
        assert _transporte({"transpPerLb": 0}, cat) == 0
        assert cat.faltantes == []
