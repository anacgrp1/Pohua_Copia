# -*- coding: utf-8 -*-
"""El veredicto, fuera del navegador.

Hasta ahora FEASIBLE / REQUIRES REVIEW se calculaba, se pintaba y se quedaba
ahi: vivia en una pestana del navegador y desaparecia al cerrarla. Para que un
correo llegue al plant manager, ese valor tiene que salir de la app y quedar
escrito en algun sitio que no dependa de que la ventana siga abierta.

Esto es ese sitio. Un registro de una linea por veredicto, en
`_veredictos.jsonl`, junto al resto de lo que produce el lector.

POR QUE JSONL Y NO UNA LISTA JSON
    Se escribe anadiendo al final. Si dos lecturas terminan a la vez, cada una
    escribe su linea y ninguna pisa a la otra; con una lista habria que leer,
    modificar y reescribir el fichero entero, y ahi si se pierden cosas.

POR QUE NO MANDA EL CORREO
    Mandar un correo es una accion hacia fuera y necesita decisiones que no son
    mias: por que canal, desde que cuenta, a quien exactamente y con que
    credenciales. Este modulo deja el veredicto anotado y marcado como
    pendiente; quien mande la notificacion lo lee y llama a `marcar_notificado`
    para cerrar el circulo. Asi el envio se puede probar, repetir y auditar por
    separado, y un fallo de correo no pierde el veredicto.

LO QUE NO SE GUARDA
    Ni el plano ni los recortes: solo el dictamen y con que datos se tomo. El
    plano ya vive en `_specs` y `_uploads`, con sus reglas de retencion.
"""

import io
import json
import os
import time

ESQUEMA = "isc-veredicto/1"
FICHERO = "_veredictos.jsonl"

FEASIBLE = "FEASIBLE"
REVIEW = "REQUIRES REVIEW"


def _ruta(base):
    return os.path.join(str(base), FICHERO)


def _ahora():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _texto(v, limite=200):
    t = " ".join(str(v or "").split())
    return t[:limite]


def _motivos(v):
    """Los motivos, siempre como lista de textos cortos."""
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    fuera = []
    for m in list(v)[:20]:
        t = _texto(m, 300)
        if t:
            fuera.append(t)
    return fuera


def leer(base):
    """Todas las lineas validas. Una linea rota no tumba el registro entero."""
    p = _ruta(base)
    if not os.path.isfile(p):
        return []
    filas = []
    with io.open(p, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                d = json.loads(linea)
            except Exception:
                continue          # una linea a medias no invalida las demas
            if isinstance(d, dict):
                filas.append(d)
    return filas


def registrar(base, datos):
    """Anota un veredicto. -> (registro, error)

    Repetir el MISMO veredicto sobre la misma pieza no crea una entrada nueva:
    la pantalla vuelve a mandarlo cada vez que se repinta, y un registro lleno
    de copias no se puede revisar. Se devuelve el que ya habia, marcado como
    repetido. Un veredicto que CAMBIA si entra: es justo lo que hay que ver.
    """
    if not isinstance(datos, dict):
        return None, "Send a JSON object."

    verdicto = _texto(datos.get("verdict") or datos.get("verdicto"), 40).upper()
    if verdicto not in (FEASIBLE, REVIEW):
        return None, ('verdict must be "%s" or "%s".' % (FEASIBLE, REVIEW))

    pn = _texto(datos.get("pn"), 60)
    if not pn:
        return None, "pn is required: it is what identifies the part."

    motivos = _motivos(datos.get("reasons") or datos.get("motivos"))
    maquina = datos.get("machine") or datos.get("maquina") or None
    if maquina is not None and not isinstance(maquina, dict):
        maquina = None

    reg = {
        "esquema": ESQUEMA,
        "id": "%s-%s" % (time.strftime("%Y%m%d%H%M%S"), pn[:20]),
        "recibido": _ahora(),
        "pn": pn,
        "descripcion": _texto(datos.get("partName") or datos.get("descripcion")),
        "cliente": _texto(datos.get("customer") or datos.get("cliente"), 80),
        "cotizacion": _texto(datos.get("quote") or datos.get("cotizacion"), 40),
        "tipo_resorte": _texto(datos.get("springType") or datos.get("tipo"), 20),
        "verdicto": verdicto,
        "motivos": motivos,
        "maquina": maquina,
        "nota": datos.get("score") if isinstance(
            datos.get("score"), (int, float)) else None,
        "banda": _texto(datos.get("band"), 60),
        "origen": _texto(datos.get("source") or "price-calculator", 40),
        # Solo lo que hay que revisar espera notificacion. Un FEASIBLE se
        # anota porque es el registro de lo que se decidio, no porque haya
        # que avisar a nadie.
        "notificado": verdicto == FEASIBLE,
        "notificado_en": None,
    }

    previos = leer(base)
    for viejo in reversed(previos):
        if viejo.get("pn") != pn:
            continue
        if (viejo.get("verdicto") == verdicto
                and viejo.get("motivos") == motivos):
            copia = dict(viejo)
            copia["repetido"] = True
            return copia, None
        break                     # solo cuenta el ULTIMO de esa pieza

    with io.open(_ruta(base), "a", encoding="utf-8") as f:
        f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    return reg, None


def listar(base, pendientes=False, limite=50):
    """Los mas recientes primero. `pendientes` = los que esperan aviso."""
    filas = leer(base)
    if pendientes:
        filas = [d for d in filas if not d.get("notificado")]
    filas.reverse()
    try:
        limite = max(1, min(int(limite), 500))
    except Exception:
        limite = 50
    return filas[:limite]


def marcar_notificado(base, ident):
    """Cierra el circulo: alguien ya aviso de este veredicto. -> (reg, error)

    Aqui SI se reescribe el fichero entero, que es lo que JSONL evita al
    escribir. Es asumible porque marcar es raro -- una vez por veredicto que se
    revisa -- mientras que registrar ocurre en cada lectura.
    """
    ident = _texto(ident, 80)
    filas = leer(base)
    tocado = None
    for d in filas:
        if d.get("id") == ident:
            d["notificado"] = True
            d["notificado_en"] = _ahora()
            tocado = d
            break
    if tocado is None:
        return None, "No verdict with that id."
    tmp = _ruta(base) + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        for d in filas:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    os.replace(tmp, _ruta(base))
    return tocado, None
