"""¿Puede este proceso mandar un correo, y si no, qué le falta?

El fallo real: el PM pulsaba «Enviar oferta», se generaba el PDF y sólo
entonces saltaba «No hay cuenta emisora configurada (SMTP_USER / IMAP_USER)»
—los nombres de SMTP— aunque el modo activo fuera otro. Estas pruebas cubren
que el diagnóstico nombre el modo activo y SUS variables, que no toque la red,
y que el envío falle antes de abrir nada.
"""

import pytest

import app.core.config as config
import app.email.outbound as outbound


CLAVES = ("MAIL_MODE", "IMAP_USER", "IMAP_PASSWORD", "SMTP_USER",
          "SMTP_PASSWORD", "GRAPH_USER", "AZURE_TENANT_ID",
          "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET")


@pytest.fixture
def ajustes(monkeypatch):
    """Configuración en blanco: sin esto, el .env de quien corre las pruebas
    decide el resultado y la prueba pasa o falla según la máquina."""
    for clave in CLAVES:
        monkeypatch.setattr(config.settings, clave, "", raising=False)

    def poner(**valores):
        for clave, valor in valores.items():
            monkeypatch.setattr(config.settings, clave, valor, raising=False)
    return poner


# --------------------------------------------------------------------------- #
# SMTP / IMAP
# --------------------------------------------------------------------------- #

def test_sin_credenciales_no_se_puede_mandar(ajustes):
    ajustes(MAIL_MODE="imap")
    d = outbound.diagnostico_envio()

    assert d["canal"] == "smtp"
    assert d["puede"] is False
    # Nombra las dos parejas: con MAIL_MODE=imap lo natural es poner las de
    # IMAP, y mandar a crear SMTP_USER sería mandar a crear algo que sobra.
    assert any("IMAP_USER" in f for f in d["faltan"])
    assert any("IMAP_PASSWORD" in f for f in d["faltan"])


def test_las_credenciales_del_buzon_sirven_para_mandar(ajustes):
    ajustes(MAIL_MODE="imap", IMAP_USER="ventas@cgr.com", IMAP_PASSWORD="x")
    d = outbound.diagnostico_envio()

    assert d["puede"] is True
    assert d["faltan"] == []


def test_con_usuario_pero_sin_contrasena_falta_la_contrasena(ajustes):
    ajustes(MAIL_MODE="imap", IMAP_USER="ventas@cgr.com")
    d = outbound.diagnostico_envio()

    assert d["puede"] is False
    assert len(d["faltan"]) == 1
    assert "PASSWORD" in d["faltan"][0]


# --------------------------------------------------------------------------- #
# Graph
# --------------------------------------------------------------------------- #

def test_graph_sin_nada_pide_las_cuatro(ajustes):
    ajustes(MAIL_MODE="graph")
    d = outbound.diagnostico_envio()

    assert d["canal"] == "graph"
    assert d["puede"] is False
    assert d["faltan"] == ["AZURE_TENANT_ID", "AZURE_CLIENT_ID",
                           "AZURE_CLIENT_SECRET", "GRAPH_USER"]
    # Ni una palabra de SMTP: ahí no pinta nada.
    assert "SMTP" not in " ".join(d["faltan"])


def test_graph_completo_puede_mandar(ajustes):
    ajustes(MAIL_MODE="graph", AZURE_TENANT_ID="t", AZURE_CLIENT_ID="c",
            AZURE_CLIENT_SECRET="s", GRAPH_USER="ventas@cgr.com")
    d = outbound.diagnostico_envio()

    assert d["puede"] is True
    assert d["faltan"] == []


def test_graph_acepta_el_buzon_de_imap_como_emisor(ajustes):
    """Es la misma cuenta; obligar a duplicarla en GRAPH_USER sería ruido."""
    ajustes(MAIL_MODE="graph", AZURE_TENANT_ID="t", AZURE_CLIENT_ID="c",
            AZURE_CLIENT_SECRET="s", IMAP_USER="ventas@cgr.com")
    assert outbound.diagnostico_envio()["puede"] is True


