/**
 * Light / dark theme.
 *
 * Two pieces, on purpose:
 *
 *  1. A tiny snippet inlined in the <head> of index.html that sets
 *     data-tema on <html> BEFORE the first paint. Without it the page
 *     renders dark for an instant and then flips to light — the flash you see
 *     on sites that decide the theme after the stylesheet loads.
 *
 *  2. This file, loaded normally, which wires the button and remembers the
 *     choice.
 *
 * The preference lives in localStorage. If the user never chose, the system
 * setting decides (prefers-color-scheme), and it keeps following the system
 * until they press the button for the first time.
 */
const Tema = (() => {
    'use strict';

    const CLAVE = 'cgr-tema';
    const OSCURO = 'dark';
    const CLARO = 'light';

    /** localStorage falla en modo privado de algunos navegadores. */
    function leerGuardado() {
        try {
            const valor = localStorage.getItem(CLAVE);
            return valor === CLARO || valor === OSCURO ? valor : null;
        } catch (err) {
            return null;
        }
    }

    function guardar(tema) {
        try {
            localStorage.setItem(CLAVE, tema);
        } catch (err) {
            // Sin poder guardar, el tema dura lo que dure la pestaña. Aceptable.
        }
    }

    function delSistema() {
        return window.matchMedia &&
               window.matchMedia('(prefers-color-scheme: light)').matches ? CLARO : OSCURO;
    }

    function actual() {
        return document.documentElement.dataset.tema === CLARO ? CLARO : OSCURO;
    }

    /**
     * El color que toca el borde superior de la página, para la barra del
     * navegador. Se lee del propio tema; los literales son la red de seguridad
     * para el instante en que el CSS todavía no ha cargado.
     */
    function colorDelBorde(tema) {
        const token = getComputedStyle(document.documentElement)
            .getPropertyValue('--bg-surface').trim();
        if (token) return token;
        return tema === CLARO ? '#e9eef7' : '#172033';
    }

    function aplicar(tema) {
        document.documentElement.dataset.tema = tema;

        // La barra del navegador en el móvil. El color NO se escribe a mano:
        // se lee de --bg-surface, que es lo que hay pegado al borde de arriba
        // de la página (la cabecera y el menú lateral). Escrito a mano se
        // desincronizó —se quedó en el #f1f4f9 de una versión anterior del
        // tema claro— y en el teléfono se veía justo eso: una franja casi
        // blanca arriba, más clara que todo lo que tenía debajo.
        const meta = document.querySelector('meta[name="theme-color"]');
        if (meta) meta.setAttribute('content', colorDelBorde(tema));

        const boton = document.getElementById('btnTema');
        if (boton) {
            const siguiente = tema === CLARO ? 'dark' : 'light';
            const texto = (typeof I18N !== 'undefined')
                ? I18N.t('tema.cambiarA.' + siguiente) : `Switch to ${siguiente} mode`;
            boton.title = texto;
            boton.setAttribute('aria-label', texto);
        }
    }

    function alternar() {
        const nuevo = actual() === CLARO ? OSCURO : CLARO;
        aplicar(nuevo);
        guardar(nuevo);
    }

    function init() {
        // El <head> ya aplicó el tema; aquí sólo se deja consistente por si
        // este archivo se carga en una página sin ese snippet.
        aplicar(leerGuardado() || delSistema());

        const boton = document.getElementById('btnTema');
        if (boton) boton.addEventListener('click', alternar);

        // Mientras no haya elección explícita, se sigue al sistema.
        if (window.matchMedia) {
            const consulta = window.matchMedia('(prefers-color-scheme: light)');
            const alCambiar = () => {
                if (!leerGuardado()) aplicar(delSistema());
            };
            if (consulta.addEventListener) consulta.addEventListener('change', alCambiar);
            else if (consulta.addListener) consulta.addListener(alCambiar);
        }
    }

    return { init, alternar, actual };
})();

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', Tema.init);
} else {
    Tema.init();
}
