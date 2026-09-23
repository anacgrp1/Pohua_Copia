# -*- coding: utf-8 -*-
"""Los tres diámetros son dos datos y una resta.

Por qué existe
--------------
OD = ID + 2d, por definición de cómo se enrolla un alambre redondo. Un plano
que acota el exterior y el interior YA dice el calibre; no hace falta que lo
repita.

El lector, que tiene prohibido inventar —y hace bien—, devolvía null y lo
anotaba en sus advertencias: «sólo se puede inferir a partir de la diferencia
entre 1.94 y 1.53». Ahí moría. Y sin calibre no hay máquina, ni precio de
material, ni peso: el RFQ entero se paraba por una resta que el propio lector
había dejado escrita.

Una resta no es una estimación. La frontera que estas pruebas vigilan: se
completa lo que se deduce de otras cotas, y NO se completa lo que sencillamente
no está —las espiras, sobre todo, que es el dato que o viene en el plano o hay
que preguntárselo al cliente—.
"""

import pytest

from app.vision.spring_extractor import normalizar


def leido(**campos):
    base = {"tipo_resorte": "compresion"}
    base.update(campos)
    return normalizar(base)


class TestElCalibreSaleDeLaDiferencia:

    def test_el_caso_de_INT_097CBB6A(self):
        # OD 1.94 in y ID 1.53 in, tal como los acotaba el plano.
        r = leido(diametro_exterior_mm=49.28, diametro_interior_mm=38.86,
                  longitud_libre_mm=63.5)
        assert r.diametro_alambre_mm == pytest.approx(5.21, abs=0.01)
        # Y con él sale el medio, que es el que usa el peso.
        assert r.diametro_medio_mm == pytest.approx(44.07, abs=0.01)

    def test_se_dice_que_se_calculó(self):
        # Un número deducido y uno leído del plano no valen lo mismo. Quien
        # aprueba tiene que poder distinguirlos sin abrir el dibujo.
        r = leido(diametro_exterior_mm=49.28, diametro_interior_mm=38.86)
        assert any("(OD - ID)/2" in a for a in r.advertencias)

    def test_el_del_plano_manda_sobre_la_resta(self):
        # Si el plano SÍ acota el alambre, ese es el bueno aunque la resta
        # diera otra cosa: las cotas reales llevan tolerancias y redondeos.
        r = leido(diametro_alambre_mm=5.0, diametro_exterior_mm=49.28,
                  diametro_interior_mm=38.86)
        assert r.diametro_alambre_mm == 5.0
        assert not any("(OD - ID)/2" in a for a in r.advertencias)

    def test_un_interior_mayor_que_el_exterior_no_se_usa(self):
        # Sale negativo: el lector confundió las cotas. Mejor sin calibre —y
        # que el aviso lo diga— que con uno imposible.
        r = leido(diametro_exterior_mm=38.86, diametro_interior_mm=49.28)
        assert r.diametro_alambre_mm is None


class TestLosOtrosDosTambien:

    def test_el_interior_sale_de_exterior_y_calibre(self):
        r = leido(diametro_exterior_mm=49.28, diametro_alambre_mm=5.21)
        assert r.diametro_interior_mm == pytest.approx(38.86, abs=0.01)

    def test_el_exterior_sale_de_interior_y_calibre(self):
        r = leido(diametro_interior_mm=38.86, diametro_alambre_mm=5.21)
        assert r.diametro_exterior_mm == pytest.approx(49.28, abs=0.01)
        assert any("ID + 2d" in a for a in r.advertencias)

    def test_con_un_solo_diametro_no_se_puede(self):
        # Un dato es un dato, no dos. Aquí sí falta información de verdad.
        r = leido(diametro_exterior_mm=49.28)
        assert r.diametro_alambre_mm is None
        assert r.diametro_interior_mm is None


class TestLoQueNoSeInventa:
    """La frontera. Al otro lado están los números que no se deducen de nada."""

    def test_las_espiras_no_se_rellenan_nunca(self):
        r = leido(diametro_exterior_mm=49.28, diametro_interior_mm=38.86,
                  longitud_libre_mm=63.5)
        assert r.numero_espiras_totales is None
        assert r.numero_espiras_activas is None

    def test_ni_el_paso_ni_la_longitud_del_cuerpo(self):
        r = leido(diametro_exterior_mm=49.28, diametro_interior_mm=38.86,
                  longitud_libre_mm=63.5)
        assert r.paso_mm is None
        assert r.longitud_cuerpo_mm is None

    def test_las_advertencias_del_lector_no_se_pierden(self):
        # Se AÑADE a lo que el modelo anotó, no se reemplaza: su nota sobre las
        # espiras es la que le dice al PM que hay que preguntarle al cliente.
        r = leido(diametro_exterior_mm=49.28, diametro_interior_mm=38.86,
                  advertencias=["el dibujo no indica el número de espiras"])
        assert "el dibujo no indica el número de espiras" in r.advertencias
        assert len(r.advertencias) == 2

    def test_sin_advertencias_previas_tampoco_estorba(self):
        r = leido(diametro_exterior_mm=49.28, diametro_interior_mm=38.86)
        assert len(r.advertencias) == 1


class TestElRfqQuedaCosteable:

    def test_con_el_calibre_derivado_ya_sólo_faltan_las_espiras(self):
        from pricing.rodea_adapter import falta_para_el_peso
        r = leido(diametro_exterior_mm=49.28, diametro_interior_mm=38.86,
                  longitud_libre_mm=63.5)
        assert falta_para_el_peso(r.to_dict()) == "numero_espiras_totales"

    def test_y_con_las_espiras_no_falta_nada(self):
        from pricing.rodea_adapter import falta_para_el_peso, longitud_desarrollada_pulg
        r = leido(diametro_exterior_mm=49.28, diametro_interior_mm=38.86,
                  longitud_libre_mm=63.5, numero_espiras_totales=9.5)
        assert falta_para_el_peso(r.to_dict()) is None
        assert longitud_desarrollada_pulg(r.to_dict()) > 0
