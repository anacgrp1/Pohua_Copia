# -*- coding: utf-8 -*-
"""De espiras activas a espiras totales, con las muertas que toquen.

Por qué existe
--------------
El peso del alambre es ``π · Dm · Nt`` por la sección, así que necesita las
espiras TOTALES. Muchos planos acotan sólo las ACTIVAS, que son las que mandan
en la rigidez.

Aquí se pasaba de unas a otras sumando 2 y ya: ``activas + 2``, escrito dos
veces —en ``falta_para_el_peso`` y en ``longitud_desarrollada_pulg``— y sin
mirar el tipo de extremo. Eso es correcto sólo para extremos cerrados. Para
unos extremos planos el total ES el número de activas, y sumarle dos espiras
infla el peso y con él el precio.

El núcleo (ISCQuotingCore) ya resuelve esto con una tabla por tipo de extremo,
y el Spring Calculator RESTA esas mismas para volver a las activas. Si las dos
tablas no son idénticas, el resorte sale desplazado una espira sin que nadie lo
note: ahí se estropeó antes «planos y esmerilados», donde el lector descontaba
0 y la calculadora 1.

Por eso esto vive en un archivo propio y no suelto dentro del adaptador: es la
tabla, una sola, y quien la cambie ve al lado la advertencia de que hay otra
copia que tiene que cambiar con ella.

    Extremos                        Muertas   Totales
    Cerrados (esmerilados o no)        2       Na + 2
    Planos y esmerilados               1       Na + 1
    Planos                             0       Na

Sólo compresión. En extensión el número del plano ya son las espiras del
cuerpo y se usa tal cual —no hay espiras muertas—; en torsión la fórmula es
otra.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Optional, Tuple

# La tabla. Tiene que ser la misma que la del Spring Calculator.
CERRADOS = 2.0
PLANOS_ESMERILADOS = 1.0
PLANOS = 0.0

# Cuando el plano no dice qué extremos lleva. Es lo más común en resortes de
# compresión, y es lo que la planta hace por defecto; se supone, pero se dice
# que se supuso, porque dos espiras son peso real.
MUERTAS_POR_DEFECTO = CERRADOS

_SIN_EXTREMOS = ("el plano no dice el tipo de extremos: se suponen cerrados "
                 "(2 espiras muertas)")


def _normalizar(texto: Any) -> str:
    """Minúsculas, sin acentos y con un solo espacio entre palabras."""
    s = unicodedata.normalize("NFKD", str(texto or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _num(v) -> Optional[float]:
    try:
        n = float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return n


def espiras_muertas(spring_data: Dict[str, Any]) -> Tuple[float, str]:
    """Cuántas espiras no trabajan, y de dónde sale ese número.

    Devuelve ``(muertas, explicación)``. La explicación viaja hasta la pantalla
    porque un total CALCULADO y uno LEÍDO del plano no valen lo mismo, y quien
    aprueba tiene derecho a saber cuál está mirando.

    El orden no es casual: lo que el plano diga gana siempre a la tabla. Si
    alguien se tomó la molestia de acotar las espiras muertas, es porque ese
    resorte no sigue la convención.
    """
    # 1. El plano lo dice en total.
    dichas = _num(spring_data.get("espiras_muertas_totales"))
    if dichas is not None and dichas >= 0:
        return dichas, f"{dichas:g} dead coils stated on the drawing"

    # 2. El plano lo dice por extremo.
    por_extremo = _num(spring_data.get("espiras_muertas_por_extremo"))
    if por_extremo is not None and por_extremo >= 0:
        total = por_extremo * 2
        return total, (f"{total:g} dead coils "
                       f"({por_extremo:g} per end, stated on the drawing)")

    # 3. La tabla, según los extremos que declare el plano.
    extremos = _normalizar(spring_data.get("tipo_extremos"))
    if not extremos:
        return MUERTAS_POR_DEFECTO, _SIN_EXTREMOS

    # "squared" es lo mismo que "closed", y "open" lo mismo que "plain": los
    # planos usan las cuatro palabras indistintamente.
    cerrado = any(p in extremos for p in
                  ("closed", "squared", "square", "cerrado", "cerrados",
                   "cuadrado", "cuadrados"))
    plano = any(p in extremos for p in
                ("plain", "open", "plano", "planos", "abierto", "abiertos"))
    esmerilado = any(p in extremos for p in
                     ("ground", "esmerilado", "esmerilados", "rectificado",
                      "rectificados"))

    # Cerrado manda sobre plano: "closed and ground" lleva las dos palabras y
    # las muertas son 2, no 1.
    if cerrado:
        cual = "closed ground" if esmerilado else "closed"
        return CERRADOS, (f"{CERRADOS:g} dead coils, from the end type stated "
                          f"on the drawing ({cual})")
    if plano:
        if esmerilado:
            return PLANOS_ESMERILADOS, (
                f"{PLANOS_ESMERILADOS:g} dead coil, from the end type stated "
                f"on the drawing (plain ground)")
        return PLANOS, ("no dead coils, from the end type stated on the "
                        "drawing (plain)")

    # Dice algo, pero no algo que se reconozca. No se inventa: se trata como si
    # no lo dijera, y se avisa con el texto tal cual para que se pueda añadir.
    return MUERTAS_POR_DEFECTO, (
        f"{_SIN_EXTREMOS}; the drawing says "
        f"\"{str(spring_data.get('tipo_extremos')).strip()}\", "
        f"which is not a recognised end type")


def es_compresion(spring_data: Dict[str, Any]) -> bool:
    tipo = _normalizar(spring_data.get("tipo_resorte"))
    return tipo.startswith("compres")


def espiras_totales(spring_data: Dict[str, Any]) -> Tuple[Optional[float], Optional[str]]:
    """Las espiras totales que hay que usar para el peso, y cómo se supieron.

    Devuelve ``(totales, explicación)``. La explicación es ``None`` cuando el
    número venía leído del plano: no hay nada que explicar.

    Devuelve ``(None, None)`` cuando no se puede saber, que es exactamente
    cuando NO hay que cotizar. Aquí no se estima: un peso inventado se
    convierte en un costo de material inventado, y ése sí viaja hasta la oferta
    sin que nadie lo vuelva a mirar.
    """
    totales = _num(spring_data.get("numero_espiras_totales"))
    if totales and totales > 0:
        return totales, None

    activas = _num(spring_data.get("numero_espiras_activas"))
    if not activas or activas <= 0:
        return None, None

    # En extensión las espiras del plano son las del cuerpo y se usan tal cual;
    # en torsión la fórmula del desarrollo es otra y las patas no se cuentan
    # aquí. Sumar extremos en cualquiera de los dos sería inventar alambre.
    if not es_compresion(spring_data):
        return None, None

    muertas, porque = espiras_muertas(spring_data)
    return activas + muertas, f"active coils + {porque}"
