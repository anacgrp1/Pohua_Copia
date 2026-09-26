"""Lo que el PM corrige en la calculadora completa es lo que se aprueba.

El camino de vuelta de «Open full quote»: la calculadora manda el PN tal como
quedó y el resultado del motor con el que el PM lo vio; se guarda en el RFQ
(``datos_json.cotizacion_pm``) y desde entonces la ventana de revisión y la
oferta costean CON ESO, sin volver a correr el motor. Antes lo corregido se
quedaba en la hoja y la ventana enseñaba el costeo del sistema.
"""
import os
from unittest import mock

import pytest

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

import app.rfq.costeo as costeo  # noqa: E402


def tier(qty, sell, mat=1.38, routing=None):
    return {"qty": qty, "sell": sell, "mat": mat, "lbBuy": qty * 0.9,
            "revenue": qty * sell, "hours": 12.0,
            "pnl": {"result": sell * 0.2, "av": sell * 0.57, "ccv": sell * 0.57,
                    "ccd": sell * 0.55, "ccvHr": 1683.0},
            "routing": routing or []}


PN = {
    "pn": "1-633064", "desc": "Compression Spring", "unit": "pc",
    "material": {"code": "MW", "diaIn": 0.170, "weightLb": 0.92554,
                 "basePerLb": 1.04, "surchPerLb": 0, "transpPerLb": 0.30, "mkPct": 6},
    "tiers": [
        {"qty": 111000, "routing": [{"machine": "SIMPLEX MC 50", "family": "COILER",
                                     "pph": 950, "setupH": 5, "machH": 60}]},
        {"qty": 222000, "routing": [{"machine": "SIMPLEX MC 50", "family": "COILER"}]},
        {"qty": 333000, "routing": []},
        {"qty": None}, {"qty": None},
    ],
}

# Lo que el PM vio: el precio ya con su margen tocado (25 % en vez de 20 %).
RESULTADO = {"tiers": [tier(111000, 3.60), tier(222000, 3.59), tier(333000, 3.58),
                       None, None],
             "flags": [{"m": "Scrap above 5 %"}]}

PM = {"pn": PN, "resultado": RESULTADO, "contribution": 25.0,
      "cabecera": {"numero": "2026-CGRINTERNA-020", "representante": "John Tvrdy"},
      "material_nombre": "Music Wire (ASTM A228)",
      "por": "pm@cgr-international.com", "en": "2026-09-25T15:40:00+00:00"}


class TestCostearConElPM:

    def test_sin_cotizacion_del_pm_no_hay_nada(self):
        assert costeo.cotizacion_del_pm({}) is None
        assert costeo.cotizacion_del_pm({"cotizacion_pm": "basura"}) is None
        assert costeo.cotizacion_del_pm({"cotizacion_pm": {"pn": PN, "resultado": {}}}) is None

    def test_la_del_pm_manda_y_el_motor_no_se_corre(self):
        with mock.patch("pricing.engine.compute_price_via_node") as motor:
            r = costeo.costear("INT-1", {"cotizacion_pm": PM, "volumen": 333000}, {})
        motor.assert_not_called()
        assert r["error_costeo"] is None
        assert r["cantidades"] == [111000, 222000, 333000]
        assert [t["precio_pc"] for t in r["tramos"]] == [3.60, 3.59, 3.58]
        # El objetivo es el del PM, no el 20 % del sistema.
        assert r["tramos"][0]["objetivo_pct"] == 25.0
        # La ruta sale del PN que mandó la calculadora.
        assert r["tramos"][0]["ruta"][0]["maquina"] == "SIMPLEX MC 50"
        assert r["tramos"][0]["ruta"][0]["familia"] == "COILER"

    def test_lo_comun_sale_del_pn_del_pm(self):
        r = costeo.costear("INT-1", {"cotizacion_pm": PM}, {})
        assert r["comunes"]["material"] == "MW"
        assert r["comunes"]["material_nombre"] == "Music Wire (ASTM A228)"
        assert r["comunes"]["dia_in"] == pytest.approx(0.170)
        assert r["comunes"]["peso_lb_pc"] == pytest.approx(0.92554)
        assert r["comunes"]["base_lb"] == pytest.approx(1.04)

    def test_la_ventana_sabe_de_donde_salen_los_numeros(self):
        r = costeo.costear("INT-1", {"cotizacion_pm": PM}, {})
        assert r["costeo"]["completo"] is True
        assert r["costeo"]["origen"] == "calculadora"
        assert r["costeo"]["pm"] == {"por": "pm@cgr-international.com",
                                     "en": "2026-09-25T15:40:00+00:00",
                                     "numero": "2026-CGRINTERNA-020"}
        assert r["costeo"]["banderas_motor"] == ["Scrap above 5 %"]

    def test_sin_cotizacion_del_pm_se_costea_como_siempre(self):
        """Sin cantidades ni material el costeo dice por qué, igual que antes."""
        r = costeo.costear("INT-1", {}, {})
        assert r["tramos"] == []
        assert r["costeo"]["origen"] is None


