# -*- coding: utf-8 -*-
"""El 004-222, contra las tres pantallas que Ana marcó como correctas.

Cada número de aquí está leído de una de esas tres capturas. Si una de estas
pruebas se pone roja, Pohua dejó de dar lo que da la calculadora de la planta,
y eso es una cotización que sale mal sin que nada lo diga.

Lo que hacía falta para llegar aquí, por orden de dinero:

  · Los datos de máquina. Los de Pohua salían de derivarlos del precio de
    compra; los de verdad los contestó el taller. La W11A pasó de 11.16 $/h y
    600 pzs/h a 15.00 y 1500.
  · El orden de preferencia. La columna `orden_uso` existía desde la migración
    013 y nadie la llenó, así que se elegía por coste — y salía una máquina
    que ni siquiera corre ese alambre.
  · Los precios de alambre. La tabla estaba vacía: cero de 186 filas. El Music
    Wire de .039" son 1.80 $/lb.
  · Las cajas. Dos de dieciséis. La de este tramo, la COR11050, no existía.
  · El ángulo de hélice en el peso. El alambre no da vueltas planas: avanza un
    paso en cada vuelta. Medio por ciento en esta pieza, y siempre hacia abajo.
"""

import math

import pytest

from pricing.rodea_adapter import longitud_desarrollada_pulg, peso_alambre_lb


# Las cotas del plano, como las lee el lector.
PLANO = {
    "tipo_resorte": "compresion",
    "tipo_extremos": "squared and ground",
    "material": "MW",
    "diametro_alambre_mm": 0.991,
    "diametro_exterior_mm": 12.129,
    "longitud_libre_mm": 38.1,
    "numero_espiras_totales": 12.25,
}


class TestElPesoDeLaPieza:
    """Pantalla 1: WEIGHT / PART 0.00576 lb."""

    def test_el_peso_es_el_de_la_pantalla(self):
        L = longitud_desarrollada_pulg(PLANO)
        assert round(peso_alambre_lb(L, 0.991, "MW"), 5) == 0.00576

    def test_el_alambre_va_en_helice_no_plano(self):
        # π·Dm·Nt da 16.8756 in. Con el paso son 16.9610: la espira es la
        # hipotenusa, no la circunferencia.
        L = longitud_desarrollada_pulg(PLANO)
        plano = math.pi * ((12.129 - 0.991) / 25.4) * 12.25
        assert L > plano
        assert round(L, 4) == 16.9610

    def test_ignorar_la_helice_cotiza_barato(self):
        # Siempre hacia abajo: es la dirección que importa.
        L = longitud_desarrollada_pulg(PLANO)
        plano = math.pi * ((12.129 - 0.991) / 25.4) * 12.25
        assert peso_alambre_lb(L, 0.991, "MW") > peso_alambre_lb(plano, 0.991, "MW")

    def test_sin_paso_se_queda_con_la_longitud_plana(self):
        # Corto por medio por ciento es mejor que no dar peso: sin peso no hay
        # costo de material y el RFQ se para.
        sin_l0 = dict(PLANO)
        del sin_l0["longitud_libre_mm"]
        L = longitud_desarrollada_pulg(sin_l0)
        assert round(L, 4) == round(math.pi * ((12.129 - 0.991) / 25.4) * 12.25, 4)

    def test_en_extension_no_se_corrige(self):
        # Las espiras van juntas: el paso es el calibre, no hay hélice que
        # valga. Es la convención del núcleo para ese tipo.
        ext = dict(PLANO, tipo_resorte="extension")
        L = longitud_desarrollada_pulg(ext)
        assert round(L, 4) == round(math.pi * ((12.129 - 0.991) / 25.4) * 12.25, 4)


class TestLaRuta:
    """Pantalla 3: tres operaciones con sus tarifas."""

    ESPERADA = [
        ("TORIN W11A", "COILER", 3.0, 1500.0, 15.0, 40.0),
        ("Grinder A", "SECONDARY", 1.0, 500.0, 15.0, 27.0),
        ("Stationary Oven", "SECONDARY", 3.0, 400.0, 10.0, 27.0),
    ]

    @staticmethod
    @pytest.fixture(scope="class")
    def taller():
        import json
        from pathlib import Path
        ruta = Path(__file__).resolve().parents[2] / "pricing" / "nucleo" / "taller_2026.json"
        d = json.loads(ruta.read_text(encoding="utf-8"))
        return {m["name"]: m for m in d["coilers"] + d["secondary"]}

    @pytest.mark.parametrize("nombre,familia,setup,pph,maq,labor", ESPERADA)
    def test_cada_operacion_con_sus_numeros(self, taller, nombre, familia,
                                            setup, pph, maq, labor):
        m = taller[nombre]
        assert m["setupH"] == setup
        assert m["pph"] == pph
        assert m["machineRateH"] == maq
        assert m["laborRateH"] == labor

    def test_el_esmerilado_lo_pide_el_plano(self):
        from pricing import reglas
        ops = reglas.operaciones_secundarias(
            "Compression Spring", tipo_extremos="Squared & Ground",
            material_codigo="MW")
        assert [o["m"] for o in ops] == ["Grinder A"]

    def test_el_horno_no_lo_pide_el_plano(self):
        # El taller lo corrigió: «not all compression». En la pantalla buena
        # está puesto a mano, y por eso es una política, no una regla.
        from pricing import reglas
        ops = reglas.operaciones_secundarias(
            "Compression Spring", tipo_extremos="Squared & Ground",
            material_codigo="MW")
        assert "Stationary Oven" not in [o["m"] for o in ops]


