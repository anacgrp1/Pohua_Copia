/**
 * Password: el ojo para ver lo que se escribe y la lista de requisitos.
 *
 * DOS COSAS, y las dos se aplican solas.
 *
 * 1. EL OJO. Todo `input[type="password"]` de la aplicación —el acceso, el
 *    cambio de contraseña propia, el alta de una persona, el reseteo— recibe
 *    un botón para ver lo escrito. No es un adorno: una contraseña larga
 *    tecleada a ciegas se equivoca, y el remedio de la gente cuando no puede
 *    verla es escribir una corta que no falle. El ojo empuja hacia arriba, no
 *    hacia abajo.
 *
 *    Vuelve a taparse al salir del campo: enseñarla es una comprobación de un
 *    momento, no un estado en el que se deje la pantalla mientras alguien pasa
 *    por detrás.
 *
 * 2. LOS REQUISITOS. Un campo marcado con `data-reglas` enseña debajo lo que
 *    la contraseña TIENE que cumplir, y cada requisito se pone en verde con su
 *    palomita en cuanto se cumple, mientras se escribe. Antes esto era una
 *    línea de texto —"Al menos 12 caracteres"— y las otras dos condiciones no
 *    se decían en ninguna parte: se descubrían cuando el servidor rechazaba el
 *    alta. Pedir algo y no decir qué es hace perder el trabajo ya escrito.
 *
 * LAS REGLAS SON LAS DEL SERVIDOR, copiadas de `app/auth/passwords.py`. El que
 * manda sigue siendo el servidor: esta lista NO deja pasar nada, sólo cuenta
 * de antemano lo que allí se va a comprobar. Que las dos listas no se separen
 * lo vigila `tests/frontend/test_politica_password.py`, que lee este archivo y
 * el de Python y falla si dejan de coincidir.
 */
