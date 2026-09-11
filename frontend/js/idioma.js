/**
 * El selector de idioma: el botón de la esquina y su lista.
 *
 * Va al lado del de tema porque son la misma clase de cosa —dos preferencias
 * de quien mira, no ajustes del sistema— y quien busca una espera encontrar la
 * otra al lado.
 *
 * Es una lista propia y no un <select> nativo: un <select> se pinta con el
 * estilo del sistema operativo y en la esquina, sobre el fondo estrellado,
 * canta. Eso obliga a poner a mano lo que el <select> daba gratis: roles ARIA,
 * teclado y cierre al pulsar fuera.
 */
const SelectorIdioma = (() => {
    'use strict';

    let abierto = false;

    const boton = () => document.getElementById('btnIdioma');
    const lista = () => document.getElementById('idiomaLista');

    function pintarLista() {
        const ul = lista();
        if (!ul) return;
        ul.innerHTML = I18N.IDIOMAS.map(i => `
            <li role="option" aria-selected="${i.codigo === I18N.idioma}">
                <button type="button" class="idioma-opcion ${i.codigo === I18N.idioma ? 'activa' : ''}"
                        data-codigo="${i.codigo}" lang="${i.codigo}">
                    <span class="idioma-corto">${i.corto}</span>
                    <span>${i.etiqueta}</span>
                </button>
            </li>`).join('');
    }

    function pintarBoton() {
        const corto = document.getElementById('idiomaCorto');
        const actual = I18N.IDIOMAS.find(i => i.codigo === I18N.idioma);
        if (corto && actual) corto.textContent = actual.corto;
    }

    function abrir() {
        pintarLista();
        const ul = lista();
        if (!ul) return;
        ul.hidden = false;
        abierto = true;
        boton()?.setAttribute('aria-expanded', 'true');
        ul.querySelector('.activa')?.focus({ preventScroll: true });
    }

    function cerrar({ devolverFoco = false } = {}) {
        const ul = lista();
        if (!ul || !abierto) return;
        ul.hidden = true;
        abierto = false;
        boton()?.setAttribute('aria-expanded', 'false');
        if (devolverFoco) boton()?.focus({ preventScroll: true });
    }

    function init() {
        const b = boton();
        if (!b) return;

        pintarBoton();

        b.addEventListener('click', (ev) => {
            ev.stopPropagation();
            abierto ? cerrar() : abrir();
        });

        lista()?.addEventListener('click', (ev) => {
            const opcion = ev.target.closest('.idioma-opcion');
            if (!opcion) return;
            I18N.fijar(opcion.dataset.codigo);
            cerrar({ devolverFoco: true });
        });

        // Fuera del selector se cierra; con Escape también, y el foco vuelve al
        // botón para no perderse al final del documento.
        document.addEventListener('click', (ev) => {
            if (abierto && !ev.target.closest('#idioma')) cerrar();
        });
        document.addEventListener('keydown', (ev) => {
            if (ev.key === 'Escape' && abierto) cerrar({ devolverFoco: true });
        });

        // Al cambiar de idioma se repinta el propio selector.
        I18N.alCambiar(() => { pintarBoton(); if (abierto) pintarLista(); });
    }

    return { init };
})();

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', SelectorIdioma.init);
} else {
    SelectorIdioma.init();
}