class TestLaPoliticaDelHorno:

    class Cat:
        def __init__(self):
            self.faltantes = []

    def _con(self, valor, monkeypatch):
        import app.core.config as config
        monkeypatch.setattr(config.settings, "RELEVADO_SIEMPRE_COMPRESION",
                            valor, raising=False)
        from pricing.rodea_adapter import _con_relevado
        cat = self.Cat()
        ops = _con_relevado([{"m": "Grinder A", "why": "ground ends"}],
                            "Compression Spring", cat)
        return ops, cat

    def test_encendida_pone_el_horno(self, monkeypatch):
        ops, _ = self._con(True, monkeypatch)
        assert [o["m"] for o in ops] == ["Grinder A", "Stationary Oven"]

    def test_y_dice_que_lo_puso_la_casa(self, monkeypatch):
        # Quien aprueba tiene que distinguir una operación que pide el dibujo
        # de una que pone la política.
        _, cat = self._con(True, monkeypatch)
        assert len(cat.faltantes) == 1
        assert "política de la casa" in cat.faltantes[0]

    def test_apagada_no_toca_nada(self, monkeypatch):
        ops, cat = self._con(False, monkeypatch)
        assert [o["m"] for o in ops] == ["Grinder A"]
        assert cat.faltantes == []

    def test_no_lo_pone_dos_veces(self, monkeypatch):
        import app.core.config as config
        monkeypatch.setattr(config.settings, "RELEVADO_SIEMPRE_COMPRESION",
                            True, raising=False)
        from pricing.rodea_adapter import _con_relevado
        cat = self.Cat()
        ops = _con_relevado([{"m": "Stationary Oven", "why": "17-7 ageing"}],
                            "Compression Spring", cat)
        assert [o["m"] for o in ops] == ["Stationary Oven"]
        assert cat.faltantes == []

    def test_no_toca_extension(self, monkeypatch):
        import app.core.config as config
        monkeypatch.setattr(config.settings, "RELEVADO_SIEMPRE_COMPRESION",
                            True, raising=False)
        from pricing.rodea_adapter import _con_relevado
        cat = self.Cat()
        ops = _con_relevado([], "Tension Spring", cat)
        assert ops == []

    def test_con_None_sigue_siendo_None(self, monkeypatch):
        # None es "no pudimos preguntar a las reglas". Añadirle el horno lo
        # convertiría en una lista, y el aviso de ruta incompleta se perdería.
        import app.core.config as config
        monkeypatch.setattr(config.settings, "RELEVADO_SIEMPRE_COMPRESION",
                            True, raising=False)
        from pricing.rodea_adapter import _con_relevado
        assert _con_relevado(None, "Compression Spring", self.Cat()) is None


class TestElEmpaque:
    """Pantalla 3: COR11050, 2,000 por caja, 11.52 lb, tramo 57.6 lb."""

    def test_la_caja_del_tramo_de_10000(self):
        from pricing import reglas
        e = reglas.empaque(0.00576, "Compression Spring", 10000)
        assert e["id"] == "COR11050"
        assert e["ppb"] == 2000
        assert round(e["boxWt"], 2) == 11.52
        assert round(e["tierWt"], 1) == 57.6

    def test_otro_tramo_puede_llevar_otra_caja(self):
        # La elige el peso TOTAL, así que 50.000 no van en la misma.
        from pricing import reglas
        assert reglas.empaque(0.00576, "Compression Spring", 50000)["id"] != "COR11050"


class TestElMaterial:
    """Pantalla 3: MW, 1.80 $/lb base, 0.30 transporte, 6 % markup."""

    def test_el_precio_del_calibre(self):
        import json
        from pathlib import Path
        ruta = Path(__file__).resolve().parents[2] / "pricing" / "nucleo" / "catalogo.json"
        precios = json.loads(ruta.read_text(encoding="utf-8"))["materialPrices"]
        mw039 = [p for p in precios if p["code"] == "MW" and p["dia"] == 0.039]
        assert mw039 and mw039[0]["latest"] == 1.8

    def test_el_precio_va_por_calibre_no_por_material(self):
        # El mismo Music Wire vale 2.80 a .020" y 1.80 a .039".
        import json
        from pathlib import Path
        ruta = Path(__file__).resolve().parents[2] / "pricing" / "nucleo" / "catalogo.json"
        precios = json.loads(ruta.read_text(encoding="utf-8"))["materialPrices"]
        mw = {p["dia"]: p["latest"] for p in precios if p["code"] == "MW"}
        assert mw[0.02] != mw[0.039]
