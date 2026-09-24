# -*- coding: utf-8 -*-
"""El 004-222 por el camino de la calculadora: lector -> Spring Calc -> precio.

Dentro de Pohua, "AI Read Drawing" lee el plano con `vendor/isc_extractor`, la
Spring Calc lo dimensiona y le pasa el peso a la calculadora de precios. Las
tres piezas vienen del núcleo, y la copia de Pohua se había quedado atrás del
commit que arregló justamente este plano (9a7c966, "SPRING WIRE" es music
wire).

El plano dice "ACTIVE COILS 10 TO 10.5 APPROX" y, de material, "SPRING WIRE".
Con el lector viejo las activas viajaban en el campo de las TOTALES, la Spring
Calc les restaba las dos muertas de los extremos, y salía todo lo de la
pantalla mala: 10.25 totales, 8.25 activas, 4.892 lbf/in, 0.00483 lb. Y como
"SPRING WIRE" no casaba con ningún material, REQUIRES REVIEW.
"""

import re
import subprocess
import json
import shutil
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
V2 = RAIZ / "vendor" / "calculadora" / "Spring Engineering Calculator V2.html"
V7 = RAIZ / "vendor" / "calculadora" / "ISC Price Calculator V7 to Automate.html"


@pytest.fixture(scope="module")
def adapter():
    import sys
    sys.path.insert(0, str(RAIZ / "vendor"))
    from isc_extractor import adapter as a
    return a


class TestElLector:

    def test_spring_wire_es_music_wire(self, adapter):
        assert adapter.codigo_material("SPRING WIRE") == "MW"

    def test_la_palabra_concreta_manda(self, adapter):
        # "hard drawn spring wire" es Hard Drawn, no Music Wire.
        assert adapter.codigo_material("HARD DRAWN SPRING WIRE") == "HD"

    def test_las_activas_se_convierten_en_totales(self, adapter):
        spec = {"tipo_resorte": "compresion",
                "material": {"nombre": "SPRING WIRE"},
                "extremos": {"tipo": "CLOSED & GROUND"},
                "espiras": {"numero_espiras_activas": 10.25,
                            "numero_espiras_totales": None},
                "metadatos_extraccion": {}}
        r = adapter._completar_espiras(spec, "compresion", "MW")
        r = r[0] if isinstance(r, tuple) else r
        # 12.25: la Spring Calc les resta 2 y vuelve a las 10.25 del plano.
        assert (r or spec)["espiras"]["numero_espiras_totales"] == 12.25


def _spec_como_lo_devuelve_el_modelo():
    """El 004-222 tal como llega del modelo: en mm y REDONDEADO por él.

    ".039 in" -> 0.991 mm (es 0.9906) y ".562 high" -> 14.275 (es 14.2748). En
    la Spring Calc eso se veía como 0.039016 y 0.562008: las milésimas que el
    plano no dice.
    """
    return {"tipo_resorte": "compresion",
            "identificacion": {"numero_parte": "004-222", "unidad_dimensional": "in"},
            "material": {"designacion": "SPRING WIRE"},
            "extremos": {"tipo": "CLOSED & GROUND"},
            "dimensiones_mm": {
                "diametro_alambre": {"nominal": 0.991, "texto_original": "WIRE DIA .039 in"},
                "diametro_exterior": {"nominal": None, "valor_minimo": 12.065,
                                      "valor_maximo": 12.192,
                                      "texto_original": "O.D .475/.480 in"},
                "longitud_libre_L0": {"nominal": 38.1,
                                      "texto_original": "FREE LENGTH 1.500 in"}},
            "espiras": {"numero_espiras_activas": 10.25, "numero_espiras_totales": None},
            "cargas": [{"etiqueta": "compress to .562 high", "longitud_mm": 14.275,
                        "fuerza_N": 16.9}],
            "metadatos_extraccion": {}}


