# -*- coding: utf-8 -*-
"""El flujo lee el plano con el MISMO lector que la calculadora.

Antes el correo pasaba por un lector propio (``app/vision``) y la calculadora
por el del núcleo (``isc_extractor``): el mismo plano daba dos resortes. En la
calculadora suelta el 004-222 salía con su lista de factibilidad, FEASIBLE y
la ruta completa; en el flujo, sin nada de eso, la Spring Calc decía «No
customer drawing parsed yet» y la ventana de revisión «Sin ruta».
"""

import shutil
import sys
from pathlib import Path

import pytest

from app.vision import lector_nucleo

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def payload_demo():
    """Un payload real del lector (su plano de demostración)."""
    sys.path.append(str(RAIZ / "vendor"))
    from isc_extractor import adapter, demo
    spec, tipo, router, diag = demo.cargar()
    return adapter.adaptar(spec, tipo, diag=diag, router=router)


class TestLaFormaDelResorte:

    def test_las_cotas_y_las_espiras_del_lector(self, payload_demo):
        r = lector_nucleo.a_resorte(payload_demo)
        assert r["tipo_resorte"] == "compresion"
        assert r["diametro_alambre_mm"] == 1.1
        # Las TOTALES, ya convertidas por el lector: la calculadora resta las
        # muertas a lo que le llegue.
        assert r["numero_espiras_totales"] == 6.0
        assert r["tipo_extremos"] == "closed_ground"

    def test_lleva_lo_que_la_calculadora_recibe_de_ai_read_drawing(self, payload_demo):
        pc = lector_nucleo.a_resorte(payload_demo)["plano_calculadora"]
        assert pc["springType"] == "compression"
        assert any(f["key"] == "wireDia" for f in pc["fields"])
        assert pc["feasibility"] and pc["verdict"]

    def test_se_sabe_con_que_lector_se_leyo(self, payload_demo):
        assert lector_nucleo.a_resorte(payload_demo)["lector"] == "nucleo"


class TestElRespaldo:

    def test_sin_nucleo_lee_el_de_siempre(self, monkeypatch):
        import app.vision.pipeline as pipeline
        monkeypatch.setattr(lector_nucleo, "leer", lambda planos: None)
        monkeypatch.setattr(pipeline, "analizar_dibujos", lambda planos, cliente=None: {
            "texto": '{"tipo_resorte": "compresion", "diametro_alambre_mm": 1.6}'})
        r = lector_nucleo.leer_planos([{"nombre": "a.pdf", "contenido": b"x"}])
        assert r["diametro_alambre_mm"] == 1.6 and r["lector"] == "vision"


class TestLaRelectura:

    def test_un_resorte_del_lector_viejo_se_vuelve_a_leer(self, monkeypatch):
        import app.rfq.relectura as relectura
        monkeypatch.setattr(lector_nucleo, "disponible", lambda: True)
        assert relectura.hay_que_leer({"diametro_alambre_mm": 0.991})

    def test_uno_ya_leido_por_el_nucleo_no(self, monkeypatch):
        import app.rfq.relectura as relectura
        monkeypatch.setattr(lector_nucleo, "disponible", lambda: True)
        assert not relectura.hay_que_leer({"diametro_alambre_mm": 0.991,
                                           "plano_calculadora": {"fields": [1]}})

    def test_si_el_nucleo_no_pudo_no_se_insiste(self, monkeypatch):
        import app.rfq.relectura as relectura
        monkeypatch.setattr(lector_nucleo, "disponible", lambda: True)
        assert not relectura.hay_que_leer({"diametro_alambre_mm": 0.991,
                                           "lector": "vision"})


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node")
class TestLasReglasVenElMismoPlano:

    def test_el_horno_sale_de_la_lista_de_factibilidad(self):
        from pricing import reglas
        ops = reglas.operaciones_secundarias(
            "Compression Spring", tipo_extremos="closed_ground", material_codigo="MW",
            plano_calculadora={"fields": [{"key": "endType", "value": "closed_ground"}],
                               "feasibility": [{"label": "Heat treatment: stress relieve"}]})
        assert [o["m"] for o in ops] == ["Grinder A", "Stationary Oven"]


class TestLaVentanaEnsenaLaRuta:

    def test_la_ruta_sale_de_lo_que_se_mando_al_motor(self):
        from app.rfq.costeo import tramo_para_ventana
        # El motor del núcleo no devuelve `routing` en su resultado.
        resultado = {"qty": 10000, "sell": 0.3946, "pnl": {}, "hours": 63.3}
        enviado = {"routing": [
            {"machine": "TORIN (FENN) W11A", "family": "COILER", "pph": 1500,
             "setupH": 3, "machH": 15},
            {"machine": "Grinder A", "family": "SECONDARY", "pph": 500, "setupH": 1},
            {"machine": "", "family": ""}]}
        v = tramo_para_ventana(resultado, 20, enviado)
        assert [(o["maquina"], o["familia"]) for o in v["ruta"]] == [
            ("TORIN (FENN) W11A", "COILER"), ("Grinder A", "SECONDARY")]
        assert v["ruta"][0]["costo_h"] == 15
