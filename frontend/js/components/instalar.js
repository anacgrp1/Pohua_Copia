/**
 * Aviso de instalación: la barra de arriba que ofrece guardar Pohua como
 * aplicación en el teléfono.
 *
 * Sólo aparece en el móvil. En un ordenador el cotizador se usa en una pestaña
 * más, junto al correo y al ERP; ahí una barra insistiendo en "instálame" es
 * ruido. En el teléfono sí cambia algo: instalada arranca a pantalla completa,
 * sin barra de direcciones, y queda un icono en la pantalla de inicio en vez de
 * un enlace perdido en el historial.
 *
 * Hay DOS caminos, porque los navegadores no se ponen de acuerdo:
 *
 *   1. Chrome y Edge (Android) avisan con `beforeinstallprompt` cuando la
 *      aplicación cumple los requisitos. Ese aviso se guarda —el navegador sólo
 *      lo lanza una vez— y se dispara al pulsar el botón. Aquí "Instalar" abre
 *      el diálogo del sistema y se acabó.
 *
 *   2. Safari en iPhone no tiene ese evento ni forma de instalar por código:
 *      es el usuario quien tiene que ir a Compartir → Añadir a inicio. Ahí el
 *      botón no puede instalar nada, así que explica el camino en vez de
 *      prometer algo que no va a pasar.
 *
 * Cuándo NO se enseña:
 *   - Ya está instalada: `display-mode: standalone` (o `navigator.standalone`
 *     en iOS). Ofrecer instalar lo que ya está instalado desconcierta.
 *   - La cerraron. Se recuerda, y no vuelve a salir en un mes: un aviso que
 *     reaparece en cada visita después de decirle que no es una molestia, no un
 *     recordatorio.
 *   - No es un móvil.
 */
const Instalar = (() => {
    'use strict';

    const CLAVE = 'cgr-instalar-oculto';
    const DESCANSO_MS = 30 * 24 * 60 * 60 * 1000;   // un mes

    // Aviso de Chrome/Edge, guardado para poder lanzarlo al pulsar el botón.
    let aviso = null;
    let barra = null;

    const esMovil = () =>
        window.matchMedia && window.matchMedia('(max-width: 768px)').matches;

    /** ¿Se está viendo ya como aplicación instalada? */
    const yaInstalada = () =>
        (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) ||
        window.navigator.standalone === true;

    /** iPhone o iPad: ahí no existe `beforeinstallprompt`. */
    function esIOS() {
        const ua = navigator.userAgent || '';
        // iPadOS 13+ se presenta como Mac; se distingue porque tiene táctil.
        const iPadModerno = /Macintosh/.test(ua) && navigator.maxTouchPoints > 1;
        return /iPad|iPhone|iPod/.test(ua) || iPadModerno;
    }

    function silenciada() {
        try {
            const hasta = Number(localStorage.getItem(CLAVE));
            return Number.isFinite(hasta) && hasta > Date.now();
        } catch (err) {
            return false;
        }
    }

    function silenciar() {
        try { localStorage.setItem(CLAVE, String(Date.now() + DESCANSO_MS)); }
        catch (err) { /* modo privado: sólo se calla en esta sesión */ }
    }

    /**
     * Publica el alto de la barra en --alto-instalar.
     *
     * La barra es fija y tapa la esquina de controles y el botón del menú, que
     * también son fijos. En vez de sumar altos a mano en cinco sitios, se
     * publica uno y el CSS lo suma donde haga falta. Es lo mismo que hace la
     * barra del asistente con --alto-asistente.
     */
    function medir() {
        const alto = barra && !barra.hidden ? barra.getBoundingClientRect().height : 0;
        document.documentElement.style.setProperty('--alto-instalar', Math.round(alto) + 'px');
    }

    function cerrar() {
        silenciar();
        if (barra) barra.hidden = true;
        medir();
    }

    async function instalar() {
        if (esIOS()) {
            // En iOS no hay nada que lanzar: se explica el camino y la barra se
            // queda abierta mientras lo siguen.
            const texto = barra.querySelector('.instalar-texto');
            if (texto) texto.textContent = I18N.t('instalar.ios');
            const boton = barra.querySelector('.instalar-boton');
            if (boton) boton.hidden = true;
            medir();
            return;
        }
        if (!aviso) return;

        const guardado = aviso;
        aviso = null;              // el navegador no deja reutilizarlo
        guardado.prompt();
        try {
            const { outcome } = await guardado.userChoice;
            // Tanto si acepta como si no, la barra se va: ya respondió.
            if (outcome === 'accepted') Toast.success(I18N.t('instalar.hecho'));
        } catch (err) {
            console.warn('No se pudo abrir el diálogo de instalación:', err);
        }
        cerrar();
    }

    function pintar() {
        if (barra) return;

        barra = document.createElement('div');
        barra.className = 'instalar-barra';
        barra.setAttribute('role', 'region');
        barra.hidden = true;
        barra.innerHTML = `
            <span class="instalar-icono" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                     stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 3v12"/><polyline points="7 10 12 15 17 10"/>
                    <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>
                </svg>
            </span>
            <span class="instalar-texto"></span>
            <button type="button" class="btn btn-primary btn-sm instalar-boton"></button>
            <button type="button" class="instalar-cerrar" aria-label="">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                     stroke-linecap="round" aria-hidden="true">
                    <line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/>
                </svg>
            </button>`;
        document.body.insertBefore(barra, document.body.firstChild);

        barra.querySelector('.instalar-boton').addEventListener('click', instalar);
        barra.querySelector('.instalar-cerrar').addEventListener('click', cerrar);

        traducir();
        I18N.alCambiar(traducir);
        window.addEventListener('resize', medir, { passive: true });
    }

    function traducir() {
        if (!barra) return;
        const texto = barra.querySelector('.instalar-texto');
        const boton = barra.querySelector('.instalar-boton');
        const cerrarBtn = barra.querySelector('.instalar-cerrar');
        if (texto) texto.textContent = I18N.t('instalar.mensaje');
        if (boton) boton.textContent = I18N.t(esIOS() ? 'instalar.como' : 'instalar.boton');
        if (cerrarBtn) {
            cerrarBtn.setAttribute('aria-label', I18N.t('instalar.cerrar'));
            cerrarBtn.setAttribute('title', I18N.t('instalar.cerrar'));
        }
        medir();
    }

    function mostrar() {
        if (!esMovil() || yaInstalada() || silenciada()) return;
        pintar();
        barra.hidden = false;
        medir();
    }

    function init() {
        // Chrome/Edge: se captura el aviso antes de que el navegador enseñe el
        // suyo, y a partir de ahí la barra es nuestra.
        window.addEventListener('beforeinstallprompt', (ev) => {
            ev.preventDefault();
            aviso = ev;
            mostrar();
        });

        // Ya instalada desde otra pestaña o desde el menú del navegador.
        window.addEventListener('appinstalled', () => {
            aviso = null;
            if (barra) { barra.hidden = true; medir(); }
        });

        // iOS nunca lanza el evento, así que la barra sale sola. Se espera un
        // momento: si aparece nada más cargar, tapa la portada justo cuando la
        // persona está viendo de qué va esto.
        if (esIOS()) setTimeout(mostrar, 2500);
    }

    return { init, mostrar, cerrar };
})();

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', Instalar.init);
} else {
    Instalar.init();
}
