/**
 * Diálogos de confirmación, en el estilo de la aplicación.
 *
 * Sustituyen a `confirm()` y `prompt()` del navegador, que pintan una caja gris
 * del sistema operativo en medio de la interfaz: no siguen el tema, no se
 * pueden traducir y en algunos navegadores llegan a bloquear la pestaña entera.
 *
 * Devuelven una promesa, así que en quien los llama se leen igual de derechos
 * que el `confirm()` al que sustituyen:
 *
 *     if (!await Confirmar.pedir({ mensaje: '¿Cerrar sesión?' })) return;
 *
 * Accesibilidad: el foco entra en el diálogo y no se sale de él mientras está
 * abierto, Escape cancela, Enter acepta y al cerrar el foco vuelve al botón
 * desde el que se abrió. Eso es justo lo que un `confirm()` hace gratis y lo
 * que más se olvida al sustituirlo.
 */
const Confirmar = (() => {
    'use strict';

    let abierto = null;   // { cerrar(valor) } del diálogo en pantalla

    /*
     * Cuándo volvió la ventana a primer plano. Un diálogo «firme» (aprobar)
     * no acepta nada en el primer instante después de volver: al cambiar de
     * pestaña o de programa (Alt+Tab, clic en la barra de tareas) llegaban
     * pulsaciones y clics sueltos al botón que tenía el foco, y un RFQ quedó
     * aprobado sin que nadie pulsara «Aprobar» (INT-59C34202, 2026-09-29).
     */
    let vueltaEn = 0;
    const marcarVuelta = () => { vueltaEn = Date.now(); };
    window.addEventListener('focus', marcarVuelta);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) marcarVuelta(); });

    /** El texto llega de mensajes de error y de la base de datos: nunca a innerHTML. */
    function texto(valor) {
        const nodo = document.createElement('span');
        nodo.textContent = valor == null ? '' : String(valor);
        return nodo.innerHTML;
    }

    const ICONOS = {
        pregunta: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        peligro:  '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    };

    /**
     * Monta el diálogo y devuelve una promesa con lo que el usuario decida.
     *
     * `campo` distingue los dos usos: sin él es un sí/no; con él, el diálogo
     * lleva un cuadro de texto y resuelve con lo escrito (o null si se cancela).
     */
    function montar({ titulo, mensaje, aceptar, cancelar, peligro, campo, firme }) {
        // Dos diálogos a la vez no tienen sentido: el anterior se cancela.
        if (abierto) abierto.cerrar(campo ? null : false);

        const fondo = document.createElement('div');
        fondo.className = 'dialogo-fondo';

        const idTitulo = 'dlg-t-' + Date.now();
        fondo.innerHTML = `
            <div class="dialogo ${peligro ? 'dialogo--peligro' : ''}" role="dialog"
                 aria-modal="true" aria-labelledby="${idTitulo}">
                <div class="dialogo-cabecera">
                    <span class="dialogo-icono">${peligro ? ICONOS.peligro : ICONOS.pregunta}</span>
                    <h2 class="dialogo-titulo" id="${idTitulo}">${texto(titulo)}</h2>
                </div>
                ${mensaje ? `<p class="dialogo-mensaje">${texto(mensaje)}</p>` : ''}
                ${campo ? `
                    <label class="form-label" for="dialogoCampo">${texto(campo.etiqueta)}</label>
                    ${campo.tipo === 'password'
                        ? `<input class="form-input dialogo-campo" id="dialogoCampo"
                                  type="password" autocomplete="new-password"
                                  placeholder="${texto(campo.marcador || '')}"
                                  ${campo.reglas ? 'data-reglas' : ''}>`
                        : `<textarea class="form-input dialogo-campo" id="dialogoCampo" rows="3"
                                  placeholder="${texto(campo.marcador || '')}"></textarea>`}` : ''}
                <div class="dialogo-acciones">
                    <button type="button" class="btn btn-ghost" data-accion="cancelar">${texto(cancelar || I18N.t('dlg.cancelar'))}</button>
                    <button type="button" class="btn ${peligro ? 'btn-danger' : 'btn-primary'}"
                            data-accion="aceptar">${texto(aceptar || I18N.t('dlg.confirmar'))}</button>
                </div>
            </div>`;

        document.body.appendChild(fondo);

        const caja = fondo.querySelector('.dialogo');
        const entrada = fondo.querySelector('.dialogo-campo');
        const btnAceptar = fondo.querySelector('[data-accion="aceptar"]');
        const btnCancelar = fondo.querySelector('[data-accion="cancelar"]');
        const focoPrevio = document.activeElement;
        const abiertoEn = Date.now();

        return new Promise((resolver) => {
            let resuelto = false;

            function cerrar(valor) {
                if (resuelto) return;
                resuelto = true;
                abierto = null;
                document.removeEventListener('keydown', alPulsar, true);
                fondo.classList.add('cerrando');
                setTimeout(() => fondo.remove(), 150);
                // Devolver el foco a donde estaba: si no, se pierde al final
                // del documento y navegar con el tabulador se vuelve un lío.
                if (focoPrevio && focoPrevio.focus) focoPrevio.focus({ preventScroll: true });
                resolver(valor);
            }

            function aceptar(ev) {
                // «Firme»: sólo un clic de verdad, con la ventana a la vista
                // desde hace un momento y el diálogo abierto hace un momento.
                if (firme) {
                    const ahora = Date.now();
                    if (document.hidden || !document.hasFocus() ||
                        ahora - abiertoEn < 500 || ahora - vueltaEn < 900 ||
                        (ev && ev.isTrusted === false)) {
                        return;
                    }
                }
                if (!entrada) return cerrar(true);
                const valor = entrada.value.trim();
                if (campo.obligatorio && !valor) {
                    entrada.classList.add('campo-invalido');
                    entrada.focus();
                    return;
                }
                cerrar(valor);
            }

            function alPulsar(ev) {
                if (ev.key === 'Escape') {
                    ev.preventDefault();
                    return cerrar(entrada ? null : false);
                }
                // En un cuadro de texto Enter sirve para escribir; se acepta con Ctrl/Cmd+Enter.
                if (ev.key === 'Enter' && (!entrada || ev.ctrlKey || ev.metaKey)) {
                    // Un diálogo firme no se acepta con el teclado: un Enter
                    // perdido (al volver de otra ventana) no puede aprobar.
                    if (firme) { ev.preventDefault(); return; }
                    if (document.activeElement === btnCancelar) return;
                    ev.preventDefault();
                    return aceptar();
                }
                if (ev.key !== 'Tab') return;

                // El foco no debe salir del diálogo mientras está abierto.
                const focos = caja.querySelectorAll('button, textarea, input, [href]');
                if (!focos.length) return;
                const primero = focos[0];
                const ultimo = focos[focos.length - 1];
                if (ev.shiftKey && document.activeElement === primero) {
                    ev.preventDefault();
                    ultimo.focus();
                } else if (!ev.shiftKey && document.activeElement === ultimo) {
                    ev.preventDefault();
                    primero.focus();
                }
            }

            btnAceptar.addEventListener('click', aceptar);
            btnCancelar.addEventListener('click', () => cerrar(entrada ? null : false));
            // Sólo el fondo cancela: un clic dentro de la caja no debe cerrarla.
            fondo.addEventListener('mousedown', (ev) => {
                if (ev.target === fondo) cerrar(entrada ? null : false);
            });
            if (entrada) {
                entrada.addEventListener('input', () => entrada.classList.remove('campo-invalido'));
            }
            document.addEventListener('keydown', alPulsar, true);

            abierto = { cerrar };
            // En uno firme el foco empieza en «Cancelar»: una tecla suelta no
            // puede caer en el botón que decide.
            requestAnimationFrame(() => (entrada || (firme ? btnCancelar : btnAceptar)).focus({ preventScroll: true }));
        });
    }

    /**
     * Diálogo con varios campos. Resuelve con un objeto {id: valor}, o null si
     * se cancela.
     *
     * Existe para el alta de usuarios: son cuatro datos, y encadenar cuatro
     * `prompt()` seguidos —o cuatro diálogos de un campo— es maltratar a quien
     * los rellena. Comparte caja, teclas y foco con el resto de diálogos.
     */
    function montarFormulario({ titulo, mensaje, aceptar, cancelar, campos }) {
        if (abierto) abierto.cerrar(null);

        const fondo = document.createElement('div');
        fondo.className = 'dialogo-fondo';
        const idTitulo = 'dlg-f-' + Date.now();

        const html = campos.map((c) => {
            const id = 'campo-' + c.id;
            // La casilla lleva su etiqueta AL LADO, no encima: una etiqueta
            // arriba y un cuadradito solo debajo se lee como si faltara algo.
            if (c.tipo === 'checkbox') {
                return `<div class="form-group">
                            <label class="form-casilla" for="${id}">
                                <input type="checkbox" id="${id}" ${c.valor ? 'checked' : ''}>
                                <span>${texto(c.etiqueta)}</span>
                            </label>
                            ${c.nota ? `<p class="dialogo-nota">${texto(c.nota)}</p>` : ''}
                        </div>`;
            }
            const control = c.tipo === 'select'
                ? `<select class="form-select" id="${id}">${c.opciones || ''}</select>`
                : c.tipo === 'textarea'
                ? `<textarea class="form-textarea" id="${id}" rows="${c.filas || 3}"
                             placeholder="${texto(c.marcador || '')}">${texto(c.valor == null ? '' : String(c.valor))}</textarea>`
                : `<input class="form-input" id="${id}" type="${texto(c.tipo || 'text')}"
                          value="${texto(c.valor == null ? '' : String(c.valor)).replace(/"/g, '&quot;')}"
                          ${c.requerido ? 'required' : ''}
                          placeholder="${texto(c.marcador || '')}"
                          ${c.reglas ? 'data-reglas' : ''}
                          autocomplete="${c.tipo === 'password' ? 'new-password' : 'off'}">`;
            return `<div class="form-group">
                        <label class="form-label" for="${id}">${texto(c.etiqueta)}</label>
                        ${control}
                        ${c.nota ? `<p class="dialogo-nota">${texto(c.nota)}</p>` : ''}
                    </div>`;
        }).join('');

        fondo.innerHTML = `
            <div class="dialogo dialogo--formulario" role="dialog" aria-modal="true"
                 aria-labelledby="${idTitulo}">
                <div class="dialogo-cabecera">
                    <span class="dialogo-icono">${ICONOS.pregunta}</span>
                    <h2 class="dialogo-titulo" id="${idTitulo}">${texto(titulo)}</h2>
                </div>
                ${mensaje ? `<p class="dialogo-mensaje">${texto(mensaje)}</p>` : ''}
                <form class="dialogo-form">${html}</form>
                <div class="dialogo-acciones">
                    <button type="button" class="btn btn-ghost" data-accion="cancelar">${texto(cancelar || I18N.t('dlg.cancelar'))}</button>
                    <button type="button" class="btn btn-primary" data-accion="aceptar">${texto(aceptar || I18N.t('dlg.crear'))}</button>
                </div>
            </div>`;

        document.body.appendChild(fondo);
        const caja = fondo.querySelector('.dialogo');
        const focoPrevio = document.activeElement;

        return new Promise((resolver) => {
            let resuelto = false;

            function cerrar(valor) {
                if (resuelto) return;
                resuelto = true;
                abierto = null;
                document.removeEventListener('keydown', alPulsar, true);
                fondo.classList.add('cerrando');
                setTimeout(() => fondo.remove(), 150);
                if (focoPrevio && focoPrevio.focus) focoPrevio.focus({ preventScroll: true });
                resolver(valor);
            }

            function aceptar() {
                const salida = {};
                for (const c of campos) {
                    const el = fondo.querySelector('#campo-' + c.id);
                    if (c.tipo === 'checkbox') { salida[c.id] = el.checked; continue; }
                    const valor = (el.value || '').trim();
                    if (c.requerido && !valor) {
                        el.classList.add('campo-invalido');
                        el.focus();
                        return;
                    }
                    salida[c.id] = valor;
                }
                cerrar(salida);
            }

            function alPulsar(ev) {
                if (ev.key === 'Escape') { ev.preventDefault(); return cerrar(null); }
                // En un área de texto, Enter es un salto de línea, no «Aceptar».
                if (ev.key === 'Enter' && ev.target.tagName !== 'BUTTON'
                        && ev.target.tagName !== 'TEXTAREA') {
                    ev.preventDefault();
                    return aceptar();
                }
                if (ev.key !== 'Tab') return;
                const focos = caja.querySelectorAll('button, input, select, textarea');
                if (!focos.length) return;
                const primero = focos[0], ultimo = focos[focos.length - 1];
                if (ev.shiftKey && document.activeElement === primero) {
                    ev.preventDefault(); ultimo.focus();
                } else if (!ev.shiftKey && document.activeElement === ultimo) {
                    ev.preventDefault(); primero.focus();
                }
            }

            fondo.querySelector('[data-accion="aceptar"]').addEventListener('click', aceptar);
            fondo.querySelector('[data-accion="cancelar"]').addEventListener('click', () => cerrar(null));
            fondo.addEventListener('mousedown', (ev) => { if (ev.target === fondo) cerrar(null); });
            fondo.addEventListener('input', (ev) => ev.target.classList.remove('campo-invalido'));
            document.addEventListener('keydown', alPulsar, true);

            abierto = { cerrar };
            requestAnimationFrame(() => caja.querySelector('input, select')?.focus({ preventScroll: true }));
        });
    }

    return {
        montarFormulario,

        /** Sí/no. Resuelve true si se acepta. `firme: true` para decisiones
         *  que no deben poder tomarse sin querer (sólo con un clic). */
        pedir(opciones) {
            return montar({ titulo: I18N.t('dlg.confirmar'), ...opciones, campo: null });
        },

        /** Con cuadro de texto. Resuelve con lo escrito, o null si se cancela.
         *
         * `tipo: 'password'` cambia el área de texto por un campo de
         * contraseña —con su ojo, y con la lista de requisitos si además se
         * pasa `reglas: true`—. Lo usa el reseteo de la contraseña de otra
         * persona, que es escribir una contraseña, no un comentario.
         */
        pedirTexto(opciones) {
            const { etiqueta, marcador, obligatorio, tipo, reglas, ...resto } = opciones;
            return montar({
                titulo: I18N.t('dlg.confirmar'),
                ...resto,
                campo: { etiqueta, marcador, obligatorio, tipo, reglas },
            });
        },
    };
})();


/**
 * Diálogo de varios campos. Vive aquí, junto a Confirmar, porque comparte caja,
 * teclas y manejo del foco: son el mismo componente con distinto contenido.
 */
const Formulario = {
    /** Resuelve con {id: valor} o null si se cancela. */
    pedir(opciones) {
        return Confirmar.montarFormulario(opciones);
    },
};
