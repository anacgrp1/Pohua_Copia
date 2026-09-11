"""Resolucion de la localizacion de cada dato sobre el plano + recortes PNG.

El modelo devuelve `localizacion: [{campo, pagina, word_indices|nbox}]`.
Aqui se convierte a cajas normalizadas reales (via la capa de texto del PDF,
que es exacta) y se generan los recortes de verificacion.
"""

import io
import os
import uuid

from PIL import Image

from . import config


def _clamp(b):
    x = min(max(float(b[0]), 0.0), 1.0)
    y = min(max(float(b[1]), 0.0), 1.0)
    w = min(max(float(b[2]), 0.005), 1.0 - x)
    h = min(max(float(b[3]), 0.005), 1.0 - y)
    return [x, y, w, h]


def resolver(spec, mapa, n_paginas=1):
    """-> { "ruta.del.campo": {"pagina": int, "nbox": [x,y,w,h], "via": str} }"""
    out = {}
    for item in (spec.get("localizacion") or []):
        if not isinstance(item, dict):
            continue
        campo = item.get("campo")
        if not campo:
            continue

        # 1) via preferente: indices de palabras reales del PDF
        wi = item.get("word_indices") or []
        cajas, pagina = [], None
        for i in wi:
            if isinstance(i, int) and 0 <= i < len(mapa):
                pi, nb = mapa[i]
                if pagina is None:
                    pagina = pi
                if pi == pagina:
                    cajas.append(nb)
        if cajas:
            x0 = min(b[0] for b in cajas)
            y0 = min(b[1] for b in cajas)
            x1 = max(b[0] + b[2] for b in cajas)
            y1 = max(b[1] + b[3] for b in cajas)
            out[campo] = {"pagina": pagina or 0,
                          "nbox": _clamp([x0, y0, x1 - x0, y1 - y0]),
                          "via": "ocr"}
            continue

        # 2) respaldo: la caja estimada por el modelo
        nb = item.get("nbox")
        if isinstance(nb, (list, tuple)) and len(nb) == 4:
            try:
                pag = int(item.get("pagina") or 0)
            except (TypeError, ValueError):
                pag = 0
            out[campo] = {"pagina": max(0, min(pag, n_paginas - 1)),
                          "nbox": _clamp(nb), "via": "modelo"}
    return out


def recortar(paginas, ubic, destino, pad=None):
    """Guarda el recorte de `ubic` y devuelve su nombre de fichero, o None."""
    if not ubic:
        return None
    pad = config.CROP_PAD if pad is None else pad
    pi = ubic.get("pagina", 0)
    if not (0 <= pi < len(paginas)):
        return None
    pag = paginas[pi]
    img = Image.open(io.BytesIO(pag["png"]))
    W, H = img.size
    x, y, w, h = ubic["nbox"]
    px, py, pw, ph = int(x * W), int(y * H), int(w * W), int(h * H)
    p = int(pad * W)
    caja = (max(0, px - p), max(0, py - p),
            min(W, px + pw + p), min(H, py + ph + p))
    if caja[2] <= caja[0] or caja[3] <= caja[1]:
        return None
    nombre = uuid.uuid4().hex[:12] + ".png"
    img.crop(caja).save(os.path.join(destino, nombre))
    return nombre


def guardar_paginas(paginas, destino, job):
    """Guarda las paginas completas. -> [nombres]"""
    nombres = []
    for i, p in enumerate(paginas):
        n = "%s_p%d.png" % (job, i)
        with open(os.path.join(destino, n), "wb") as f:
            f.write(p["png"])
        nombres.append(n)
    return nombres
