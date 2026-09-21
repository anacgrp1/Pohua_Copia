"""Qué decirle a quien está delante cuando la llamada al modelo falla.

Por qué existe
-------------
Las dos llamadas al modelo —el chat del asistente y la lectura del plano—
terminaban igual cuando algo iba mal: un mensaje de consuelo. «No se pudo
consultar el modelo. Inténtalo de nuevo.» Inténtalo de nuevo no sirve de nada
si lo que pasa es que la cuenta se quedó sin saldo o la clave es de otra
organización: se puede intentar cien veces y va a fallar las cien.

La causa sí estaba, pero sólo en el registro del servidor. Eso convierte cada
fallo en una expedición: entrar a Render, buscar el traceback, interpretarlo.

Aquí se traduce la excepción de la librería a una frase que dice qué pasó y
qué hacer. Lo que NO se traduce se sigue diciendo en genérico, porque inventar
una causa es peor que admitir que no se sabe.

Qué no sale de aquí
-------------------
Ni la clave, ni el identificador de la organización, ni el cuerpo entero de la
respuesta. El registro sigue teniendo el detalle completo —``log.exception``—;
esto es lo que se puede enseñar en una pantalla que alguien podría estar
compartiendo.
"""

from __future__ import annotations

import re
from typing import Any, Dict

# Código → qué decir. El código viaja aparte para que la web lo pueda traducir
# (frontend/js/i18n.js) y para poder distinguirlos sin leer el texto.
SIN_SALDO = "modelo_sin_saldo"
CLAVE_MALA = "modelo_clave_mala"
SIN_PERMISO = "modelo_sin_permiso"
NO_EXISTE = "modelo_no_existe"
DEMASIADO = "modelo_demasiadas_peticiones"
SATURADO = "modelo_saturado"
PETICION_MALA = "modelo_peticion_mala"
SIN_CONEXION = "modelo_sin_conexion"
DESCONOCIDO = "modelo_desconocido"

_TEXTOS = {
    SIN_SALDO: ("La cuenta de Anthropic se quedó sin saldo. Hay que recargarla "
                "en console.anthropic.com; reintentar no va a servir."),
    CLAVE_MALA: ("La clave ANTHROPIC_API_KEY no es válida o fue revocada. "
                 "Hay que poner una buena en el servidor."),
    SIN_PERMISO: ("La clave no tiene permiso para este modelo. Revisa a qué "
                  "organización pertenece y qué modelos tiene habilitados."),
    NO_EXISTE: ("El modelo configurado no existe o ya se retiró. Revisa "
                "LLM_MODEL y VISION_MODEL en el servidor."),
    DEMASIADO: ("Demasiadas peticiones seguidas. Espera un momento y vuelve a "
                "intentarlo: esto sí se arregla solo."),
    SATURADO: ("El modelo está saturado ahora mismo. Vuelve a intentarlo en un "
               "momento: esto sí se arregla solo."),
    PETICION_MALA: ("La petición al modelo no era válida. Suele ser que el "
                    "contexto creció demasiado; está en el registro."),
    SIN_CONEXION: ("No se pudo alcanzar la API de Anthropic desde el servidor. "
                   "Puede ser un corte pasajero o la salida a internet."),
    DESCONOCIDO: ("No se pudo consultar el modelo. El detalle está en el "
                  "registro del servidor."),
}

# Lo que dice el cuerpo del error de Anthropic cuando se acabó el saldo. Es un
# 400 con `invalid_request_error`, así que sin mirar el texto se confundiría
# con una petición mal montada —y mandaría a revisar el contexto cuando lo que
# hay que hacer es pagar—.
_SENAS_DE_SALDO = ("credit balance is too low", "insufficient credit",
                   "saldo", "billing")


def explicar(error: Exception) -> Dict[str, Any]:
    """Traduce la excepción a ``{codigo, texto, reintentar}``.

    ``reintentar`` dice si tiene sentido volver a pulsar el botón. Es la
    diferencia entre «espera un momento» y «esto no se va a arreglar solo».
    """
    codigo = _clasificar(error)
    return {
        "codigo": codigo,
        "texto": _TEXTOS[codigo],
        # Sólo lo pasajero: saturación, límite de ritmo y cortes de red.
        "reintentar": codigo in (DEMASIADO, SATURADO, SIN_CONEXION),
    }


def _clasificar(error: Exception) -> str:
    nombre = type(error).__name__
    texto = str(error).lower()
    estado = getattr(error, "status_code", None)

    # Primero lo que se reconoce por el texto, porque el saldo agotado llega
    # como un 400 genérico y hay que mirar dentro para no confundirlo.
    if any(sena in texto for sena in _SENAS_DE_SALDO):
        return SIN_SALDO

    # Por el tipo de la librería `anthropic`, que es lo más fiable cuando está.
    por_nombre = {
        "AuthenticationError": CLAVE_MALA,
        "PermissionDeniedError": SIN_PERMISO,
        "NotFoundError": NO_EXISTE,
        "RateLimitError": DEMASIADO,
        "BadRequestError": PETICION_MALA,
        "APIConnectionError": SIN_CONEXION,
        "APITimeoutError": SIN_CONEXION,
        "InternalServerError": SATURADO,
    }
    if nombre in por_nombre:
        return por_nombre[nombre]

    # Y si no, por el código de estado, que sobrevive aunque la librería
    # cambie los nombres de sus clases.
    por_estado = {401: CLAVE_MALA, 403: SIN_PERMISO, 404: NO_EXISTE,
                  429: DEMASIADO, 400: PETICION_MALA, 529: SATURADO}
    if isinstance(estado, int):
        if estado in por_estado:
            return por_estado[estado]
        if estado >= 500:
            return SATURADO

    # `str(error)` de la librería empieza por "Error code: 400 - {...}". Ese
    # número es la mejor pista cuando la excepción llega envuelta en otra y ya
    # no tiene ni su clase ni su `status_code` —que es justo lo que pasa
    # cuando el fallo cruza una capa—.
    en_el_texto = re.search(r"error code:\s*(\d{3})", texto)
    if en_el_texto:
        numero = int(en_el_texto.group(1))
        if numero in por_estado:
            return por_estado[numero]
        if numero >= 500:
            return SATURADO

    if "overloaded" in texto:
        return SATURADO
    if "rate limit" in texto:
        return DEMASIADO
    if "authentication" in texto or "invalid x-api-key" in texto:
        return CLAVE_MALA
    if "not_found" in texto or "model" in texto and "not found" in texto:
        return NO_EXISTE
    if "connection" in texto or "timed out" in texto or "timeout" in texto:
        return SIN_CONEXION

    return DESCONOCIDO
