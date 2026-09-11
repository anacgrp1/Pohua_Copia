"""Envoltorio del motor de costeo (subproceso de Node)."""

import os
import shutil
import unittest
from unittest import mock

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

from pricing import engine  # noqa: E402

HAY_NODE = shutil.which("node") is not None


class TestErroresDeInfraestructura(unittest.TestCase):
    """Un entorno sin Node no debe parecer un error de datos: en Render, si la
    imagen no trae Node, el costeo entero deja de funcionar y hay que verlo."""

    def test_sin_node_el_mensaje_lo_dice(self):
        with mock.patch.object(engine, "node_disponible", return_value=False):
            with self.assertRaises(engine.ErrorMotorCosteo) as ctx:
                engine.compute_price_via_node({})
        self.assertIn("Node.js", str(ctx.exception))

    def test_salida_ilegible(self):
        salida = mock.Mock(stdout="esto no es json", stderr="")
        with mock.patch.object(engine, "node_disponible", return_value=True), \
             mock.patch("subprocess.run", return_value=salida):
            with self.assertRaises(engine.ErrorMotorCosteo):
                engine.compute_price_via_node({})

    def test_timeout(self):
        import subprocess
        with mock.patch.object(engine, "node_disponible", return_value=True), \
             mock.patch("subprocess.run",
                        side_effect=subprocess.TimeoutExpired("node", 60)):
            with self.assertRaises(engine.ErrorMotorCosteo) as ctx:
                engine.compute_price_via_node({})
        self.assertIn("segundos", str(ctx.exception))


@unittest.skipUnless(HAY_NODE, "requiere Node.js")
class TestMotorReal(unittest.TestCase):

    def test_ctx_overrides_ausente_no_revienta(self):
        """runner.js hacía `ctx_overrides.params` a secas: un null tumbaba el
        proceso con un TypeError en vez de usar los valores por defecto."""
        pn = {
            "pn": "T-1", "desc": "Compression Spring", "unit": "pc",
            "material": {"code": "MW", "diaIn": 0.063, "weightLb": 0.011,
                         "basePerLb": 2.55, "surchPerLb": 0, "transpPerLb": 0.30,
                         "mkPct": 6, "moqLb": None, "devLenIn": 12.86},
            "components": [{"desc": "", "usd": None}, {"desc": "", "usd": None}],
            "consumable": {"desc": "", "usd": None},
            "tiers": [{
                "qty": 5000,
                "routing": [{"machine": "NUCOIL CSF-200", "family": "COILER",
                             "setupH": 6.0, "pph": 327.0, "laborH": 40.0,
                             "machH": 44.643, "tgtH": 44.643, "ratio": 1.0,
                             "scrapPct": 5}],
                "tooling": {}, "sub": {}, "packing": {"id": "COR100803", "qtyPerBox": 1000},
            }] + [{"qty": None, "routing": [], "tooling": {}, "sub": {}, "packing": {}}] * 4,
            "selTier": 0, "opsTier": 0, "ohOverride": None,
            "remarks": "", "rev": "", "drawing": None, "springFeas": None, "notes": "",
        }
        resultado = engine.compute_price_via_node(pn, ctx_overrides=None)
        self.assertIn("tiers", resultado)
        self.assertGreater(resultado["tiers"][0]["sell"], 0)

    def test_un_pn_invalido_da_error_controlado(self):
        with self.assertRaises(engine.ErrorMotorCosteo):
            engine.compute_price_via_node({})


if __name__ == "__main__":
    unittest.main()
