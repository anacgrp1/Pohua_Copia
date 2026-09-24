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

import io
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


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node")
class TestElPrecioDeLaPantalla:
    """Imagen 2, tramo 1: el motor, con las entradas de la imagen 3."""

    def test_da_0_3946(self, tmp_path):
        ruta = lambda maq, fam, setup, pph, mh, lh: {
            "machine": maq, "family": fam, "setupH": setup, "pph": pph,
            "machH": mh, "laborH": lh, "ratio": None, "scrapPct": 5, "tgtH": mh}
        vacio = {"machine": "", "setupH": None, "pph": None, "family": "",
                 "machH": None, "laborH": None, "ratio": None, "scrapPct": 5, "tgtH": None}
        # La caja la elige el peso del tramo (regla `embalaje` del núcleo):
        # por eso la imagen 2 dice $0.0004 en el primer tramo y $0.0003 en los
        # otros dos.
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
        pn = {"pn": "004-222", "desc": "Compression Spring", "unit": "pc",
              "material": {"code": "MW", "diaIn": 0.039016, "weightLb": 0.00576,
                           "basePerLb": 1.8, "surchPerLb": 0, "transpPerLb": 0.3,
                           "mkPct": 6, "moqLb": None, "devLenIn": None},
              "components": [{"desc": "", "usd": None}, {"desc": "", "usd": None}],
              "consumable": {"desc": "", "usd": None},
              "tiers": [tramo(10000), tramo(22000), tramo(50000)],
              "selTier": 0, "opsTier": 0, "ohOverride": None}
        dbs = {"packing": [{"id": "COR11050", "price": 0.83},
                           {"id": "COR100803", "price": 0.63},
                           {"id": "COR121212U", "price": 0.73}],
               "surchargeAppliesTo": ["SS", "SS177", "316"]}
        (tmp_path / "in.json").write_text(json.dumps({"pn": pn, "dbs": dbs}))
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
