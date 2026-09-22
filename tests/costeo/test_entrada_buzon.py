"""Una configuración que no puede funcionar no se reintenta a ciegas.

En dos horas y media, el registro traía 84 líneas de ERROR con su traza, todas
iguales: el worker del servidor intentando abrir un buzón para el que no tiene
credenciales. Y era la configuración CORRECTA —lee la aplicación de escritorio
y el servidor se aparta—. El problema no era el intento fallido: era que
enterraba lo que sí había que ver.
"""

import pytest

import app.core.config as config
import app.email.entrada as entrada


CLAVES = ("MAIL_MODE", "IMAP_SERVER", "IMAP_USER", "IMAP_PASSWORD",
          "GRAPH_USER", "AZURE_TENANT_ID", "AZURE_CLIENT_ID",
          "AZURE_CLIENT_SECRET")


@pytest.fixture
def ajustes(monkeypatch):
    for clave in CLAVES:
        monkeypatch.setattr(config.settings, clave, "", raising=False)
    entrada.olvidar_avisos()

    def poner(**valores):
        for clave, valor in valores.items():
            monkeypatch.setattr(config.settings, clave, valor, raising=False)
    yield poner
    entrada.olvidar_avisos()


# --------------------------------------------------------------------------- #
# El diagnóstico
# --------------------------------------------------------------------------- #

def test_sin_credenciales_no_se_puede_leer(ajustes):
    ajustes(MAIL_MODE="imap")
    d = entrada.diagnostico_lectura()

    assert d["puede"] is False
    assert d["faltan"] == ["IMAP_SERVER", "IMAP_USER", "IMAP_PASSWORD"]


def test_con_credenciales_si(ajustes):
    ajustes(MAIL_MODE="imap", IMAP_SERVER="outlook.office365.com",
            IMAP_USER="ventas@cgr.com", IMAP_PASSWORD="x")
    assert entrada.diagnostico_lectura()["puede"] is True


def test_graph_pide_las_suyas_y_no_habla_de_imap(ajustes):
    ajustes(MAIL_MODE="graph")
    d = entrada.diagnostico_lectura()

    assert d["canal"] == "graph"
    assert d["faltan"] == ["AZURE_TENANT_ID", "AZURE_CLIENT_ID",
                           "AZURE_CLIENT_SECRET", "GRAPH_USER"]
    assert "IMAP_PASSWORD" not in d["faltan"]


def test_outlook_en_un_servidor_linux_no_puede(ajustes, monkeypatch):
    ajustes(MAIL_MODE="outlook")
    monkeypatch.setattr("sys.platform", "linux")
    assert entrada.diagnostico_lectura()["puede"] is False


def test_el_diagnostico_no_toca_la_red(ajustes, monkeypatch):
    ajustes(MAIL_MODE="imap", IMAP_SERVER="s", IMAP_USER="u", IMAP_PASSWORD="p")
    import socket

    def prohibido(*a, **k):
        raise AssertionError("el diagnóstico abrió una conexión")

    monkeypatch.setattr(socket.socket, "connect", prohibido)
    monkeypatch.setattr(socket, "create_connection", prohibido)
    assert entrada.diagnostico_lectura()["puede"] is True


# --------------------------------------------------------------------------- #
# Decirlo una vez, no una por ciclo
# --------------------------------------------------------------------------- #

def test_se_avisa_una_vez_y_luego_se_calla(ajustes, caplog):
    ajustes(MAIL_MODE="imap")
    diagnostico = entrada.diagnostico_lectura()

    with caplog.at_level("WARNING"):
        for _ in range(28):          # los mismos ciclos del registro real
            entrada.avisar_una_vez(diagnostico)

    avisos = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(avisos) == 1, f"se avisó {len(avisos)} veces"


def test_la_frase_dice_qué_falta(ajustes):
    ajustes(MAIL_MODE="imap")
    frase = entrada.avisar_una_vez(entrada.diagnostico_lectura())

    assert "IMAP_USER" in frase
    assert "IMAP" in frase