const Password = (() => {
    'use strict';

    // --- La política, igual que en app/auth/passwords.py --------------------
    const LONGITUD_MINIMA = 12;
    const VARIEDAD_MINIMA = 5;
    const COMUNES = [
        'contrasena123', 'contraseña123', 'password123', 'cotizador123',
        'administrador', '12345678901234', 'qwertyuiop123',
    ];

    const REGLAS = [
        {
            id: 'largo',
            clave: 'pw.regla.largo',
            datos: { n: LONGITUD_MINIMA },
            cumple: (v) => v.length >= LONGITUD_MINIMA,
        },
        {
            id: 'variedad',
            clave: 'pw.regla.variedad',
            datos: { n: VARIEDAD_MINIMA },
            cumple: (v) => new Set(v).size >= VARIEDAD_MINIMA,
        },
        {
            id: 'comun',
            clave: 'pw.regla.comun',
            datos: {},
            cumple: (v) => !COMUNES.includes(v.toLowerCase()),
        },
    ];

    const ICONO_OJO = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
    const ICONO_TACHADO = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
    const ICONO_PALOMITA = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
    const ICONO_PUNTO = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/></svg>';

    function esc(valor) {
        const nodo = document.createElement('span');
        nodo.textContent = valor == null ? '' : String(valor);
        return nodo.innerHTML;
    }

    /** ¿Cumple la política? Lo usa quien quiera bloquear un botón. */
    function valida(valor) {
        const v = valor || '';
        return REGLAS.every(r => r.cumple(v));
    }

    // ------------------------------------------------------------------ ojo

    function ponerOjo(campo) {
        if (campo.dataset.ojo) return;
        campo.dataset.ojo = '1';

        // El campo se envuelve para poder colocar el botón encima del borde
        // derecho. Se conservan las clases del campo: el ancho y el hueco de
        // la derecha los pone el CSS a partir de .pw-caja.
        const caja = document.createElement('span');
        caja.className = 'pw-caja';
        campo.parentNode.insertBefore(caja, campo);
        caja.appendChild(campo);

        const boton = document.createElement('button');
        boton.type = 'button';                 // dentro de un <form>, no envía
        boton.className = 'pw-ojo';
        boton.tabIndex = -1;                   // el orden del formulario es el
                                               // de los campos, no el de este
                                               // atajo; se alcanza con ratón o
                                               // pulsación, y con teclado ya
                                               // está el propio campo
        boton.setAttribute('aria-hidden', 'true');
        boton.innerHTML = ICONO_OJO;
        boton.title = I18N.t('pw.ver');

        const alternar = () => {
            const oculto = campo.type === 'password';
            campo.type = oculto ? 'text' : 'password';
            boton.innerHTML = oculto ? ICONO_TACHADO : ICONO_OJO;
            boton.title = I18N.t(oculto ? 'pw.ocultar' : 'pw.ver');
            boton.classList.toggle('pw-ojo--abierto', oculto);
        };
        boton.addEventListener('click', alternar);

        caja.appendChild(boton);

        // Al salir del campo vuelve a taparse. Sin esto, una contraseña
        // destapada se queda a la vista en una pantalla que nadie está ya
        // mirando.
        //
        // Se escucha `focusout` de la CAJA, no `blur` del campo, y esa
        // diferencia importa: al pulsar el ojo el navegador le da el foco al
        // botón —lo hace incluso con tabindex="-1"—, así que el campo se queda
        // sin foco en ese mismo instante. Escuchando el campo, el siguiente
        // clic en cualquier otro sitio ya no le llegaba a nadie y la
        // contraseña se quedaba destapada para siempre. La caja incluye al
        // botón, así que el foco sigue "dentro" mientras se usa el ojo y sale
        // sólo cuando se va de verdad.
        caja.addEventListener('focusout', (ev) => {
            if (caja.contains(ev.relatedTarget)) return;   // sigue dentro
            if (campo.type === 'text') alternar();
        });
    }

    // -------------------------------------------------------------- reglas

    function fila(regla, texto) {
        return `<li class="pw-regla" data-regla="${regla}">
                    <span class="pw-marca" aria-hidden="true">${ICONO_PUNTO}</span>
                    <span>${esc(texto)}</span>
                </li>`;
    }

    function listaReglas(campo) {
        // El campo "repetir" enseña SÓLO que las dos coincidan. Las otras tres
        // ya están escritas dos centímetros más arriba, en el campo de al
        // lado: repetirlas llena la pantalla de requisitos y hace que la única
        // condición nueva —la que de verdad se comprueba aquí— pase
        // desapercibida entre las otras.
        const items = campo.dataset.igualQue
            ? fila('igual', I18N.t('pw.regla.igual'))
            : REGLAS.map(r => fila(r.id, I18N.t(r.clave, r.datos))).join('');
        const igual = '';

        const caja = document.createElement('div');
        caja.className = 'pw-reglas';
        // aria-live: quien use lector de pantalla se entera de que un
        // requisito pasó a cumplirse sin tener que ir a buscarlo.
        caja.innerHTML = `
            ${campo.dataset.igualQue ? '' : `<p class="pw-reglas-titulo">${esc(I18N.t('pw.debe'))}</p>`}
            <ul class="pw-reglas-lista" aria-live="polite">${items}${igual}</ul>`;
        return caja;
    }

    function revisar(campo, caja) {
        const valor = campo.value || '';
        const vacio = valor.length === 0;

        const marcar = (li, ok) => {
            li.classList.toggle('pw-regla--ok', ok);
            const marca = li.querySelector('.pw-marca');
            if (marca) marca.innerHTML = ok ? ICONO_PALOMITA : ICONO_PUNTO;
        };

        REGLAS.forEach(r => {
            const li = caja.querySelector(`[data-regla="${r.id}"]`);
            // Con el campo vacío nada está "cumplido": la regla de no ser una
            // contraseña común la cumpliría técnicamente una cadena vacía, y
            // una palomita verde antes de escribir nada es mentira.
            if (li) marcar(li, !vacio && r.cumple(valor));   // null en "repetir"
        });

        const liIgual = caja.querySelector('[data-regla="igual"]');
        if (liIgual) {
            const otro = document.getElementById(campo.dataset.igualQue);
            marcar(liIgual, !vacio && !!otro && otro.value === valor);
        }
    }

    function ponerReglas(campo) {
        if (campo.dataset.reglasPuestas) return;
        campo.dataset.reglasPuestas = '1';

        const caja = listaReglas(campo);
        // Después de la caja del ojo (que ya envuelve al campo), no del campo.
        const ancla = campo.closest('.pw-caja') || campo;
        ancla.parentNode.insertBefore(caja, ancla.nextSibling);

        const mirar = () => revisar(campo, caja);
        campo.addEventListener('input', mirar);

        // Si es el campo "repetir", también hay que revisarlo cuando cambia el
        // otro: si alguien corrige el de arriba, el de abajo deja de coincidir
        // y tiene que enterarse sin tocarlo.
        if (campo.dataset.igualQue) {
            document.getElementById(campo.dataset.igualQue)
                ?.addEventListener('input', mirar);
        }
        mirar();
    }

    // ---------------------------------------------------------------- riego

    /** Prepara todos los campos de contraseña que haya bajo `raiz`. */
    function conectar(raiz = document) {
        if (!raiz || typeof raiz.querySelectorAll !== 'function') return;
        raiz.querySelectorAll('input[type="password"]').forEach(campo => {
            ponerOjo(campo);
            if (campo.dataset.reglas !== undefined) ponerReglas(campo);
        });
    }

    /**
     * Se vigila el documento entero, igual que en Avatar y por lo mismo: los
     * campos de contraseña aparecen desde el acceso, el perfil y dos diálogos
     * que se montan al vuelo. Pedirle a cada sitio que se acuerde de llamar
     * aquí es garantizar que un día uno se olvide y salga un campo sin ojo.
     */
    function vigilar() {
        conectar(document);
        if (typeof MutationObserver === 'undefined') return;
        new MutationObserver((cambios) => {
            for (const cambio of cambios) {
                for (const nodo of cambio.addedNodes) {
                    if (nodo.nodeType !== 1) continue;
                    if (nodo.matches?.('input[type="password"]')) {
                        ponerOjo(nodo);
                        if (nodo.dataset.reglas !== undefined) ponerReglas(nodo);
                    } else {
                        conectar(nodo);
                    }
                }
            }
        }).observe(document.documentElement, { childList: true, subtree: true });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', vigilar, { once: true });
    } else {
        vigilar();
    }

    return { conectar, valida, LONGITUD_MINIMA, VARIEDAD_MINIMA, COMUNES };
})();
