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
                                     "numero": "2026-CGRINTERNA-020",
                                     "version": None}
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
             mock.patch("app.rfq.repository.anotar_datos") as anotar:
            ventana = rutas.guardar_cotizacion_pm("INT-1", body, usuario)

        guardado = anotar.call_args[0][1]["cotizacion_pm"]
        assert guardado["n"] == 1 and guardado["fijada"] is False
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
             mock.patch("app.rfq.repository.anotar_datos") as anotar, \
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
             mock.patch("app.rfq.repository.anotar_datos") as anotar, \
             mock.patch.object(rutas.costeo_rfq, "costear",
                               return_value={"cantidades": [], "tramos": [], "costeo": {},
                                             "comunes": {}, "error_costeo": None}) as costear:
            rutas.recalcular_rfq("INT-1", RecalculoRequest(ajustes={"diametro_alambre_mm": "4.5"}),
                                 mock.Mock(correo="pm@x"))
        cambios = anotar.call_args[0][1]
        assert cambios["cotizacion_pm"] is None
        # La calculadora se reabrirá con el PN del sistema (cotas nuevas).
        assert cambios["pm_restauracion"]["version"] is None
        # Y la ventana se costea ya sin la del PM.
        assert "cotizacion_pm" not in costear.call_args[0][1]


# --------------------------------------------------------------------------- #
# Versiones: el PM prueba, vuelve, y puede escoger una anterior
# --------------------------------------------------------------------------- #

import app.rfq.versiones_pm as versiones  # noqa: E402


def cot(precio, por="pm@x", en="2026-09-26T16:00:00+00:00"):
    return {"pn": dict(PN, remarks=f"p{precio}"),
            "resultado": {"tiers": [tier(111000, precio)], "flags": []},
            "contribution": 20.0, "cabecera": {"numero": "Q-1"}, "por": por, "en": en}


def aplicar(datos, cambios):
    fuera = dict(datos)
    for k, v in (cambios or {}).items():
        if v is None:
            fuera.pop(k, None)
        else:
            fuera[k] = v
    return fuera