class TestElRepositorio:

    def test_anotar_guarda_bajo_cotizacion_pm_y_none_la_borra(self):
        import app.rfq.repository as repository

        fila = {"id": 7, "version": 1, "datos_json": {"customer": "cgr", "cotizacion_pm": PM}}
        cur = mock.MagicMock()
        conn = mock.MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        with mock.patch.object(repository, "_ultima_version_id", return_value=fila):
            r = repository.anotar_cotizacion_pm("INT-1", None, conexion=conn)
        assert "cotizacion_pm" not in r["datos"]
        assert r["datos"]["customer"] == "cgr"
        sql, valores = cur.execute.call_args[0]
        assert "UPDATE rfqs SET datos_json" in sql and valores[1] == 7

        with mock.patch.object(repository, "_ultima_version_id", return_value=fila):
            r = repository.anotar_cotizacion_pm("INT-1", {"pn": PN}, conexion=conn)
        assert r["datos"]["cotizacion_pm"] == {"pn": PN}


class TestElEndpoint:

    @pytest.fixture
    def rutas(self):
        import api.routes.rfqs as modulo
        return modulo

    def _detalle(self, rutas):
        from api.models.schemas import RFQDetail
        campos = {c: None for c in RFQDetail.model_fields}
        campos.update({"id": 7, "rfq_id": "INT-1", "version": 1, "estado": "RequiresReview",
                       "datos_json": {"customer": "cgr"}, "banderas": []})
        return RFQDetail(**campos)

    def test_guarda_y_devuelve_la_ventana_con_los_numeros_del_pm(self, rutas):
        from api.models.schemas import CotizacionPMRequest

        usuario = mock.Mock(correo="pm@cgr-international.com")
        body = CotizacionPMRequest(pn=PN, resultado=RESULTADO, contribution=25.0,
                                   cabecera={"numero": "2026-CGRINTERNA-020"})
        with mock.patch.object(rutas, "get_rfq", return_value=self._detalle(rutas)), \
             mock.patch("app.rfq.repository.anotar_cotizacion_pm") as anotar:
            ventana = rutas.guardar_cotizacion_pm("INT-1", body, usuario)

        guardado = anotar.call_args[0][1]
        assert guardado["por"] == "pm@cgr-international.com"
        assert guardado["pn"] == PN and guardado["contribution"] == 25.0
        assert guardado["en"]
        assert [t["precio_pc"] for t in ventana["tramos"]] == [3.60, 3.59, 3.58]
        assert ventana["costeo"]["origen"] == "calculadora"

    def test_sin_tramos_no_se_guarda_nada(self, rutas):
        from fastapi import HTTPException

        from api.models.schemas import CotizacionPMRequest

        body = CotizacionPMRequest(pn=PN, resultado={"tiers": [None, None]})
        with mock.patch.object(rutas, "get_rfq", return_value=self._detalle(rutas)), \
             mock.patch("app.rfq.repository.anotar_cotizacion_pm") as anotar, \
             pytest.raises(HTTPException):
            rutas.guardar_cotizacion_pm("INT-1", body, mock.Mock(correo="pm@x"))
        anotar.assert_not_called()

    def test_recalcular_con_cotas_nuevas_suelta_la_del_pm(self, rutas):
        """Con cotas corregidas la cotización del PM ya no describe el resorte."""
        from api.models.schemas import RecalculoRequest

        detalle = self._detalle(rutas)
        detalle.datos_json = {"customer": "cgr", "cotizacion_pm": PM}
        detalle.resorte = {"diametro_alambre_mm": 4.318}
        recalculo = {"tocados": ["diametro_alambre_mm"], "guardado": True, "error": None,
                     "resorte": {"diametro_alambre_mm": 4.5}, "factibilidad": {}}
        with mock.patch.object(rutas, "get_rfq", return_value=detalle), \
             mock.patch("app.rfq.recalculo.recalcular", return_value=recalculo), \
             mock.patch("app.rfq.repository.anotar_cotizacion_pm") as anotar, \
             mock.patch.object(rutas.costeo_rfq, "costear",
                               return_value={"cantidades": [], "tramos": [], "costeo": {},
                                             "comunes": {}, "error_costeo": None}) as costear:
            rutas.recalcular_rfq("INT-1", RecalculoRequest(ajustes={"diametro_alambre_mm": "4.5"}),
                                 mock.Mock(correo="pm@x"))
        anotar.assert_called_once_with("INT-1", None)
        # Y la ventana se costea ya sin la del PM.
        assert "cotizacion_pm" not in costear.call_args[0][1]