def test_graph_sin_buzon_lo_dice(ajustes):
    ajustes(MAIL_MODE="graph", AZURE_TENANT_ID="t", AZURE_CLIENT_ID="c",
            AZURE_CLIENT_SECRET="s")
    d = outbound.diagnostico_envio()

    assert d["puede"] is False
    assert d["faltan"] == ["GRAPH_USER"]


# --------------------------------------------------------------------------- #
# Outlook de escritorio
# --------------------------------------------------------------------------- #

def test_outlook_en_un_servidor_linux_no_puede(ajustes, monkeypatch):
    """MAIL_MODE=outlook en Render no es una configuración a medias: es una
    que no puede funcionar, y decirlo ahorra buscar credenciales que no hay."""
    ajustes(MAIL_MODE="outlook")
    monkeypatch.setattr("sys.platform", "linux")
    d = outbound.diagnostico_envio()

    assert d["canal"] == "outlook"
    assert d["puede"] is False
    assert "graph" in d["nota"].lower()


def test_outlook_en_windows_si_puede(ajustes, monkeypatch):
    ajustes(MAIL_MODE="outlook")
    monkeypatch.setattr("sys.platform", "win32")
    d = outbound.diagnostico_envio()

    assert d["puede"] is True
    assert d["faltan"] == []


# --------------------------------------------------------------------------- #
# enviar() falla antes de abrir nada
# --------------------------------------------------------------------------- #

def test_enviar_sin_cuenta_falla_nombrando_el_modo(ajustes):
    ajustes(MAIL_MODE="graph")
    with pytest.raises(outbound.SinCuentaEmisora) as err:
        outbound.enviar({"destinatario": "a@b.com", "asunto": "x",
                         "cuerpo_texto": "y"})

    assert err.value.modo == "graph"
    assert "AZURE_TENANT_ID" in err.value.faltan
    assert "GRAPH" in str(err.value)


def test_enviar_no_llega_al_transporte_sin_cuenta(ajustes, monkeypatch):
    """Si llegara, el error sería el del transporte y no diría qué poner."""
    ajustes(MAIL_MODE="imap")
    llamadas = []
    import app.email.smtp_sender as smtp_sender
    monkeypatch.setattr(smtp_sender, "enviar_correo_smtp",
                        lambda *a, **k: llamadas.append(1))

    with pytest.raises(outbound.SinCuentaEmisora):
        outbound.enviar({"destinatario": "a@b.com", "asunto": "x",
                         "cuerpo_texto": "y"})
    assert llamadas == []


def test_con_cuenta_si_llega_al_transporte(ajustes, monkeypatch):
    ajustes(MAIL_MODE="imap", IMAP_USER="ventas@cgr.com", IMAP_PASSWORD="x")
    import app.email.smtp_sender as smtp_sender
    monkeypatch.setattr(smtp_sender, "enviar_correo_smtp", lambda *a, **k: True)

    assert outbound.enviar({"destinatario": "a@b.com", "asunto": "x",
                            "cuerpo_texto": "y"}) is True


# --------------------------------------------------------------------------- #
# El diagnóstico es barato: se llama al pintar la pantalla
# --------------------------------------------------------------------------- #

def test_el_diagnostico_no_toca_la_red(ajustes, monkeypatch):
    ajustes(MAIL_MODE="graph", AZURE_TENANT_ID="t", AZURE_CLIENT_ID="c",
            AZURE_CLIENT_SECRET="s", GRAPH_USER="ventas@cgr.com")
    import socket

    def prohibido(*a, **k):
        raise AssertionError("el diagnóstico abrió una conexión")

    monkeypatch.setattr(socket.socket, "connect", prohibido)
    monkeypatch.setattr(socket, "create_connection", prohibido)

    assert outbound.diagnostico_envio()["puede"] is True
