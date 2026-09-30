"""El dictamen del Spring Calc en el servidor (INT-9084602A, 2026-09-30).

El caso que lo motivó: SS 302 de 15.875 mm con 127 mm de DE. El motor de
factibilidad lo mandaba a revisión con tres avisos y la ventana dejaba
aprobarlo. La planta no puede enrollarlo: ni el límite de 15 mm del motor de
coste ni ninguna bobinadora lo admiten.
"""
import os
import shutil
from unittest import mock

import pytest

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

from pricing import spring_calc  # noqa: E402

requiere_node = pytest.mark.skipif(
    shutil.which("node") is None or not spring_calc.disponible(),
    reason="sin Node o sin núcleo")

INT_9084602A = {"tipo_resorte": "Compresion", "diametro_alambre_mm": 15.875,
                "diametro_exterior_mm": 127, "longitud_libre_mm": 355.6,
                "numero_espiras_totales": 14}


@requiere_node
def test_el_int_9084602a_no_es_fabricable():
    r = spring_calc.evaluar(INT_9084602A, "302 ASTM A313")
    assert r["evaluado"] and r["factible"] is False
    assert spring_calc.bloquea(r)
    codigos = [b["codigo"] for b in r["bloqueos"]]
    assert codigos == ["alambre_maximo", "sin_maquina"]
    assert r["material"]["codigo"] == "SS"
    assert r["maquina"]["mejor"] is None
    # Lo más grueso que enrolla el taller en compresión (AIM 3000).
    assert r["bloqueos"][1]["alambre_max_taller"] == pytest.approx(9.525)


@requiere_node
def test_un_resorte_normal_pasa_y_dice_su_bobinadora():
    r = spring_calc.evaluar({"tipo_resorte": "compression", "diametro_alambre_mm": 1.2,
                             "diametro_exterior_mm": 10, "longitud_libre_mm": 30,
                             "numero_espiras_totales": 10}, "Music wire A228")
    assert r["factible"] is True and not spring_calc.bloquea(r)
    assert r["bloqueos"] == []
    assert r["maquina"]["mejor"] == "SIMPLEX MC 50"
    assert 0 <= r["score"] <= 100 and r["banda"]


@requiere_node
def test_las_banderas_llegan_en_los_tres_idiomas():
    r = spring_calc.evaluar(INT_9084602A, "SS")
    rango = [b for b in r["banderas"]
             if b["titulo"] == "Wire diameter outside material data range"][0]
    assert rango["nivel"] == "warn"
    assert rango["textos"]["es"].startswith("Diámetro de alambre fuera")
    assert rango["textos"]["fr"].startswith("Diamètre de fil")


def test_sin_calibre_no_hay_dictamen():
    assert spring_calc.evaluar({"diametro_exterior_mm": 20}) is None
    assert spring_calc.evaluar(None) is None
    assert not spring_calc.bloquea(None)


def test_sin_node_no_bloquea_nada():
    with mock.patch.object(spring_calc, "disponible", return_value=False):
        assert spring_calc.evaluar(INT_9084602A, "SS") is None


@pytest.mark.parametrize("texto,esperado", [
    ("Closed and ground", "closed_ground"), ("squared", "closed"),
    ("plain ends", "plain"), ("Plain & ground", "plain_ground"),
    ("", "closed"), (None, "closed"),
])
def test_tipo_de_extremos(texto, esperado):
    assert spring_calc.tipo_de_extremos(texto) == esperado


@pytest.mark.parametrize("texto,esperado", [
    ("Compresión", "compression"), ("Tension spring", "extension"),
    ("torsión", "torsion"), (None, "compression"),
])
def test_tipo_calculadora(texto, esperado):
    assert spring_calc.tipo_calculadora(texto) == esperado


# --------------------------------------------------------------------------
# El endpoint de aprobar lo rechaza aunque alguien salte el botón
# --------------------------------------------------------------------------

def test_approve_devuelve_409_si_no_es_fabricable():
    from fastapi import HTTPException
    import api.routes.rfqs as rutas

    detalle = mock.Mock(spring_calc={"factible": False, "evaluado": True,
                                     "bloqueos": [{"codigo": "sin_maquina"}]})
    usuario = mock.Mock(correo="pm@x")
    with mock.patch.object(rutas, "get_rfq", return_value=detalle), \
         mock.patch("app.feasibility.pm_decision.aprobar") as aprobar, \
         pytest.raises(HTTPException) as err:
        rutas.approve_rfq("INT-9084602A", mock.Mock(nota=None), usuario)
    assert err.value.status_code == 409
    aprobar.assert_not_called()


def test_approve_sigue_si_es_fabricable_o_no_se_pudo_calcular():
    import api.routes.rfqs as rutas
    usuario = mock.Mock(correo="pm@x")
    resultado = {"id": 1, "rfq_id": "INT-1", "version": 1,
                 "veredicto_final": "feasible", "estado": "Approved"}
    for sc in ({"factible": True, "bloqueos": []}, None):
        with mock.patch.object(rutas, "get_rfq", return_value=mock.Mock(spring_calc=sc)), \
             mock.patch("app.feasibility.pm_decision.aprobar", return_value=resultado):
            r = rutas.approve_rfq("INT-1", mock.Mock(nota=None), usuario)
        assert r.estado == "Approved"
