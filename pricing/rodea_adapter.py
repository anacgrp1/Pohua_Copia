"""Adaptador de costeo — traduce los datos del resorte al esquema PN del motor.

Antes este módulo rellenaba el PN con constantes: precio de alambre 2.50 USD/lb
(con un ``TODO`` al lado), máquina «AIM 3000», 6 h de setup, 327 piezas/hora y
5 % de scrap, para **cualquier** resorte. El precio que salía de ahí no era el
de la pieza, era el de esa máquina imaginaria.

Ahora todo eso se lee del catálogo (``pricing/repository.py``) y lo que no está
en la base no se inventa: se reporta en ``faltantes`` y el precio se marca como
incompleto.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import pricing.mensajes as mensajes
from pricing import repository

log = logging.getLogger("cotizador.pricing.adapter")

# Descripción que espera el motor JS según el tipo de resorte.
_TIPO_A_DESC = {
    "compresion": "Compression Spring",
    "compression": "Compression Spring",
    "extension": "Tension Spring",
    "tension": "Tension Spring",
    "torsion": "Torsion Spring",
    "wireform": "Wire Form",
    "alambre": "Wire Form",
}

# Escalón vacío: el motor espera siempre cinco.
_TIER_VACIO = {"qty": None, "routing": [], "tooling": {}, "sub": {}, "packing": {}}


def _num(valor: Any) -> Optional[float]:
    """Convierte a float lo que se pueda; None si no es un número utilizable."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if numero == numero else None  # descarta NaN


# Densidad del alambre en lb/pulg³, por código de material.
#
# Copia EXACTA de WIRE_DENS de pricing/engine.js — mismas claves y mismos
# valores. No se añade ninguna que el motor no tenga: si aquí hubiera un
# material de más, el peso que calculamos y el que el motor habría calculado
# dejarían de coincidir para ese material, y el costo de materia prima saldría
# distinto según por dónde se mirara.
#
# (SS177 y 316 no están, igual que en el motor: caen al valor por defecto.
# Si en ISC miden una densidad distinta para los inoxidables, hay que
# añadirlas en LOS DOS sitios a la vez.)
_DENSIDAD_LB_IN3 = {
    "MW": .284, "CSI": .284, "HD": .284, "OT": .284, "GMW": .284,
    "GHD": .284, "SG": .284, "BB": .284,
    "SS": .286,
    "PHOSB": .320, "BRASS": .308, "HAST": .321,
}
_DENSIDAD_POR_DEFECTO = .284  # acero al carbono, igual que el motor


def longitud_desarrollada_pulg(spring_data: Dict[str, Any]) -> Optional[float]:
    """Longitud de alambre desarrollada, en pulgadas.

    Es ``π · Dm · Nt`` (diámetro medio por número total de espiras), la fórmula
    estándar para el cuerpo de un resorte helicoidal.  El diámetro medio se
    obtiene del que haya: medio, exterior menos un calibre, o interior más un
    calibre.

    Devuelve None si falta geometría.  No se estima: un peso inventado se
    convierte directamente en un costo de material inventado.

    Ojo: es la longitud del CUERPO.  En extensión no incluye los ganchos y en
    torsión no incluye las patas; ``build_pn_for_engine`` lo anota como
    faltante para esos dos tipos.
    """
    d = _num(spring_data.get("diametro_alambre_mm"))
    if not d or d <= 0:
        return None

    dm = _num(spring_data.get("diametro_medio_mm"))
    if not dm:
        od = _num(spring_data.get("diametro_exterior_mm"))
        idd = _num(spring_data.get("diametro_interior_mm"))
        if od:
            dm = od - d
        elif idd:
            dm = idd + d
    if not dm or dm <= 0:
        return None

    espiras = _num(spring_data.get("numero_espiras_totales"))
    if not espiras:
        # Con espiras activas se puede aproximar el total en compresión
        # (dos espiras de cierre), pero no en los demás tipos.
        activas = _num(spring_data.get("numero_espiras_activas"))
        tipo = str(spring_data.get("tipo_resorte") or "").lower()
        if activas and tipo.startswith("compres"):
            espiras = activas + 2
    if not espiras or espiras <= 0:
        return None

    import math
    return math.pi * (dm / 25.4) * espiras