def test_si_cambia_lo_que_falta_se_vuelve_a_avisar(ajustes):
    """Poner una credencial y que siga faltando otra es información nueva."""
    ajustes(MAIL_MODE="imap")
    entrada.avisar_una_vez(entrada.diagnostico_lectura())

    ajustes(IMAP_SERVER="outlook.office365.com", IMAP_USER="v@cgr.com")
    segunda = entrada.diagnostico_lectura()
    assert segunda["faltan"] == ["IMAP_PASSWORD"]
    # La clave del aviso cambió, así que este sí se escribe.
    assert "IMAP_PASSWORD" in entrada.avisar_una_vez(segunda)


# --------------------------------------------------------------------------- #
# El ciclo no revienta: se aparta
# --------------------------------------------------------------------------- #

def test_el_ciclo_no_abre_el_buzon_si_no_puede(ajustes, monkeypatch):
    ajustes(MAIL_MODE="imap")

    import app.main as main
    import app.rfq.horario as horario
    monkeypatch.setattr(horario, "abierto", lambda: True)

    from app.email.factory import EmailProviderFactory

    def prohibido():
        raise AssertionError("se intentó abrir el buzón sin poder")

    monkeypatch.setattr(EmailProviderFactory, "get_provider", prohibido)

    resultado = main.ciclo_deteccion()

    # Ni un error contado: esto no es un fallo, es un reparto de trabajo.
    assert resultado.errores == 0
    assert resultado.encontrados == 0
    # Y el porqué viaja con el resultado, para que la pantalla lo diga sin
    # que nadie abra el registro del servidor.
    assert any("no puede abrir el buzón" in d for d in resultado.detalles)


# --------------------------------------------------------------------------- #
# Apagado a propósito ≠ mal configurado
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("modo", ["ninguno", "none", "off", "apagado", "NINGUNO"])
def test_se_puede_decir_que_este_proceso_no_lee(ajustes, modo):
    ajustes(MAIL_MODE=modo)
    d = entrada.diagnostico_lectura()

    assert d["apagado"] is True
    assert d["puede"] is False
    # Vacío a propósito: no falta nada, está apagado. Decir que "faltan
    # credenciales" mandaría a buscar unas que nadie quiere poner.
    assert d["faltan"] == []


def test_apagado_se_dice_en_info_no_como_aviso(ajustes, caplog):
    """Marcar como problema algo que alguien eligió es la forma más rápida de
    que nadie vuelva a leer los avisos."""
    ajustes(MAIL_MODE="ninguno")
    with caplog.at_level("DEBUG"):
        for _ in range(10):
            entrada.avisar_una_vez(entrada.diagnostico_lectura())

    assert [r for r in caplog.records if r.levelname == "WARNING"] == []
    assert len([r for r in caplog.records if r.levelname == "INFO"]) == 1


def test_el_preflight_no_lo_marca_como_falta(ajustes):
    ajustes(MAIL_MODE="ninguno")
    import app.core.preflight as preflight

    class _Inf:
        def __init__(self):
            self.puntos = []
        def en(self, grupo): self.grupo = grupo
        def ok(self, t, d=""): self.puntos.append(("ok", t))
        def falta(self, t, d=""): self.puntos.append(("falta", t))
        def ojo(self, t, d=""): self.puntos.append(("ojo", t))

    inf = _Inf()
    preflight._buzon(inf, config.settings, con_buzon=False,
                     latido={"activo": False, "sabido": True, "hace": None})

    assert not [p for p in inf.puntos if p[0] == "falta"], inf.puntos
    assert any("a propósito" in t for estado, t in inf.puntos if estado == "ok")


def test_los_modos_de_verdad_siguen_sin_estar_apagados(ajustes):
    for modo in ("imap", "graph", "outlook"):
        ajustes(MAIL_MODE=modo)
        assert entrada.diagnostico_lectura()["apagado"] is False, modo
