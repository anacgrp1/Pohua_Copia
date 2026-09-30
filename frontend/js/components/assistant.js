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
 *     aunque no haya clave de IA configurada.
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
        errores:  '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
        estado:   '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
        registro: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
        recorrido:'<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>',
        espera:   '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><line x1="8" y1="9" x2="16" y2="9"/><line x1="8" y1="13" x2="13" y2="13"/></svg>',
        siguiente:'<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="13 17 18 12 13 7"/><polyline points="6 17 11 12 6 7"/></svg>',
        revisar:  '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>',
        hoja:     '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="2" width="16" height="20" rx="2"/><line x1="8" y1="6" x2="16" y2="6"/><line x1="8" y1="10" x2="10" y2="10"/><line x1="14" y1="10" x2="16" y2="10"/><line x1="8" y1="14" x2="10" y2="14"/><line x1="14" y1="14" x2="16" y2="14"/><line x1="8" y1="18" x2="16" y2="18"/></svg>',
        ciclo:    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>',
        dictaminados: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>',
        clientes: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
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
        dejarVivo();
    }

    /*
     * Listas que se mantienen al día solas: «Requiere atención» y «RFQ
     * dictaminados». Mientras una está abierta se vuelve a pedir cada 10 s
     * (con la pestaña a la vista) y al momento cuando se dictamina,
     * se cotiza o se escoge una versión de un RFQ —aquí o en otra pestaña,
     * ver `API.avisarRfq`—. Un RFQ dictaminado sale solo de «Requiere
     * atención» y entra en «RFQ dictaminados». Sólo se repinta si la lista
     * cambió, para no mover la tabla bajo el ratón.
     */
    const REPASO_MS = 10000;
    let vivo = null;           // 'atencion' | 'dictaminados' | null
    let repasoVivo = null;
    let ultimoHtml = '';

    function hacerVivo(clave, html) {
        vivo = clave;
        ultimoHtml = html;
        if (!repasoVivo) {
            repasoVivo = setInterval(() => { if (!document.hidden) repasar(); }, REPASO_MS);
        }
    }

    function dejarVivo() {
        vivo = null;
        ultimoHtml = '';
        if (repasoVivo) { clearInterval(repasoVivo); repasoVivo = null; }
    }

    function repasar() {
        if (vivo === 'atencion') verAtencion(true);
        else if (vivo === 'dictaminados') verDictaminados(true);
        else if (vivo === 'espera') verEspera(true);
    }

    /** Pinta la lista viva; en un repaso, sólo si cambió. */
    function mostrarVivo(clave, html, silencio) {
        if (silencio && (vivo !== clave || html === ultimoHtml)) return;
        mostrar(html);
        hacerVivo(clave, html);
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
                        ${lista(d.por_estado.map(e => [I18N.estado(e.estado), e.total]), I18N.t('asis.sinRfqs'))}
                    </ul></div>
                    <div><h4>${esc(I18N.t('asis.materiales'))}</h4><ul class="assistant-lista">
                        ${lista(d.materiales.map(m => [m.material, m.total]), I18N.t('asis.sinMaterial'))}
                    </ul></div>
                 </div>`);
        } catch (err) { fallo(err, I18N.t('asis.errResumen')); }
    }

    async function verAtencion(silencio) {
        if (silencio !== true) { dejarVivo(); ocupado(I18N.t('asis.tituloAtencion')); }
        try {
            const d = await API.assistantAttention();
            if (silencio === true && vivo !== 'atencion') return;
            if (!d.pendientes.length) {
                mostrarVivo('atencion', cabecera(I18N.t('asis.tituloAtencion'), I18N.t('asis.deLaBase2')) +
                    `<p class="assistant-vacio">${esc(I18N.t('asis.nadaPendiente'))}</p>`, silencio === true);
                return;
            }
            const filas = d.pendientes.map(p => `
                <tr>
                    <td><a href="/rfq-detail?id=${encodeURIComponent(p.rfq_id)}"
                           class="assistant-enlace" data-rfq="${esc(p.rfq_id)}">${esc(p.rfq_id)}</a></td>
                    <td>${esc(p.cliente_nombre || p.cliente_id || '—')}</td>
                    <td>${esc(p.part_number || '—')}</td>
                    <td><span class="badge">${esc(I18N.estado(p.estado))}</span></td>
                    <td>${esc(p.dias_esperando)} d</td>
                    <td class="${p.criticas > 0 && p.motivo !== 'oferta' ? 'assistant-critico' : ''}">${esc(I18N.motivoPendiente(p))}</td>
                </tr>`).join('');

            mostrarVivo('atencion',
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
                 </div>`, silencio === true);
        } catch (err) { if (silencio !== true) fallo(err, I18N.t('asis.errLista')); }
    }

    /*
     * «Esperando al cliente»: los RFQ a los que les faltan datos y a cuyo
     * comprador se le escribió pidiéndolos. No esperan a nadie de aquí —por
     * eso no salen en «Requiere atención»—, pero conviene verlos: cuánto
     * llevan esperando y qué se pidió, por si hay que llamar al cliente.
     */
    async function verEspera(silencio) {
        const titulo = I18N.t('asis.tituloEspera');
        if (silencio !== true) { dejarVivo(); ocupado(titulo); }
        try {
            const d = await API.rfqsEsperando(50);
            if (silencio === true && vivo !== 'espera') return;
            const lista = (d && d.rfqs) || [];
            if (!lista.length) {
                mostrarVivo('espera', cabecera(titulo, I18N.t('asis.deLaBase2')) +
                    `<p class="assistant-vacio">${esc(I18N.t('asis.nadaEspera'))}</p>`, silencio === true);
                return;
            }
            const campo = (c) => { const k = 'campo.' + c; const t = I18N.t(k); return t === k ? c : t; };
            const dias = (f) => {
                const t = Date.parse(f || '');
                return Number.isFinite(t) ? Math.max(0, Math.floor((Date.now() - t) / 86400000)) : '—';
            };
            const filas = lista.map((r) => `
                <tr>
                    <td><a href="/rfq-detail?id=${encodeURIComponent(r.rfq_id)}"
                           class="assistant-enlace" data-rfq="${esc(r.rfq_id)}">${esc(r.rfq_id)}</a></td>
                    <td>${esc(r.cliente_nombre || r.cliente_id || '—')}</td>
                    <td>${esc((r.campos_faltantes || []).map(campo).join(', ') || '—')}</td>
                    <td>${esc(dias(r.fecha_registro))} d</td>
                </tr>`).join('');
            mostrarVivo('espera',
                cabecera(titulo, I18N.t('asis.esperaNota', { n: lista.length })) +
                `<div class="assistant-tabla-caja">
                    <table class="assistant-tabla">
                        <thead><tr><th>${esc(I18N.t('asis.col.rfq'))}</th>
                                   <th>${esc(I18N.t('asis.col.cliente'))}</th>
                                   <th>${esc(I18N.t('asis.col.falta'))}</th>
                                   <th>${esc(I18N.t('asis.col.espera'))}</th></tr></thead>
                        <tbody>${filas}</tbody>
                    </table>
                 </div>`, silencio === true);
        } catch (err) { if (silencio !== true) fallo(err, I18N.t('asis.errLista')); }
    }

    /** El RFQ que se está mirando en la ficha, si se está en una. */
    function rfqDeLaFicha() {
        if (seccion() !== 'rfq-detail' || typeof RFQDetailPage === 'undefined') return null;
        return RFQDetailPage.rfqActual && RFQDetailPage.rfqActual.rfq_id === RFQDetailPage.currentRfqId
            ? RFQDetailPage.rfqActual : null;
    }

    /*
     * «Siguiente pendiente»: la ficha del RFQ que más lleva esperando
     * dictamen (el primero de «Requiere atención»), saltando el que ya se
     * está mirando. Es el «¿y ahora qué?» de quien dictamina: sin él, había
     * que volver a la lista, buscar y abrir.
     */
    async function irAlSiguiente() {
        try {
            const d = await API.assistantAttention();
            const actual = rfqDeLaFicha();
            const siguiente = (d.pendientes || []).find((p) => !actual || p.rfq_id !== actual.rfq_id);
            if (!siguiente) { Toast.info(I18N.t('asis.nadaPendiente')); return; }
            cerrar();
            APP.navigate('rfq-detail', { id: siguiente.rfq_id });
        } catch (err) { if (!(err && err.sesionExpirada)) Toast.error(err.message); }
    }

    /** «Revisar» desde la barra, en la ficha: la ventana de revisión. */
    function revisarEste() {
        const rfq = rfqDeLaFicha();
        if (!rfq) return;
        if (rfq.estado === 'Incomplete') { Toast.info(I18N.t('ficha.esperaTitulo')); return; }
        cerrar();
        Revision.abrir(rfq.rfq_id);
    }

    /** «Abrir en la hoja»: la calculadora con este RFQ (en consulta si ya se dictaminó). */
    function hojaDeEste() {
        const rfq = rfqDeLaFicha();
        if (!rfq) return;
        cerrar();
        const cerrado = rfq.estado === 'Approved' || rfq.estado === 'Declined';
        APP.navigate('quoting', cerrado ? { rfq: rfq.rfq_id, consulta: '1' } : { rfq: rfq.rfq_id });
    }

    /*
     * Los RFQ que ya tienen dictamen —aprobados o rechazados—, los más nuevos
     * arriba. El número lleva a la ficha del RFQ, como en toda la aplicación;
     * «Ver en la hoja» abre la cotización en consulta, sin tocar el borrador
     * de nadie (lo mismo que la tabla de la pantalla Resumen).
     */
    async function verDictaminados(silencio) {
        const titulo = I18N.t('asis.tituloDictaminados');
        if (silencio !== true) { dejarVivo(); ocupado(titulo); }
        try {
            const d = await API.rfqsDecididos(50);
            if (silencio === true && vivo !== 'dictaminados') return;
            const lista = (d && d.rfqs) || [];
            if (!lista.length) {
                mostrarVivo('dictaminados', cabecera(titulo, I18N.t('asis.deLaBase2')) +
                    `<p class="assistant-vacio">${esc(I18N.t('resumen.sinDecididas'))}</p>`, silencio === true);
                return;
            }
            const aprobados = lista.filter((r) => r.estado === 'Approved').length;
            const filas = lista.map((r) => {
                const aprobado = r.estado === 'Approved';
                return `
                <tr>
                    <td><a href="/rfq-detail?id=${encodeURIComponent(r.rfq_id)}"
                           class="assistant-enlace" data-rfq="${esc(r.rfq_id)}">${esc(r.rfq_id)}</a></td>
                    <td>${esc(r.cliente_nombre || r.cliente_id || '—')}</td>
                    <td>${esc(r.part_number || '—')}</td>
                    <td>${esc((r.fecha_registro || '').slice(0, 10) || '—')}</td>
                    <td><span class="badge ${aprobado ? 'badge-approved' : 'badge-declined'}"><span class="badge-dot"></span>${esc(I18N.estado(r.estado))}</span></td>
                    <td class="assistant-acciones-fila">${r.oferta === 'pendiente'
                        ? `<button type="button" class="btn btn-primary btn-sm" data-enviar-oferta="${esc(r.rfq_id)}">${esc(I18N.t('oferta.enviarAhora'))}</button> ` : ''}<button type="button" class="btn btn-secondary btn-sm" data-hoja="${esc(r.rfq_id)}">${esc(I18N.t('resumen.verHoja'))}</button></td>
                </tr>`;
            }).join('');
            mostrarVivo('dictaminados',
                cabecera(titulo, I18N.t('asis.dictaminadosNota',
                                        { a: aprobados, d: lista.length - aprobados })) +
                `<div class="assistant-tabla-caja">
                    <table class="assistant-tabla">
                        <thead><tr><th>${esc(I18N.t('asis.col.rfq'))}</th>
                                   <th>${esc(I18N.t('asis.col.cliente'))}</th>
                                   <th>${esc(I18N.t('asis.col.pieza'))}</th>
                                   <th>${esc(I18N.t('asis.col.fecha'))}</th>
                                   <th>${esc(I18N.t('asis.col.resultado'))}</th>
                                   <th></th></tr></thead>
                        <tbody>${filas}</tbody>
                    </table>
                 </div>`, silencio === true);
        } catch (err) { if (silencio !== true) fallo(err, I18N.t('asis.errLista')); }
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

    // --------------------------------------------------- acciones de Monitor

    /** Sólo lo que falló: ERROR y WARNING de las últimas líneas del registro. */
    async function verErrores() {
        ocupado(I18N.t('asis.tituloErrores'));
        try {
            const d = await API.getLogs(400);
            const malas = (d.lineas || []).filter(
                l => l.nivel === 'ERROR' || l.nivel === 'CRITICAL' || l.nivel === 'WARNING');
            if (!malas.length) {
                mostrar(cabecera(I18N.t('asis.tituloErrores'),
                                 I18N.t('asis.deLineas', { n: d.total || 0 }))
                    + `<p class="assistant-vacio">${esc(I18N.t('asis.sinErrores'))}</p>`);
                return;
            }
            // De abajo arriba: lo último que falló es lo que se viene a ver.
            const filas = malas.reverse().map(l => `
                <li class="assistant-log assistant-log--${esc((l.nivel || '').toLowerCase())}">
                    <span class="assistant-log-marca">${esc(l.marca || '')}</span>
                    <span class="assistant-log-nivel">${esc(l.nivel)}</span>
                    <span class="assistant-log-origen">${esc(l.origen || '')}</span>
                    <span class="assistant-log-mensaje">${esc(l.mensaje)}</span>
                </li>`).join('');
            mostrar(cabecera(I18N.t('asis.tituloErrores'),
                             I18N.t('asis.deLineas', { n: d.total || 0 }))
                + `<ul class="assistant-logs">${filas}</ul>`);
        } catch (err) { fallo(err, I18N.t('asis.tituloErrores')); }
    }

    /** El servicio de un vistazo: si corre, qué lee y cuándo vuelve. */
    async function verEstado() {
        ocupado(I18N.t('asis.tituloEstado'));
        try {
            const e = await API.getStatus();
            const h = e.horario;
            const r = (typeof Horario !== 'undefined' && h) ? Horario.resumen(h)
                                                            : { enEspera: false, detalle: '' };
            const reloj = (iso) => {
                if (!iso) return '—';
                const d = new Date(iso);
                return isNaN(d) ? String(iso)
                    : d.toLocaleString(I18N.locale || undefined,
                                       { hour: '2-digit', minute: '2-digit',
                                         day: 'numeric', month: 'short' });
            };
            const marcha = !e.running ? I18N.t('asis.est.parado')
                         : (r.enEspera ? I18N.t('asis.est.espera') : I18N.t('asis.est.enMarcha'));
            const filas = [
                [I18N.t('asis.est.servicio'), marcha],
                [I18N.t('asis.est.buzon'), `${(e.mode || '').toUpperCase()}${e.folder ? ' · ' + e.folder : ''}`],
                [I18N.t('asis.est.intervalo'), I18N.t('asis.est.minutos', { n: e.interval_seconds })],
                [I18N.t('asis.est.ultimo'), reloj(e.last_cycle)],
                [I18N.t('asis.est.siguiente'), reloj(e.next_cycle)],
                [I18N.t('asis.est.procesados'), e.total_processed],
                [I18N.t('asis.est.rfqs'), e.total_rfqs],
                [I18N.t('asis.est.errores'), e.total_errors],
            ];
            mostrar(cabecera(I18N.t('asis.tituloEstado'), r.detalle || '')
                + `<ul class="assistant-lista">${filas.map(
                    ([k, v]) => `<li><span>${esc(k)}</span><b>${esc(v)}</b></li>`).join('')}</ul>`);
        } catch (err) { fallo(err, I18N.t('asis.tituloEstado')); }
    }

    /**
     * El registro como fichero de texto, sin pasar por el servidor.
     *
     * Ya está descargado para pintarlo: volver a pedirlo en otro formato sería
     * una ruta nueva en la API para algo que el navegador sabe hacer solo.
     */
    async function descargarRegistro() {
        try {
            const d = await API.getLogs(1000);
            const texto = (d.lineas || []).map(
                l => `${l.marca || ''}  ${(l.nivel || '').padEnd(8)}  ${l.origen || ''}  ${l.mensaje}`
            ).join('\n');
            const fecha = new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-');
            const url = URL.createObjectURL(new Blob([texto], { type: 'text/plain;charset=utf-8' }));
            const a = document.createElement('a');
            a.href = url;
            a.download = `pohua-registro-${fecha}.txt`;
            a.click();
            // Sin esto el blob se queda en memoria hasta recargar la página.
            setTimeout(() => URL.revokeObjectURL(url), 1000);
            Toast.success(I18N.t('asis.registroHecho'));
        } catch (err) {
            if (err && err.sesionExpirada) return;
            Toast.error(err.message);
        }
    }

    // ------------------------------------------------------ acciones de Mail

    /** El recorrido de un correo: cuántos hay parados en cada escalón. */
    async function verRecorrido() {
        ocupado(I18N.t('asis.tituloRecorrido'));
        try {
            const d = await API.assistantPipeline();
            const etapas = d.etapas || [];
            if (!etapas.length) {
                mostrar(cabecera(I18N.t('asis.tituloRecorrido'))
                    + `<p class="assistant-vacio">${esc(I18N.t('asis.sinDatos'))}</p>`);
                return;
            }
            // Las etapas en el idioma puesto, como en el Monitor (dashboard.js):
            // el texto del servidor sólo si no hay traducción.
            const traducir = (clave, vars, respaldo) => {
                const texto = I18N.t(clave, vars);
                return texto === clave ? (respaldo || '') : texto;
            };
            const filas = etapas.map(e => {
                const etiqueta = traducir('etapa.' + e.clave, null, e.etiqueta);
                const n = (/\d+/.exec(e.detalle || '') || [''])[0];
                const detalle = traducir('etapa.' + e.clave + '.det', { n }, e.detalle);
                return { ...e, etiqueta, detalle };
            }).map(e => `
                <li class="${e.espera ? 'assistant-etapa--espera' : ''}">
                    <span>${esc(e.etiqueta)}${e.detalle ? ` <small>${esc(e.detalle)}</small>` : ''}</span>
                    <b>${esc(e.total)}</b>
                </li>`).join('');
            mostrar(cabecera(I18N.t('asis.tituloRecorrido'), I18N.t('asis.recorridoNota'))
                + `<ul class="assistant-lista">${filas}</ul>`);
        } catch (err) { fallo(err, I18N.t('asis.tituloRecorrido')); }
    }

    // -------------------------------------------------- acciones de Overview

    /** Quién pidió más esta semana, y quién todavía no está en el catálogo. */
    async function verClientes() {
        ocupado(I18N.t('asis.tituloClientes'));
        try {
            const d = await API.assistantTopClientes(7);
            const lista = d.clientes || [];
            if (!lista.length) {
                mostrar(cabecera(I18N.t('asis.tituloClientes'))
                    + `<p class="assistant-vacio">${esc(I18N.t('asis.sinSemana'))}</p>`);
                return;
            }
            const filas = lista.map(c => `
                <li>
                    <span>${esc(c.cliente)}
                        ${c.estrella ? `<small class="assistant-marca">★ ${esc(I18N.t('asis.estrella'))}</small>` : ''}
                        ${c.es_nuevo ? `<small class="assistant-marca assistant-marca--nuevo">${esc(I18N.t('asis.nuevo'))}</small>` : ''}
                    </span>
                    <b>${esc(c.total)}</b>
                </li>`).join('');
            mostrar(cabecera(I18N.t('asis.tituloClientes'),
                             I18N.t('asis.semanaNota', { n: d.total_rfqs, nuevos: d.nuevos }))
                + `<ul class="assistant-lista">${filas}</ul>`);
        } catch (err) { fallo(err, I18N.t('asis.tituloClientes')); }
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

    // ------------------------------------------------- los botones de cada sección

    /**
     * Qué botón sale en cada apartado.
     *
     * Antes salían los tres mismos en toda la aplicación, y en Monitor eso
     * quería decir un "Exportar a Excel" que no tenía nada que ver con lo que
     * hay en pantalla: quien está mirando el registro del servicio quiere ver
     * qué falló, no bajarse una hoja de RFQs. Un acceso rápido que no sirve
     * donde está ocupa sitio y enseña a no mirar la fila.
     *
     * Así que la fila la decide la sección. La clave es la misma que el router
     * pone en `body[data-pagina]`.
     *
     *   Monitor   el registro del servicio  → qué falló, cómo está, llévatelo
     *   Mail      el correo entrando        → por dónde va cada correo, qué está parado
     *   Quoting   la calculadora            → sólo lo que espera dictamen; lo demás
     *                                         robaría sitio a la propia calculadora
     *   Overview  el panel                  → las cifras, quién pidió, qué espera, y la hoja
     *
     * Las pantallas que no están en la tabla (la ficha de un RFQ, la oferta,
     * el perfil) se quedan con `POR_DEFECTO`, que es lo de siempre.
     */
    const ACCIONES = {
        resumen:  verResumen,
        atencion: () => verAtencion(),
        dictaminados: () => verDictaminados(),
        espera:   () => verEspera(),
        siguiente: irAlSiguiente,
        revisar:  revisarEste,
        hoja:     hojaDeEste,
        ciclo:    () => APP.correrCiclo(),
        exportar: exportar,
        errores:  verErrores,
        estado:   verEstado,
        registro: descargarRegistro,
        recorrido: verRecorrido,
        clientes: verClientes,
    };

    // [icono, clave del texto, ¿es el de aviso?, permiso (rfq:leer si no se dice)]
    const CHIPS = {
        siguiente: ['siguiente', 'asis.siguiente', false],
        revisar:   ['revisar',   'asis.revisar',   false, 'rfq:leer'],
        hoja:      ['hoja',      'asis.hoja',      false, 'precio:calcular'],
        espera:    ['espera',    'asis.espera',    false],
        ciclo:     ['ciclo',     'asis.ciclo',     false, 'worker:operar'],
        errores:   ['errores',   'asis.errores',   true],
        estado:    ['estado',    'asis.estado',    false],
        registro:  ['registro',  'asis.registro',  false],
        recorrido: ['recorrido', 'asis.recorrido', false],
        atencion:  ['atencion',  'asis.atencion',  true],
        dictaminados: ['dictaminados', 'asis.dictaminados', false],
        resumen:   ['resumen',   'asis.resumen',   false],
        clientes:  ['clientes',  'asis.topClientes', false],
        exportar:  ['exportar',  'asis.exportar',  false],
    };

    /*
     * El orden es el de importancia, de izquierda a derecha (ISC, 2026-09-27):
     * primero lo que pide actuar —lo que espera dictamen y el siguiente que
     * atender—, luego lo que se consulta a diario y al final lo ocasional
     * (el reparto de clientes, exportar, descargar el registro). En el
     * teléfono la fila se desliza, así que lo primero es lo que se ve sin
     * deslizar. Es fijo a propósito: un orden que cambiara según el uso
     * movería los botones de sitio y habría que buscarlos cada vez.
     */
    const POR_SECCION = {
        'monitor':    ['errores', 'ciclo', 'estado', 'atencion', 'registro'],
        'mail':       ['atencion', 'siguiente', 'espera', 'recorrido'],
        'quoting':    ['atencion', 'siguiente', 'espera', 'dictaminados'],
        'resumen':    ['atencion', 'espera', 'dictaminados', 'resumen', 'clientes', 'exportar'],
        // En la ficha de un RFQ, lo que se hace con ESE RFQ y después el siguiente.
        'rfq-detail': ['revisar', 'siguiente', 'hoja', 'atencion'],
    };
    const POR_DEFECTO = ['atencion', 'siguiente', 'resumen', 'exportar'];

    function seccion() {
        return document.body.dataset.pagina || '';
    }

    function chips() {
        const cuales = POR_SECCION[seccion()] || POR_DEFECTO;
        return cuales.map((clave) => {
            const [icono, texto, aviso, permiso] = CHIPS[clave];
            return `<button type="button" class="btn btn-chip${aviso ? ' btn-chip--aviso' : ''}"
                            data-accion="${clave}" data-permiso="${permiso || 'rfq:leer'}">${
                        ICONOS[icono]}<span>${esc(I18N.t(texto))}</span></button>`;
        }).join('');
    }

    /**
     * Repinta la fila al cambiar de sección. La llama el router.
     *
     * Se toca sólo la fila de botones, no la barra entera: el campo de texto
     * puede tener media pregunta escrita y navegar no debería borrarla. Y se
     * cierra el panel de resultados, que era de la pantalla anterior.
     */
    function alCambiarSeccion() {
        const fila = document.getElementById('assistantAcciones');
        if (!fila) return;
        fila.innerHTML = chips();
        APP.aplicarPermisos?.(fila);
        cerrar();
        publicarAlto(document.getElementById('assistantDock'));
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

            <div class="assistant-acciones" id="assistantAcciones">${chips()}</div>`;
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

        // Las listas vivas se enteran al momento de lo que cambia en un RFQ.
        ['dictaminado', 'cotizado', 'version'].forEach((tipo) => {
            window.addEventListener('pohua:rfq-' + tipo, () => { if (vivo) setTimeout(repasar, 300); });
        });

        publicarAlto(muelle);
        if (window.ResizeObserver) {
            // Coge todos los casos: abrir el panel, cerrarlo, cambiar el ancho
            // de la ventana, entrar y salir de la aplicación.
            new ResizeObserver(() => publicarAlto(muelle)).observe(muelle);
        } else {
            window.addEventListener('resize', () => publicarAlto(muelle), { passive: true });
        }

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
            if (chip) return ACCIONES[chip.dataset.accion]?.();

            if (ev.target.closest('#assistantEnviar')) return preguntar();

            // «Enviar oferta» de un aprobado que no la tiene: al envío directo.
            const envio = ev.target.closest('[data-enviar-oferta]');
            if (envio) {
                ev.preventDefault();
                cerrar();
                APP.navigate('quote-review', { id: envio.dataset.enviarOferta, enviar: '1' });
                return;
            }

            // «Ver en la hoja» de un dictaminado: la hoja en consulta.
            const hoja = ev.target.closest('[data-hoja]');
            if (hoja) {
                ev.preventDefault();
                cerrar();
                APP.navigate('quoting', { rfq: hoja.dataset.hoja, consulta: '1' });
                return;
            }

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

    return { init, limpiar, cerrarPanel: cerrar, alCambiarSeccion };
})();