def peso_alambre_lb(longitud_pulg: Optional[float], diametro_mm: Optional[float],
                    codigo_material: Optional[str]) -> Optional[float]:
    """Peso del alambre en libras: ``π/4 · d² · L · densidad``.

    Réplica exacta de ``wireFormWeight`` del motor JS, para que el peso que
    manda el adaptador sea el que el motor habría calculado.
    """
    if not longitud_pulg or not diametro_mm or longitud_pulg <= 0 or diametro_mm <= 0:
        return None
    import math
    d_pulg = diametro_mm / 25.4
    densidad = _DENSIDAD_LB_IN3.get(
        str(codigo_material or "").upper(), _DENSIDAD_POR_DEFECTO)
    return math.pi / 4 * d_pulg * d_pulg * longitud_pulg * densidad


def _cantidades(lista: Any, unica: Optional[float]) -> List[float]:
    """Las cantidades a costear, limpias, únicas, de menor a mayor, máximo 5."""
    fuera: List[float] = []
    for v in (lista if isinstance(lista, (list, tuple)) else []):
        n = _num(v)
        if n and n > 0 and n not in fuera:
            fuera.append(n)
    if not fuera and unica and unica > 0:
        fuera = [unica]
    return sorted(fuera)[:5]


def _tramo(cantidad: float, routing: List[Dict[str, Any]],
           empaque: Dict[str, Any]) -> Dict[str, Any]:
    """Un tramo del motor con su ruta y su empaque; lo demás en blanco."""
    return {
        "qty": cantidad,
        # Copia por tramo: el motor escribe dentro (`scrapWarn`, lotes) y dos
        # tramos compartiendo la misma lista se pisarían.
        "routing": [dict(op) for op in routing],
        "tooling": {"desc": "", "cost": None, "amortQty": None},
        "sub": {"supplier": "", "service": "", "minUsd": None, "perLb": None,
                "perPc": None, "partsPerBatch": None, "shareSkid": "NO"},
        "packing": {
            "id": empaque.get("codigo"),
            "qtyPerBox": empaque.get("piezas_por_caja"),
        },
    }


