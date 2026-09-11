"""Rasterizado de planos y extraccion de la capa de texto.

Usa PyMuPDF (fitz) para todo: no necesita poppler instalado en el sistema.
Devuelve, por cada pagina:
    { "png": bytes, "w": int, "h": int, "words": [ {text, nbox}, ... ] | None }
nbox = [x, y, w, h] en fracciones de la pagina (0..1).
"""

import io
import os

from PIL import Image

from . import config


def _resize_png(img, max_side):
    w, h = img.size
    sc = min(1.0, float(max_side) / float(max(w, h)))
    if sc < 1.0:
        img = img.resize((max(1, int(w * sc)), max(1, int(h * sc))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return img, buf.getvalue()


def _words_de_pagina(page):
    """Capa de texto nativa -> palabras con caja normalizada. None si es escaneo.

    LAS CAJAS SE GIRAN, y esa es toda la gracia de esta funcion.

    `get_text("words")` devuelve las coordenadas en el sistema del PDF, SIN
    aplicar el `/Rotate` de la pagina. La imagen que se rasteriza si lo aplica.
    En un plano que es apaisado por rotacion -- que son casi todos -- las dos
    cosas no coinciden, y el recorte cae en cualquier sitio.

    Se veia asi: en un plano con `/Rotate 90` la palabra "DRAWING" salia de 7
    puntos de ancho por 33 de alto, y TODOS los recortes tenian la misma
    anchura, la del margen y nada mas. El recorte que existe para ensenar de
    donde sale un dato ensenaba un trozo de linea del dibujo, asi que quien
    revisaba la lectura no podia comprobar nada -- que es peor que no tener
    recorte, porque parece que si se puede.

    `rotation_matrix` es la identidad cuando la pagina no declara giro: los
    planos que ya salian bien siguen igual.
    """
    pw, ph = page.rect.width, page.rect.height
    if pw <= 0 or ph <= 0:
        return None
    Rect = type(page.rect)          # sin importar fitz: aqui no esta importado
    giro = page.rotation_matrix
    out = []
    for w in page.get_text("words"):     # (x0,y0,x1,y1,texto,bloque,linea,palabra)
        txt = w[4]
        if not str(txt).strip():
            continue
        r = Rect(w[0], w[1], w[2], w[3]) * giro
        out.append({
            "text": str(txt),
            "nbox": [r.x0 / pw, r.y0 / ph, r.width / pw, r.height / ph],
        })
    return out or None


def cargar(path, dpi=None, max_side=None, max_pages=None):
    """Devuelve (paginas, avisos)."""
    dpi = dpi or config.DPI
    max_side = max_side or config.MAX_SIDE
    max_pages = max_pages or config.MAX_PAGES
    avisos = []
    ext = os.path.splitext(str(path))[1].lower()
    paginas = []

    if ext == ".pdf":
        try:
            import pymupdf as fitz          # nombre nuevo (PyMuPDF >= 1.24)
        except ImportError:
            import fitz                     # nombre antiguo, por compatibilidad
        doc = fitz.open(str(path))
        total = doc.page_count
        n = min(total, max_pages)
        if total > n:
            avisos.append(
                "The drawing has %d sheets; only the first %d were read "
                "(raise max_pages in config.json if you need more)." % (total, n))
        for i in range(n):
            page = doc[i]
            pix = page.get_pixmap(dpi=dpi)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            img, png = _resize_png(img, max_side)
            paginas.append({"png": png, "w": img.size[0], "h": img.size[1],
                            "words": _words_de_pagina(page)})
        doc.close()
        if paginas and not any(p["words"] for p in paginas):
            avisos.append(
                "This PDF has no text layer (it is a scan): the crops showing "
                "where each value came from will be approximate.")
    else:
        img = Image.open(str(path))
        if getattr(img, "n_frames", 1) > 1:
            avisos.append("Multi-page image: only the first frame was read.")
        img = img.convert("RGB")
        img, png = _resize_png(img, max_side)
        paginas.append({"png": png, "w": img.size[0], "h": img.size[1], "words": None})
        avisos.append("Image input: no text layer, so the crops are approximate.")

    if not paginas:
        raise RuntimeError(
            "Could not read any page from this file. It may be corrupt, "
            "password-protected, or not a drawing at all.")
    return paginas, avisos


def bloques_imagen(paginas):
    """Paginas -> bloques de contenido image para la Messages API."""
    import base64
    return [{
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png",
                   "data": base64.standard_b64encode(p["png"]).decode("ascii")},
    } for p in paginas]


def listado_palabras(paginas, max_words=1400):
    """Texto con las palabras indexadas por pagina, para que el modelo cite indices.

    El indice es GLOBAL (continua entre paginas) para que una sola lista de
    word_indices no sea ambigua.
    """
    lineas = []
    idx = 0
    mapa = []                       # indice global -> (pagina, nbox)
    for pi, p in enumerate(paginas):
        if not p["words"]:
            continue
        lineas.append("--- PAGINA %d ---" % pi)
        for w in p["words"]:
            if idx >= max_words:
                lineas.append("... (lista truncada)")
                return "\n".join(lineas), mapa
            lineas.append("%d: %s" % (idx, w["text"]))
            mapa.append((pi, w["nbox"]))
            idx += 1
    if not mapa:
        return "", mapa
    return "\n".join(lineas), mapa
