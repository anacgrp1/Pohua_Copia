/**
 * La ventana de revisión del Plant Manager.
 *
 * Una sola vista con todo lo que hace falta para dictaminar un RFQ sin abrir
 * la cotización completa: qué pide el cliente, lo que el sistema extrajo del
 * correo y del plano, los avisos de factibilidad, y los TRAMOS ya costeados
 * —precio por pieza, margen, cascada de costes, material, ruta y totales—,
 * uno por cada cantidad que venía en el correo.
 *
 * Dos caras, un mismo DOM:
 *
 *   - Compu (> 768 px): una caja compacta en el centro, con pestañas por
 *     tramo, cinco fichas de cascada y tres columnas.
 *   - Teléfono (≤ 768 px): pantalla completa, una sola columna, los tramos
 *     como tarjetas, la cascada como lista y los botones de 44 px al pie.
 *
 * Quién la abre:
 *
 *   - La campana de avisos y las filas de la cola del Resumen dejan
 *     `#/rfq/<id>` en la dirección; aquí se escucha `hashchange` y se abre.
 *     Así un enlace pegado en un chat también llega a la ventana.
 *   - El botón "Review" del detalle del RFQ llama a `Revision.abrir(id)`.
 *
 * Qué hace cada botón:
 *
 *   - Approve      → POST /approve    (el flujo de aprobación sigue después)
 *   - Send back    → POST /send-back  (con nota obligatoria; no sale correo)
 *   - Decline      → POST /decline    (con motivo; avisa al cliente)
 *   - Open full quote → la pantalla de cotización completa.
 *
 * Los números NO se calculan aquí: vienen costeados del servidor, con el
 * catálogo de Neon. Si al catálogo le faltó algo (precio del alambre, tarifa
 * de máquina), `costeo.completo` viene en falso y la ventana lo dice en la
 * franja ámbar en vez de enseñar una cifra como si fuera fiable.
 */
