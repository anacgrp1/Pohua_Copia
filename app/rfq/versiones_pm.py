"""Las versiones de la cotización que el PM deja en la calculadora.

El PM corrige en la calculadora completa y vuelve a la ventana de revisión con
esos números (``datos_json.cotizacion_pm``). Pero corregir es probar: pone un
precio, vuelve, no le convence, prueba otro… y hasta ahora sólo quedaba el
último. Si quería regresar a lo de hace un rato tenía que volver a teclearlo
de memoria.

Aquí se guardan las versiones y se elige entre ellas. Tres ideas:

* **Una versión es lo que el PM trae de vuelta**, no cada tecla. La
  calculadora guarda sola cada segundo y medio mientras se escribe; eso
  actualiza la versión EN CURSO (``fijada = False``). Al pulsar «Volver a la
  revisión» la versión se fija y pasa al historial. El siguiente cambio abre
  una nueva. Así el historial tiene las versiones que el PM llegó a mirar,
  no doscientas intermedias.
* **Lo que no cambia no es una versión nueva.** Reabrir la calculadora la
  hace guardar aunque nadie toque nada; si lo guardado es igual a lo que ya
  había (mismo PN, mismos precios), no pasa nada.
* **Elegir una versión la vuelve la actual** —la ventana y la oferta usan
  ésa— y le deja una marca (``pm_restauracion``) para que la calculadora, la
  próxima vez que se abra, cargue ESA versión en vez de su último borrador.
  Si no, las dos pantallas dirían cosas distintas. También se puede volver
  al cálculo del sistema sin perder las versiones.

Funciones puras: reciben ``datos_json`` y devuelven los cambios que hay que
escribir (clave → valor, ``None`` = quitar). Quien llama los escribe.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, List, Optional

# Se guardan como mucho estas versiones fijadas; las más viejas se van. Cada
# una lleva el PN entero y el resultado del motor (unos KB), y un RFQ que se
# cotiza cuarenta veces no necesita las cuarenta.
MAX_VERSIONES = 20

CLAVE_ACTUAL = "cotizacion_pm"
CLAVE_VERSIONES = "cotizacion_pm_versiones"
CLAVE_RESTAURACION = "pm_restauracion"


def _num(v) -> Optional[float]:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def precios(cotizacion: dict) -> List[Optional[float]]:
    """El precio por pieza de cada tramo calculado, en orden."""
    tiers = ((cotizacion or {}).get("resultado") or {}).get("tiers") or []
    return [_num(t.get("sell")) for t in tiers if isinstance(t, dict)]


def cantidades(cotizacion: dict) -> List[Optional[float]]:
    tiers = ((cotizacion or {}).get("resultado") or {}).get("tiers") or []
    return [_num(t.get("qty")) for t in tiers if isinstance(t, dict)]


def huella(cotizacion: dict) -> str:
    """Lo que hace distinta a una cotización de otra: el PN y sus precios.

    No entran quién ni cuándo: la misma hoja guardada dos veces es la misma
    versión.
    """
    c = cotizacion or {}
    carga = {"pn": c.get("pn"), "precios": precios(c), "contribution": c.get("contribution")}
    texto = json.dumps(carga, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()


def _versiones(datos: dict) -> List[dict]:
    v = (datos or {}).get(CLAVE_VERSIONES)
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _siguiente(datos: dict) -> int:
    ns = [int(x.get("n") or 0) for x in _versiones(datos)]
    actual = (datos or {}).get(CLAVE_ACTUAL) or {}
    if isinstance(actual, dict) and actual.get("n"):
        ns.append(int(actual["n"]))
    return (max(ns) if ns else 0) + 1


def _fijar(versiones: List[dict], version: dict) -> List[dict]:
    """Mete (o reemplaza) la versión en el historial, sin pasar del tope."""
    fuera = [x for x in versiones if x.get("n") != version.get("n")]
    fuera.append(version)
    fuera.sort(key=lambda x: int(x.get("n") or 0))
    return fuera[-MAX_VERSIONES:]


def registrar(datos: dict, nueva: dict, motivo: str = "guardado") -> Optional[Dict[str, Any]]:
    """Lo que la calculadora mandó, dentro del historial.

    ``motivo`` es ``"guardado"`` (el guardado automático mientras se escribe)
    o ``"volver"`` (el PM pulsó «Volver a la revisión»: se fija la versión).

    Devuelve los cambios a escribir, o ``None`` si no hay nada que cambiar.
    """
    datos = datos or {}
    actual = datos.get(CLAVE_ACTUAL) if isinstance(datos.get(CLAVE_ACTUAL), dict) else None
    fijar = motivo == "volver"
    igual = actual is not None and huella(actual) == huella(nueva)

    if igual:
        if not fijar or actual.get("fijada"):
            return None                       # nada nuevo que guardar
        version = dict(actual, fijada=True)
    elif actual is not None and not actual.get("fijada") and actual.get("n"):
        # La versión en curso se sigue escribiendo: mismo número.
        version = dict(nueva, n=actual["n"], fijada=fijar)
    else:
        version = dict(nueva, n=_siguiente(datos), fijada=fijar)

    cambios: Dict[str, Any] = {CLAVE_ACTUAL: version}
    if fijar:
        cambios[CLAVE_VERSIONES] = _fijar(_versiones(datos), _para_historial(version))
    return cambios


def _para_historial(version: dict) -> dict:
    return copy.deepcopy(version)


def restaurar(datos: dict, n: Optional[int], usuario: str, ahora: str) -> Dict[str, Any]:
    """Vuelve actual la versión ``n``; con ``n=None``, el cálculo del sistema.

    Lanza ``KeyError`` si la versión no existe.
    """
    datos = datos or {}
    marca = {"en": ahora, "por": usuario, "version": n}
    if n is None:
        cambios: Dict[str, Any] = {CLAVE_ACTUAL: None, CLAVE_RESTAURACION: marca}
        actual = datos.get(CLAVE_ACTUAL)
        # La versión en curso sin fijar se guarda antes de soltarla: el PM la
        # trajo de la calculadora y podría querer volver a ella.
        if isinstance(actual, dict) and actual.get("n") and not actual.get("fijada"):
            cambios[CLAVE_VERSIONES] = _fijar(_versiones(datos),
                                              dict(actual, fijada=True))
        return cambios

    elegida = next((x for x in _versiones(datos) if int(x.get("n") or 0) == int(n)), None)
    if elegida is None:
        raise KeyError(n)
    version = dict(copy.deepcopy(elegida), fijada=True, restaurada_en=ahora,
                   restaurada_por=usuario)
    cambios = {CLAVE_ACTUAL: version, CLAVE_RESTAURACION: marca}
    actual = datos.get(CLAVE_ACTUAL)
    if isinstance(actual, dict) and actual.get("n") and not actual.get("fijada") \
            and actual.get("n") != elegida.get("n"):
        cambios[CLAVE_VERSIONES] = _fijar(_versiones(datos), dict(actual, fijada=True))
    return cambios


def resumen(datos: dict) -> Dict[str, Any]:
    """Lo que la ventana enseña para elegir: las versiones, sin el PN entero."""
    datos = datos or {}
    actual = datos.get(CLAVE_ACTUAL) if isinstance(datos.get(CLAVE_ACTUAL), dict) else None
    lista = _versiones(datos)
    if actual and actual.get("n") and not any(x.get("n") == actual.get("n") for x in lista):
        lista = lista + [actual]                # la en curso, todavía sin fijar
    en_uso = actual.get("n") if actual else None
    filas = []
    for v in sorted(lista, key=lambda x: int(x.get("n") or 0), reverse=True):
        es_actual = v.get("n") == en_uso
        fuente = actual if es_actual else v
        filas.append({
            "n": v.get("n"),
            "por": fuente.get("por"),
            "en": fuente.get("en"),
            "numero": (fuente.get("cabecera") or {}).get("numero"),
            "precios": precios(fuente),
            "cantidades": cantidades(fuente),
            "contribution": _num(fuente.get("contribution")),
            "fijada": bool(fuente.get("fijada")),
            "en_uso": es_actual,
        })
    return {"versiones": filas, "en_uso": en_uso,
            "sistema_en_uso": actual is None}


def pn_restaurado(datos: dict) -> Optional[Dict[str, Any]]:
    """Qué tiene que cargar la calculadora tras una restauración, si hubo una.

    ``{"en", "version", "pn"}``: con ``version`` el PN de esa versión; sin
    ella (``None``) la calculadora vuelve al PN del sistema, que ya le llega
    como ``pn`` normal.
    """
    marca = (datos or {}).get(CLAVE_RESTAURACION)
    if not isinstance(marca, dict) or not marca.get("en"):
        return None
    actual = (datos or {}).get(CLAVE_ACTUAL) or {}
    pn = actual.get("pn") if marca.get("version") is not None else None
    return {"en": marca["en"], "version": marca.get("version"), "pn": pn}