class TestVersiones:

    def test_mientras_escribe_es_la_misma_version(self):
        d = aplicar({}, versiones.registrar({}, cot(3.6)))
        assert d["cotizacion_pm"]["n"] == 1 and not d["cotizacion_pm"]["fijada"]
        d = aplicar(d, versiones.registrar(d, cot(3.7)))
        assert d["cotizacion_pm"]["n"] == 1
        assert versiones.precios(d["cotizacion_pm"]) == [3.7]
        assert "cotizacion_pm_versiones" not in d       # todavía nada fijado

    def test_al_volver_se_fija_y_el_siguiente_cambio_abre_otra(self):
        d = aplicar({}, versiones.registrar({}, cot(3.6), motivo="volver"))
        assert d["cotizacion_pm"]["fijada"] is True
        assert [v["n"] for v in d["cotizacion_pm_versiones"]] == [1]
        d = aplicar(d, versiones.registrar(d, cot(10.0)))
        assert d["cotizacion_pm"]["n"] == 2 and not d["cotizacion_pm"]["fijada"]
        d = aplicar(d, versiones.registrar(d, cot(10.0), motivo="volver"))
        assert [v["n"] for v in d["cotizacion_pm_versiones"]] == [1, 2]

    def test_lo_que_no_cambia_no_escribe_nada(self):
        d = aplicar({}, versiones.registrar({}, cot(3.6), motivo="volver"))
        # Reabrir la hoja la hace guardar aunque nadie toque nada.
        assert versiones.registrar(d, cot(3.6, en="otra hora")) is None
        assert versiones.registrar(d, cot(3.6), motivo="volver") is None

    def test_volver_sin_cambios_fija_la_en_curso(self):
        d = aplicar({}, versiones.registrar({}, cot(3.6)))
        d = aplicar(d, versiones.registrar(d, cot(3.6), motivo="volver"))
        assert d["cotizacion_pm"]["fijada"] and d["cotizacion_pm"]["n"] == 1
        assert [v["n"] for v in d["cotizacion_pm_versiones"]] == [1]

    def _dos_versiones(self):
        d = aplicar({}, versiones.registrar({}, cot(3.6), motivo="volver"))
        return aplicar(d, versiones.registrar(d, cot(10.0), motivo="volver"))

    def test_escoger_una_anterior_la_vuelve_la_actual(self):
        d = self._dos_versiones()
        d = aplicar(d, versiones.restaurar(d, 1, "pm@x", "2026-09-26T17:00:00+00:00"))
        assert d["cotizacion_pm"]["n"] == 1
        assert versiones.precios(d["cotizacion_pm"]) == [3.6]
        assert d["pm_restauracion"] == {"en": "2026-09-26T17:00:00+00:00", "por": "pm@x",
                                        "version": 1}
        # La ventana y la oferta costean con ésa.
        r = costeo.costear("INT-1", d, {})
        assert [t["precio_pc"] for t in r["tramos"]] == [3.6]
        assert r["costeo"]["pm"]["version"] == 1
        # Las dos siguen en el historial.
        assert [v["n"] for v in d["cotizacion_pm_versiones"]] == [1, 2]

    def test_volver_al_sistema_no_borra_las_versiones(self):
        d = self._dos_versiones()
        d = aplicar(d, versiones.restaurar(d, None, "pm@x", "t"))
        assert "cotizacion_pm" not in d
        assert [v["n"] for v in d["cotizacion_pm_versiones"]] == [1, 2]
        assert versiones.resumen(d)["sistema_en_uso"] is True

    def test_la_en_curso_no_se_pierde_al_escoger_otra(self):
        d = aplicar({}, versiones.registrar({}, cot(3.6), motivo="volver"))
        d = aplicar(d, versiones.registrar(d, cot(4.0)))            # v2 en curso
        d = aplicar(d, versiones.restaurar(d, 1, "pm@x", "t"))
        assert [v["n"] for v in d["cotizacion_pm_versiones"]] == [1, 2]

    def test_una_version_que_no_existe(self):
        with pytest.raises(KeyError):
            versiones.restaurar(self._dos_versiones(), 9, "pm@x", "t")

    def test_el_resumen_para_la_ventana(self):
        d = self._dos_versiones()
        r = versiones.resumen(d)
        assert r["en_uso"] == 2 and r["sistema_en_uso"] is False
        assert [(v["n"], v["precios"], v["en_uso"]) for v in r["versiones"]] == [
            (2, [10.0], True), (1, [3.6], False)]
        assert "pn" not in r["versiones"][0]           # sin el PN entero

    def test_tras_escoger_la_calculadora_sabe_que_cargar(self):
        d = self._dos_versiones()
        assert versiones.pn_restaurado(d) is None
        d = aplicar(d, versiones.restaurar(d, 1, "pm@x", "t1"))
        r = versiones.pn_restaurado(d)
        assert r["en"] == "t1" and r["version"] == 1 and r["pn"]["remarks"] == "p3.6"
        d = aplicar(d, versiones.restaurar(d, None, "pm@x", "t2"))
        assert versiones.pn_restaurado(d) == {"en": "t2", "version": None, "pn": None}

    def test_el_historial_tiene_tope(self):
        d = {}
        for i in range(versiones.MAX_VERSIONES + 5):
            d = aplicar(d, versiones.registrar(d, cot(1.0 + i), motivo="volver"))
        ns = [v["n"] for v in d["cotizacion_pm_versiones"]]
        assert len(ns) == versiones.MAX_VERSIONES and ns[-1] == versiones.MAX_VERSIONES + 5


class TestElegirVersionEndpoint(TestElEndpoint):

    def test_escoger_version_y_volver_al_sistema(self, rutas):
        from fastapi import HTTPException

        from api.models.schemas import VersionPMRequest

        d = aplicar({}, versiones.registrar({}, cot(3.6), motivo="volver"))
        d = aplicar(d, versiones.registrar(d, cot(10.0), motivo="volver"))
        detalle = self._detalle(rutas)
        detalle.datos_json = d
        with mock.patch.object(rutas, "get_rfq", return_value=detalle), \
             mock.patch("app.rfq.repository.anotar_datos") as anotar:
            ventana = rutas.usar_version_pm("INT-1", VersionPMRequest(version=1),
                                            mock.Mock(correo="pm@x"))
        assert anotar.call_args[0][1]["cotizacion_pm"]["n"] == 1
        assert [t["precio_pc"] for t in ventana["tramos"]] == [3.6]
        assert ventana["versiones_pm"]["en_uso"] == 1

        with mock.patch.object(rutas, "get_rfq", return_value=detalle), \
             mock.patch("app.rfq.repository.anotar_datos"), \
             pytest.raises(HTTPException):
            rutas.usar_version_pm("INT-1", VersionPMRequest(version=9), mock.Mock(correo="pm@x"))
