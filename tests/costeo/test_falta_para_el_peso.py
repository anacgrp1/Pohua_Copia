"""«Faltan diámetro, diámetro medio o número de espiras» nombra tres cosas.

El peso del alambre es π·Dm·Nt por la sección, así que hacen falta tres cotas y
cada una puede venir de varios sitios. Decirlas las tres cuando sólo falla una
deja a quien lee sin saber cuál escribir — y el diámetro medio casi nunca está
impreso en un plano, se deduce del exterior menos un calibre, así que
mencionarlo manda a buscar una cota que no existe.
"""

import pytest

import pricing.mensajes as mensajes
from pricing.rodea_adapter import falta_para_el_peso, longitud_desarrollada_pulg


def test_sin_nada_lo_primero_es_el_calibre():
    assert falta_para_el_peso({}) == "diametro_alambre_mm"


def test_con_calibre_falta_un_diametro_cualquiera():
    assert falta_para_el_peso({"diametro_alambre_mm": 2.0}) == "diametro_exterior_mm"


@pytest.mark.parametrize("clave", ["diametro_medio_mm", "diametro_exterior_mm",
                                   "diametro_interior_mm"])
def test_cualquiera_de_los_tres_diametros_sirve(clave):
    """El medio se deduce del exterior o del interior: pedirlo por su nombre
    mandaría a buscar una cota que el plano no suele traer."""
    datos = {"diametro_alambre_mm": 2.0, clave: 16.0}
    assert falta_para_el_peso(datos) == "numero_espiras_totales"


def test_con_las_tres_no_falta_nada():
    datos = {"diametro_alambre_mm": 2.0, "diametro_exterior_mm": 16.0,
             "numero_espiras_totales": 9}
    assert falta_para_el_peso(datos) is None
    assert longitud_desarrollada_pulg(datos) is not None


def test_en_compresion_las_espiras_activas_bastan():
    """Dos espiras de cierre: el total se aproxima sin inventar nada."""
    datos = {"diametro_alambre_mm": 2.0, "diametro_exterior_mm": 16.0,
             "numero_espiras_activas": 7, "tipo_resorte": "compresion"}
    assert falta_para_el_peso(datos) is None


def test_en_torsion_no_bastan():
    """Ahí las patas no se cuentan como dos espiras: aproximar sería inventar."""
    datos = {"diametro_alambre_mm": 2.0, "diametro_exterior_mm": 16.0,
             "numero_espiras_activas": 7, "tipo_resorte": "torsion"}
    assert falta_para_el_peso(datos) == "numero_espiras_totales"


def test_el_diagnostico_coincide_con_el_calculo():
    """Si dice que no falta nada, el peso tiene que salir. Y al revés."""
    casos = [
        {},
        {"diametro_alambre_mm": 2.0},
        {"diametro_alambre_mm": 2.0, "diametro_exterior_mm": 16.0},
        {"diametro_alambre_mm": 2.0, "diametro_exterior_mm": 16.0,
         "numero_espiras_totales": 9},
        {"diametro_alambre_mm": 2.0, "diametro_interior_mm": 12.0,
         "numero_espiras_totales": 9},
        {"diametro_alambre_mm": 2.0, "diametro_medio_mm": 14.0,
         "numero_espiras_activas": 7, "tipo_resorte": "compresion"},
    ]
    for datos in casos:
        falta = falta_para_el_peso(datos)
        sale = longitud_desarrollada_pulg(datos) is not None
        assert (falta is None) == sale, datos


def test_el_mensaje_dice_la_cota_no_la_clave():
    """«falta numero_espiras_totales» es el nombre de una variable, no una
    instrucción de qué ir a buscar al plano."""
    texto = mensajes.texto(
        "SIN_PESO_POR", campo="numero_espiras_totales",
        nombre=mensajes.etiqueta_campo("numero_espiras_totales"))

    assert "número de espiras" in texto
    assert "numero_espiras_totales" not in texto
    # Y ya no nombra las tres cuando sólo falla una.
    assert "diámetro medio" not in texto


def test_el_motivo_viaja_con_su_codigo_y_su_campo():
    """La web necesita la clave para traducirla al idioma que tenga puesto."""
    entrada = mensajes.entrada(
        "SIN_PESO_POR", campo="numero_espiras_totales", nombre="x")

    assert entrada["codigo"] == "SIN_PESO_POR"
    assert entrada["datos"]["campo"] == "numero_espiras_totales"
