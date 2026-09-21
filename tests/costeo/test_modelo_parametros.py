"""Un parámetro de más tumbaba tres cosas a la vez.

`temperature` dejó de aceptarse en los modelos recientes: devuelven un 400
«`temperature` is deprecated for this model» y la llamada entera se cae. Eso
se llevó por delante la lectura del plano —sin cotas el RFQ no salía
factible—, la extracción de datos del correo y el chat del asistente. Tres
síntomas que parecían tres problemas.
"""

import pytest

import app.core.modelo as modelo


class _Cliente:
    """Un modelo que rechaza los parámetros que se le digan."""

    def __init__(self, rechaza=(), mensaje=None):
        self.rechaza = set(rechaza)
        self.mensaje = mensaje or ("Error code: 400 - {'type': 'error', 'error': "
                                   "{'type': 'invalid_request_error', 'message': "
                                   "'`temperature` is deprecated for this model.'}}")
        self.llamadas = []
        self.messages = self

    def create(self, **kwargs):
        self.llamadas.append(dict(kwargs))
        sobra = self.rechaza & set(kwargs)
        if sobra:
            raise RuntimeError(self.mensaje)
        return {"ok": True}


@pytest.fixture(autouse=True)
def sin_memoria():
    modelo.olvidar_rechazos()
    yield
    modelo.olvidar_rechazos()


# --------------------------------------------------------------------------- #
# El caso real
# --------------------------------------------------------------------------- #

def test_se_quita_la_temperatura_y_se_reintenta():
    cliente = _Cliente(rechaza={"temperature"})
    r = modelo.crear_mensaje(cliente, model="claude-opus-4-8", max_tokens=100,
                             temperature=0.0, messages=[])

    assert r == {"ok": True}
    assert len(cliente.llamadas) == 2
    assert "temperature" in cliente.llamadas[0]
    assert "temperature" not in cliente.llamadas[1]
    # Y lo demás sigue igual: quitar uno no puede alterar la petición.
    assert cliente.llamadas[1]["max_tokens"] == 100
    assert cliente.llamadas[1]["model"] == "claude-opus-4-8"


def test_la_segunda_vez_ya_no_se_paga_la_llamada_fallida():
    cliente = _Cliente(rechaza={"temperature"})
    modelo.crear_mensaje(cliente, model="claude-opus-4-8", temperature=0.0)
    cliente.llamadas.clear()

    modelo.crear_mensaje(cliente, model="claude-opus-4-8", temperature=0.0)
    assert len(cliente.llamadas) == 1
    assert "temperature" not in cliente.llamadas[0]


def test_lo_aprendido_es_por_modelo():
    """Que uno lo rechace no dice nada del siguiente."""
    cliente = _Cliente(rechaza={"temperature"})
    modelo.crear_mensaje(cliente, model="claude-opus-4-8", temperature=0.0)

    otro = _Cliente()          # éste sí la acepta
    modelo.crear_mensaje(otro, model="claude-haiku-4-5-20251001", temperature=0.2)
    assert otro.llamadas[0]["temperature"] == 0.2


# --------------------------------------------------------------------------- #
# Lo que NO debe reintentar
# --------------------------------------------------------------------------- #

def test_un_400_por_otra_cosa_sube_tal_cual():
    """Reintentar sin un parámetro no arreglaría un contexto demasiado largo,
    y escondería el problema de verdad."""
    cliente = _Cliente(rechaza={"temperature"},
                       mensaje="Error code: 400 - prompt is too long")
    with pytest.raises(RuntimeError, match="too long"):
        modelo.crear_mensaje(cliente, model="x", temperature=0.0)
    assert len(cliente.llamadas) == 1      # no se reintentó


def test_un_valor_invalido_no_se_resuelve_quitando_el_parametro():
    """«temperature: must be <= 1» es un error de configuración: quitarlo lo
    taparía y nadie lo arreglaría nunca."""
    cliente = _Cliente(rechaza={"temperature"},
                       mensaje="Error code: 400 - temperature: must be <= 1")
    with pytest.raises(RuntimeError):
        modelo.crear_mensaje(cliente, model="x", temperature=5.0)
    assert len(cliente.llamadas) == 1


def test_no_se_quita_lo_que_no_se_puede_quitar():
    """Sin max_tokens la respuesta se corta: eso no es prescindible."""
    cliente = _Cliente(rechaza={"max_tokens"},
                       mensaje="Error code: 400 - max_tokens is deprecated")
    with pytest.raises(RuntimeError):
        modelo.crear_mensaje(cliente, model="x", max_tokens=10)
    assert len(cliente.llamadas) == 1


def test_si_falla_tambien_sin_el_parametro_el_error_sube():
    cliente = _Cliente(rechaza={"temperature", "max_tokens"},
                       mensaje="Error code: 400 - `temperature` is deprecated")
    # El segundo intento truena por max_tokens y ya no se reintenta más.
    with pytest.raises(RuntimeError):
        modelo.crear_mensaje(cliente, model="x", temperature=0.0, max_tokens=10)
    assert len(cliente.llamadas) == 2


# --------------------------------------------------------------------------- #
# Qué se manda por defecto
# --------------------------------------------------------------------------- #

def test_sin_temperatura_configurada_no_se_manda_nada():
    assert modelo.parametros_de_muestreo(None) == {}
    assert modelo.parametros_de_muestreo("") == {}
    assert modelo.parametros_de_muestreo("   ") == {}


def test_con_temperatura_configurada_se_manda():
    assert modelo.parametros_de_muestreo(0.0) == {"temperature": 0.0}
    assert modelo.parametros_de_muestreo("0.3") == {"temperature": 0.3}


def test_una_temperatura_ilegible_no_rompe_la_llamada():
    assert modelo.parametros_de_muestreo("tibia") == {}


def test_el_valor_por_defecto_de_la_configuracion_es_vacio():
    """Si volviera a 0.0, los modelos recientes volverían a fallar."""
    import app.core.config as config
    assert getattr(config.settings, "VISION_TEMPERATURE", "x") is None
