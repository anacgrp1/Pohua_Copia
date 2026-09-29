"""Deshacer una aprobación hecha sin querer (INT-59C34202, 2026-09-29)."""
import json
from unittest import mock

import pytest

import app.feasibility.pm_decision as pm_decision
import app.rfq.repository as repository


class Cursor:
    def __init__(self, registro):
        self.registro = registro
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def execute(self, sql, params):
        self.registro.append((sql, params))


class Conexion:
    def __init__(self):
        self.sql = []
    def cursor(self):
        return Cursor(self.sql)


def fila(estado="Approved", oferta=None):
    datos = {"remitente": "d@x"}
    if oferta is not None:
        datos["oferta"] = oferta
    return {"id": 7, "version": 1, "estado": estado, "notas": "[PM: pm@x] APROBADO",
            "datos_json": json.dumps(datos)}


def test_vuelve_a_revision_sin_veredicto_y_con_nota():
    conn = Conexion()
    with mock.patch.object(repository, "_ultima_version_id", return_value=fila()):
        r = pm_decision.deshacer_aprobacion("INT-1", "Se aprobó al cambiar de pestaña",
                                            usuario="pm@x", conexion=conn)
    assert r["estado"] == "RequiresReview" and r["veredicto_final"] is None
    sql, params = conn.sql[0]
    assert "veredicto_final = NULL" in sql and params[0] == "RequiresReview"
    assert "APROBACIÓN DESHECHA — Se aprobó al cambiar de pestaña" in params[1]
    assert params[1].startswith("[PM: pm@x] APROBADO\n")


@pytest.mark.parametrize("oferta", [{"enviada": True}, {"encolada": True}])
def test_si_la_oferta_ya_salio_no_se_deshace(oferta):
    conn = Conexion()
    with mock.patch.object(repository, "_ultima_version_id", return_value=fila(oferta=oferta)), \
         pytest.raises(ValueError, match="ya salió"):
        pm_decision.deshacer_aprobacion("INT-1", "x", usuario="pm@x", conexion=conn)
    assert conn.sql == []


def test_solo_aprobados_y_con_motivo():
    conn = Conexion()
    with mock.patch.object(repository, "_ultima_version_id", return_value=fila("RequiresReview")), \
         pytest.raises(ValueError, match="no está aprobado"):
        pm_decision.deshacer_aprobacion("INT-1", "x", conexion=conn)
    with pytest.raises(ValueError):
        pm_decision.deshacer_aprobacion("INT-1", "  ", conexion=conn)
