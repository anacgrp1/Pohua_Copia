"""El Monitor de la web enseña también lo que hace el lector de escritorio.

Cuando el buzón lo lee la aplicación de escritorio, el servidor se aparta y
su registro no dice nada de los correos: el Monitor enseñaba «0 correos, 0
RFQ» mientras en la planta el lector trabajaba. La aplicación manda con el
latido sus líneas y sus contadores; aquí se guardan y se mezclan con lo del
servidor, en orden de hora.
"""
import os

import pytest

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")


@pytest.fixture
def estado():
    import api.routes.status as modulo
    with modulo._lock:
        modulo._escritorio["lineas"].clear()
        modulo._escritorio["vistas"].clear()
        modulo._escritorio["totales"] = {"procesados": 0, "rfqs": 0, "errores": 0}
    return modulo


def _linea(ident, marca, mensaje, nivel="INFO"):
    return {"id": ident, "marca": marca, "nivel": nivel, "mensaje": mensaje,
            "origen": "lector.escritorio"}


class TestSeGuardaLoDelLatido:

    def test_las_lineas_entran_una_vez(self, estado):
        lineas = [_linea("1", "2026-09-24 21:44:00,000", "Ciclo: 1 RFQ")]
        assert estado.registrar_escritorio(lineas, None, "leyendo") == 1
        # El mismo latido repetido (un reintento) no duplica.
        assert estado.registrar_escritorio(lineas, None, "leyendo") == 0
        assert len(estado._lineas_escritorio()) == 1

    def test_los_contadores_se_suman_en_status(self, estado):
        estado.registrar_escritorio([], {"procesados": 2, "rfqs": 1, "errores": 0}, "leyendo")
        assert estado._totales_escritorio() == {"procesados": 2, "rfqs": 1, "errores": 0}


class TestElRegistroSaleMezclado:

    def test_en_orden_de_hora_con_el_del_servidor(self, estado):
        from api.models.schemas import LogLine
        estado.registrar_escritorio([
            _linea("a", "2026-09-24 21:44:37,000", "RFQ_NUEVO: Spring Quote"),
            _linea("b", "2026-09-24 21:50:00,000", "Ciclo: 0 sin leer"),
        ], None, None)
        del_servidor = [
            LogLine(marca="2026-09-24 21:44:18,000", nivel="INFO", origen="api.rfqs",
                    mensaje="RFQ aprobado"),
            LogLine(nivel="TRACE", mensaje="  File x, line 1"),     # sin marca
            LogLine(marca="2026-09-24 21:47:51,000", nivel="INFO", origen="server",
                    mensaje="Worker en espera"),
        ]
        juntas = estado._con_el_escritorio(del_servidor, 50)
        assert [x.mensaje for x in juntas] == [
            "RFQ aprobado", "  File x, line 1", "RFQ_NUEVO: Spring Quote",
            "Worker en espera", "Ciclo: 0 sin leer"]
        assert juntas[2].origen == "lector.escritorio"

    def test_sin_lector_el_registro_es_el_de_siempre(self, estado):
        from api.models.schemas import LogLine
        solo = [LogLine(marca="2026-09-24 21:44:18,000", mensaje="x")]
        assert estado._con_el_escritorio(solo, 50) is solo

    def test_el_latido_acepta_las_lineas(self):
        import inspect

        import api.server as servidor
        campos = servidor.HeartbeatRequest.model_fields
        assert {"lineas", "totales", "estado"} <= set(campos)
        assert "registrar_escritorio" in inspect.getsource(servidor.api_worker_heartbeat)
