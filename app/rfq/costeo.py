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
from typing import Optional

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


def tramo_para_ventana(t: dict, objetivo_pct, entrada: Optional[dict] = None) -> dict:
    """Traduce un tramo del motor a lo que dibuja la ventana.

    ``entrada`` es el mismo tramo tal como se le MANDÓ al motor. La ruta sale
    de ahí: el motor del núcleo no la devuelve en su resultado, y leerla del
    resultado dejaba la ventana diciendo «Sin ruta» con la ruta puesta y las
    horas calculadas.
    """
    pnl = t.get("pnl") or {}
    sell = num(t.get("sell"))
    resultado = num(pnl.get("result"))
    resultado_pct = (resultado / sell * 100) if (sell and resultado is not None) else None
    ruta = []
    for op in ((entrada or {}).get("routing") or t.get("routing") or []):
        if not op or not op.get("machine"):
            continue
        ruta.append({"maquina": op.get("machine"),
                     # Qué clase de máquina es: la que enrolla el resorte
                     # (COILER) o una operación posterior (SECONDARY).
                     "familia": op.get("family") or None,
                     "pph": num(op.get("pph")),
                     "setup_h": num(op.get("setupH")),
                     "costo_h": num(op.get("machH"))})
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




def _motivo(costeo: dict, codigo: str, **datos) -> None:
    """Un motivo del costeo, en las dos formas: la de siempre y la traducible."""
    import pricing.mensajes as mensajes
    costeo["faltantes"] = [mensajes.texto(codigo, **datos)]
    costeo["faltantes_i18n"] = [mensajes.entrada(codigo, **datos)]


def datos_para_motor(datos: dict, resorte: dict, material_rfq=None) -> dict:
    """Lo que se le pasa al motor: el resorte, con las cantidades del correo.

    Vive aparte porque lo usan dos caminos que tienen que coincidir: el costeo
    que enseña la ventana de revisión y el PN con el que se abre la calculadora
    completa. Si se prepararan por separado, la calculadora podría abrirse con
    un material o unas cantidades distintas de las del número que el PM acaba
    de ver, y nadie sabría cuál de los dos creer.
    """
    datos = datos or {}
    resorte = resorte or {}
    cantidades = cantidades_del_rfq(datos)

    # Si el plano no dio material y el correo sí, se usa el del correo.
    datos_resorte = dict(resorte)
    if not datos_resorte.get("material") and material_rfq:
        datos_resorte["material"] = material_rfq
    datos_resorte["cantidades"] = cantidades
    datos_resorte["cantidad"] = cantidades[0] if cantidades else None
    return datos_resorte


def pn_inicial(rfq_id: str, datos: dict, resorte: dict, material_rfq=None) -> dict:
    """El PN con el que se abre la calculadora completa, ya relleno.

    Es el MISMO que se le manda al motor para costear —mismo material, mismos
    tramos, misma ruta—, y tiene la forma exacta que la calculadora guarda en
    su borrador (`blankPn()`), así que allí se adopta tal cual en vez de
    copiarse campo por campo desde el navegador.

    Devuelve ``{pn, faltantes, error}``. Nunca lanza: si el catálogo no está,
    se devuelve el PN en blanco con el motivo, y la calculadora abre vacía en
    lugar de no abrir.
    """
    datos_resorte = datos_para_motor(datos, resorte, material_rfq)
    try:
        from pricing.rodea_adapter import build_pn_for_engine
        pn, catalogo = build_pn_for_engine(rfq_id, datos_resorte)
        return {"pn": pn, "faltantes": list(catalogo.faltantes), "error": None}
    except Exception as err:      # el catálogo no puede impedir abrir la hoja
        log.exception("RFQ %s: no se pudo armar el PN inicial: %s", rfq_id, err)
        return {"pn": None, "faltantes": [], "error": str(err)}


def cotizacion_del_pm(datos: dict) -> Optional[dict]:
    """La cotización que el PM dejó en la calculadora, si sirve para costear."""
    pm = (datos or {}).get("cotizacion_pm")
    if not isinstance(pm, dict):
        return None
    pn = pm.get("pn")
    resultado = pm.get("resultado") or {}
    if not isinstance(pn, dict) or not isinstance(resultado, dict):
        return None
    if not any(t for t in (resultado.get("tiers") or [])):
        return None
    return pm


