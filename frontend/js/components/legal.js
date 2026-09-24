/**
 * Lo legal dentro de la aplicación: el aviso de cookies, la aceptación del
 * aviso de privacidad y de los términos, y los enlaces a los documentos.
 *
 * Los documentos en sí son páginas públicas en /legal/ (se leen sin sesión).
 * Aquí sólo está lo que tiene que pasar DENTRO de Pohua:
 *
 *   banner()            El aviso de cookies y almacenamiento, en el primer
 *                       contacto (art. 14 del Reglamento de la LFPDPPP; art. 82
 *                       de la ley Informatique et Libertés). Pohua sólo usa lo
 *                       estrictamente necesario, así que informa y no pide
 *                       consentimiento; si algún día se añade algo opcional,
 *                       `permitido()` es la puerta y vale `false` hasta que la
 *                       persona diga que sí.
 *   exigirAceptacion()  Tras entrar: si la cuenta no aceptó la versión vigente
 *                       de los documentos, un diálogo que no deja seguir sin
 *                       aceptar. La aceptación queda en la base con la fecha y
 *                       la versión (POST /api/legal/aceptar).
 *   enlaces(el)         Los tres enlaces, para el pie de cada pantalla.
 *   notaLogin(el)       "Al entrar acepta…", debajo del formulario de acceso.
 */