class TestLasMilesimas:
    """El flujo y la calculadora suelta enseñan las cotas EXACTAS del plano."""

    @staticmethod
    def _pulgadas(adapter, spec, clave):
        for f in adapter.campos(spec, "compresion"):
            if f["key"] == clave:
                return float(f["value"]) / 25.4
        raise AssertionError(clave)

    def test_el_alambre_es_039_y_no_039016(self, adapter):
        from isc_extractor import normalizar
        spec = _spec_como_lo_devuelve_el_modelo()
        assert round(self._pulgadas(adapter, spec, "wireDia"), 6) == 0.039016
        normalizar.aplicar(spec)
        assert abs(self._pulgadas(adapter, spec, "wireDia") - 0.039) < 1e-9

    def test_la_altura_de_trabajo_es_562(self, adapter):
        from isc_extractor import normalizar
        spec = _spec_como_lo_devuelve_el_modelo()
        normalizar.aplicar(spec)
        assert abs(self._pulgadas(adapter, spec, "workingHeight") - 0.562) < 1e-9

    def test_lo_que_ya_era_exacto_no_cambia(self, adapter):
        from isc_extractor import normalizar
        spec = _spec_como_lo_devuelve_el_modelo()
        normalizar.aplicar(spec)
        od = spec["dimensiones_mm"]["diametro_exterior"]
        assert (od["valor_minimo"], od["valor_maximo"]) == (12.065, 12.192)
        assert spec["dimensiones_mm"]["longitud_libre_L0"]["nominal"] == 38.1

    def test_un_plano_en_mm_no_se_toca(self, adapter):
        from isc_extractor import normalizar
        spec = _spec_como_lo_devuelve_el_modelo()
        spec["identificacion"]["unidad_dimensional"] = "mm"
        assert normalizar.cotas_en_pulgadas(spec) == 0
        assert spec["dimensiones_mm"]["diametro_alambre"]["nominal"] == 0.991

    def test_sin_unidad_declarada_decide_el_texto_del_plano(self, adapter):
        from isc_extractor import normalizar
        spec = _spec_como_lo_devuelve_el_modelo()
        del spec["identificacion"]["unidad_dimensional"]
        assert normalizar.plano_en_pulgadas(spec)
        normalizar.aplicar(spec)
        assert spec["dimensiones_mm"]["diametro_alambre"]["nominal"] == 0.9906

    def test_una_fraccion_del_plano_tambien_vale(self, adapter):
        from isc_extractor import normalizar
        spec = {"identificacion": {"unidad_dimensional": "in"},
                "dimensiones_mm": {"diametro_exterior": {
                    "nominal": 14.29, "texto_original": "OD 9/16 in"}}}
        normalizar.cotas_en_pulgadas(spec)
        assert spec["dimensiones_mm"]["diametro_exterior"]["nominal"] == 14.2875

    def test_lo_que_no_es_redondeo_no_se_mueve(self, adapter):
        from isc_extractor import normalizar
        # 1.2 mm no sale de redondear .039 in (0.9906), ni una décima de mm
        # cae en una milésima de pulgada: se queda como está.
        spec = {"identificacion": {"unidad_dimensional": "in"},
                "dimensiones_mm": {"diametro_alambre": {
                    "nominal": 1.2, "texto_original": "WIRE .039 in"}}}
        assert normalizar.cotas_en_pulgadas(spec) == 0
        assert spec["dimensiones_mm"]["diametro_alambre"]["nominal"] == 1.2


class TestLaSpringCalc:

    def test_music_wire_reconoce_spring_wire(self):
        texto = V2.read_text(encoding="utf-8", errors="replace")
        linea = re.search(r'\{id:"music".*$', texto, re.M).group(0)
        assert '"SPRINGWIRE"' in linea and '"SPRINGSTEELWIRE"' in linea

    def test_conserva_el_css_de_pohua(self):
        # Se parcheó en vez de regenerarla para no perder esto.
        texto = V2.read_text(encoding="utf-8", errors="replace")
        assert "data-nube-tema" in texto
        assert "background:transparent !important" in texto


class TestLaCalculadoraDePrecios:

    def test_su_seed_va_vacio(self):
        # El catálogo no se versiona: le llega de Neon al abrirse.
        texto = V7.read_text(encoding="utf-8", errors="replace")
        i = texto.index("const SEED = ") + len("const SEED = ")
        seed, _ = json.JSONDecoder().raw_decode(texto[i:])
        for clave in ("machines", "materialPrices", "packing", "customers",
                      "platingHistory", "subcontractors"):
            assert seed.get(clave) == [], clave

    def test_su_motor_es_el_del_nucleo(self):
        # El motor incrustado y `pricing/nucleo/engine.js` tienen que ser el
        # mismo cálculo: si no, la hoja y el servidor dan dos precios.
        html = V7.read_text(encoding="utf-8", errors="replace")
        js = (RAIZ / "pricing" / "nucleo" / "engine.js").read_text(encoding="utf-8")
        tramo = lambda s: s[s.index("const DEFAULT_PARAMS="):s.index("module.exports")]
        norm = lambda s: re.sub(r"\s+", "", s)
        assert norm(tramo(html)) == norm(tramo(js))


