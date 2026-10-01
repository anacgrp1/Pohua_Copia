"""Contribución + overheads + HQ + comisión ≥ 95 %: no hay precio (2026-09-30).

El caso que lo motivó: contribución al 70 % con overheads automáticos del
30 % y HQ del 5 %. El motor no podía calcular precio (divisor negativo) y se
caía en silencio al suelo de ISC ($1,000 / 75,000 pzas = $0.0133), y la
tabla salía entera en negativo como si fuera un precio de verdad.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

from app.rfq import costeo  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
requiere_node = pytest.mark.skipif(shutil.which("node") is None, reason="sin Node")


def _tramo(qty, **extra):
    t = {"qty": qty, "override": None, "contribPct": None, "ohPct": None, "prodBatch": None,
         "routing": [{"machine": "A", "family": "COILER", "pph": 300, "setupH": 2, "laborH": 40,
                      "machH": 30, "tgtH": 90, "ratio": None, "scrapPct": 5},
                     {"machine": "G", "family": "SECONDARY", "pph": 500, "setupH": 1, "laborH": 40,
                      "machH": 11, "tgtH": 55, "ratio": None, "scrapPct": 0}],
         "sub": {"supplier": "", "perLb": None, "minUsd": None, "perPc": None,
                 "partsPerBatch": None, "shareSkid": "NO"},
         "packing": {"id": None, "qtyPerBox": None}, "tooling": {"cost": None, "amortQty": None}}
    t.update(extra)
    return t


def _correr(contribucion, tiers):
    pn = {"pn": "X", "desc": "Compression Spring",
          "material": {"code": "MW", "diaIn": 0.05, "weightLb": 0.0374, "devLenIn": 10,
                       "basePerLb": 1.2, "surchPerLb": 0, "transpPerLb": 0.1, "mkPct": None, "moqLb": None},
          "components": [{"usd": None}, {"usd": None}], "consumable": {"usd": None},
          "tiers": tiers + [_tramo(None)] * (5 - len(tiers)), "selTier": 0, "opsTier": 0, "ohOverride": None}
    out = subprocess.run(
        ["node", str(RAIZ / "pricing" / "runner.js")],
        input=json.dumps({"pn": pn, "ctx_overrides": {"contribution": contribucion}}),
        capture_output=True, text=True, check=True, timeout=30)
    return json.loads(out.stdout)


@requiere_node
def test_con_70_de_contribucion_no_hay_precio_y_el_motor_lo_dice():
    r = _correr(70, [_tramo(66000, override=10, ohPct=50), _tramo(75000), _tramo(80000)])
    t1, t2, t3 = [t for t in r["tiers"] if t]
    # Tier 1 tiene precio a mano: no es «sin precio», pero el aviso lo dice.
    assert t1["sinPrecio"] is False and t1["overridden"] is True and t1["sellCalc"] is None
    # Tiers 2 y 3: ningún precio los cubre; el suelo queda en `sell` pero marcado.
    for t in (t2, t3):
        assert t["sinPrecio"] is True and t["sellCalc"] is None
        assert t["contribMax"] == pytest.approx(60.0)      # 95 − 30 − 5 − 0
        assert t["pnl"]["result"] < 0
    errores = [f["m"] for f in r["flags"] if f["t"] == "err"]
    assert any("Tier 2" in m and "105.0%" in m and "NO PRICE" in m and "60.0%" in m for m in errores)
    assert any("Tier 1" in m and "125.0%" in m and "price override" in m for m in errores)


@requiere_node
def test_con_20_de_contribucion_todo_tiene_precio():
    r = _correr(20, [_tramo(75000)])
    t = next(t for t in r["tiers"] if t)
    assert t["sinPrecio"] is False and t["sellCalc"] > 0
    assert t["contribMax"] == pytest.approx(60.0)
    assert not [f for f in r["flags"] if f["t"] == "err"]


def test_la_ventana_no_ensena_el_suelo_como_precio():
    t = {"qty": 75000, "sell": 0.0133, "sinPrecio": True, "contribMax": 60, "contribPct": 70, "oh": 30,
         "pnl": {"result": -0.23}}
    v = costeo.tramo_para_ventana(t, 70)
    assert v["sin_precio"] is True and v["precio_pc"] is None
    assert v["contrib_max"] == 60 and v["contrib_pct"] == 70
    normal = costeo.tramo_para_ventana({"qty": 75000, "sell": 0.5314, "pnl": {"result": 0.1}}, 20)
    assert normal["sin_precio"] is False and normal["precio_pc"] == 0.5314


def test_la_oferta_no_sale_con_un_tramo_sin_precio():
    from unittest import mock
    import app.rfq.oferta as oferta
    costeado = {"cantidades": [75000.0], "comunes": {"material": "MW"}, "error_costeo": None,
                "tramos": [{"cantidad": 75000.0, "precio_pc": None, "sin_precio": True,
                            "contrib_pct": 70.0, "contrib_max": 60.0}],
                "costeo": {"completo": True, "faltantes": [], "faltantes_i18n": [], "origen": {}}}
    rfq = {"rfq_id": "RFQ-1", "estado": "Approved", "cliente_id": "C", "part_number": "P",
           "material": "MW", "datos": {"remitente": "b@c.com"}, "resorte": {}, "notas": None,
           "fecha_registro": None}
    with mock.patch.object(oferta, "_cargar", return_value=rfq), \
         mock.patch.object(costeo, "costear", return_value=costeado):
        prep = oferta.preparar("RFQ-1")
        assert not prep["listo"]
        assert prep["motivos_i18n"][0]["codigo"] == "OFERTA_SIN_PRECIO"
        assert "60.0" in prep["motivos"][0] or "60" in prep["motivos"][0]
        with pytest.raises(ValueError):
            oferta.enviar("RFQ-1", usuario="pm@x", forzar=True)   # ni forzando