const Legal = (() => {
    'use strict';

    const CLAVE = 'cgr-legal';
    const DOCS = ['privacidad', 'cookies', 'terminos'];

    function version() {
        return (window.POHUA_LEGAL && window.POHUA_LEGAL.VERSION) || '1';
    }

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    function url(doc) {
        return `/legal/?doc=${doc}&lang=${encodeURIComponent(I18N.idioma || 'en')}`;
    }

    function enlace(doc, texto) {
        return `<a href="${url(doc)}" target="_blank" rel="noopener">${esc(texto || I18N.t('legal.' + doc))}</a>`;
    }

    // ---------------------------------------------------------- preferencias

    function leer() {
        try { return JSON.parse(localStorage.getItem(CLAVE) || 'null') || {}; }
        catch (_) { return {}; }
    }

    function escribir(dato) {
        try { localStorage.setItem(CLAVE, JSON.stringify(dato)); } catch (_) { /* modo privado */ }
    }

    /**
     * ¿Se puede usar una tecnología OPCIONAL de esta categoría?
     *
     * Hoy Pohua no tiene ninguna, así que esto no se llama en ningún sitio.
     * Está para que la próxima persona que quiera meter una analítica o un
     * chat de terceros tenga la puerta hecha y cerrada por defecto: nada
     * opcional se carga sin un sí explícito guardado aquí.
     */
    function permitido(categoria) {
        const d = leer();
        return !!(d.opcionales && d.opcionales[categoria] === true);
    }

    // ---------------------------------------------------------------- banner

    let bannerEl = null;

    function pintarBanner() {
        if (!bannerEl) return;
        bannerEl.innerHTML = `
            <p class="legal-banner-texto">${esc(I18N.t('legal.banner'))}
               ${enlace('cookies', I18N.t('legal.masCookies'))} · ${enlace('privacidad')}</p>
            <button type="button" class="btn btn-primary btn-sm" data-legal="entendido">${esc(I18N.t('legal.entendido'))}</button>`;
        bannerEl.querySelector('[data-legal="entendido"]').addEventListener('click', () => {
            const d = leer();
            d.informado = version();
            d.fecha = new Date().toISOString();
            escribir(d);
            bannerEl.remove();
            bannerEl = null;
        });
    }

    function banner() {
        if (leer().informado === version() || bannerEl) return;
        bannerEl = document.createElement('div');
        bannerEl.className = 'legal-banner';
        bannerEl.setAttribute('role', 'region');
        bannerEl.setAttribute('aria-label', I18N.t('legal.masCookies'));
        document.body.appendChild(bannerEl);
        pintarBanner();
    }

    // ----------------------------------------------------------- aceptación

    let dialogo = null;

    function exigirAceptacion() {
        const yo = API.getUsuario();
        if (!yo || !yo.legal_pendiente || dialogo) return;

        const fondo = document.createElement('div');
        fondo.className = 'dialogo-fondo legal-dialogo';
        fondo.innerHTML = `
            <div class="dialogo dialogo--formulario" role="dialog" aria-modal="true" aria-labelledby="legalTitulo">
                <div class="dialogo-cabecera">
                    <h2 class="dialogo-titulo" id="legalTitulo">${esc(I18N.t('legal.aceptTitulo'))}</h2>
                </div>
                <p class="dialogo-mensaje">${esc(I18N.t('legal.aceptTexto'))}</p>
                <ul class="legal-lista">
                    ${DOCS.map((d) => `<li>${enlace(d)}</li>`).join('')}
                </ul>
                <label class="legal-casilla">
                    <input type="checkbox" id="legalCasilla">
                    <span>${esc(I18N.t('legal.aceptCasilla'))}</span>
                </label>
                <p class="login-error" id="legalError" hidden></p>
                <div class="dialogo-acciones">
                    <button type="button" class="btn btn-ghost" data-accion="salir">${esc(I18N.t('legal.salir'))}</button>
                    <button type="button" class="btn btn-primary" data-accion="aceptar" disabled>${esc(I18N.t('legal.aceptar'))}</button>
                </div>
            </div>`;
        document.body.appendChild(fondo);
        dialogo = fondo;

        const casilla = fondo.querySelector('#legalCasilla');
        const aceptar = fondo.querySelector('[data-accion="aceptar"]');
        const error = fondo.querySelector('#legalError');
        casilla.addEventListener('change', () => { aceptar.disabled = !casilla.checked; });

        // Sin Escape: este diálogo no se cierra sin decidir.
        fondo.addEventListener('keydown', (ev) => {
            if (ev.key === 'Escape') { ev.preventDefault(); ev.stopPropagation(); }
        }, true);

        aceptar.addEventListener('click', async () => {
            if (!casilla.checked) return;
            aceptar.disabled = true;
            try {
                await API.aceptarLegal(yo.legal_pendiente);
                yo.legal_pendiente = null;
                API.guardarUsuario(yo);
                fondo.remove();
                dialogo = null;
            } catch (err) {
                aceptar.disabled = false;
                if (err && err.sesionExpirada) return;
                error.textContent = I18N.t('legal.fallo', { motivo: err.message });
                error.hidden = false;
            }
        });

        fondo.querySelector('[data-accion="salir"]').addEventListener('click', () => {
            fondo.remove();
            dialogo = null;
            if (typeof APP !== 'undefined' && APP.cerrarSesion) APP.cerrarSesion();
        });

        requestAnimationFrame(() => casilla.focus({ preventScroll: true }));
    }

    // ----------------------------------------------------------- enlaces

    const conEnlaces = new Set();

    function pintarEnlaces(el) {
        el.innerHTML = DOCS.map((d) => enlace(d)).join('<span aria-hidden="true"> · </span>');
    }

    function enlaces(el) {
        if (!el) return;
        conEnlaces.add(el);
        pintarEnlaces(el);
    }

    const conNota = new Set();

    function pintarNota(el) {
        const texto = esc(I18N.t('legal.login'))
            .split('{terminos}').join(enlace('terminos', I18N.t('legal.terminos').toLowerCase()))
            .split('{privacidad}').join(enlace('privacidad', I18N.t('legal.privacidad').toLowerCase()))
            .split('{cookies}').join(enlace('cookies', I18N.t('legal.loginCookies')));
        el.innerHTML = texto;
    }

    function notaLogin(el) {
        if (!el) return;
        conNota.add(el);
        pintarNota(el);
    }

    // Un cambio de idioma vuelve a escribir todo lo de aquí.
    I18N.alCambiar(() => {
        pintarBanner();
        conEnlaces.forEach((el) => (el.isConnected ? pintarEnlaces(el) : conEnlaces.delete(el)));
        conNota.forEach((el) => (el.isConnected ? pintarNota(el) : conNota.delete(el)));
    });

    return { banner, exigirAceptacion, enlaces, notaLogin, permitido };
})();
