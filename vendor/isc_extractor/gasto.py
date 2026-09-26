"""Contador de gasto y aviso de saldo bajo.

Por que es un contador y no una consulta
----------------------------------------
La API de IA **no expone el saldo**. La Usage & Cost API existe, pero
exige una Admin API key (`sk-ant-admin...`) y no esta disponible para cuentas
individuales; la clave que usa el lector es una normal. Asi que no hay forma de
preguntar cuanto queda: lo unico que se puede hacer es apuntar lo que se gasta.

Esto es importante y hay que decirlo en cada mensaje: **es una estimacion, no el
saldo real**. Se desvia si la clave se usa desde otro sitio -- y se usa: la
calculadora tiene un modo de respaldo que llama a la API desde el navegador.
La cifra buena esta siempre en la consola del proveedor de IA.

Aun asi vale la pena, porque el sintoma de quedarse sin saldo en un puesto de
cotizacion es "la herramienta ha dejado de funcionar", y nadie lo relaciona con
la facturacion hasta que alguien lo investiga.

Como se usa
-----------
    POST /api/credito  {"recarga": 50}   -> apunta una recarga de 50 USD
    GET  /api/credito                    -> estado actual
El lector apunta cada lectura por su cuenta.
"""

import json
import os
import time

# USD por millon de tokens. Tarifa de primera parte, 2026-08.
# Este es el UNICO sitio donde viven los precios: probar_lote.py los importa.
PRECIOS = {
    "claude-opus-5":    {"in": 5.00, "out": 25.00},
    "claude-opus-4-8":  {"in": 5.00, "out": 25.00},
    "claude-sonnet-5":  {"in": 3.00, "out": 15.00},
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00},
    "claude-haiku-4-5": {"in": 1.00, "out": 5.00},
}

# Escribir en cache cuesta 1,25x con TTL de 5 min y 2x con TTL de 1 h.
# Leer cuesta 0,1x.
FACTOR_ESCRITURA = {"5m": 1.25, "1h": 2.0}
FACTOR_LECTURA = 0.1

FICHERO = "_gasto.json"
AVISO_POR_DEFECTO = 5.00        # USD restantes a partir de los cuales se avisa


def coste_llamada(modelo, uso, ttl="5m"):
    """-> USD de una llamada, contando la actividad de cache. None si no se sabe."""
    p = PRECIOS.get(modelo)
    if not p or not uso:
        return None
    entrada = (uso.get("in") or 0) * p["in"]
    entrada += (uso.get("cache_w") or 0) * p["in"] * FACTOR_ESCRITURA.get(ttl, 1.25)
    entrada += (uso.get("cache_r") or 0) * p["in"] * FACTOR_LECTURA
    return (entrada + (uso.get("out") or 0) * p["out"]) / 1e6


def _ruta(base):
    return os.path.join(str(base), FICHERO)


def _leer(base):
    try:
        with open(_ruta(base), encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("recargas", [])
    d.setdefault("lecturas", 0)
    d.setdefault("gastado_usd", 0.0)
    d.setdefault("historial", [])
    return d


def _escribir(base, d):
    """Escritura tolerante: perder el contador nunca debe tumbar una lectura."""
    try:
        tmp = _ruta(base) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
        os.replace(tmp, _ruta(base))
        return True
    except Exception:
        return False


def coste_lectura(router, diag, cfg):
    """Coste de UNA lectura de plano: router + extractor (con sus reparaciones)."""
    cfg = cfg or {}
    ttl = str(cfg.get("prompt_cache") or "5m")
    m_rt = (router or {}).get("_modelo") or cfg.get("model_router")
    m_ex = cfg.get("model_extractor")
    total = coste_llamada(m_rt, (router or {}).get("_uso") or {}, ttl) or 0.0
    for u in ((diag or {}).get("uso") or []):
        total += coste_llamada(m_ex, u, ttl) or 0.0
    return total


def registrar(base, router, diag, cfg, tipo=None):
    """Apunta una lectura. Devuelve el estado despues de apuntarla."""
    usd = coste_lectura(router, diag, cfg)
    d = _leer(base)
    d["lecturas"] += 1
    d["gastado_usd"] = round(d["gastado_usd"] + usd, 6)
    # Sin nombres de fichero ni datos del plano: esto no es un registro de
    # trabajo, es un contador, y vive en una carpeta que se comparte.
    d["historial"].append({"t": int(time.time()), "tipo": tipo,
                           "usd": round(usd, 6)})
    d["historial"] = d["historial"][-500:]
    _escribir(base, d)
    return estado(base, cfg)


def recargar(base, usd):
    """Apunta una recarga de saldo. -> estado, o None si el importe no vale."""
    try:
        usd = float(usd)
    except (TypeError, ValueError):
        return None
    if usd <= 0:
        return None
    d = _leer(base)
    d["recargas"].append({"t": int(time.time()), "usd": round(usd, 2)})
    _escribir(base, d)
    return estado(base, None)


def estado(base, cfg):
    """-> dict con lo gastado, lo recargado y si toca avisar.

    `restante` es None mientras no se haya apuntado ninguna recarga: sin saber
    cuanto se cargo no se puede estimar lo que queda, y es preferible no decir
    nada a inventarse un numero.
    """
    cfg = cfg or {}
    d = _leer(base)
    cargado = round(sum(r.get("usd") or 0 for r in d["recargas"]), 2)
    gastado = round(d.get("gastado_usd") or 0.0, 4)
    umbral = cfg.get("aviso_saldo_usd", AVISO_POR_DEFECTO)

    restante = round(cargado - gastado, 4) if d["recargas"] else None
    media = round(gastado / d["lecturas"], 4) if d["lecturas"] else None
    quedan = int(restante / media) if (restante and media and media > 0
                                       and restante > 0) else None

    return {
        "cargado_usd": cargado,
        "gastado_usd": gastado,
        "restante_usd": restante,
        "lecturas": d["lecturas"],
        "media_usd": media,
        "lecturas_restantes": quedan,
        "umbral_usd": umbral,
        "avisar": bool(restante is not None and umbral and restante <= umbral),
        "agotado": bool(restante is not None and restante <= 0),
        "estimado": True,
    }


def aviso(est):
    """Estado -> la linea que se le ensena al usuario, o None si no hay que decir nada.

    En ingles, como el resto de lo que ve la calculadora.
    """
    if not est or not est.get("avisar"):
        return None
    if est.get("agotado"):
        return ("ESTIMATED CREDIT EXHAUSTED: this parser has spent about $%.2f of "
                "the $%.2f topped up. The next drawing will probably fail. Top up "
                "at the AI provider's console, then record it so this warning clears. "
                "(Estimate based on this parser's own usage - the real balance is "
                "in the console.)" % (est["gastado_usd"], est["cargado_usd"]))
    cola = ""
    if est.get("lecturas_restantes"):
        n = est["lecturas_restantes"]
        cola = " - roughly %d more drawing%s at $%.3f each" % (
            n, "" if n == 1 else "s", est["media_usd"])
    return ("LOW CREDIT: about $%.2f left of the $%.2f topped up%s. Top up at "
            "the AI provider's console before it runs out. (Estimate based on this "
            "parser's own usage - the real balance is in the console.)"
            % (est["restante_usd"], est["cargado_usd"], cola))
