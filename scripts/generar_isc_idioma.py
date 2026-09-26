# -*- coding: utf-8 -*-
"""Genera frontend/js/isc-idioma.js a partir de isc_idioma_diccionario.py.

    python scripts/generar_isc_idioma.py

El JS resultante se inyecta en la calculadora al servirla (api/lector.py) y
traduce lo que pinta al idioma de Pohua. Ver la cabecera del propio JS.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

from isc_idioma_diccionario import D, PLANTILLAS  # noqa: E402

DESTINO = RAIZ / "frontend" / "js" / "isc-idioma.js"

CABECERA = '''/**
 * El idioma de la calculadora de ISC, siguiendo al de Pohua.
 *
 * La Spring Engineering Calculator está escrita en inglés y pinta casi toda
 * su interfaz desde JavaScript (innerHTML en cada recálculo). No se toca su
 * HTML —es la copia que hace scripts/vendorizar_nucleo.py y se regenera—:
 * este script se inyecta al servirla (api/lector.py) y traduce lo que se ve.
 *
 * Cómo: un diccionario de textos exactos EN → ES/FR y unas plantillas (regex)
 * para los mensajes que llevan cifras. Un MutationObserver traduce cada
 * trozo que la calculadora vuelve a pintar; el original en inglés se guarda
 * en el propio nodo de texto para poder volver a él al cambiar de idioma.
 *
 * El idioma se lee de Pohua (window.parent.I18N.idioma) y se sigue en vivo
 * con parent.I18N.alCambiar; si la calculadora se abre sola, del localStorage
 * que comparte con Pohua ('cgr-idioma'). Lo que no está en el diccionario se
 * queda en inglés: cifras, nombres de máquinas y de materiales, sobre todo.
 *
 * GENERADO por scripts/generar_isc_idioma.py a partir de
 * scripts/isc_idioma_diccionario.py. No se edita a mano.
 */
(function () {
    'use strict';

    const CLAVE = 'cgr-idioma';
    const IDX = { es: 0, fr: 1 };

'''

CUERPO = r'''
    /** La ventana de Pohua (la que tiene I18N), subiendo por los marcos: el
     *  Spring Calculator vive dentro de la calculadora de precios, dos niveles
     *  por debajo de Pohua. */
    function pohua() {
        let w = window, salto = 0;
        try {
            while (w.parent && w.parent !== w && salto < 5) {
                w = w.parent; salto++;
                if (w.I18N && w.I18N.idioma) return w;
            }
        } catch (_) { /* otro origen: no se puede leer */ }
        return null;
    }

    function idiomaActual() {
        const p = pohua();
        if (p) return p.I18N.idioma;
        try { const v = localStorage.getItem(CLAVE); if (v) return v; } catch (_) { /* privado */ }
        return 'en';
    }

    let idioma = idiomaActual();
    let escribiendo = false;      // para no reaccionar a los propios cambios

    function traducir(texto, idx) {
        const t = texto.trim();
        if (!t) return null;
        const e = D[t];
        if (e) return e[idx];
        for (const [re, es, fr] of P) {
            if (re.test(t)) return t.replace(re, idx === 0 ? es : fr);
        }
        return null;
    }

    /** Sustituye el texto conservando los espacios de los bordes. */
    function conBordes(original, nuevo) {
        const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(original);
        return m[1] + nuevo + m[3];
    }

    /** Un <option> sin atributo value TOMA SU VALOR DEL TEXTO: traducirlo
     *  cambiaría lo que lee la calculadora (`select.value` daría "Resorte de
     *  compresión" en vez de "Compression Spring", y `select.value = 'Net 30'`
     *  dejaría de encontrar su opción). Antes de traducir se le fija el value
     *  con el texto en inglés; lo que se traduce es sólo lo que se ve. */
    function fijarValor(n) {
        const op = n.parentNode;
        if (op && op.tagName === 'OPTION' && !op.hasAttribute('value')) op.setAttribute('value', op.value);
    }

    function nodoTexto(n) {
        const en = (n.__en != null) ? n.__en : n.nodeValue;
        if (n.__en == null && idioma !== 'en') n.__en = n.nodeValue;
        const idx = IDX[idioma];
        if (idx == null) {                       // inglés: se restaura el original
            if (n.__en != null && n.nodeValue !== n.__en) n.nodeValue = n.__en;
            return;
        }
        const tr = traducir(en, idx);
        if (tr != null) fijarValor(n);
        const salida = tr == null ? en : conBordes(en, tr);
        if (n.nodeValue !== salida) { n.nodeValue = salida; n.__puesto = salida; }
    }

    const ATRIBUTOS = ['placeholder', 'title', 'aria-label'];

    function elemento(el) {
        for (const a of ATRIBUTOS) {
            if (!el.hasAttribute(a)) continue;
            const clave = '__en_' + a;
            const en = (el[clave] != null) ? el[clave] : el.getAttribute(a);
            if (el[clave] == null && idioma !== 'en') el[clave] = en;
            const idx = IDX[idioma];
            const nuevo = (idx == null) ? en : (traducir(en, idx) || en);
            if (el.getAttribute(a) !== nuevo) { el.setAttribute(a, nuevo); el['__puesto_' + a] = nuevo; }
        }
    }

    // Ni texto ni atributos.
    const SALTAR = { SCRIPT: 1, STYLE: 1, NOSCRIPT: 1 };
    // Su texto es lo que escribe quien usa la calculadora: no se toca. Pero sus
    // atributos sí (el placeholder de "Feasibility Remarks" es un TEXTAREA).
    const SIN_TEXTO = { SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, TEXTAREA: 1 };

    function recorrer(raiz) {
        if (!raiz) return;
        escribiendo = true;
        try {
            if (raiz.nodeType === 3) {
                if (!SIN_TEXTO[raiz.parentNode && raiz.parentNode.tagName]) nodoTexto(raiz);
                return;
            }
            if (raiz.nodeType !== 1 && raiz.nodeType !== 9 && raiz.nodeType !== 11) return;
            if (raiz.nodeType === 1) {
                if (SALTAR[raiz.tagName]) return;
                elemento(raiz);
                if (SIN_TEXTO[raiz.tagName]) return;
            }
            const w = document.createTreeWalker(raiz, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
                acceptNode(n) {
                    if (n.nodeType === 1) return SALTAR[n.tagName] ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
                    return SIN_TEXTO[n.parentNode && n.parentNode.tagName] ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
                }
            });
            let n;
            while ((n = w.nextNode())) {
                if (n.nodeType === 3) nodoTexto(n); else elemento(n);
            }
        } finally {
            escribiendo = false;
        }
    }

    function todo() {
        recorrer(document.body);
        if (document.title) {
            if (document.__enTitle == null) document.__enTitle = document.title;
            const idx = IDX[idioma];
            document.title = (idx == null) ? document.__enTitle : (traducir(document.__enTitle, idx) || document.__enTitle);
        }
        document.documentElement.setAttribute('lang', idioma);
    }

    function vigilar() {
        const obs = new MutationObserver((cambios) => {
            if (escribiendo) return;
            for (const c of cambios) {
                // El observador avisa DESPUÉS (en una microtarea), cuando
                // `escribiendo` ya volvió a false: lo que escribió este script
                // se reconoce por el valor que dejó puesto. Sin esto, el texto
                // ya traducido se tomaba por el original nuevo y volver al
                // inglés (o pasar al francés) dejaba esos trozos en español.
                if (c.type === 'characterData' && c.target.__puesto === c.target.nodeValue) continue;
                if (c.type === 'attributes' && c.target['__puesto_' + c.attributeName] === c.target.getAttribute(c.attributeName)) continue;
                if (c.type === 'childList') {
                    c.addedNodes.forEach((n) => recorrer(n));
                } else if (c.type === 'characterData') {
                    // La calculadora cambió el texto: el original ya no vale.
                    c.target.__en = null;
                    recorrer(c.target);
                } else if (c.type === 'attributes') {
                    c.target['__en_' + c.attributeName] = null;
                    recorrer(c.target);
                }
            }
        });
        obs.observe(document.documentElement, {
            childList: true, subtree: true, characterData: true,
            attributes: true, attributeFilter: ATRIBUTOS,
        });
    }

    function cambiar(nuevo) {
        if (!nuevo || nuevo === idioma) return;
        idioma = nuevo;
        todo();
    }

    function seguirAPohua() {
        const p = pohua();
        if (p && p.I18N.alCambiar) {
            p.I18N.alCambiar((codigo) => cambiar(codigo));
            return;
        }
        window.addEventListener('storage', (ev) => { if (ev.key === CLAVE) cambiar(ev.newValue || 'en'); });
    }

    function arrancar() {
        todo();
        vigilar();
        seguirAPohua();
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', arrancar);
    else arrancar();

    // Para depurar desde la consola: ISC_IDIOMA.cambiar('es')
    window.ISC_IDIOMA = { cambiar, get idioma() { return idioma; }, traducir: (t) => traducir(t, IDX[idioma]) };
})();
'''


def _js_regex(patron: str) -> str:
    return "/" + patron.replace("/", r"\/") + "/"


def _js_plantilla(texto: str) -> str:
    # \1 → $1 (String.prototype.replace)
    return json.dumps(re.sub(r"\\(\d)", r"$\1", texto), ensure_ascii=False)


def main() -> None:
    for patron, _, _ in PLANTILLAS:
        re.compile(patron)                 # que ninguna regex esté rota
    d_js = "    const D = " + json.dumps(
        {k: list(v) for k, v in D.items()}, ensure_ascii=False,
        separators=(",", ":")).replace('],"', '],\n        "') + ";\n\n"
    p_js = "    const P = [\n" + ",\n".join(
        "        [%s, %s, %s]" % (_js_regex(r), _js_plantilla(es), _js_plantilla(fr))
        for r, es, fr in PLANTILLAS) + "\n    ];\n"
    DESTINO.write_text(CABECERA + d_js + p_js + CUERPO, encoding="utf-8")
    print("%s: %d textos, %d plantillas" % (DESTINO.relative_to(RAIZ), len(D), len(PLANTILLAS)))


if __name__ == "__main__":
    main()