const Revision = (() => {
    'use strict';

    let capa = null;        // el velo con la ventana dentro, o null
    let datos = null;       // lo que devolvió /revision
    let tramoActivo = 0;    // índice del tramo elegido
    let ocupado = false;    // una acción en curso: los botones se bloquean
    let rfqAbierto = null;  // para no reabrir la misma dos veces

    // ------------------------------------------------------------ utilidades

    function esc(v) {
        return String(v == null ? '' : v)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function t(clave, sustituciones) {
        let texto = I18N.t(clave);
        if (sustituciones) {
            for (const [k, v] of Object.entries(sustituciones)) {
                texto = texto.replace(new RegExp('\\{' + k + '\\}', 'g'), v);
            }
        }
        return texto;
    }

    function esNum(v) { return typeof v === 'number' && isFinite(v); }

    /** $ con tantos decimales como pida la cifra: $0.8658/pc, $12.50, $1,234. */
    function dinero(v, dec) {
        if (!esNum(v)) return '—';
        if (dec == null) dec = Math.abs(v) < 10 ? 4 : (Math.abs(v) < 1000 ? 2 : 0);
        return '$' + v.toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec });
    }

    function pct(v, dec) {
        if (!esNum(v)) return '—';
        return v.toFixed(dec == null ? 1 : dec) + '%';
    }

    function num(v, dec) {
        if (!esNum(v)) return '—';
        return v.toLocaleString(undefined, { minimumFractionDigits: dec || 0, maximumFractionDigits: dec == null ? 3 : dec });
    }

    function entero(v) {
        return esNum(v) ? Math.round(v).toLocaleString() : '—';
    }

    function claseEstado(estado) {
        if (typeof RFQTable !== 'undefined' && RFQTable.badgeClass) return RFQTable.badgeClass(estado);
        return { New: 'badge-new', RequiresReview: 'badge-review', Incomplete: 'badge-review',
                 Approved: 'badge-approved', Declined: 'badge-declined' }[estado] || '';
    }

    function tipoResorte(codigo) {
        const clave = 'rev.tipo.' + (codigo || '');
        const texto = I18N.t(clave);
        return texto === clave ? (codigo || '') : texto;
    }

    // ------------------------------------------------------------- avisos

    /** Todo lo que el PM tiene que saber antes de fiarse del número. */
    function avisos(d) {
        const lista = [];
        const f = d.factibilidad || {};
        const c = d.costeo || {};
        const tramo = (d.tramos || [])[tramoActivo];

        if (d.error_costeo) lista.push({ nivel: 'error', texto: t('rev.aviso.errorCosteo') + ' ' + d.error_costeo });
        if (!c.completo) {
            for (const m of (c.faltantes || [])) lista.push({ nivel: 'warn', texto: m });
            if (!(c.faltantes || []).length && (d.tramos || []).length) {
                lista.push({ nivel: 'warn', texto: t('rev.aviso.incompleto') });
            }
        }
        for (const m of (c.banderas_motor || [])) if (m) lista.push({ nivel: 'warn', texto: m });
        if (tramo && tramo.avisos) {
            if (tramo.avisos.bajo_piso) lista.push({ nivel: 'warn', texto: t('rev.aviso.bajoPiso') });
            if (tramo.avisos.bajo_contribucion) lista.push({ nivel: 'warn', texto: t('rev.aviso.bajoContribucion') });
            if (tramo.avisos.scrap) lista.push({ nivel: 'warn', texto: t('rev.aviso.scrap') });
        }
        if (tramo && tramo.material && tramo.material.moq_manda) {
            lista.push({ nivel: 'info', texto: t('rev.aviso.moq') });
        }
        for (const m of (f.motivos || [])) {
            const texto = typeof m === 'string' ? m : (m && (m.texto || m.motivo || m.mensaje)) || JSON.stringify(m);
            lista.push({ nivel: 'info', texto });
        }
        for (const campo of (d.campos_faltantes || [])) {
            lista.push({ nivel: 'warn', texto: t('rev.aviso.campoFalta', { campo }) });
        }
        return lista;
    }

    // ------------------------------------------------------------- plantilla

    function cabecera(d) {
        const r = d.rfq || {};
        const partes = [r.part_number, tipoResorte(r.tipo_resorte), r.rfq_id, r.customer]
            .filter(Boolean).map(esc);
        return `
            <div class="revision-cab">
                <div class="revision-titulo" title="${esc(r.asunto || '')}">
                    ${partes.join('<span class="revision-sep">·</span>')}
                </div>
                <span class="badge ${claseEstado(r.estado)}">
                    <span class="badge-dot"></span>${esc(r.estado || '')}
                </span>
                <button type="button" class="revision-cerrar" data-accion="cerrar" aria-label="${esc(t('rev.cerrar'))}">&times;</button>
            </div>`;
    }

    function comunes(d) {
        const c = d.comunes || {};
        const chip = (etq, valor) => `
            <div class="revision-chip">
                <span class="revision-chip-etq">${esc(etq)}</span>
                <span class="revision-chip-val">${valor}</span>
            </div>`;
        const material = c.material ? esc(c.material) + (c.material_nombre ? ` <small>${esc(c.material_nombre)}</small>` : '') : '—';
        return `
            <section class="revision-comunes" aria-label="${esc(t('rev.todosTramos'))}">
                <div class="revision-rotulo">${esc(t('rev.todosTramos'))}</div>
                <div class="revision-chips">
                    ${chip(t('rev.material'), material)}
                    ${chip('Ø', esNum(c.dia_in) ? num(c.dia_in, 3) + ' in' : '—')}
                    ${chip(t('rev.peso'), esNum(c.peso_lb_pc) ? num(c.peso_lb_pc, 3) + ' lb/pc' : '—')}
                    ${chip(t('rev.base'), esNum(c.base_lb) ? dinero(c.base_lb, 2) + '/lb' : '—')}
                    ${chip(t('rev.surcharge'), esNum(c.surcharge_lb) && esNum(c.base_lb) ? dinero(c.surcharge_lb, 2) + '/lb' : '—')}
                </div>
            </section>`;
    }

    function pestanas(d) {
        const tramos = d.tramos || [];
        if (!tramos.length) {
            const cantidades = (d.cantidades || []).map(entero).join(' · ');
            return `<div class="revision-sin-tramos">${esc(t('rev.sinTramos'))}${cantidades ? ` <b>${cantidades}</b>` : ''}</div>`;
        }
        return `
            <div class="revision-tramos" role="tablist" aria-label="${esc(t('rev.tramos'))}">
                ${tramos.map((tr, i) => `
                    <button type="button" role="tab" class="revision-tramo ${i === tramoActivo ? 'activo' : ''} ${tr.llega ? 'llega' : 'corto'}"
                            data-tramo="${i}" aria-selected="${i === tramoActivo}">
                        <span class="revision-tramo-qty">${entero(tr.cantidad)} <small>pcs</small></span>
                        <span class="revision-tramo-precio">${dinero(tr.precio_pc)}<small>/pc</small></span>
                        <span class="revision-tramo-margen">${pct(tr.resultado_pct)} <small>${esc(t('rev.margen'))}</small></span>
                    </button>`).join('')}
            </div>`;
    }

    function franja(lista) {
        if (!lista.length) return '';
        const nivel = lista.some(a => a.nivel === 'error') ? 'error'
                    : lista.some(a => a.nivel === 'warn') ? 'warn' : 'info';
        return `
            <div class="revision-franja revision-franja--${nivel}" role="status">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
                </svg>
                <ul>${lista.map(a => `<li class="revision-aviso--${a.nivel}">${esc(a.texto)}</li>`).join('')}</ul>
            </div>`;
    }

    function cascada(tr) {
        const c = (tr && tr.cascada) || {};
        const ficha = (clase, etq, valor, sub) => `
            <div class="revision-ficha ${clase}">
                <span class="revision-ficha-etq">${esc(etq)}</span>
                <span class="revision-ficha-val">${valor}</span>
                <span class="revision-ficha-sub">${sub || ''}</span>
            </div>`;
        const llega = tr && tr.llega;
        return `
            <div class="revision-cascada">
                ${ficha('', t('rev.sell'), dinero(c.sell), '/pc')}
                ${ficha('', 'AV', dinero(c.av), pct(c.av_pct))}
                ${ficha('', 'C/CV', dinero(c.ccv), pct(c.ccv_pct))}
                ${ficha('', 'C/CD', dinero(c.ccd), pct(c.ccd_pct))}
                ${ficha(llega ? 'revision-ficha--ok' : 'revision-ficha--corto',
                        t('rev.resultado') + ' · ' + t('rev.objetivo') + ' ' + pct(tr && tr.objetivo_pct, 0),
                        pct(c.resultado_pct), dinero(c.resultado) + '/pc')}
            </div>`;
    }

    function columnas(tr) {
        const m = (tr && tr.material) || {};
        const ruta = (tr && tr.ruta) || [];
        const tot = (tr && tr.totales) || {};
        const fila = (etq, valor) => `<div class="revision-fila"><span>${esc(etq)}</span><b>${valor}</b></div>`;
        return `
            <div class="revision-columnas">
                <section class="revision-bloque">
                    <h4>${esc(t('rev.materialTramo'))}</h4>
                    ${fila(t('rev.materialPc'), esNum(m.pc) ? `${dinero(m.pc)} <small>· ${pct(m.pct)}</small>` : '—')}
                    ${fila(t('rev.alambre'), esNum(m.lb_comprar) ? num(m.lb_comprar, 1) + ' lb' : '—')}
                    ${m.moq_manda ? `<div class="revision-nota">${esc(t('rev.aviso.moq'))}</div>` : ''}
                </section>
                <section class="revision-bloque">
                    <h4>${esc(t('rev.ruta'))}</h4>
                    ${ruta.length ? ruta.map(op => fila(op.maquina || '—',
                        `${esNum(op.pph) ? num(op.pph, 0) + ' pc/h' : '—'} <small>· ${esNum(op.setup_h) ? num(op.setup_h, 2) + ' h ' + esc(t('rev.setup')) : '—'}</small>`)).join('')
                        : `<div class="revision-nota">${esc(t('rev.sinRuta'))}</div>`}
                </section>
                <section class="revision-bloque">
                    <h4>${esc(t('rev.totalesTramo'))}</h4>
                    ${fila(t('rev.ingreso'), dinero(tot.ingreso, 2))}
                    ${fila(t('rev.horas'), esNum(tot.horas) ? num(tot.horas, 1) + ' h' : '—')}
                    ${fila('C/CV ' + t('rev.porHora'), esNum(tot.ccv_hora) ? dinero(tot.ccv_hora, 2) + '/h' : '—')}
                </section>
            </div>`;
    }

    function pie(d) {
        const r = d.rfq || {};
        const puede = d.puede_dictaminar && API.puede('rfq:dictaminar');
        const abierto = r.estado === 'RequiresReview' || r.estado === 'New' || r.estado === 'Incomplete';
        const botones = [];
        if (puede && abierto) {
            botones.push(`<button type="button" class="btn btn-secondary revision-btn" data-accion="devolver">${esc(t('rev.devolver'))}</button>`);
            botones.push(`<button type="button" class="btn btn-success revision-btn" data-accion="aprobar">${esc(t('rev.aprobar'))}</button>`);
        }
        if (puede && r.estado !== 'Declined') {
            botones.push(`<button type="button" class="btn btn-danger revision-btn revision-btn--suave" data-accion="declinar">${esc(t('rev.declinar'))}</button>`);
        }
        botones.push(`<button type="button" class="btn btn-primary revision-btn" data-accion="cotizar">${esc(t(r.estado === 'Approved' ? 'rev.abrirOferta' : 'rev.abrirCompleta'))}</button>`);
        return `
            <div class="revision-pie">
                <div class="revision-pie-nota">${esc(puede && abierto ? t('rev.pieNota') : (puede ? t('rev.pieCerrado') : t('rev.pieSoloLectura')))}</div>
                <div class="revision-acciones">${botones.join('')}</div>
            </div>`;
    }

    function plantilla(d) {
        const tr = (d.tramos || [])[tramoActivo];
        const r = d.rfq || {};
        return `
            <div class="revision" role="dialog" aria-modal="true" aria-labelledby="revisionTitulo">
                ${cabecera(d)}
                <div class="revision-cuerpo">
                    ${comunes(d)}
                    ${pestanas(d)}
                    ${franja(avisos(d))}
                    ${tr ? cascada(tr) + columnas(tr) : ''}
                    ${r.notas ? `<section class="revision-bloque revision-notas"><h4>${esc(t('rev.notas'))}</h4><pre>${esc(r.notas)}</pre></section>` : ''}
                </div>
                ${pie(d)}
            </div>`;
    }

    // ------------------------------------------------------------- acciones

    function bloquear(si) {
        ocupado = si;
        if (!capa) return;
        capa.querySelectorAll('.revision-btn').forEach(b => { b.disabled = si; });
        capa.classList.toggle('ocupado', si);
    }

    async function aprobar() {
        if (!API.puede('rfq:dictaminar')) { Toast.error(I18N.t('aviso.sinPermisoRfq')); return; }
        const si = await Confirmar.pedir({
            titulo: I18N.t('dlg.aprobar.titulo'),
            mensaje: I18N.t('dlg.aprobar.mensaje'),
            aceptar: I18N.t('dlg.aprobar.si'),
        });
        if (!si) return;
        bloquear(true);
        try {
            await API.approveRFQ(rfqAbierto, {});
            Toast.success(I18N.t('aviso.rfqAprobada'));
            const id = rfqAbierto;
            cerrar();
            APP.navigate('quote-review', { id });
        } catch (err) {
            if (!err.sesionExpirada) Toast.error(err.message);
        } finally { bloquear(false); }
    }

    async function devolver() {
        if (!API.puede('rfq:dictaminar')) { Toast.error(I18N.t('aviso.sinPermisoRfq')); return; }
        const nota = await Confirmar.pedirTexto({
            titulo: I18N.t('rev.dlg.devolver.titulo'),
            mensaje: I18N.t('rev.dlg.devolver.mensaje'),
            etiqueta: I18N.t('rev.dlg.devolver.nota'),
            marcador: I18N.t('rev.dlg.devolver.ejemplo'),
            obligatorio: true,
            aceptar: I18N.t('rev.devolver'),
        });
        if (nota === null) return;
        bloquear(true);
        try {
            await API.rfqSendBack(rfqAbierto, nota);
            Toast.success(I18N.t('rev.aviso.devuelto'));
            await recargar();
        } catch (err) {
            if (!err.sesionExpirada) Toast.error(err.message);
        } finally { bloquear(false); }
    }

    async function declinar() {
        if (!API.puede('rfq:dictaminar')) { Toast.error(I18N.t('aviso.sinPermisoRfq')); return; }
        const nota = await Confirmar.pedirTexto({
            titulo: I18N.t('dlg.rechazar.titulo'),
            mensaje: I18N.t('dlg.rechazar.mensaje'),
            etiqueta: I18N.t('dlg.rechazar.motivo'),
            marcador: I18N.t('dlg.rechazar.ejemplo'),
            obligatorio: true,
            aceptar: I18N.t('dlg.rechazar.si'),
            peligro: true,
        });
        if (nota === null) return;
        bloquear(true);
        try {
            await API.declineRFQ(rfqAbierto, { nota, enviar_correo: true });
            Toast.success(I18N.t('aviso.rfqRechazada'));
            await recargar();
        } catch (err) {
            if (!err.sesionExpirada) Toast.error(err.message);
        } finally { bloquear(false); }
    }

    /** Aprobado → la pantalla de la oferta; si no, el detalle del RFQ. */
    function cotizar() {
        const id = rfqAbierto;
        const estado = datos && datos.rfq && datos.rfq.estado;
        cerrar();
        APP.navigate(estado === 'Approved' ? 'quote-review' : 'rfq-detail', { id });
    }

    // ------------------------------------------------------------- ciclo

    function pintar() {
        if (!capa || !datos) return;
        capa.innerHTML = plantilla(datos);
        const titulo = capa.querySelector('.revision-titulo');
        if (titulo) titulo.id = 'revisionTitulo';
        const activo = capa.querySelector('.revision-tramo.activo');
        if (activo && window.matchMedia('(max-width: 768px)').matches) {
            activo.scrollIntoView({ block: 'nearest', inline: 'center' });
        }
    }

    async function recargar() {
        if (!rfqAbierto) return;
        datos = await API.rfqRevision(rfqAbierto);
        if (tramoActivo >= (datos.tramos || []).length) tramoActivo = 0;
        pintar();
        // La campana y el Resumen enseñan el mismo RFQ: que se enteren.
        if (typeof Notificaciones !== 'undefined' && Notificaciones.refrescar) Notificaciones.refrescar();
    }

    async function abrir(rfqId) {
        if (!rfqId) return;
        if (capa && rfqAbierto === rfqId) return;
        if (capa) cerrar(true);
        if (!API.puede('rfq:leer')) { Toast.warning(I18N.t('aviso.sinPermiso')); return; }

        rfqAbierto = rfqId;
        tramoActivo = 0;
        datos = null;
        capa = document.createElement('div');
        capa.className = 'revision-fondo';
        capa.innerHTML = `<div class="revision revision--cargando" role="dialog" aria-modal="true">
            <div class="loading-overlay"><div class="spinner"></div> ${esc(t('rev.cargando'))}</div></div>`;
        document.body.appendChild(capa);
        document.body.classList.add('revision-abierta');

        capa.addEventListener('click', alClic);
        document.addEventListener('keydown', alTeclear);

        try {
            datos = await API.rfqRevision(rfqId);
            if (!capa || rfqAbierto !== rfqId) return;   // se cerró mientras cargaba
            pintar();
        } catch (err) {
            if (err.sesionExpirada) { cerrar(); return; }
            if (!capa) return;
            capa.innerHTML = `<div class="revision" role="dialog" aria-modal="true">
                <div class="revision-cab"><div class="revision-titulo">${esc(rfqId)}</div>
                    <button type="button" class="revision-cerrar" data-accion="cerrar" aria-label="${esc(t('rev.cerrar'))}">&times;</button></div>
                <div class="revision-cuerpo"><div class="revision-franja revision-franja--error"><ul><li>${esc(err.message)}</li></ul></div></div>
            </div>`;
        }
    }

    function cerrar(silencio) {
        if (capa) capa.remove();
        capa = null; datos = null; rfqAbierto = null; ocupado = false;
        document.body.classList.remove('revision-abierta');
        document.removeEventListener('keydown', alTeclear);
        // La dirección deja de nombrar el RFQ para que "atrás" no lo reabra.
        if (!silencio && /^#\/rfq\//.test(location.hash)) {
            history.replaceState(history.state, '', location.pathname + location.search);
        }
    }

    function alClic(ev) {
        if (ocupado) return;
        const pestana = ev.target.closest('[data-tramo]');
        if (pestana) {
            tramoActivo = Number(pestana.dataset.tramo) || 0;
            pintar();
            return;
        }
        const boton = ev.target.closest('[data-accion]');
        if (boton) {
            const accion = boton.dataset.accion;
            if (accion === 'cerrar') cerrar();
            else if (accion === 'aprobar') aprobar();
            else if (accion === 'devolver') devolver();
            else if (accion === 'declinar') declinar();
            else if (accion === 'cotizar') cotizar();
            return;
        }
        // Clic en el velo, fuera de la caja: se cierra. En el teléfono la caja
        // ocupa todo, así que esto sólo pasa en la compu.
        if (ev.target === capa) cerrar();
    }

    function alTeclear(ev) {
        if (ev.key !== 'Escape' || ocupado) return;
        // Si hay un diálogo de confirmación encima, la tecla es para él.
        if (document.querySelector('.dialogo-fondo')) return;
        cerrar();
    }

    /** `#/rfq/<id>` en la dirección abre la ventana; quitarlo la cierra. */
    function porDireccion() {
        const m = /^#\/rfq\/(.+)$/.exec(location.hash || '');
        if (m) {
            let id = m[1];
            try { id = decodeURIComponent(id); } catch (_) { /* tal cual */ }
            abrir(id);
        } else if (capa) {
            cerrar(true);
        }
    }

    function init() {
        window.addEventListener('hashchange', porDireccion);
        // Al cambiar de idioma se vuelve a pintar con los textos nuevos.
        if (I18N.alCambiar) I18N.alCambiar(() => { if (capa && datos) pintar(); });
        porDireccion();
    }

    return { init, abrir, cerrar, recargar };
})();