def build_pn_for_engine(
    rfq_id: str,
    spring_data: Dict[str, Any],
    conexion=None,
) -> Tuple[Dict[str, Any], repository.Catalogo]:
    """Construye el PN para el motor y devuelve también el catálogo consultado.

    Devuelve la tupla ``(pn, catalogo)``: el catálogo lleva la trazabilidad
    (``origen``) y la lista de datos que faltaban (``faltantes``), que la ruta
    HTTP adjunta a la respuesta para que quien la lea sepa cuánto se puede fiar
    del número.
    """
    tipo = str(spring_data.get("tipo_resorte") or "").strip().lower()
    desc = _TIPO_A_DESC.get(tipo, "Compression Spring")

    diam_mm = _num(spring_data.get("diametro_alambre_mm"))
    od_mm = _num(spring_data.get("diametro_exterior_mm"))
    cantidad = _num(spring_data.get("cantidad"))
    material_codigo = (spring_data.get("material") or "").strip() or None

    # Los tramos de cantidad. Un RFQ real casi nunca trae UNA cantidad: trae
    # "10,000, 25,000 y 50,000" y quiere precio para cada una. Se admiten
    # hasta cinco —los que tiene el motor— y se ordenan de menor a mayor,
    # que es como los lee el PM. Sin lista, se usa `cantidad` como único tramo.
    cantidades = _cantidades(spring_data.get("cantidades"), cantidad)

    catalogo = repository.cargar_catalogo(
        tipo_resorte=tipo or "compresion",
        material_codigo=material_codigo,
        diametro_alambre_mm=diam_mm,
        diametro_exterior_mm=od_mm,
        empaque_codigo=spring_data.get("empaque"),
        conexion=conexion,
    )

    if not cantidades:
        mensajes.falta(catalogo, "SIN_CANTIDAD")

    maquina = catalogo.maquina or {}
    material = catalogo.material or {}
    empaque = catalogo.empaque or {}
    params = catalogo.parametros or {}

    # scrap y markup salen de los parámetros versionados; si no hay juego
    # vigente se dejan en None y el motor aplica los suyos, pero queda anotado.
    scrap_pct = _num(params.get("scrapDefault"))
    markup_material = _num(params.get("matMk"))

    # Peso de alambre: sin él el motor calcula el material en 0 y el precio
    # sale sin la materia prima dentro, que suele ser el grueso del costo.
    dev_len = longitud_desarrollada_pulg(spring_data)
    peso_lb = peso_alambre_lb(dev_len, diam_mm, material.get("codigo") or material_codigo)
    if peso_lb is None:
        mensajes.falta(catalogo, "SIN_PESO_ALAMBRE")
    elif tipo.startswith(("extension", "tension", "torsion")):
        mensajes.falta(catalogo, "PESO_SOLO_CUERPO")

    routing = []
    if maquina:
        routing.append({
            "machine": maquina.get("nombre"),
            "family": maquina.get("familia") or "COILER",
            "setupH": maquina.get("horas_setup"),
            "pph": maquina.get("pph"),
            "laborH": maquina.get("horas_labor"),
            "machH": maquina.get("ccv_objetivo_h"),
            "tgtH": maquina.get("ccv_objetivo_h"),
            "ratio": maquina.get("multiplicador") or 1.0,
            "scrapPct": scrap_pct,
        })

    pn: Dict[str, Any] = {
        "pn": rfq_id,
        "desc": desc,
        "notes": "",
        "unit": "pc",
        "material": {
            # Sin material en catálogo se manda el código tal cual vino, para
            # que el motor lo señale, en lugar de sustituirlo por "MW".
            "code": material.get("codigo") or material_codigo,
            "diaIn": (diam_mm / 25.4) if diam_mm else None,
            "weightLb": peso_lb,
            "devLenIn": dev_len,
            "basePerLb": material.get("precio_lb"),
            "surchPerLb": material.get("surcharge_lb") or 0,
            "transpPerLb": _num(params.get("transpPerLb")) or 0,
            "mkPct": markup_material,
            "moqLb": None,
        },
        "components": [{"desc": "", "usd": None}, {"desc": "", "usd": None}],
        "consumable": {"desc": "", "usd": None},
        # Un tramo por cantidad, todos con la misma ruta: el RFQ no dice que
        # a 50,000 piezas se use otra máquina, así que no se inventa. Los que
        # sobran hasta cinco van vacíos, que es como el motor los ignora.
        "tiers": [
            _tramo(q, routing, empaque) if q is not None else dict(_TIER_VACIO)
            for q in (cantidades + [None] * 5)[:5]
        ],
        "selTier": 0,
        "opsTier": 0,
        "ohOverride": None,
        "remarks": "",
        "rev": "",
        "drawing": None,
        "springFeas": None,
    }

    if catalogo.faltantes:
        log.info("Costeo de %s incompleto (%d datos faltantes): %s",
                 rfq_id, len(catalogo.faltantes), "; ".join(catalogo.faltantes))

    return pn, catalogo


def overrides_de_parametros(parametros: Dict[str, Any],
                            representante: Optional[str] = None) -> Dict[str, Any]:
    """Traduce los parámetros de la base al ``ctx_overrides`` del motor JS.

    Sólo se mandan las claves que existan en la base: las demás las pone el
    motor con sus valores por omisión.

    ``representante`` es el vendedor asignado a la cuenta; el motor lo usa para
    decidir si aplica comisión. Antes venía escrito a mano en ``runner.js``, así
    que todas las cotizaciones salían a nombre de la misma persona.
    """
    overrides: Dict[str, Any] = {}
    if parametros:
        overrides["params"] = dict(parametros)
    if representante:
        overrides["rep"] = representante
    return overrides