def costear_con_el_pm(pm: dict) -> dict:
    """El costeo tal como el PM lo vio en la calculadora.

    No se vuelve a correr el motor: se usan los tramos que la calculadora
    calculó con SUS parámetros y SUS bases en el momento en que el PM guardó.
    Es el único modo de que la ventana de revisión y la oferta enseñen
    exactamente el número que el PM aprobó, y no otro parecido.
    """
    pn = pm.get("pn") or {}
    resultado = pm.get("resultado") or {}
    objetivo = num(pm.get("contribution")) or 20.0
    enviados = pn.get("tiers") or []
    tramos = [tramo_para_ventana(t, objetivo, enviados[i] if i < len(enviados) else None)
              for i, t in enumerate(resultado.get("tiers") or []) if t]
    cantidades = [num(t.get("qty")) for t in enviados if t and num(t.get("qty"))]
    mat = pn.get("material") or {}
    comunes = {
        "material": mat.get("code"),
        "material_nombre": pm.get("material_nombre"),
        "dia_in": num(mat.get("diaIn")),
        "peso_lb_pc": num(mat.get("weightLb")),
        "base_lb": num(mat.get("basePerLb")),
        "surcharge_lb": num(mat.get("surchPerLb")),
    }
    costeo = {"completo": True, "faltantes": [], "faltantes_i18n": [],
              "origen": "calculadora",
              "banderas_motor": [f.get("m") for f in (resultado.get("flags") or [])
                                 if isinstance(f, dict)],
              "pm": {"por": pm.get("por"), "en": pm.get("en"),
                     "numero": (pm.get("cabecera") or {}).get("numero"),
                     "version": pm.get("n")}}
    return {"cantidades": cantidades, "tramos": tramos, "costeo": costeo,
            "comunes": comunes, "error_costeo": None}


def costear(rfq_id: str, datos: dict, resorte: dict, material_rfq=None) -> dict:
    """Costea el RFQ por tramos. Nunca lanza: el costeo no puede tumbar a quien lo pide.

    Devuelve ``{cantidades, tramos, costeo, comunes, error_costeo}``.

    Si el PM ya dejó su cotización en la calculadora (``datos_json.
    cotizacion_pm``), ésa manda: es lo que corrigió y lo que va a aprobar.
    """
    pm = cotizacion_del_pm(datos)
    if pm:
        return costear_con_el_pm(pm)

    datos_resorte = datos_para_motor(datos, resorte, material_rfq)
    cantidades = datos_resorte.get("cantidades") or []

    tramos, costeo, comunes = [], {"completo": False, "faltantes": [],
                                   "faltantes_i18n": [], "origen": None}, {}
    error_costeo = None
    if cantidades and (datos_resorte.get("diametro_alambre_mm") or datos_resorte.get("material")):
        try:
            from pricing.engine import compute_price_via_node
            from pricing.rodea_adapter import build_pn_for_engine, overrides_de_parametros
            pn, catalogo = build_pn_for_engine(rfq_id, datos_resorte)
            resultado = compute_price_via_node(
                pn, ctx_overrides=overrides_de_parametros(
                    catalogo.parametros, None, catalogo.dbs_motor))
            params = catalogo.parametros or {}
            objetivo = num(params.get("contribution")) or 20.0
            enviados = pn.get("tiers") or []
            tramos = [tramo_para_ventana(t, objetivo,
                                         enviados[i] if i < len(enviados) else None)
                      for i, t in enumerate(resultado.get("tiers") or []) if t]
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
                      # Los mismos motivos con su código, para que la web los
                      # diga en el idioma que tenga puesto (pricing/mensajes.py).
                      "faltantes_i18n": list(getattr(catalogo, "faltantes_i18n", [])),
                      "origen": catalogo.origen,
                      "banderas_motor": [f.get("m") for f in (resultado.get("flags") or [])]}
        except Exception as err:      # el costeo no puede tumbar la ventana
            log.exception("RFQ %s: no se pudo costear: %s", rfq_id, err)
            error_costeo = str(err)
    elif not cantidades:
        _motivo(costeo, "SIN_CANTIDADES_RFQ")
    else:
        _motivo(costeo, "SIN_MATERIAL_NI_DIAMETRO")

    return {"cantidades": cantidades, "tramos": tramos, "costeo": costeo,
            "comunes": comunes, "error_costeo": error_costeo}
