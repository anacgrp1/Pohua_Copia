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

    // Lo ya bajado, por «rfq|nombre»: una promesa de { nombre, url }. Se
    // guarda la PROMESA, no el resultado, para que dos pedidos del mismo
    // plano (la precarga y el clic) compartan una sola descarga.
    const cache = new Map();
    const MAX_CACHE = 24;
    // La lista de planos de cada RFQ, cuando ya se sabe (la ventana de
    // revisión y la cotización la traen): así el clic no la vuelve a pedir.
    const listas = new Map();

    function guardar(clave, promesa) {
        cache.set(clave, promesa);
        while (cache.size > MAX_CACHE) {
            const [vieja, p] = cache.entries().next().value;
            cache.delete(vieja);
            p.then((x) => { try { URL.revokeObjectURL(x.url); } catch (_) {} }).catch(() => {});
        }
        // Si falla, que no se quede apuntada: el siguiente clic lo reintenta.
        promesa.catch(() => { if (cache.get(clave) === promesa) cache.delete(clave); });
        return promesa;
    }

    function bajar(rfqId, nombre) {
        const clave = rfqId + '|' + nombre;
        if (cache.has(clave)) return cache.get(clave);
        return guardar(clave, API.descargarPlano(rfqId, nombre)
            .then((blob) => ({ nombre, url: URL.createObjectURL(blob) })));
    }

    /** Empezar a bajarlos ya, sin esperar al clic. */
    function precargar(rfqId, planos) {
        const nombres = (planos || []).map((p) => (typeof p === 'string' ? p : p && p.nombre)).filter(Boolean);
        if (!rfqId || !nombres.length) return;
        listas.set(rfqId, nombres);
        const ir = () => nombres.forEach((n) => { bajar(rfqId, n).catch(() => {}); });
        if (window.requestIdleCallback) requestIdleCallback(ir, { timeout: 1500 }); else setTimeout(ir, 300);
    }

    /** Ficheros que ya están en el navegador (la cotización los bajó para la hoja). */
    function registrar(rfqId, ficheros) {
        const lista = (ficheros || []).filter((f) => f && f.name);
        if (!rfqId || !lista.length) return;
        listas.set(rfqId, lista.map((f) => f.name));
        lista.forEach((f) => {
            const clave = rfqId + '|' + f.name;
            if (!cache.has(clave)) guardar(clave, Promise.resolve({ nombre: f.name, url: URL.createObjectURL(f) }));
        });
    }

    function esc(v) {
        return String(v == null ? '' : v).replace(/[&<>"']/g, (c) => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    const esImagen = (n) => /\.(png|jpe?g|gif|webp)$/i.test(n || '');

    function cerrar() {
        if (!capa) return;
        capa.remove();
        capa = null;
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

    /** Las fichas para cambiar de plano, sin tocar el dibujo de abajo. */
    function pintarFichas(planos, i) {
        if (!capa) return;
        const html = `<div class="plano-fichas">${planos.map((x, k) => `
            <button type="button" class="plano-ficha${k === i ? ' on' : ''}" data-plano="${k}">${esc(x.nombre)}</button>`).join('')}</div>`;
        const hay = capa.querySelector('.plano-fichas');
        if (hay) hay.outerHTML = html;
        else capa.querySelector('.plano-barra').insertAdjacentHTML('afterend', html);
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

        const vacio = (clave, extra) => {
            if (!capa) return;
            capa.querySelector('.plano-caja').innerHTML = `
                <div class="plano-barra"><b>${esc(I18N.t('plano.ver.titulo'))}</b><span class="plano-esp"></span>
                    <button type="button" class="btn btn-ghost btn-sm" data-plano-cerrar>✕</button></div>
                <div class="plano-vacio">${esc(I18N.t(clave))}${extra ? ' ' + esc(extra) : ''}</div>`;
        };

        try {
            let nombres = listas.get(rfqId);
            if (!nombres) {
                const r = await API.rfqPlanos(rfqId);
                nombres = ((r && r.planos) || []).map((p) => p.nombre);
                listas.set(rfqId, nombres);
            }
            if (!capa) return;
            if (!nombres.length) { vacio('plano.ver.vacio'); return; }

            // Todos a la vez, y el primero se enseña en cuanto llega: no se
            // espera a los demás (un correo con tres planos tardaba el triple).
            const promesas = nombres.map((n) => bajar(rfqId, n));
            let primero;
            try {
                primero = await promesas[0];
            } catch (err) {
                if (err && err.sesionExpirada) { cerrar(); return; }
                primero = null;
            }
            if (!capa) return;
            if (primero) {
                capa.__planos = [primero];
                pintar(rfqId, capa.__planos, 0);
            }
            if (promesas.length === 1 && primero) return;
            // Los demás, cuando lleguen: sólo se añaden sus fichas, sin
            // recargar el dibujo que ya se está viendo.
            const resto = await Promise.allSettled(promesas);
            if (!capa) return;
            const planos = resto.filter((x) => x.status === 'fulfilled').map((x) => x.value);
            if (!planos.length) { vacio('plano.ver.fallo'); return; }
            capa.__planos = planos;
            if (!primero) { pintar(rfqId, planos, 0); return; }
            if (planos.length > 1) pintarFichas(planos, 0);
        } catch (err) {
            if (err && err.sesionExpirada) { cerrar(); return; }
            vacio('plano.ver.fallo', err.message || '');
        }
    }

    const ICONO = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>';

    /** El botón, listo para pegar en cualquier pantalla. */
    function boton(rfqId, clase, n, planos) {
        // Con la lista a mano, la descarga empieza ya: al pulsar, el plano
        // suele estar bajado y se abre al momento.
        if (planos && planos.length) precargar(rfqId, planos);
        const texto = I18N.t('plano.ver.boton') + (n > 1 ? ` (${n})` : '');
        return `<button type="button" class="${esc(clase || 'btn btn-secondary')} plano-boton"
                        data-ver-plano="${esc(rfqId)}" title="${esc(I18N.t('plano.ver.ayuda'))}">${ICONO}<span>${esc(texto)}</span></button>`;
    }

    // Al pasar el ratón o tocar el botón, a por la lista y los planos: medio
    // segundo de ventaja antes del clic.
    const adelantar = (ev) => {
        const b = ev.target.closest && ev.target.closest('[data-ver-plano]');
        if (!b) return;
        const id = b.dataset.verPlano;
        if (listas.has(id)) { precargar(id, listas.get(id)); return; }
        API.rfqPlanos(id).then((r) => precargar(id, (r && r.planos) || [])).catch(() => {});
    };
    document.addEventListener('pointerenter', adelantar, true);
    document.addEventListener('focusin', adelantar);

    // Un solo escuchador para todos los botones, estén donde estén.
    document.addEventListener('click', (ev) => {
        const b = ev.target.closest && ev.target.closest('[data-ver-plano]');
        if (!b) return;
        ev.preventDefault();
        abrir(b.dataset.verPlano);
    });

    return { abrir, cerrar, boton, precargar, registrar };
})();
