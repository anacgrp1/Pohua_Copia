/**
 * El plano que mandó el cliente, visto desde Pohua.
 *
 * El dibujo viaja con el RFQ desde que entra el correo (está guardado en la
 * base), pero hasta ahora sólo se podía VER si la calculadora lo enseñaba, y
 * la calculadora vive en un marco que a veces no carga sus capas, está en
 * consulta (todo apagado) o ni siquiera está abierto. Esto lo abre desde
 * Pohua mismo, en una ventana encima de lo que haya: la ficha, la revisión o
 * la cotización.
 *
 *   PlanoCliente.abrir(rfqId)            → lista los planos y abre el primero
 *   PlanoCliente.boton(rfqId, clase)     → el HTML de un botón que lo abre
 *
 * El fichero se baja con la sesión de Pohua (`API.descargarPlano`) y se
 * enseña tal cual: los PDF con el visor del navegador, las imágenes en un
 * <img> que se amplía con un clic. Nada se convierte.
 */
const PlanoCliente = (() => {
    'use strict';

    let capa = null;
    let urls = [];

    function esc(v) {
        return String(v == null ? '' : v).replace(/[&<>"']/g, (c) => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    const esImagen = (n) => /\.(png|jpe?g|gif|webp)$/i.test(n || '');

    function cerrar() {
        if (!capa) return;
        capa.remove();
        capa = null;
        urls.forEach((u) => { try { URL.revokeObjectURL(u); } catch (_) {} });
        urls = [];
        document.removeEventListener('keydown', alTeclear, true);
    }

    function alTeclear(ev) {
        if (ev.key === 'Escape') { ev.stopPropagation(); cerrar(); }
    }

    function lienzo(nombre, url) {
        if (esImagen(nombre)) {
            return `<div class="plano-img"><img src="${esc(url)}" alt="${esc(nombre)}"
                        title="${esc(I18N.t('plano.ver.zoom'))}"></div>`;
        }
        return `<iframe class="plano-pdf" src="${esc(url)}#view=FitH" title="${esc(nombre)}"></iframe>
                <p class="plano-nota">${esc(I18N.t('plano.ver.noSeVe'))}</p>`;
    }

    function pintar(rfqId, planos, i) {
        const p = planos[i];
        const fichas = planos.length > 1
            ? `<div class="plano-fichas">${planos.map((x, k) => `
                <button type="button" class="plano-ficha${k === i ? ' on' : ''}" data-plano="${k}">${esc(x.nombre)}</button>`).join('')}</div>`
            : '';
        capa.querySelector('.plano-caja').innerHTML = `
            <div class="plano-barra">
                <div class="plano-titulo">
                    <b>${esc(I18N.t('plano.ver.titulo'))}</b>
                    <span class="plano-rfq">${esc(rfqId)} · ${esc(p.nombre)}</span>
                </div>
                <span class="plano-esp"></span>
                <a class="btn btn-secondary btn-sm" href="${esc(p.url)}" target="_blank" rel="noopener">${esc(I18N.t('plano.ver.abrir'))}</a>
                <a class="btn btn-secondary btn-sm" href="${esc(p.url)}" download="${esc(p.nombre)}">${esc(I18N.t('plano.ver.descargar'))}</a>
                <button type="button" class="btn btn-ghost btn-sm plano-cerrar" data-plano-cerrar aria-label="${esc(I18N.t('dlg.cancelar'))}">✕</button>
            </div>
            ${fichas}
            <div class="plano-cuerpo">${lienzo(p.nombre, p.url)}</div>`;
        const img = capa.querySelector('.plano-img img');
        if (img) img.addEventListener('click', () => img.parentNode.classList.toggle('grande'));
    }

    async function abrir(rfqId) {
        if (!rfqId) return;
        cerrar();
        capa = document.createElement('div');
        capa.className = 'plano-fondo';
        capa.setAttribute('role', 'dialog');
        capa.setAttribute('aria-label', I18N.t('plano.ver.titulo'));
        capa.innerHTML = `<div class="plano-caja"><div class="plano-cargando">
            <div class="spinner"></div> ${esc(I18N.t('plano.ver.cargando'))}</div></div>`;
        document.body.appendChild(capa);
        document.addEventListener('keydown', alTeclear, true);
        capa.addEventListener('click', (ev) => {
            if (ev.target === capa || ev.target.closest('[data-plano-cerrar]')) return cerrar();
            const f = ev.target.closest('[data-plano]');
            if (f) pintar(rfqId, capa.__planos, Number(f.dataset.plano) || 0);
        });

        try {
            const r = await API.rfqPlanos(rfqId);
            const lista = (r && r.planos) || [];
            if (!lista.length) {
                capa.querySelector('.plano-caja').innerHTML = `
                    <div class="plano-barra"><b>${esc(I18N.t('plano.ver.titulo'))}</b><span class="plano-esp"></span>
                        <button type="button" class="btn btn-ghost btn-sm" data-plano-cerrar>✕</button></div>
                    <div class="plano-vacio">${esc(I18N.t('plano.ver.vacio'))}</div>`;
                return;
            }
            // Se bajan con la sesión de Pohua: una URL directa en un <iframe>
            // no lleva el token y el servidor contestaría 401.
            const planos = [];
            for (const p of lista) {
                try {
                    const blob = await API.descargarPlano(rfqId, p.nombre);
                    const url = URL.createObjectURL(blob);
                    urls.push(url);
                    planos.push({ nombre: p.nombre, url });
                } catch (err) {
                    if (err && err.sesionExpirada) { cerrar(); return; }
                    console.warn('No se pudo bajar el plano ' + p.nombre + ': ' + err.message);
                }
            }
            if (!capa) return;                    // se cerró mientras bajaba
            if (!planos.length) {
                capa.querySelector('.plano-caja').innerHTML = `
                    <div class="plano-barra"><b>${esc(I18N.t('plano.ver.titulo'))}</b><span class="plano-esp"></span>
                        <button type="button" class="btn btn-ghost btn-sm" data-plano-cerrar>✕</button></div>
                    <div class="plano-vacio">${esc(I18N.t('plano.ver.fallo'))}</div>`;
                return;
            }
            capa.__planos = planos;
            pintar(rfqId, planos, 0);
        } catch (err) {
            if (err && err.sesionExpirada) { cerrar(); return; }
            if (capa) capa.querySelector('.plano-caja').innerHTML = `
                <div class="plano-barra"><b>${esc(I18N.t('plano.ver.titulo'))}</b><span class="plano-esp"></span>
                    <button type="button" class="btn btn-ghost btn-sm" data-plano-cerrar>✕</button></div>
                <div class="plano-vacio">${esc(I18N.t('plano.ver.fallo'))} ${esc(err.message || '')}</div>`;
        }
    }

    const ICONO = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>';

    /** El botón, listo para pegar en cualquier pantalla. */
    function boton(rfqId, clase, n) {
        const texto = I18N.t('plano.ver.boton') + (n > 1 ? ` (${n})` : '');
        return `<button type="button" class="${esc(clase || 'btn btn-secondary')} plano-boton"
                        data-ver-plano="${esc(rfqId)}" title="${esc(I18N.t('plano.ver.ayuda'))}">${ICONO}<span>${esc(texto)}</span></button>`;
    }

    // Un solo escuchador para todos los botones, estén donde estén.
    document.addEventListener('click', (ev) => {
        const b = ev.target.closest && ev.target.closest('[data-ver-plano]');
        if (!b) return;
        ev.preventDefault();
        abrir(b.dataset.verPlano);
    });

    return { abrir, cerrar, boton };
})();
