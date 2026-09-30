/**
 * Los campos de Pohua con el teclado del teléfono.
 *
 * En el teléfono el teclado tapa media pantalla, y lo que se está escribiendo
 * suele quedar justo debajo. Esto, para TODOS los campos de la aplicación
 * (páginas y diálogos):
 *
 *   - Publica en :root lo que queda visible con el teclado abierto
 *     (--vv-alto, --vv-arriba, de visualViewport). Las hojas de los diálogos
 *     usan eso para quedarse encima del teclado (style.css).
 *   - Al tocar un campo, cuando el teclado ya subió, lo lleva al centro de lo
 *     visible si quedó tapado.
 *   - Le pone a cada campo el teclado que le toca si nadie lo dijo: @ y sin
 *     mayúsculas para un correo, números para una cifra.
 *
 * En la compu no hace nada visible: sólo actúa con puntero de dedo.
 */
(function () {
    'use strict';

    const tactil = () => window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
    const vv = window.visualViewport;
    const raiz = document.documentElement;

    function publicar() {
        if (!vv) return;
        raiz.style.setProperty('--vv-alto', vv.height + 'px');
        raiz.style.setProperty('--vv-arriba', vv.offsetTop + 'px');
    }
    if (vv) {
        vv.addEventListener('resize', publicar);
        vv.addEventListener('scroll', publicar);
        publicar();
    }

    /** El teclado adecuado, sólo si el campo no lo declara ya. */
    function vestir(campo) {
        if (campo.__vestido) return;
        campo.__vestido = true;
        const tipo = (campo.getAttribute('type') || '').toLowerCase();
        const poner = (a, v) => { if (!campo.hasAttribute(a)) campo.setAttribute(a, v); };
        if (tipo === 'email') {
            poner('inputmode', 'email');
            poner('autocapitalize', 'off');
            poner('autocorrect', 'off');
            poner('spellcheck', 'false');
        } else if (tipo === 'number') {
            poner('inputmode', campo.step && campo.step !== '1' ? 'decimal' : 'numeric');
        } else if (tipo === 'tel') {
            poner('inputmode', 'tel');
        } else if (tipo === 'password' || tipo === 'url') {
            poner('autocapitalize', 'off');
            poner('autocorrect', 'off');
            poner('spellcheck', 'false');
        }
    }

    function aLaVista(campo) {
        const r = campo.getBoundingClientRect();
        const arriba = vv ? vv.offsetTop : 0;
        const alto = vv ? vv.height : window.innerHeight;
        const margen = 24;
        if (r.top < arriba + margen || r.bottom > arriba + alto - margen) {
            campo.scrollIntoView({ block: 'center', behavior: 'smooth' });
        }
    }

    // `pointerdown` llega antes de que el teclado se abra: es cuando el tipo de
    // teclado todavía se puede elegir.
    document.addEventListener('pointerdown', (ev) => {
        const campo = ev.target && ev.target.closest && ev.target.closest('input, textarea');
        if (campo) vestir(campo);
    }, true);

    document.addEventListener('focusin', (ev) => {
        const campo = ev.target;
        if (!campo || !campo.matches || !campo.matches('input, textarea, select')) return;
        vestir(campo);
        if (!tactil() || campo.type === 'checkbox' || campo.type === 'radio') return;
        // El teclado tarda en subir; se mira cuando ya ocupó su sitio.
        let hecho = false;
        const mirar = () => { if (hecho) return; hecho = true; aLaVista(campo); };
        if (vv) vv.addEventListener('resize', function una() { vv.removeEventListener('resize', una); setTimeout(mirar, 60); });
        setTimeout(mirar, 350);
    });
})();