def _pn_004_222():
    """Las entradas de la imagen 3: la ruta, el alambre y la caja de cada tramo."""
    ruta = lambda maq, fam, setup, pph, mh, lh: {
        "machine": maq, "family": fam, "setupH": setup, "pph": pph,
        "machH": mh, "laborH": lh, "ratio": None, "scrapPct": 5, "tgtH": mh}
    vacio = {"machine": "", "setupH": None, "pph": None, "family": "",
             "machH": None, "laborH": None, "ratio": None, "scrapPct": 5, "tgtH": None}
    # La caja la elige el peso del tramo (regla `embalaje` del núcleo): por
    # eso la imagen 2 dice $0.0004 en el primer tramo y $0.0003 en los otros.
    caja = {10000: ("COR11050", 2000), 22000: ("COR100803", 2500),
            50000: ("COR121212U", 2500)}
    tramo = lambda q: {
        "qty": q, "routing": [ruta("TORIN (FENN) W11A", "COILER", 3, 1500, 15, 40),
                              ruta("Grinder A", "SECONDARY", 1, 500, 15, 27),
                              ruta("Stationary Oven", "SECONDARY", 3, 400, 10, 27)]
                             + [dict(vacio) for _ in range(5)],
        "tooling": {"desc": "", "cost": None, "amortQty": None},
        "sub": {"supplier": "", "service": "", "minUsd": None, "perLb": None,
                "perPc": None, "partsPerBatch": None, "shareSkid": "NO"},
        "packing": {"id": caja[q][0], "qtyPerBox": caja[q][1]},
        "prodBatch": None, "moqMode": "SHIP", "shipQty": None,
        "override": None, "killed": False, "contribPct": None, "ohPct": None}
    return {"pn": "004-222", "desc": "Compression Spring", "unit": "pc",
            "material": {"code": "MW", "diaIn": 0.039016, "weightLb": 0.00576,
                         "basePerLb": 1.8, "surchPerLb": 0, "transpPerLb": 0.3,
                         "mkPct": 6, "moqLb": None, "devLenIn": None},
            "components": [{"desc": "", "usd": None}, {"desc": "", "usd": None}],
            "consumable": {"desc": "", "usd": None},
            "tiers": [tramo(10000), tramo(22000), tramo(50000)],
            "selTier": 0, "opsTier": 0, "ohOverride": None}


_DBS = {"packing": [{"id": "COR11050", "price": 0.83},
                    {"id": "COR100803", "price": 0.63},
                    {"id": "COR121212U", "price": 0.73}],
        "surchargeAppliesTo": ["SS", "SS177", "316"]}


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node")
class TestElPrecioDeLaPantalla:
    """Imagen 2, tramo 1: el motor, con las entradas de la imagen 3."""

    def test_da_0_3946(self, tmp_path):
        (tmp_path / "in.json").write_text(json.dumps({"pn": _pn_004_222(), "dbs": _DBS}))
        js = f"""
        const {{ ENGINE, DEFAULT_PARAMS }} = require({json.dumps(str(RAIZ / 'pricing' / 'nucleo' / 'engine.js'))});
        const d = JSON.parse(require('fs').readFileSync({json.dumps(str(tmp_path / 'in.json'))}, 'utf8'));
        const r = ENGINE.computePN(d.pn, {{params: DEFAULT_PARAMS, dbs: d.dbs,
            rep: 'John Tvrdy', contribution: 20, shareCountFn: () => 1}});
        process.stdout.write(JSON.stringify(r.tiers.slice(0,3).map(t => [t.sell, t.floorPc, t.nOps, t.oh, t.lbBuy, t.hours])));
        """
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True,
                             check=True, timeout=60).stdout
        t = json.loads(out)
        assert [round(x[0], 4) for x in t] == [0.3946, 0.3425, 0.3020]
        assert [round(x[1], 4) for x in t] == [0.1200, 0.0545, 0.0240]
        assert t[0][2] == 3 and round(t[0][3], 1) == 30.0
        assert [round(x[4], 1) for x in t] == [67.2, 147.8, 335.9]
        assert [round(x[5], 1) for x in t] == [63.3, 130.8, 288.3]


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node")
class TestElServidorDaLoMismo:
    """La ventana del RFQ costea por `pricing/runner.js`, no por la hoja.

    Hasta 2026-09 el runner cargaba su propia copia del motor (V5, con un SEED
    escrito a mano) y con estas mismas entradas daba $0.5098: la ventana y la
    calculadora enseñaban dos precios del mismo resorte.
    """

    def test_el_runner_da_el_precio_de_la_calculadora(self):
        from pricing.engine import compute_price_via_node
        r = compute_price_via_node(_pn_004_222(), ctx_overrides={
            "dbs": _DBS, "rep": "John Tvrdy", "contribution": 20})
        assert [round(t["sell"], 4) for t in r["tiers"][:3]] == [0.3946, 0.3425, 0.3020]

    def test_no_hay_otra_copia_del_motor(self):
        assert not (RAIZ / "pricing" / "engine.js").exists()
        runner = (RAIZ / "pricing" / "runner.js").read_text(encoding="utf-8")
        assert "ISC_NUCLEO_MOTOR" in runner and "SEED" not in runner.split("require(MOTOR)")[1]
