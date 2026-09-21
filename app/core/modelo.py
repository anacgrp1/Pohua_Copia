"""Llamar al modelo sin mandarle parámetros que ya no acepta.

El caso
-------
``temperature`` dejó de aceptarse en los modelos recientes (Opus 4.7 en
adelante, Sonnet 4.6, la familia 5). No lo ignoran: devuelven un 400
``invalid_request_error`` con «`temperature` is deprecated for this model», y
la llamada entera se cae.

Aquí eso tumbó tres cosas a la vez, y las tres parecían problemas distintos:

* la lectura del plano —sin cotas, el RFQ no salía factible—,
* la extracción de datos del correo,
* el chat del asistente.

Tres síntomas, un parámetro.

Cómo se resuelve
----------------
No se mantiene una lista de qué modelo acepta qué: esa lista envejece sola y
el día que cambie otro parámetro volvemos aquí. En vez de eso, si la API
rechaza un parámetro por nombre, se quita ESE y se reintenta una vez. Y se
apunta para ese modelo, para no pagar la llamada fallida en cada intento.

Es deliberadamente estrecho: sólo reintenta cuando el error dice que el
parámetro sobra. Un 400 por cualquier otra cosa —el contexto demasiado largo,
un bloque mal armado— sube tal cual, porque reintentar sin un parámetro no lo
arreglaría y escondería el problema de verdad.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Set

log = logging.getLogger("cotizador.modelo")

# Lo que ya sabemos que este modelo rechaza, para no volver a intentarlo.
# Vive en memoria del proceso a propósito: si mañana el modelo vuelve a
# aceptarlo, basta con reiniciar y no hay que tocar una tabla.
_RECHAZADOS: Dict[str, Set[str]] = {}

# Los que se pueden quitar sin cambiar lo que se pide. `max_tokens` no está
# —sin él la respuesta se corta— ni `model`, ni `messages`.
_PRESCINDIBLES = ("temperature", "top_p", "top_k")


def _dice_que_sobra(error: Exception, parametro: str) -> bool:
    """¿El error se queja de ESE parámetro por estar de más?

    Se exige que aparezca el nombre Y una palabra de "sobra". Con sólo el
    nombre, un error de validación de su valor —fuera de rango— también
    casaría, y quitarlo sería tapar un error de configuración real.
    """
    texto = str(error).lower()
    if parametro not in texto:
        return False
    return any(pista in texto for pista in
               ("deprecated", "unsupported", "not supported", "no longer",
                "unexpected", "not permitted", "cannot be used"))


def crear_mensaje(cliente, **kwargs) -> Any:
    """``cliente.messages.create(**kwargs)``, quitando lo que el modelo rechace.

    Devuelve la respuesta tal cual. Lanza lo que lance la librería salvo el
    caso concreto de un parámetro de más, que se resuelve reintentando sin él.
    """
    modelo = str(kwargs.get("model") or "")

    # Lo que ya se sabe que sobra en este modelo, fuera antes de salir.
    for parametro in _RECHAZADOS.get(modelo, ()):
        kwargs.pop(parametro, None)

    try:
        return cliente.messages.create(**kwargs)
    except Exception as error:
        sobra = next((p for p in _PRESCINDIBLES
                      if p in kwargs and _dice_que_sobra(error, p)), None)
        if sobra is None:
            raise

        log.warning("El modelo %s no acepta '%s': se quita y se reintenta. "
                    "Quítalo también de la configuración para ahorrarte esta "
                    "llamada.", modelo or "(sin nombre)", sobra)
        _RECHAZADOS.setdefault(modelo, set()).add(sobra)
        kwargs.pop(sobra, None)
        return cliente.messages.create(**kwargs)


def parametros_de_muestreo(temperatura=None) -> Dict[str, Any]:
    """Los parámetros de muestreo que toca mandar, si es que toca alguno.

    Vacío cuando no hay temperatura configurada, que es lo normal ahora: los
    modelos recientes no la aceptan, y para lo que se les pide aquí —leer un
    plano y devolver JSON— su comportamiento por defecto es el que se quiere.
    Mandar un parámetro "por si acaso" es justo lo que rompió la lectura.
    """
    if temperatura is None or str(temperatura).strip() == "":
        return {}
    try:
        return {"temperature": float(temperatura)}
    except (TypeError, ValueError):
        log.warning("Temperatura ilegible (%r): no se manda.", temperatura)
        return {}


def olvidar_rechazos() -> None:
    """Limpia lo aprendido. Para las pruebas; en producción no hace falta."""
    _RECHAZADOS.clear()
