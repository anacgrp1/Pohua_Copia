"""«Inténtalo de nuevo» no sirve si el problema no se arregla reintentando.

El chat del asistente y la lectura del plano contestaban lo mismo pasara lo
que pasara. Con la cuenta sin saldo o la clave revocada, se podía pulsar cien
veces y fallar las cien, sin una pista de por qué. La causa estaba sólo en el
registro del servidor.
"""

import pytest

import app.core.modelo_errores as me


class _ErrorFalso(Exception):
    """Imita los errores de la librería: nombre de clase y status_code."""

    def __init__(self, mensaje="", estado=None, nombre=None):
        super().__init__(mensaje)
        if estado is not None:
            self.status_code = estado
        if nombre:
            self.__class__ = type(nombre, (_ErrorFalso,), {})


def _como(nombre, mensaje="", estado=None):
    clase = type(nombre, (Exception,), {})
    err = clase(mensaje)
    if estado is not None:
        err.status_code = estado
    return err


# --------------------------------------------------------------------------- #
# Lo que NO se arregla reintentando
# --------------------------------------------------------------------------- #

def test_sin_saldo_se_reconoce_aunque_llegue_como_peticion_mala():
    """Es el caso que más engaña: la API lo manda como 400
    invalid_request_error, así que sin mirar el texto mandaría a revisar el
    contexto cuando lo que hay que hacer es recargar."""
    err = _como("BadRequestError",
                "Your credit balance is too low to access the Claude API",
                estado=400)
    r = me.explicar(err)

    assert r["codigo"] == me.SIN_SALDO
    assert r["reintentar"] is False
    assert "saldo" in r["texto"].lower()


@pytest.mark.parametrize("nombre, estado, esperado", [
    ("AuthenticationError", 401, me.CLAVE_MALA),
    ("PermissionDeniedError", 403, me.SIN_PERMISO),
    ("NotFoundError", 404, me.NO_EXISTE),
    ("BadRequestError", 400, me.PETICION_MALA),
])
def test_lo_que_no_se_arregla_solo_se_dice_y_no_invita_a_reintentar(
        nombre, estado, esperado):
    r = me.explicar(_como(nombre, "algo", estado=estado))
    assert r["codigo"] == esperado
    assert r["reintentar"] is False


def test_un_modelo_retirado_manda_a_revisar_la_configuracion():
    r = me.explicar(_como("NotFoundError", "model not found", estado=404))
    assert "VISION_MODEL" in r["texto"]


# --------------------------------------------------------------------------- #
# Lo que sí se arregla solo
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("nombre, estado, esperado", [
    ("RateLimitError", 429, me.DEMASIADO),
    ("InternalServerError", 500, me.SATURADO),
    ("APIConnectionError", None, me.SIN_CONEXION),
    ("APITimeoutError", None, me.SIN_CONEXION),
])
def test_lo_pasajero_invita_a_reintentar(nombre, estado, esperado):
    r = me.explicar(_como(nombre, "algo", estado=estado))
    assert r["codigo"] == esperado
    assert r["reintentar"] is True


def test_el_529_de_saturacion_es_pasajero():
    r = me.explicar(_como("APIStatusError", "overloaded_error", estado=529))
    assert r["codigo"] == me.SATURADO
    assert r["reintentar"] is True


# --------------------------------------------------------------------------- #
# Sin tipo ni código: por el texto, y si no, genérico honesto
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("texto, esperado", [
    ("Error: overloaded", me.SATURADO),
    ("rate limit exceeded", me.DEMASIADO),
    ("authentication failed", me.CLAVE_MALA),
    ("Connection refused", me.SIN_CONEXION),
])
def test_sin_clase_conocida_se_mira_el_texto(texto, esperado):
    assert me.explicar(Exception(texto))["codigo"] == esperado


def test_lo_que_no_se_reconoce_no_se_inventa():
    """Inventar una causa es peor que admitir que no se sabe.

    Pero admitirlo no es quedarse callado: va el error de verdad detrás, que
    casi siempre basta para saber qué pasa sin abrir el registro.
    """
    r = me.explicar(Exception("algo rarísimo que nadie previó"))
    assert r["codigo"] == me.DESCONOCIDO
    assert "algo rarísimo que nadie previó" in r["texto"]
    assert r["reintentar"] is False


# --------------------------------------------------------------------------- #
# Lo que no puede salir a una pantalla
# --------------------------------------------------------------------------- #

def test_no_se_filtra_la_clave_ni_la_organizacion():
    err = _como("AuthenticationError",
                "invalid x-api-key: sk-ant-api03-SECRETO123 (org org-abc999)",
                estado=401)
    r = me.explicar(err)

    assert "sk-ant" not in r["texto"]
    assert "org-abc999" not in r["texto"]


def test_todos_los_codigos_tienen_texto():
    for codigo in (me.SIN_SALDO, me.CLAVE_MALA, me.SIN_PERMISO, me.NO_EXISTE,
                   me.DEMASIADO, me.SATURADO, me.PETICION_MALA,
                   me.SIN_CONEXION, me.DESCONOCIDO):
        assert me._TEXTOS[codigo].strip()


# --------------------------------------------------------------------------- #
# El detalle: sin él, «desconocido» manda a abrir el registro del servidor,
# que es justo la expedición que esto venía a evitar.
# --------------------------------------------------------------------------- #

def test_lo_desconocido_lleva_un_trozo_del_error_de_verdad():
    r = me.explicar(Exception("connection reset by peer while streaming"))
    assert r["codigo"] == me.DESCONOCIDO or r["codigo"] == me.SIN_CONEXION
    r2 = me.explicar(Exception("algo que nadie previó jamás"))
    assert "algo que nadie previó jamás" in r2["texto"]


def test_el_detalle_no_lleva_la_clave_ni_la_organizacion():
    r = me.explicar(Exception(
        "fallo con sk-ant-api03-SECRETO123 en org-abc999 "
        "para ana.ramirez@cgr-international.com (req_xyz789)"))
    for secreto in ("sk-ant", "org-abc999", "ana.ramirez", "req_xyz789"):
        assert secreto not in r["texto"], secreto
        assert secreto not in r["detalle"], secreto


def test_un_error_larguisimo_se_recorta():
    r = me.explicar(Exception("x" * 2000))
    assert len(r["detalle"]) <= 180


def test_una_respuesta_que_no_se_puede_leer_es_otro_problema():
    """El modelo contestó: eso no se arregla mirando la clave ni el saldo."""
    from app.vision.spring_extractor import ExtraccionError
    r = me.explicar(ExtraccionError("No se encontró ningún objeto JSON."))

    assert r["codigo"] == me.RESPUESTA_ILEGIBLE
    assert r["reintentar"] is False
    assert "JSON" in r["texto"]


def test_un_400_dice_cual_400_fue():
    r = me.explicar(Exception("Error code: 400 - prompt is too long: 250000 tokens"))
    assert r["codigo"] == me.PETICION_MALA
    assert "too long" in r["texto"]
