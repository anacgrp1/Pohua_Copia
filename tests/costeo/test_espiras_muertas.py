# -*- coding: utf-8 -*-
"""Regla 1: de espiras activas a totales, con las muertas del tipo de extremo.

Por qué existe
--------------
Antes se sumaban 2 siempre. Para unos extremos planos eso inventa dos espiras
de alambre, y el alambre es el grueso del costo: el precio sale inflado sin que
nada avise.

Y hay una trampa peor, la que el núcleo documenta: el lector manda TOTALES y el
Spring Calculator RESTA las muertas para volver a las activas. Si las dos
tablas no coinciden, el resorte sale desplazado una espira —más rigidez, más
carga, menos peso— y todo cuadra por dentro. Por eso aquí se fija la tabla
número a número: si alguien la cambia de un lado, esto se cae.
"""

import pytest

from pricing import espiras
from pricing.rodea_adapter import falta_para_el_peso, longitud_desarrollada_pulg


def resorte(**extra):
    base = dict(tipo_resorte="compresion", diametro_alambre_mm=5.21,
                diametro_exterior_mm=49.28)
    base.update(extra)
    return base


class TestLaTabla:
    """Los tres números. Tienen que ser los mismos que los del Spring
    Calculator; si cambian aquí, hay que cambiarlos allí en el mismo viaje."""

    @pytest.mark.parametrize("extremos, muertas", [
        ("closed and ground", 2.0),
        ("closed", 2.0),
        ("squared and ground", 2.0),
        ("squared", 2.0),
        ("cerrados y esmerilados", 2.0),
        ("cerrados", 2.0),
        ("plain and ground", 1.0),
        ("open and ground", 1.0),
        ("planos y esmerilados", 1.0),
        ("plain", 0.0),
        ("open", 0.0),
        ("planos", 0.0),
    ])
    def test_cada_tipo_de_extremo_da_sus_muertas(self, extremos, muertas):
        n, _ = espiras.espiras_muertas(resorte(tipo_extremos=extremos))
        assert n == muertas

    def test_cerrado_gana_a_esmerilado(self):
        # "closed and ground" lleva las dos palabras. Si "ground" mandara,
        # saldría 1 y el resorte perdería una espira entera.
        n, _ = espiras.espiras_muertas(resorte(tipo_extremos="closed and ground"))
        assert n == 2.0

    def test_sin_extremos_se_suponen_cerrados_y_se_dice(self):
        n, porque = espiras.espiras_muertas(resorte())
        assert n == 2.0
        assert "suponen cerrados" in porque

    def test_un_extremo_que_no_se_reconoce_no_se_inventa(self):
        # Se trata como si no lo dijera —cerrados— pero el texto sale en la
        # explicación, que es lo que permite añadirlo al reconocedor en vez de
        # descubrirlo meses después en un precio raro.
        n, porque = espiras.espiras_muertas(resorte(tipo_extremos="pigtail"))
        assert n == 2.0
        assert "pigtail" in porque


class TestLoQueDigaElPlanoManda:

    def test_las_muertas_acotadas_ganan_a_la_tabla(self):
        # Extremos cerrados dirían 2; el plano dice 3 y mandan las 3.
        n, porque = espiras.espiras_muertas(
            resorte(tipo_extremos="closed and ground", espiras_muertas_totales=3))
        assert n == 3
        assert "stated on the drawing" in porque

    def test_tambien_valen_por_extremo(self):
        n, _ = espiras.espiras_muertas(resorte(espiras_muertas_por_extremo=0.5))
        assert n == 1.0

    def test_cero_muertas_acotadas_es_cero_no_ausente(self):
        # 0 es falsy: si se mira con `if not`, un plano que dice "0 espiras
        # muertas" acabaría con las 2 de la tabla.
        n, _ = espiras.espiras_muertas(
            resorte(tipo_extremos="closed", espiras_muertas_totales=0))
        assert n == 0


class TestTotales:

    def test_las_totales_del_plano_se_usan_tal_cual(self):
        n, porque = espiras.espiras_totales(resorte(numero_espiras_totales=9.5))
        assert n == 9.5
        assert porque is None          # nada que explicar: venía leído

    def test_activas_mas_muertas(self):
        n, porque = espiras.espiras_totales(
            resorte(numero_espiras_activas=7.5, tipo_extremos="plain"))
        assert n == 7.5
        assert "active coils" in porque

    def test_en_extension_no_se_suman_extremos(self):
        # Las espiras del plano ya son las del cuerpo. Sumarles dos sería
        # inventar alambre que no existe.
        n, _ = espiras.espiras_totales(
            dict(tipo_resorte="extension", numero_espiras_activas=7.5))
        assert n is None

    def test_en_torsion_tampoco(self):
        n, _ = espiras.espiras_totales(
            dict(tipo_resorte="torsion", numero_espiras_activas=7.5))
        assert n is None

    def test_sin_espiras_de_ningun_tipo_no_hay_total(self):
        assert espiras.espiras_totales(resorte()) == (None, None)


class TestLasDosFuncionesNoPuedenDiscrepar:
    """El fallo que esto cierra: `falta_para_el_peso` decía "no falta nada" y
    `longitud_desarrollada_pulg` devolvía None igualmente, porque cada una
    llevaba su propia copia de la regla. El PM veía un aviso genérico sobre un
    RFQ que, según el otro lado del código, estaba completo."""

    @pytest.mark.parametrize("d", [
        resorte(numero_espiras_totales=9.5),
        resorte(numero_espiras_activas=7.5, tipo_extremos="closed"),
        resorte(numero_espiras_activas=7.5, tipo_extremos="plain"),
        resorte(numero_espiras_activas=7.5),
        resorte(),
        dict(tipo_resorte="extension", diametro_alambre_mm=2.0,
             diametro_exterior_mm=20.0, numero_espiras_activas=7.5),
    ])
    def test_si_no_falta_nada_hay_longitud_y_al_reves(self, d):
        falta = falta_para_el_peso(d)
        largo = longitud_desarrollada_pulg(d)
        assert (falta is None) == (largo is not None), (
            f"discrepan: falta={falta!r}, longitud={largo!r}")


class TestElPesoCambiaDeVerdad:

    def test_unos_extremos_planos_pesan_menos_que_unos_cerrados(self):
        planos = longitud_desarrollada_pulg(
            resorte(numero_espiras_activas=7.5, tipo_extremos="plain"))
        cerrados = longitud_desarrollada_pulg(
            resorte(numero_espiras_activas=7.5, tipo_extremos="closed"))
        assert planos < cerrados
        # Dos espiras de 44.07 mm de diámetro medio: no es un matiz.
        assert cerrados - planos > 10      # pulgadas de alambre
