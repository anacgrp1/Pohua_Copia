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


# ---------------------------------------------------------------------------
# Cuando el plano no acota las espiras
# ---------------------------------------------------------------------------
#
# «O viene acotado o hay que preguntárselo al cliente» era demasiado tajante.
# Las espiras no siempre están escritas, pero muchas veces están IMPLÍCITAS en
# otras cotas que sí lo están, y sacarlas de ahí no es estimar: es la misma
# aritmética que saca el calibre de (OD - ID)/2.
#
# Tres caminos, de más fiable a menos:
#
#   1. ALTURA SÓLIDA. Es geometría pura y no necesita saber de qué material es
#      el resorte. Con los extremos esmerilados, todas las espiras se apoyan
#      unas sobre otras: Ls = Nt · d. Sin esmerilar, la punta del alambre deja
#      un calibre de más: Ls = (Nt + 1) · d.
#
#   2. PASO. También geometría. En extremos cerrados y esmerilados,
#      L0 = p · Na + 2d; sin esmerilar, L0 = p · Na + 3d. Se despeja Na y se
#      le suman las muertas de la tabla de arriba.
#
#   3. RIGIDEZ. k = G·d⁴ / (8·Dm³·Na), así que Na = G·d⁴ / (8·Dm³·k). Esta
#      NECESITA el módulo de cortante del material, y ahí está el problema:
#      el núcleo (ISCQuotingCore) ya tiene esa tabla y usarla aquí con otros
#      números repetiría el fallo de las espiras muertas —dos tablas que
#      divergen sin que nadie lo note—. Se deja el hueco preparado y la
#      decisión escrita, no una segunda tabla inventada.
#
# Lo que se saca por estos caminos queda MARCADO como calculado, con la
# fórmula y la cota de la que salió, para que quien aprueba vea de dónde
# viene. Un número deducido y uno leído del plano no valen lo mismo.

# Debajo de esto, un resultado no es un resorte: es un error de lectura.
_ESPIRAS_MINIMAS = 1.5
_ESPIRAS_MAXIMAS = 400.0


def _esmerilados(spring_data: Dict[str, Any]) -> bool:
    """¿Las puntas van rectificadas? Decide qué convención toca."""
    extremos = _normalizar(spring_data.get("tipo_extremos"))
    return any(p in extremos for p in
               ("ground", "esmerilado", "esmerilados",
                "rectificado", "rectificados"))


def _creible(n: Optional[float]) -> Optional[float]:
    """El resultado, si cae dentro de lo que puede ser un resorte."""
    if n is None:
        return None
    return n if _ESPIRAS_MINIMAS <= n <= _ESPIRAS_MAXIMAS else None


def totales_por_altura_solida(spring_data: Dict[str, Any]
                              ) -> Tuple[Optional[float], Optional[str]]:
    """Nt a partir de la altura sólida. Geometría pura, sin material.

    Es el camino bueno: la altura sólida se acota a menudo —es lo que hay que
    respetar en el hueco donde va el resorte— y no depende de ninguna
    constante del material.
    """
    ls = _num(spring_data.get("altura_solida_mm"))
    d = _num(spring_data.get("diametro_alambre_mm"))
    if not ls or not d or ls <= 0 or d <= 0:
        return None, None

    if _esmerilados(spring_data):
        nt = _creible(round(ls / d, 2))
        formula = f"solid height / wire = {ls:g} / {d:g}"
    else:
        nt = _creible(round(ls / d - 1, 2))
        formula = f"(solid height / wire) - 1 = ({ls:g} / {d:g}) - 1"
    if nt is None:
        return None, None
    return nt, f"{nt:g} total coils from the solid height ({formula})"


def totales_por_paso(spring_data: Dict[str, Any]
                     ) -> Tuple[Optional[float], Optional[str]]:
    """Nt a partir del paso y la longitud libre. También geometría pura.

    Menos útil en la práctica que la altura sólida, porque el paso se acota
    pocas veces; pero cuando está, sale exacto.
    """
    p = _num(spring_data.get("paso_mm"))
    l0 = _num(spring_data.get("longitud_libre_mm"))
    d = _num(spring_data.get("diametro_alambre_mm"))
    if not p or not l0 or not d or p <= 0 or l0 <= 0 or d <= 0:
        return None, None

    # Lo que ocupan los extremos cerrados dentro de la longitud libre.
    extremos_mm = 2 * d if _esmerilados(spring_data) else 3 * d
    activas = (l0 - extremos_mm) / p
    if activas <= 0:
        return None, None

    muertas, _ = espiras_muertas(spring_data)
    nt = _creible(round(activas + muertas, 2))
    if nt is None:
        return None, None
    return nt, (f"{nt:g} total coils from the pitch "
                f"(active = ({l0:g} - {extremos_mm:g}) / {p:g}, "
                f"plus {muertas:g} dead)")


def totales_por_rigidez(spring_data: Dict[str, Any],
                        modulo_cortante_psi: Optional[float] = None
                        ) -> Tuple[Optional[float], Optional[str]]:
    """Nt a partir de la constante del resorte. Necesita el material.

    ``Na = G · d⁴ / (8 · Dm³ · k)``.

    Se le pasa el módulo desde fuera a propósito: aquí NO vive una tabla de
    módulos. El núcleo ya tiene la suya y dos tablas de constantes del mismo
    material acaban divergiendo —es exactamente lo que pasó con las espiras
    muertas—. Mientras no haya una sola, esta función devuelve ``None`` y el
    camino queda documentado en vez de adivinado.
    """
    if not modulo_cortante_psi:
        return None, None

    k = _num(spring_data.get("constante_resorte_N_mm"))
    d = _num(spring_data.get("diametro_alambre_mm"))
    dm = _num(spring_data.get("diametro_medio_mm"))
    if not dm:
        od = _num(spring_data.get("diametro_exterior_mm"))
        if od and d:
            dm = od - d
    if not k or not d or not dm or k <= 0 or d <= 0 or dm <= 0:
        return None, None

    # Todo a pulgadas y libras, que es en lo que está el módulo.
    g = float(modulo_cortante_psi)
    d_in = d / 25.4
    dm_in = dm / 25.4
    k_lbf_in = k * 5.71014716                     # N/mm -> lbf/in

    activas = (g * d_in ** 4) / (8 * dm_in ** 3 * k_lbf_in)
    muertas, _ = espiras_muertas(spring_data)
    nt = _creible(round(activas + muertas, 2))
    if nt is None:
        return None, None
    return nt, (f"{nt:g} total coils from the spring rate "
                f"(active = G·d⁴ / (8·Dm³·k), plus {muertas:g} dead)")


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

    # En extensión las espiras del plano son las del cuerpo y se usan tal cual;
    # en torsión la fórmula del desarrollo es otra y las patas no se cuentan
    # aquí. Nada de lo que sigue vale fuera de compresión.
    if not es_compresion(spring_data):
        return None, None

    activas = _num(spring_data.get("numero_espiras_activas"))
    if activas and activas > 0:
        muertas, porque = espiras_muertas(spring_data)
        return activas + muertas, f"active coils + {porque}"

    # El plano no acota ni las totales ni las activas. Pero puede que las
    # tenga dichas de otra forma. Se prueban las vías por orden de fiabilidad;
    # la primera que dé un número creíble gana.
    for via in (totales_por_altura_solida, totales_por_paso):
        nt, porque = via(spring_data)
        if nt:
            return nt, porque

    return None, None
