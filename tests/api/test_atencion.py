"""«Needs attention» dice lo mismo que la campana.

La campana avisaba «Quote validation required» de un RFQ factible y este
panel contestaba «Nothing is waiting», porque sólo listaba los parados en
revisión o con banderas. Lo que espera a una persona es TODO lo que no tiene
dictamen, y cada fila dice por qué espera.
"""
import inspect
import os

import pytest

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")


@pytest.fixture
def asistente():
    # Se importa dentro y no arriba: cargar la API al importar el módulo
    # fijaba la configuración antes de que las pruebas de seguridad pusieran
    # su JWT_SECRET, y las tumbaba.
    import api.routes.assistant as modulo
    return modulo


class TestElMotivo:

    def test_factible_sin_banderas_espera_la_validacion(self, asistente):
        assert asistente._motivo("New", 0, 0) == "validacion"

    def test_en_revision_o_con_banderas_espera_la_revision(self, asistente):
        assert asistente._motivo("RequiresReview", 0, 0) == "revision"
        assert asistente._motivo("New", 1, 0) == "revision"
        assert asistente._motivo("New", 0, 2) == "revision"


class TestLaConsulta:

    def test_lista_todo_lo_que_no_tiene_dictamen(self, asistente):
        fuente = inspect.getsource(asistente._atencion)
        # Menos lo que espera al cliente: eso no espera a nadie de aquí.
        assert "NOT IN ('Approved', 'Declined', 'Incomplete')" in fuente
        # Ya no se recorta a los parados en revisión o con banderas.
        assert "HAVING" not in fuente

    def test_solo_la_ultima_version_de_cada_rfq(self, asistente):
        fuente = inspect.getsource(asistente._atencion)
        assert "MAX(x.version)" in fuente

    def test_cada_fila_lleva_motivo_y_nombre_del_cliente(self, asistente):
        fuente = inspect.getsource(asistente._atencion)
        assert '"motivo"' in fuente and '"cliente_nombre"' in fuente
