/**
 * El plano del cliente, a la vista, dentro de la calculadora de precios.
 *
 * El plano que mandó el cliente ya viaja con el RFQ: al abrir la cotización
 * completa, `isc-nube.js` lo mete en la casilla «Drawing → AI Extraction»
 * (`#q-drawing`). Pero ahí sólo se veía su nombre: para mirarlo había que ir
 * a buscar el correo al buzón. Esto añade dos cosas, sobre esa misma casilla
 * —lo que haya en ella es lo que se ve, venga del correo o lo haya elegido
 * alguien a mano—:
 *
 *   1. «Ver» en cada ficha de la casilla: abre el dibujo tal cual, en grande,
 *      encima de la hoja (`ISCPlano.ver(i)`).
 *   2. Una pestaña «Plano del cliente» junto a «Quote»: el dibujo a pantalla
 *      completa para leerlo con calma mientras se cotiza, con «Abrir en otra
 *      pestaña», «Descargar» y «Leer plano con IA».
 *
 * El fichero no se toca ni se convierte: es el mismo que llegó en el correo.
 * Los PDF los pinta el visor del navegador; las imágenes, un <img> que se
 * amplía con un clic.
 */
(function () {
    'use strict';

    if (window.ISCPlano) return;

    function idioma() {
        try { return (window.parent && window.parent.I18N && window.parent.I18N.idioma) || 'en'; }
        catch (e) { return 'en'; }
    }

    var T = {
        en: { pestana: 'Customer drawing', ver: 'View', titulo: 'Customer drawing',
              abrir: 'Open in new tab', descargar: 'Download', leer: 'AI Read Drawing',
              cerrar: 'Close', vacio: 'This quote has no drawing yet. Choose one in “Drawing → AI Extraction” on the Quote tab.',
              noSeVe: 'If the drawing does not show here, open it in a new tab.',
              leyendo: 'Reading {nombre} with AI…', zoom: 'Click to zoom' },
        es: { pestana: 'Plano del cliente', ver: 'Ver', titulo: 'Plano del cliente',
              abrir: 'Abrir en otra pestaña', descargar: 'Descargar', leer: 'Leer plano con IA',
              cerrar: 'Cerrar', vacio: 'Esta cotización todavía no tiene plano. Elígelo en «Plano → extracción con IA», en la pestaña Quote.',
              noSeVe: 'Si el dibujo no se ve aquí, ábrelo en otra pestaña.',
              leyendo: 'Leyendo {nombre} con IA…', zoom: 'Clic para ampliar' },
        fr: { pestana: 'Plan du client', ver: 'Voir', titulo: 'Plan du client',
              abrir: 'Ouvrir dans un nouvel onglet', descargar: 'Télécharger', leer: 'Lire le plan (IA)',
              cerrar: 'Fermer', vacio: 'Ce devis n’a pas encore de plan. Choisissez-le dans « Plan → extraction IA », onglet Quote.',
              noSeVe: 'Si le plan ne s’affiche pas ici, ouvrez-le dans un nouvel onglet.',
              leyendo: 'Lecture de {nombre} par IA…', zoom: 'Cliquer pour agrandir' }
    };
    function t(clave, datos) {
        var s = (T[idioma()] || T.en)[clave] || T.en[clave] || '';
        for (var k in (datos || {})) s = s.split('{' + k + '}').join(String(datos[k]));
        return s;
    }
    function esc(v) {
        return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    // ------------------------------------------------------------ ficheros

    var urls = new Map();     // File -> blob: URL (se sueltan al cambiar)
    var elegido = 0;          // el que se ve en la pestaña

    function campo() { return document.getElementById('q-drawing'); }

    function ficheros() {
        var c = campo();
        return c && c.files ? [].slice.call(c.files) : [];
    }

    function urlDe(f) {
        if (!urls.has(f)) urls.set(f, URL.createObjectURL(f));
        return urls.get(f);
    }

    function soltarUrls() {
        var vivos = ficheros();
        urls.forEach(function (u, f) {
            if (vivos.indexOf(f) < 0) { URL.revokeObjectURL(u); urls.delete(f); }
        });
    }

    function esImagen(f) { return /^image\//.test(f.type) || /\.(png|jpe?g|gif|webp)$/i.test(f.name); }

    /** El dibujo: el visor de PDF del navegador, o la imagen. */
    function lienzo(f) {
        var u = urlDe(f);
        if (esImagen(f)) {
            return '<div class="ipl-img"><img src="' + esc(u) + '" alt="' + esc(f.name) +
                   '" title="' + esc(t('zoom')) + '"></div>';
        }
        return '<iframe class="ipl-pdf" src="' + esc(u) + '#view=FitH" title="' + esc(f.name) + '"></iframe>' +
               '<p class="ipl-nota">' + esc(t('noSeVe')) + '</p>';
    }

    function barra(f, enModal) {
        var puedeLeer = !!(window.ISCNubePlano && window.ISCNubePlano.leer);
        return '<div class="ipl-barra">' +
            '<span class="ipl-nombre" title="' + esc(f.name) + '">' + esc(f.name) + '</span>' +
            '<span class="ipl-esp"></span>' +
            '<a class="ipl-btn" href="' + esc(urlDe(f)) + '" target="_blank" rel="noopener">' + esc(t('abrir')) + '</a>' +
            '<a class="ipl-btn" href="' + esc(urlDe(f)) + '" download="' + esc(f.name) + '">' + esc(t('descargar')) + '</a>' +
            (puedeLeer ? '<button type="button" class="ipl-btn ipl-pri" data-ipl="leer">' + esc(t('leer')) + '</button>' : '') +
            (enModal ? '<button type="button" class="ipl-btn" data-ipl="cerrar" aria-label="' + esc(t('cerrar')) + '">✕</button>' : '') +
            '</div>';
    }

    function leer(f) {
        if (!f || !window.ISCNubePlano) return;
        try { if (typeof toast === 'function') toast(t('leyendo', { nombre: f.name })); } catch (e) {}
        window.ISCNubePlano.leer(f);
    }

    function engancharImagen(raiz) {
        var img = raiz.querySelector('.ipl-img img');
        if (img) img.addEventListener('click', function () { raiz.querySelector('.ipl-img').classList.toggle('grande'); });
    }

    // ------------------------------------------------------------ el modal

    var modal = null;

    function ver(i) {
        var lista = ficheros();
        var f = lista[i || 0];
        if (!f) return;
        cerrar();
        modal = document.createElement('div');
        modal.className = 'ipl-modal';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-label', t('titulo'));
        modal.innerHTML = '<div class="ipl-caja">' + barra(f, true) +
                          '<div class="ipl-cuerpo">' + lienzo(f) + '</div></div>';
        document.body.appendChild(modal);
        engancharImagen(modal);
        modal.addEventListener('click', function (ev) {
            var b = ev.target.closest('[data-ipl]');
            if (ev.target === modal || (b && b.dataset.ipl === 'cerrar')) return cerrar();
            if (b && b.dataset.ipl === 'leer') { cerrar(); leer(f); }
        });
        document.addEventListener('keydown', alEsc, true);
    }

    function alEsc(ev) { if (ev.key === 'Escape') { ev.stopPropagation(); cerrar(); } }

    function cerrar() {
        if (!modal) return;
        modal.remove();
        modal = null;
        document.removeEventListener('keydown', alEsc, true);
    }

    // ------------------------------------------------------ la pestaña

    function vista() { return document.getElementById('view-plano'); }

    function montarPestana() {
        var tabs = document.getElementById('viewtabs');
        var hoja = document.getElementById('view-quote');
        if (!tabs || !hoja || document.getElementById('tab-plano')) return !!document.getElementById('tab-plano');

        var boton = document.createElement('button');
        boton.id = 'tab-plano';
        boton.className = 'pohua-tab';
        boton.dataset.v = 'plano';
        boton.type = 'button';
        var ref = tabs.querySelector('[data-v="quote"]');
        tabs.insertBefore(boton, ref ? ref.nextSibling : null);
        boton.addEventListener('click', function (ev) {
            ev.stopImmediatePropagation();
            mostrar();
        });

        var v = document.createElement('div');
        v.className = 'view';
        v.id = 'view-plano';
        hoja.parentNode.insertBefore(v, hoja.nextSibling);
        v.addEventListener('click', function (ev) {
            var ficha = ev.target.closest('[data-ipl-i]');
            if (ficha) { elegido = Number(ficha.dataset.iplI) || 0; pintarVista(); return; }
            var b = ev.target.closest('[data-ipl="leer"]');
            if (b) leer(ficheros()[elegido]);
        });
        return true;
    }

    function mostrar() {
        [].forEach.call(document.querySelectorAll('#viewtabs button'), function (b) {
            b.classList.toggle('on', b.dataset.v === 'plano');
        });
        [].forEach.call(document.querySelectorAll('.view'), function (x) { x.classList.remove('on'); });
        var v = vista();
        if (v) { v.classList.add('on'); pintarVista(); }
    }

    function pintarVista() {
        var v = vista();
        if (!v) return;
        var lista = ficheros();
        if (elegido >= lista.length) elegido = 0;
        if (!lista.length) {
            v.innerHTML = '<div class="ipl-vacio">' + esc(t('vacio')) + '</div>';
            return;
        }
        var f = lista[elegido];
        var fichas = lista.length > 1
            ? '<div class="ipl-fichas">' + lista.map(function (x, i) {
                return '<button type="button" class="ipl-ficha' + (i === elegido ? ' on' : '') +
                       '" data-ipl-i="' + i + '">' + esc(x.name) + '</button>';
              }).join('') + '</div>'
            : '';
        v.innerHTML = '<div class="ipl-pagina">' + fichas + barra(f, false) +
                      '<div class="ipl-cuerpo">' + lienzo(f) + '</div></div>';
        engancharImagen(v);
    }

    function actualizar() {
        soltarUrls();
        var b = document.getElementById('tab-plano');
        if (!b) return;
        var n = ficheros().length;
        b.textContent = t('pestana') + (n > 1 ? ' (' + n + ')' : '');
        b.classList.toggle('vacia', n === 0);
        var v = vista();
        if (v && v.classList.contains('on')) pintarVista();
    }

    // ------------------------------------------------------------ estilos

    function estilos() {
        if (document.getElementById('ipl-estilos')) return;
        var s = document.createElement('style');
        s.id = 'ipl-estilos';
        s.textContent = [
            /* la pestaña se ve aunque la calculadora oculte las que no son «Quote» */
            '#viewtabs button.pohua-tab[data-v="plano"]{display:inline-block!important}',
            '#viewtabs button.pohua-tab.vacia{opacity:.55}',
            '#view-plano.on{display:block}',
            '.ipl-pagina{display:flex;flex-direction:column;gap:8px;padding:12px 16px;',
            '  height:calc(100vh - 120px);min-height:420px}',
            '.ipl-barra{display:flex;align-items:center;gap:8px;flex-wrap:wrap}',
            '.ipl-nombre{font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:40%}',
            '.ipl-esp{flex:1}',
            '.ipl-btn{display:inline-flex;align-items:center;gap:6px;padding:7px 12px;border-radius:8px;',
            '  font:600 .85rem/1 inherit;cursor:pointer;text-decoration:none;',
            '  border:1px solid var(--n-linea,#cbd5e1);background:var(--n-sutil,#f8fafc);color:var(--n-tinta,#0f172a)}',
            '.ipl-btn:hover{border-color:var(--n-info-solido,#148ec2)}',
            '.ipl-pri{background:var(--n-info-solido,#148ec2);border-color:transparent;color:#fff}',
            '.ipl-cuerpo{flex:1;min-height:0;display:flex;flex-direction:column;border-radius:10px;overflow:hidden;',
            '  border:1px solid var(--n-linea,#cbd5e1);background:var(--n-sutil,#f1f5f9)}',
            '.ipl-pdf{flex:1;width:100%;border:0;background:#fff}',
            '.ipl-nota{margin:0;padding:4px 10px;font-size:.72rem;color:var(--n-apagado,#64748b)}',
            '.ipl-img{flex:1;overflow:auto;display:flex;align-items:center;justify-content:center;background:#fff}',
            '.ipl-img img{max-width:100%;max-height:100%;cursor:zoom-in}',
            '.ipl-img.grande{align-items:flex-start;justify-content:flex-start}',
            '.ipl-img.grande img{max-width:none;max-height:none;cursor:zoom-out}',
            '.ipl-fichas{display:flex;gap:6px;flex-wrap:wrap}',
            '.ipl-ficha{padding:5px 10px;border-radius:999px;font-size:.8rem;cursor:pointer;',
            '  border:1px solid var(--n-info-linea,rgba(20,142,194,.35));background:transparent;color:var(--n-tinta,#0f172a)}',
            '.ipl-ficha.on{background:var(--n-info-fondo,rgba(20,142,194,.14));font-weight:700}',
            '.ipl-vacio{margin:40px auto;max-width:520px;text-align:center;color:var(--n-apagado,#64748b)}',
            '.ipl-modal{position:fixed;inset:0;z-index:400;background:rgba(4,8,18,.6);',
            '  display:flex;align-items:center;justify-content:center;padding:16px}',
            '.ipl-caja{width:min(1200px,96vw);height:min(900px,94vh);display:flex;flex-direction:column;gap:8px;',
            '  padding:12px;border-radius:12px;background:var(--n-papel,#fff);box-shadow:0 16px 50px rgba(0,0,0,.45)}',
            /* «Ver» dentro de cada ficha de la casilla de planos */
            '.narch-ver{margin-left:4px;padding:1px 8px;border-radius:999px;cursor:pointer;',
            '  font:600 .72rem/1.6 inherit;border:1px solid var(--n-info-linea,rgba(20,142,194,.35));',
            '  background:var(--n-papel,#fff);color:var(--n-info-solido,#148ec2)}',
            '.narch-ver:hover{background:var(--n-info-solido,#148ec2);color:#fff}',
            '@media (max-width:820px){.ipl-pagina{padding:8px;height:calc(100vh - 150px)}',
            '  .ipl-nombre{max-width:100%;flex-basis:100%}}'
        ].join('\n');
        document.head.appendChild(s);
    }

    // ------------------------------------------------------------ arranque

    function arrancar() {
        estilos();
        if (!montarPestana()) return false;
        var c = campo();
        if (c && !c.dataset.ipl) {
            c.dataset.ipl = '1';
            c.addEventListener('change', actualizar);
        }
        actualizar();
        return true;
    }

    window.ISCPlano = { ver: ver, mostrar: mostrar, actualizar: actualizar };

    // La calculadora pinta su hoja al arrancar: se espera a que exista.
    function intentar(n) {
        if (arrancar() || n <= 0) return;
        setTimeout(function () { intentar(n - 1); }, 250);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { intentar(40); });
    } else {
        intentar(40);
    }
    // El idioma de Pohua cambia en vivo: la pestaña también.
    try {
        if (window.parent && window.parent.I18N && window.parent.I18N.alCambiar) {
            window.parent.I18N.alCambiar(function () { actualizar(); });
        }
    } catch (e) { /* otro origen */ }
})();
