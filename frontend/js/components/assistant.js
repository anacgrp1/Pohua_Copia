/**
 * Asistente — barra fija, presente en toda la aplicación.
 *
 * Vive fuera de las páginas: se monta una vez sobre #assistantDock y sigue ahí
 * al navegar. Si se montara dentro de cada página habría que repetirlo en las
 * seis y el texto a medio escribir se perdería al cambiar de pantalla.
 *
 * Dos mitades que conviene no confundir, porque cuestan cosas distintas:
 *
 *   - Los tres botones son consultas a la base de datos. Cero API, funcionan
 *     aunque no haya clave de Anthropic configurada.
 *   - El campo de texto es lo ÚNICO que llama al modelo, y sólo al enviar.
 *
 * Por eso el envío bloquea el botón mientras dura: cada pulsación es una
 * llamada de pago y el doble clic es gratis para quien lo hace.
 */
const Assistant = (() => {
    'use strict';

    let montado = false;

    /** El texto viene del servidor y de correos de clientes: nunca a innerHTML. */
    function esc(valor) {
        const nodo = document.createElement('span');
        nodo.textContent = valor == null ? '' : String(valor);
        return nodo.innerHTML;
    }

    const ICONOS = {
        resumen:  '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/></svg>',
        atencion: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        exportar: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
        enviar:   '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>',
        chispa:   '<svg class="icono-sol" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><use href="#pohua-sol"/></svg>',
        cerrar:   '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    };

    // ------------------------------------------------------------------ panel

    const panel = () => document.getElementById('assistantPanel');

    function mostrar(html) {
        const p = panel();
        if (!p) return;
        p.innerHTML = html;
        p.hidden = false;
    }

    function cerrar() {
        const p = panel();
        if (p) { p.hidden = true; p.innerHTML = ''; }
    }

    function cabecera(titulo, nota) {
        return `<div class="assistant-panel-head">
                    <h3>${esc(titulo)}</h3>
                    ${nota ? `<span class="assistant-nota">${esc(nota)}</span>` : ''}
                    <button type="button" class="btn btn-ghost btn-icon" data-cerrar
                            title="${esc(I18N.t('asis.cerrar'))}" aria-label="${esc(I18N.t('asis.cerrar'))}">${ICONOS.cerrar}</button>
                </div>`;
    }

    const ocupado = (titulo, texto) =>
        mostrar(cabecera(titulo) + `<div class="assistant-cargando">${esc(texto || '…')}</div>`);

    function fallo(err, titulo) {
        if (err && err.sesionExpirada) { cerrar(); return; }
        mostrar(cabecera(titulo) + `<p class="assistant-error">${esc(err.message)}</p>`);
    }

    // --------------------------------------------------------------- acciones

    async function verResumen() {
        ocupado(I18N.t('asis.tituloResumen'));
        try {
            const d = await API.assistantSummary();
            const cifra = (v, etiqueta) =>
                `<div class="assistant-cifra"><strong>${esc(v)}</strong><span>${esc(etiqueta)}</span></div>`;
            const lista = (filas, vacio) => filas.length
                ? filas.map(([k, v]) => `<li><span>${esc(k)}</span><b>${esc(v)}</b></li>`).join('')
                : `<li class="vacio">${esc(vacio)}</li>`;

            mostrar(
                cabecera(I18N.t('asis.tituloResumen'), I18N.t('asis.deLaBase')) +
                `<div class="assistant-cifras">
                    ${cifra(d.total, I18N.t('asis.total'))}
                    ${cifra(d.ultimos_7_dias, I18N.t('asis.dias7'))}
                    ${cifra(d.ultimos_30_dias, I18N.t('asis.dias30'))}
                    ${cifra(d.clientes, I18N.t('asis.clientes'))}
                 </div>
                 <div class="assistant-columnas">
                    <div><h4>${esc(I18N.t('asis.porEstado'))}</h4><ul class="assistant-lista">
                        ${lista(d.por_estado.map(e => [e.estado, e.total]), I18N.t('asis.sinRfqs'))}
                    </ul></div>
                    <div><h4>${esc(I18N.t('asis.materiales'))}</h4><ul class="assistant-lista">
                        ${lista(d.materiales.map(m => [m.material, m.total]), I18N.t('asis.sinMaterial'))}
                    </ul></div>
                 </div>`);
        } catch (err) { fallo(err, I18N.t('asis.errResumen')); }
    }

    async function verAtencion() {
        ocupado(I18N.t('asis.tituloAtencion'));
        try {
            const d = await API.assistantAttention();
            if (!d.pendientes.length) {
                mostrar(cabecera(I18N.t('asis.tituloAtencion'), I18N.t('asis.deLaBase2')) +
                    `<p class="assistant-vacio">${esc(I18N.t('asis.nadaPendiente'))}</p>`);
                return;
            }
            const filas = d.pendientes.map(p => `
                <tr>
                    <td><a href="/rfq-detail?id=${encodeURIComponent(p.rfq_id)}"
                           class="assistant-enlace" data-rfq="${esc(p.rfq_id)}">${esc(p.rfq_id)}</a></td>
                    <td>${esc(p.cliente_id || '—')}</td>
                    <td>${esc(p.part_number || '—')}</td>
                    <td><span class="badge">${esc(p.estado)}</span></td>
                    <td>${esc(p.dias_esperando)} d</td>
                    <td class="${p.criticas > 0 ? 'assistant-critico' : ''}">${esc(p.bandera || '—')}</td>
                </tr>`).join('');

            mostrar(
                cabecera(I18N.t('asis.tituloAtencion'),
                         I18N.t('asis.esperando', { n: d.total, c: d.criticas })) +
                `<div class="assistant-tabla-caja">
                    <table class="assistant-tabla">
                        <thead><tr><th>${esc(I18N.t('asis.col.rfq'))}</th>
                                   <th>${esc(I18N.t('asis.col.cliente'))}</th>
                                   <th>${esc(I18N.t('asis.col.pieza'))}</th>
                                   <th>${esc(I18N.t('asis.col.estado'))}</th>
                                   <th>${esc(I18N.t('asis.col.espera'))}</th>
                                   <th>${esc(I18N.t('asis.col.bandera'))}</th></tr></thead>
                        <tbody>${filas}</tbody>
                    </table>
                 </div>`);
        } catch (err) { fallo(err, I18N.t('asis.errLista')); }
    }

    async function exportar() {
        try {
            await API.descargarCSV();
            Toast.success(I18N.t('aviso.csvHecho'));
        } catch (err) {
            if (err && err.sesionExpirada) return;
            Toast.error(I18N.t('aviso.csvFallo', { motivo: err.message }));
        }
    }

    async function preguntar() {
        const campo = document.getElementById('assistantInput');
        const boton = document.getElementById('assistantEnviar');
        if (!campo) return;

        const pregunta = campo.value.trim();
        if (!pregunta) { campo.focus(); return; }

        if (boton) boton.disabled = true;
        mostrar(cabecera(I18N.t('asis.tituloChat')) +
            `<p class="assistant-pregunta">${esc(pregunta)}</p>
             <div class="assistant-cargando">${esc(I18N.t('asis.pensando'))}</div>`);
        try {
            const d = await API.assistantAsk(pregunta);
            const gasto = d.tokens_entrada != null
                ? I18N.t('asis.tokens', { entrada: d.tokens_entrada, salida: d.tokens_salida }) : '';
            mostrar(cabecera(I18N.t('asis.tituloChat'), gasto) +
                `<p class="assistant-pregunta">${esc(pregunta)}</p>
                 <p class="assistant-respuesta">${esc(d.respuesta)}</p>`);
            campo.value = '';
        } catch (err) {
            fallo(err, I18N.t('asis.errPregunta'));
        } finally {
            if (boton) boton.disabled = false;
        }
    }

    // --------------------------------------------------------------- montaje

    function plantilla() {
        return `
            <!-- La burbuja. Sólo se ve en teléfono (lo decide el CSS): ahí la
                 barra entera ocupaba dos filas fijas encima del contenido, en
                 la pantalla donde menos sitio hay. Plegada deja libre todo eso
                 y se despliega al tocarla. -->
            <button type="button" class="assistant-burbuja" id="assistantBurbuja"
                    aria-expanded="false" aria-controls="assistantDock"
                    title="${esc(I18N.t('asis.abrir'))}"
                    aria-label="${esc(I18N.t('asis.abrir'))}">${ICONOS.chispa}</button>

            <div class="assistant-panel" id="assistantPanel" hidden></div>

            <div class="assistant-barra">
                <!-- El sol NO es decoración: es el mismo icono de la burbuja y
                     es el que la cierra. Abierta la barra en el teléfono, se
                     toca ese icono y se vuelve a plegar —el gesto de ida y el
                     de vuelta son el mismo sitio—, así que no hace falta una ×
                     aparte robándole espacio a los accesos rápidos.
                     En el escritorio nunca está "abierta" en este sentido, y
                     ahí el mismo botón hace lo único que tiene sentido pedirle:
                     llevar el foco al campo. -->
                <button type="button" class="assistant-chispa" id="assistantChispa"
                        title="${esc(I18N.t('asis.chat'))}"
                        aria-label="${esc(I18N.t('asis.chat'))}">${ICONOS.chispa}</button>
                <input type="text" class="assistant-input" id="assistantInput"
                       placeholder="${esc(I18N.t('asis.marcador'))}"
                       aria-label="${esc(I18N.t('asis.enviar'))}" autocomplete="off" maxlength="1000">
                <button type="button" class="btn btn-primary btn-icon assistant-enviar"
                        id="assistantEnviar"
                        title="${esc(I18N.t('asis.enviar'))}" aria-label="${esc(I18N.t('asis.enviar'))}">${ICONOS.enviar}</button>
            </div>

            <div class="assistant-acciones">
                <button type="button" class="btn btn-chip" data-accion="resumen"
                        data-permiso="rfq:leer">${ICONOS.resumen}<span>${esc(I18N.t('asis.resumen'))}</span></button>
                <button type="button" class="btn btn-chip btn-chip--aviso" data-accion="atencion"
                        data-permiso="rfq:leer">${ICONOS.atencion}<span>${esc(I18N.t('asis.atencion'))}</span></button>
                <button type="button" class="btn btn-chip" data-accion="exportar"
                        data-permiso="rfq:leer">${ICONOS.exportar}<span>${esc(I18N.t('asis.exportar'))}</span></button>
            </div>`;
    }

    /**
     * Publica el alto de la barra en --alto-asistente.
     *
     * Los avisos salen abajo a la derecha, que es justo donde vive esta barra:
     * sin esto se pisaban. No vale una constante, porque el alto cambia —el
     * panel de resultados se abre y se cierra, y los accesos rápidos se
     * reparten en dos filas en pantallas estrechas—, así que se mide de verdad
     * y se republica en cada cambio.
     *
     * En la portada y el login la barra no está montada y el alto es 0: allí
     * los avisos vuelven a la esquina de siempre.
     */
    function publicarAlto(muelle) {
        // `getClientRects()`, no `offsetParent`. En el teléfono el muelle es
        // `position: fixed` y ahí offsetParent vale null aunque esté a la
        // vista: con la comprobación anterior el alto salía 0 siempre, los
        // avisos se pintaban debajo de la burbuja y la última tarjeta de cada
        // lista se quedaba tapada. Un elemento oculto no tiene rectángulos, así
        // que esto sigue distinguiendo "no montado" de "montado y visible".
        const visible = !!muelle && muelle.getClientRects().length > 0;
        document.documentElement.style.setProperty(
            '--alto-asistente', (visible ? muelle.offsetHeight : 0) + 'px');
    }

    /**
     * Despliega o pliega la barra en el teléfono.
     *
     * Es una clase en el muelle y nada más: TODA la diferencia de aspecto la
     * hace el CSS, y sólo por debajo de 768px. En el escritorio la clase está
     * igualmente y no cambia nada, así que no hay dos comportamientos que
     * mantener ni un `if (esMovil)` que se equivoque al girar el teléfono.
     *
     * Al plegar se cierra también el panel de resultados: dejarlo abierto
     * detrás de una burbuja es guardar una pantalla que nadie va a volver a
     * ver, y al desplegar aparecería una respuesta vieja sin contexto.
     */
    function desplegar(muelle, abrir) {
        muelle.classList.toggle('assistant-dock--abierto', abrir);
        const burbuja = document.getElementById('assistantBurbuja');
        if (burbuja) burbuja.setAttribute('aria-expanded', String(!!abrir));
        // Al abrir NO se toca el foco, a propósito: enfocar el campo levanta
        // el teclado del teléfono, y eso se come media pantalla y tapa los
        // accesos rápidos justo cuando se acaban de enseñar. Tocar la burbuja
        // es "enséñame el asistente", no "voy a escribir": si se quiere
        // escribir, se toca el campo y entonces sí sale el teclado.
        if (!abrir) cerrar();
        publicarAlto(muelle);
    }

    /** Se llama una vez, al entrar en la aplicación. Repetirla no duplica nada. */
    function init({ rehacer = false } = {}) {
        const muelle = document.getElementById('assistantDock');
        if (!muelle) return;

        // Al cambiar de idioma hay que repintar la barra, pero sin tirar lo que
        // la persona estuviera escribiendo.
        if (montado) {
            if (!rehacer) return;
            const borrador = document.getElementById('assistantInput')?.value || '';
            muelle.innerHTML = plantilla();
            const campo = document.getElementById('assistantInput');
            if (campo) campo.value = borrador;
            APP.aplicarPermisos?.(muelle);
            publicarAlto(muelle);
            return;
        }

        muelle.innerHTML = plantilla();
        montado = true;

        publicarAlto(muelle);
        if (window.ResizeObserver) {
            // Coge todos los casos: abrir el panel, cerrarlo, cambiar el ancho
            // de la ventana, entrar y salir de la aplicación.
            new ResizeObserver(() => publicarAlto(muelle)).observe(muelle);
        } else {
            window.addEventListener('resize', () => publicarAlto(muelle), { passive: true });
        }

        const acciones = { resumen: verResumen, atencion: verAtencion, exportar: exportar };
        muelle.addEventListener('click', (ev) => {
            if (ev.target.closest('#assistantBurbuja')) return desplegar(muelle, true);
            if (ev.target.closest('#assistantChispa')) {
                // Abierta (teléfono): el mismo icono que la abrió la cierra.
                // Cerrada (escritorio, donde la barra está siempre a la vista):
                // el foco al campo, que es a lo que se viene.
                if (muelle.classList.contains('assistant-dock--abierto')) {
                    return desplegar(muelle, false);
                }
                return document.getElementById('assistantInput')?.focus();
            }
            if (ev.target.closest('[data-cerrar]')) return cerrar();

            const chip = ev.target.closest('.btn-chip');
            if (chip) return acciones[chip.dataset.accion]?.();

            if (ev.target.closest('#assistantEnviar')) return preguntar();

            // Los enlaces del panel navegan por el router, no recargando.
            const enlace = ev.target.closest('.assistant-enlace');
            if (enlace) {
                ev.preventDefault();
                cerrar();
                APP.navigate('rfq-detail', { id: enlace.dataset.rfq });
            }
        });

        document.getElementById('assistantInput')?.addEventListener('keydown', (ev) => {
            if (ev.key === 'Enter') { ev.preventDefault(); preguntar(); }
            if (ev.key === 'Escape') {
                // Con resultados a la vista, Escape los cierra. Sin ellos,
                // pliega la barra: es la salida que se espera de un teclado.
                const p = panel();
                if (p && !p.hidden) cerrar(); else desplegar(muelle, false);
            }
        });
    }

    /** Al cerrar sesión: fuera el panel y el texto a medias del anterior. */
    function limpiar() {
        cerrar();
        const campo = document.getElementById('assistantInput');
        if (campo) campo.value = '';
        // La próxima sesión empieza con la barra plegada, como la primera.
        document.getElementById('assistantDock')?.classList.remove('assistant-dock--abierto');
        // Fuera de la aplicación no hay barra: los avisos recuperan la esquina.
        document.documentElement.style.setProperty('--alto-asistente', '0px');
    }

    return { init, limpiar, cerrarPanel: cerrar };
})();
