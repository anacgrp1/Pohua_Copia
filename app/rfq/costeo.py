"""Costeo por tramos de un RFQ, con el motor y el catálogo de Neon.

Lo usan la ventana de revisión del PM (``GET /api/rfqs/{id}/revision``) y la
oferta al cliente (``app.rfq.oferta``): los dos tienen que enseñar EL MISMO
número, así que el costeo vive aquí y no en ninguna de las dos rutas.

El costeo se hace en el momento y no se guarda: es una foto para dictaminar o
para ofertar, y si el catálogo cambia mañana, mañana sale otra. Lo que sí se
dice siempre es cuánto se puede fiar uno del número: ``costeo.completo`` y
``costeo.faltantes`` vienen del catálogo, y si faltó el precio del alambre o la
tarifa de la máquina, el número es orientativo y quien lo pinta lo marca.
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger("cotizador.rfq.costeo")


def num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def cantidades_del_rfq(datos: dict) -> list:
    """Las cantidades pedidas: los escalones del correo, o el volumen suelto."""
    escalones = datos.get("escalones_cantidad")
    if isinstance(escalones, str):
        # El modelo a veces devuelve "10,000, 25000 y 50.000" como texto: primero
        # se quitan los separadores de miles (coma o punto seguido de tres
        # cifras) y después se recogen los números que queden.
        limpio = re.sub(r"(?<=\d)[,.](?=\d{3}(?!\d))", "", escalones)
        escalones = re.findall(r"\d+(?:\.\d+)?", limpio)
    fuera = []
    for v in (escalones if isinstance(escalones, list) else []):
        n = num(str(v).replace(",", "")) if v not in (None, "") else None
        if n and n > 0 and n not in fuera:
            fuera.append(n)
    if not fuera:
        n = num(str(datos.get("volumen") or "").replace(",", ""))
        if n and n > 0:
            fuera = [n]
    return sorted(fuera)[:5]


def tramo_para_ventana(t: dict, objetivo_pct) -> dict:
    """Traduce un tramo del motor a lo que dibuja la ventana."""
    pnl = t.get("pnl") or {}
    sell = num(t.get("sell"))
    resultado = num(pnl.get("result"))
    resultado_pct = (resultado / sell * 100) if (sell and resultado is not None) else None
    ruta = []
    for op in (t.get("routing") or []):
        if not op or not op.get("machine"):
            continue
        ruta.append({"maquina": op.get("machine"), "pph": num(op.get("pph")),
                     "setup_h": num(op.get("setupH"))})
    return {
        "cantidad": num(t.get("qty")),
        "precio_pc": sell,
        "resultado_pct": resultado_pct,
        "objetivo_pct": objetivo_pct,
        # Verde cuando llega al objetivo; ámbar si queda por debajo o hay
        # aviso. Se decide aquí para que compu y teléfono lo pinten igual.
        "llega": (resultado_pct is not None and objetivo_pct is not None
                  and resultado_pct + 0.05 >= objetivo_pct),
        "cascada": {
            "sell": sell,
            "av": num(pnl.get("av")), "av_pct": num(pnl.get("avPct")),
            "ccv": num(pnl.get("ccv")), "ccv_pct": num(pnl.get("ccvPct")),
            "ccd": num(pnl.get("ccd")), "ccd_pct": num(pnl.get("ccdPct")),
            "resultado": resultado, "resultado_pct": resultado_pct,
        },
        "material": {
            "pc": num(t.get("mat")),
            "pct": (num(t.get("mat")) / sell * 100) if (sell and num(t.get("mat")) is not None) else None,
            "lb_comprar": num(t.get("lbBuy")),
            "moq_manda": bool(t.get("moqBind")),
        },
        "ruta": ruta,
        "totales": {
            "ingreso": num(t.get("revenue")),
            "horas": num(t.get("hours")),
            "ccv_hora": num(pnl.get("ccvHr")),
        },
        "avisos": {
            "scrap": bool(t.get("scrapWarn")),
            "bajo_piso": bool(t.get("belowFloor")),
            "bajo_contribucion": bool(t.get("belowContrib")),
        },
    }




def costear(rfq_id: str, datos: dict, resorte: dict, material_rfq=None) -> dict:
    """Costea el RFQ por tramos. Nunca lanza: el costeo no puede tumbar a quien lo pide.

    Devuelve ``{cantidades, tramos, costeo, comunes, error_costeo}``.
    """
    datos = datos or {}
    resorte = resorte or {}
    cantidades = cantidades_del_rfq(datos)

    # Lo que va al motor: el resorte extraído del plano, con las cantidades del
    # correo. Si el plano no dio material y el correo sí, se usa el del correo.
    datos_resorte = dict(resorte)
    if not datos_resorte.get("material") and material_rfq:
        datos_resorte["material"] = material_rfq
    datos_resorte["cantidades"] = cantidades
    datos_resorte["cantidad"] = cantidades[0] if cantidades else None

    tramos, costeo, comunes = [], {"completo": False, "faltantes": [], "origen": None}, {}
    error_costeo = None
    if cantidades and (datos_resorte.get("diametro_alambre_mm") or datos_resorte.get("material")):
        try:
            from pricing.engine import compute_price_via_node
            from pricing.rodea_adapter import build_pn_for_engine, overrides_de_parametros
            pn, catalogo = build_pn_for_engine(rfq_id, datos_resorte)
            resultado = compute_price_via_node(
                pn, ctx_overrides=overrides_de_parametros(catalogo.parametros, None))
            params = catalogo.parametros or {}
            objetivo = num(params.get("contribution")) or 20.0
            tramos = [tramo_para_ventana(t, objetivo)
                      for t in (resultado.get("tiers") or []) if t]
            mat = pn.get("material") or {}
            comunes = {
                "material": mat.get("code"),
                "material_nombre": (catalogo.material or {}).get("nombre"),
                "dia_in": num(mat.get("diaIn")),
                "peso_lb_pc": num(mat.get("weightLb")),
                "base_lb": num(mat.get("basePerLb")),
                "surcharge_lb": num(mat.get("surchPerLb")),
            }
            costeo = {"completo": bool(catalogo.completo),
                      "faltantes": list(catalogo.faltantes),
                      "origen": catalogo.origen,
                      "banderas_motor": [f.get("m") for f in (resultado.get("flags") or [])]}
        except Exception as err:      # el costeo no puede tumbar la ventana
            log.exception("RFQ %s: no se pudo costear: %s", rfq_id, err)
            error_costeo = str(err)
    elif not cantidades:
        costeo["faltantes"] = ["El RFQ no trae ninguna cantidad: no hay tramos que costear."]
    else:
        costeo["faltantes"] = ["Sin material ni diámetro de alambre no se puede costear: "
                               "hay que capturarlos en la cotización completa."]

    return {"cantidades": cantidades, "tramos": tramos, "costeo": costeo,
            "comunes": comunes, "error_costeo": error_costeo}
