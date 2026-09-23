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
            for (const m of motivosDelCosteo(c)) lista.push({ nivel: 'warn', texto: m });
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
            // Los del motor de factibilidad vienen con su código; se dicen en
            // el idioma puesto igual que los del costeo.
            const texto = typeof m === 'string' ? m
                : (m && m.codigo) ? I18N.motivo('factib.', m)
                : ((m && (m.texto || m.motivo || m.mensaje)) || JSON.stringify(m));
            lista.push({ nivel: 'info', texto });
        }
        for (const campo of (d.campos_faltantes || [])) {
            lista.push({ nivel: 'warn', texto: t('rev.aviso.campoFalta', { campo }) });
        }
        return lista;
    }

    /**
     * Los motivos del costeo, en el idioma de Pohua.
     *
     * El servidor los manda de dos formas: la frase ya armada (siempre en
     * español, que es la que va al registro) y la misma con su CÓDIGO y sus
     * datos. Él no sabe en qué idioma está la pantalla —y el mismo RFQ lo
     * abren personas distintas—, así que la frase se arma aquí. Sin la lista
     * con códigos, o con un código que esta versión no conozca, se usa la
     * frase del servidor: mejor en español que un hueco.
     */
    function motivosDelCosteo(costeo) {
        const conCodigo = costeo.faltantes_i18n;
        if (!Array.isArray(conCodigo) || !conCodigo.length) {
            return costeo.faltantes || [];
        }
        return conCodigo.map((m) => traducirMotivo(m));
    }

    /** Un motivo suelto: por código si se conoce, y si no, tal como vino.
     *
     * Pasa por `I18N.motivo`, el mismo que traduce los del motor de
     * factibilidad: así `{campo}` se resuelve al nombre de la cota en el
     * idioma puesto —"número de espiras" y no "numero_espiras_totales"— sin
     * tener dos traductores que se van separando. */
    function traducirMotivo(m) {
        if (!m) return '';
        if (typeof m === 'string') return m;
        return I18N.motivo('costeo.', m) || m.texto || m.codigo || '';
    }

    function qtyCorta(v) {
        if (!esNum(v)) return '—';
        if (v >= 1000000) return (v / 1000000).toFixed(v % 1000000 ? 1 : 0) + 'M';
        if (v >= 1000) return Math.round(v / 1000) + 'k';
        return String(v);
    }

    // ------------------------------------------------------------- plantilla

    function cabecera(d) {
        const r = d.rfq || {};
        const pn = r.part_number || '—';
        const tipo = tipoResorte(r.tipo_resorte) || 'Compression spring';
        const quoteNum = r.quote_number || r.rfq_id || '—';
        const cliente = r.customer || '—';
        return `
            <div class="revision-cab">
                <div class="revision-cab-izq">
                    <span class="revision-cab-pn">${esc(pn)}</span>
                    <span class="revision-cab-sep">·</span>
                    <span class="revision-cab-tipo">${esc(tipo)}</span>
                </div>
                <div class="revision-cab-meta">Quote ${esc(quoteNum)} · ${esc(cliente)}</div>
                <button type="button" class="revision-cerrar" data-accion="cerrar" aria-label="${esc(t('rev.cerrar'))}">&times;</button>
            </div>`;
    }

    function comunes(d) {
        const c = d.comunes || {};
        const mat = c.material ? (esc(c.material) + (c.material_nombre ? ` — ${esc(c.material_nombre)}` : '')) : '—';
        return `
            <section class="revision-comunes" aria-label="${esc(t('rev.todosTramos'))}">
                <div class="revision-rotulo">${esc(t('rev.todosTramos'))}</div>
                <div class="revision-pills">
                    <span class="revision-pill">${mat}</span>
                    <span class="revision-pill">Ø ${esNum(c.dia_in) ? num(c.dia_in, 3) + ' in' : '—'}</span>
                    <span class="revision-pill">${esNum(c.peso_lb_pc) ? num(c.peso_lb_pc, 3) + ' lb/pc' : '—'}</span>
                    <span class="revision-pill">Base ${esNum(c.base_lb) ? dinero(c.base_lb, 2) + '/lb' : '—'}</span>
                    ${esNum(c.surcharge_lb) && c.surcharge_lb > 0 ? `<span class="revision-pill">Surcharge ${dinero(c.surcharge_lb, 2)}/lb</span>` : `<span class="revision-pill">Surcharge $0.00/lb</span>`}
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
                    <button type="button" role="tab" class="revision-tramo-card ${i === tramoActivo ? 'activo' : ''}"
                            data-tramo="${i}" aria-selected="${i === tramoActivo}">
                        <div class="revision-tramo-cab">
                            <span class="revision-tramo-tit">Tier ${i + 1}${i === 0 ? ' ★' : ''} · </span>
                            <span class="qty-larga">${entero(tr.cantidad)} pcs</span>
                            <span class="qty-corta">${qtyCorta(tr.cantidad)}</span>
                        </div>
                        <div class="revision-tramo-cuerpo">
                            <span class="revision-tramo-precio">
                                <span class="precio-largo">${dinero(tr.precio_pc)}/pc</span>
                                <span class="precio-corto">${dinero(tr.precio_pc)}</span>
                            </span>
                            <span class="revision-tramo-margen">${pct(tr.resultado_pct)}</span>
                        </div>
                    </button>`).join('')}
            </div>`;
    }

    function franja(lista) {
        if (!lista.length) return '';
        const nivel = lista.some(a => a.nivel === 'error') ? 'error'
                    : lista.some(a => a.nivel === 'warn') ? 'warn' : 'info';
        return `
            <div class="revision-franja revision-franja--${nivel}" role="status">
                <span class="revision-franja-icono">⚠</span>
                <div class="revision-franja-texto">
                    ${lista.map(a => esc(a.texto)).join(' — ')}
                </div>
            </div>`;
    }

    function cascada(tr) {
        const c = (tr && tr.cascada) || {};
        const targetPct = tr && tr.objetivo_pct != null ? pct(tr.objetivo_pct, 0) : '20%';
        const llega = tr && tr.llega;
        const resClase = llega ? 'revision-cascada--ok' : 'revision-cascada--corto';
        return `
            <div class="revision-cascada-wrap">
                <div class="revision-cascada-tit-movil">
                    MARGIN WATERFALL · PER PIECE · ${entero(tr ? tr.cantidad : 0)} PCS
                </div>
                <!-- Desktop 5 columns -->
                <div class="revision-cascada-grid">
                    <div class="revision-cascada-col">
                        <span class="revision-cascada-lbl">SELLING PRICE</span>
                        <span class="revision-cascada-val">${dinero(c.sell)}</span>
                        <span class="revision-cascada-sub">100%</span>
                    </div>
                    <div class="revision-cascada-col">
                        <span class="revision-cascada-lbl">AV</span>
                        <span class="revision-cascada-val">${dinero(c.av)}</span>
                        <span class="revision-cascada-sub">${pct(c.av_pct)}</span>
                    </div>
                    <div class="revision-cascada-col">
                        <span class="revision-cascada-lbl">C/CV</span>
                        <span class="revision-cascada-val">${dinero(c.ccv)}</span>
                        <span class="revision-cascada-sub">${pct(c.ccv_pct)}</span>
                    </div>
                    <div class="revision-cascada-col">
                        <span class="revision-cascada-lbl">C/CD</span>
                        <span class="revision-cascada-val">${dinero(c.ccd)}</span>
                        <span class="revision-cascada-sub">${pct(c.ccd_pct)}</span>
                    </div>
                    <div class="revision-cascada-col revision-cascada-col--resultado ${resClase}">
                        <span class="revision-cascada-lbl">RESULT · TARGET ${targetPct}</span>
                        <span class="revision-cascada-val">${dinero(c.resultado)}</span>
                        <span class="revision-cascada-sub">${pct(c.resultado_pct)}</span>
                    </div>
                </div>
                <!-- Mobile 5 rows -->
                <div class="revision-cascada-lista">
                    <div class="revision-cascada-fila">
                        <span class="revision-cascada-fila-lbl">Selling price</span>
                        <span class="revision-cascada-fila-val">${dinero(c.sell)}</span>
                        <span class="revision-cascada-fila-sub">100%</span>
                    </div>
                    <div class="revision-cascada-fila">
                        <span class="revision-cascada-fila-lbl">AV</span>
                        <span class="revision-cascada-fila-val">${dinero(c.av)}</span>
                        <span class="revision-cascada-fila-sub">${pct(c.av_pct)}</span>
                    </div>
                    <div class="revision-cascada-fila">
                        <span class="revision-cascada-fila-lbl">C/CV</span>
                        <span class="revision-cascada-fila-val">${dinero(c.ccv)}</span>
                        <span class="revision-cascada-fila-sub">${pct(c.ccv_pct)}</span>
                    </div>
                    <div class="revision-cascada-fila">
                        <span class="revision-cascada-fila-lbl">C/CD</span>
                        <span class="revision-cascada-fila-val">${dinero(c.ccd)}</span>
                        <span class="revision-cascada-fila-sub">${pct(c.ccd_pct)}</span>
                    </div>
                    <div class="revision-cascada-fila revision-cascada-fila--resultado ${resClase}">
                        <span class="revision-cascada-fila-lbl">Result - target ${targetPct}</span>
                        <span class="revision-cascada-fila-val">${dinero(c.resultado)}</span>
                        <span class="revision-cascada-fila-sub">${pct(c.resultado_pct)}</span>
                    </div>
                </div>
            </div>`;
    }

    function columnas(tr) {
        const m = (tr && tr.material) || {};
        const ruta = (tr && tr.ruta) || [];
        const tot = (tr && tr.totales) || {};
        const horasTot = esNum(tot.horas) ? Math.round(tot.horas) : null;
        return `
            <div class="revision-columnas-grid">
                <section class="revision-bloque">
                    <h4 class="revision-bloque-tit">MATERIAL THIS TIER</h4>
                    <div class="revision-fila-dato">
                        <span class="revision-fila-lbl">
                            <span class="lbl-desktop">$/pc</span>
                            <span class="lbl-movil">Material $/pc</span>
                        </span>
                        <span class="revision-fila-val">
                            ${esNum(m.pc) ? `<b>${dinero(m.pc)}</b> <small>· ${pct(m.pct)}</small>` : '—'}
                        </span>
                    </div>
                    <div class="revision-fila-dato">
                        <span class="revision-fila-lbl">Wire to buy</span>
                        <span class="revision-fila-val">
                            <b>${esNum(m.lb_comprar) ? num(m.lb_comprar, 0) + ' lb' : '—'}</b>
                        </span>
                    </div>
                    ${m.moq_manda ? `<div class="revision-nota">${esc(t('rev.aviso.moq'))}</div>` : ''}
                </section>

                <section class="revision-bloque">
                    <h4 class="revision-bloque-tit">
                        <span class="lbl-desktop">ROUTE${horasTot ? ` · ${horasTot} MACHINE H` : ''}</span>
                        <span class="lbl-movil">ROUTE${horasTot ? ` · ${horasTot} MACHINE HOURS` : ''}</span>
                    </h4>
                    ${ruta.length ? ruta.map(op => `
                        <div class="revision-fila-dato">
                            <span class="revision-fila-lbl">${esc(op.maquina || '—')}</span>
                            <span class="revision-fila-val">
                                <b>${esNum(op.pph) ? num(op.pph, 0) + ' pc/h' : '—'}</b>
                                <small>· setup ${esNum(op.setup_h) ? num(op.setup_h, 1) + ' h' : '—'}</small>
                            </span>
                        </div>`).join('') : `<div class="revision-nota">${esc(t('rev.sinRuta'))}</div>`}
                </section>

                <section class="revision-bloque">
                    <h4 class="revision-bloque-tit">TIER TOTALS</h4>
                    <div class="revision-fila-dato">
                        <span class="revision-fila-lbl">Revenue</span>
                        <span class="revision-fila-val">
                            <b>${dinero(tot.ingreso, 0)}</b>
                        </span>
                    </div>
                    <div class="revision-fila-dato">
                        <span class="revision-fila-lbl">
                            <span class="lbl-desktop">C/CV per h</span>
                            <span class="lbl-movil">C/CV per machine hour</span>
                        </span>
                        <span class="revision-fila-val">
                            <b>${esNum(tot.ccv_hora) ? dinero(tot.ccv_hora, 2) : '—'}</b>
                        </span>
                    </div>
                </section>
            </div>`;
    }

    function pie(d) {
        const r = d.rfq || {};
        const puede = d.puede_dictaminar && API.puede('rfq:dictaminar');
        const abierto = r.estado === 'RequiresReview' || r.estado === 'New' || r.estado === 'Incomplete';
        const icono = `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`;

        // Dos grupos, y la raya entre ellos es lo que importa: a la izquierda
        // lo que sólo MIRA —el PDF y la cotización entera—, a la derecha lo
        // que DECIDE. En una sola fila, "ver el PDF" quedaba pegado a
        // "Aprobar", que es un clic entre enterarse y cerrar la cotización.
        const ver = [
            `<button type="button" class="btn revision-btn revision-btn--fantasma" data-accion="pdf">${icono}${esc(t('rev.previewPdf'))}</button>`,
            `<button type="button" class="btn revision-btn revision-btn--fantasma" data-accion="cotizar">${esc(t(r.estado === 'Approved' ? 'rev.abrirOferta' : 'rev.abrirCompleta'))}</button>`,
        ];
        const decidir = [];
        if (puede && abierto) {
            decidir.push(`<button type="button" class="btn btn-secondary revision-btn" data-accion="devolver">${esc(t('rev.devolver'))}</button>`);
        }
        if (puede && r.estado !== 'Declined') {
            decidir.push(`<button type="button" class="btn revision-btn revision-btn--suave" data-accion="declinar">${esc(t('rev.declinar'))}</button>`);
        }
        if (puede && abierto) {
            // La verde, la última: a la derecha en la compu y abajo en el
            // teléfono, donde llega el pulgar y donde termina la lectura.
            decidir.push(`<button type="button" class="btn btn-success revision-btn" data-accion="aprobar">${esc(t('rev.aprobar'))}</button>`);
        }

        return `
            <div class="revision-pie">
                <div class="revision-pie-nota">${esc(puede && abierto ? t('rev.pieNota') : (puede ? t('rev.pieCerrado') : t('rev.pieSoloLectura')))}</div>
                <div class="revision-acciones">
                    <div class="revision-grupo revision-grupo--ver">${ver.join('')}</div>
                    ${decidir.length ? `<div class="revision-grupo revision-grupo--decidir">${decidir.join('')}</div>` : ''}
                </div>
            </div>`;
    }

    /**
     * La geometría con la que se está dictaminando, y editable.
     *
     * Por qué editable y por qué AQUÍ: el veredicto se calculaba una sola vez,
     * al entrar el correo, y se quedaba grabado. El PM mira el dibujo, ve que
     * el modelo leyó 1.6 donde dice 1.8, y antes esa corrección no tenía
     * dónde ir: o dictaminaba sobre un dato que sabe malo, o lo corregía en la
     * calculadora y el RFQ se quedaba con el valor viejo.
     *
     * Los campos son los que mueven el dictamen y el costeo. Nada más: por
     * aquí entra lo que alguien escribe en un formulario, y la lista de lo que
     * puede tocar la cierra el servidor (app/rfq/recalculo.py).
     */
    function geometria(d) {
        const g = d.resorte || {};
        const puede = d.puede_dictaminar && API.puede('rfq:dictaminar');
        const lec = d.lectura_plano;

        const campo = (clave, etiqueta, valor, unidad) => `
            <label class="revision-campo">
                <span class="revision-campo-et">${esc(etiqueta)}${unidad ? ` <i>${esc(unidad)}</i>` : ''}</span>
                <input type="text" inputmode="decimal" data-campo="${esc(clave)}"
                       value="${valor === null || valor === undefined ? '' : esc(valor)}"
                       ${puede ? '' : 'disabled'}>
            </label>`;

        // Por qué la tarjeta está vacía, cuando lo está: es la diferencia
        // entre "el correo no traía plano" y "traía uno y ni se miró".
        let nota = '';
        if (lec && lec.estado && lec.estado !== 'leido') {
            const ficheros = (lec.ficheros || []).join(', ');
            if (lec.estado === 'sin_adjunto') nota = t('plano.sinAdjunto');
            else if (lec.estado === 'formato_no_leido') {
                nota = t('plano.sinFormato', { ficheros, soportados: (lec.soportados || []).join(', ') });
            } else if (lec.estado === 'fallo') {
                nota = t('plano.fallo', { ficheros, motivo: lec.motivo || '' });
            }
        }

        const ajustado = g.ajustado_por
            ? `<span class="revision-ajustado">${esc(t('rev.ajustadoPor', { quien: g.ajustado_por }))}</span>` : '';

        /* Lo que el lector anotó del plano. Se le piden en el prompt —"anota
           cualquier ambigüedad, texto ilegible o supuesto"— y hasta ahora se
           guardaban sin que las viera nadie. Van aquí, pegadas a las cotas
           que comentan, porque es donde el PM decide si corrige un número,
           manda releer o le pregunta al cliente. */
        /* Las totales deducidas de las activas. La casilla se deja VACÍA a
           propósito: lo que el PM escriba ahí se guarda como leído del plano,
           y este número no lo es. Se enseña debajo, con el método, para que
           se vea que el peso ya está resuelto y nadie lo teclee encima —si
           teclea las activas creyendo que son las totales, el peso sale corto
           y el precio con él—. */
        const deducidas = (g.espiras_calculadas && g.espiras_origen)
            ? `<p class="revision-geo-deducido">${esc(t('rev.espirasDeducidas', {
                   n: g.espiras_calculadas, metodo: g.espiras_origen }))}</p>`
            : '';

        const avisos = (g.advertencias || []).filter(Boolean);
        const avisosHtml = avisos.length ? `
            <ul class="revision-geo-avisos">
                ${avisos.map(a => `<li>${esc(a)}</li>`).join('')}
            </ul>` : '';

        return `
            <section class="revision-bloque revision-geo">
                <h4>${esc(t('rev.geometria'))}${ajustado}</h4>
                ${nota ? `<p class="revision-geo-nota">${esc(nota)}</p>` : ''}
                ${avisosHtml}
                <div class="revision-campos">
                    ${campo('diametro_alambre_mm', t('ficha.alambre'), g.diametro_alambre_mm, 'mm')}
                    ${campo('diametro_exterior_mm', t('ficha.exterior'), g.diametro_exterior_mm, 'mm')}
                    ${campo('longitud_libre_mm', t('ficha.libre'), g.longitud_libre_mm, 'mm')}
                    ${campo('numero_espiras_totales', t('ficha.espiras'), g.espiras_totales, '')}
                    ${campo('material', t('ficha.material'), g.material_texto || '', '')}
                </div>
                ${deducidas}
                ${puede ? `<div class="revision-geo-acciones">
                    <button type="button" class="btn btn-secondary revision-btn" data-accion="leerPlano">${esc(t('plano.releer'))}</button>
                    <button type="button" class="btn btn-primary revision-btn" data-accion="recalcular">${esc(t('rev.recalcular'))}</button>
                </div>
                <p class="revision-geo-pie">${esc(t('rev.recalcularNota'))}</p>` : ''}
            </section>`;
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
                    ${geometria(d)}
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

    /**
     * Rehace el dictamen con lo que haya escrito el PM.
     *
     * `conPlano` es el botón «Leer el plano con IA»: relee el dibujo aunque el
     * resorte ya tenga cotas, porque el PM puede querer las del dibujo
     * justamente porque duda de las que hay.
     *
     * Lo que se manda son SÓLO los campos que cambiaron. Mandar el formulario
     * entero haría que cada recálculo marcara el resorte como "ajustado por
     * una persona" aunque nadie tocara nada, y se perdería la distinción entre
     * lo que leyó la IA y lo que corrigió el PM.
     */
    async function recalcular(conPlano) {
        if (!API.puede('rfq:dictaminar')) { Toast.error(I18N.t('aviso.sinPermisoRfq')); return; }
        if (!rfqAbierto || (datos && datos.esCotizacion)) return;

        const previo = (datos && datos.resorte) || {};
        const equivalencias = { numero_espiras_totales: 'espiras_totales',
                                material: 'material_texto' };
        const ajustes = {};
        capa.querySelectorAll('[data-campo]').forEach((entrada) => {
            const clave = entrada.dataset.campo;
            const escrito = entrada.value.trim();
            const antes = previo[equivalencias[clave] || clave];
            const antesTexto = (antes === null || antes === undefined) ? '' : String(antes);
            if (escrito === antesTexto) return;
            // Vaciar un campo a propósito se dice con "-": una cadena vacía es
            // "no lo mandé", y borraría sin querer lo que el modelo sí leyó.
            ajustes[clave] = escrito === '' ? '-' : escrito;
        });

        bloquear(true);
        const boton = capa.querySelector(conPlano ? '[data-accion="leerPlano"]' : '[data-accion="recalcular"]');
        const antesTexto = boton ? boton.textContent : '';
        if (boton) boton.textContent = I18N.t(conPlano ? 'plano.releyendo' : 'rev.recalculando');
        try {
            const nuevo = await API.recalcularRfq(rfqAbierto, {
                ajustes, leer_plano: !!conPlano });
            datos = nuevo;
            if (tramoActivo >= (datos.tramos || []).length) tramoActivo = 0;
            pintar();

            const rec = nuevo.recalculo || {};
            const lec = nuevo.lectura_plano;
            if (conPlano && lec && lec.estado !== 'leido') {
                Toast.error(I18N.t('plano.fallo', {
                    ficheros: (lec.ficheros || []).join(', '), motivo: lec.motivo || '' }));
            } else if (rec.error) {
                Toast.error(rec.error);
            } else if ((rec.tocados || []).length) {
                Toast.success(I18N.t('rev.recalculado', { n: rec.tocados.length }));
            } else {
                Toast.success(I18N.t('rev.recalculadoSinCambios'));
            }
        } catch (err) {
            Toast.error(err.message);
        } finally {
            if (boton) boton.textContent = antesTexto;
            bloquear(false);
        }
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
            if (datos && datos.esCotizacion) {
                const marco = document.getElementById('quotingMarco');
                if (marco && marco.contentWindow) {
                    const cw = marco.contentWindow;
                    if (typeof cw.Q === 'function') {
                        const q = cw.Q();
                        q.status = 'APPROVED';
                        q.outcome = 'NO RECEPTION';
                        if (typeof cw.nowStr === 'function') q.approvedAt = cw.nowStr();
                        if (cw.CUR) q.approvedBy = cw.CUR.email;
                        if (typeof cw.logUpsert === 'function') cw.logUpsert();
                        if (typeof cw.renderQuote === 'function') cw.renderQuote();
                        if (typeof cw.saveLocal === 'function') cw.saveLocal();
                        if (cw.SFS && typeof cw.SFS.write === 'function') cw.SFS.write();
                        if (typeof cw.fileApprovedPdf === 'function') cw.fileApprovedPdf(q);
                    }
                }
                Toast.success(I18N.t('aviso.rfqAprobada'));
                cerrar();
                return;
            }
            await API.approveRFQ(rfqAbierto, {});
            Toast.success(I18N.t('aviso.rfqAprobada'));
            const id = rfqAbierto;
            cerrar();
            APP.navigate('quote-review', { id });
        } catch (err) {
            if (!err.sesionExpirada) Toast.error(err.message);
        } finally { bloquear(false); }
    }

    /**
     * Declinar: el único botón de esta ventana que sale de la empresa.
     *
     * Existía desde el principio —con su diálogo ya escrito en los tres
     * idiomas— y nunca llegó a haber una función detrás. El clic moría con un
     * `ReferenceError` en la consola y la pantalla no se inmutaba: ni un
     * aviso, ni un error, nada. El mismo fallo que tuvo `cotizar` en su día.
     *
     * Eso, en un botón que DECLINA, es de lo peor que puede pasar: quien lo
     * pulsaba se quedaba convencido de haber rechazado el RFQ, y el RFQ
     * seguía vivo esperando dictamen. El cliente, sin respuesta.
     *
     * Tres cosas que este botón sí hace ahora:
     *
     *  - Pide el motivo, y no sigue sin él. Se guarda en las notas del RFQ,
     *    que es donde lo va a buscar dentro de seis meses quien se pregunte
     *    por qué se rechazó esta pieza. El cliente NO lo lee: el correo de
     *    declinación es el machote de la empresa y no incluye la nota.
     *  - Avisa de que el correo sale y de que no se puede deshacer, con el
     *    diálogo en rojo.
     *  - Dice si el correo SALIÓ DE VERDAD. El servidor lo devuelve en
     *    `correo_enviado`, y puede ser que no: con el envío automático
     *    apagado, o sin remitente en el correo original, el RFQ queda
     *    declinado y el comprador sin enterarse. Callarlo sería dejar al PM
     *    creyendo que avisó.
     */
    async function declinar() {
        if (!API.puede('rfq:dictaminar')) { Toast.error(I18N.t('aviso.sinPermisoRfq')); return; }
        // La ventana también sirve para mirar un borrador de la calculadora,
        // y ahí no hay nada que declinar: no hay RFQ ni cliente a quien
        // escribir.
        if (datos && datos.esCotizacion) { Toast.warning(I18N.t('rev.sinDictamen')); return; }

        const motivo = await Confirmar.pedir({
            titulo: I18N.t('dlg.rechazar.titulo'),
            mensaje: I18N.t('dlg.rechazar.mensaje'),
            aceptar: I18N.t('dlg.rechazar.si'),
            peligro: true,
            campo: { etiqueta: I18N.t('dlg.rechazar.motivo'),
                     marcador: I18N.t('dlg.rechazar.ejemplo') },
        });
        if (motivo === null) return;                 // canceló
        if (!String(motivo).trim()) {
            // Declinar sin decir por qué deja el rastro vacío justo donde más
            // falta hace. Se pide otra vez en vez de dejarlo pasar.
            Toast.warning(I18N.t('aviso.motivoHace'));
            return;
        }

        bloquear(true);
        const id = rfqAbierto;
        try {
            const r = await API.declineRFQ(id, { nota: String(motivo).trim() });
            cerrar();
            if (r && r.correo_enviado) {
                Toast.success(I18N.t('aviso.rfqRechazadaAviso'));
            } else {
                // No es un error: el dictamen quedó. Pero hay que decirlo.
                Toast.warning(I18N.t('aviso.rfqRechazadaSinCorreo'));
            }
            // Repinta la pantalla de debajo para que el RFQ salga ya con
            // su nuevo estado, sin que haya que recargar a mano.
            if (typeof APP !== 'undefined' && APP.handleRoute) APP.handleRoute();
        } catch (err) {
            if (!err.sesionExpirada) Toast.error(err.message);
        } finally { bloquear(false); }
    }

    /**
     * Devolver: ni aprueba ni declina, y NO sale nada al cliente.
     *
     * Es la salida para el caso más común de todos —falta un dato, hay que
     * preguntarle algo al comprador, el plano no cuadra— y también estaba sin
     * escribir.
     *
     * El motivo es obligatorio por lo mismo que en declinar, pero aquí pesa
     * todavía más: un RFQ devuelto sin decir qué le falta es un RFQ que vuelve
     * igual de incompleto y le hace perder el viaje a dos personas.
     */
    async function devolver() {
        if (!API.puede('rfq:dictaminar')) { Toast.error(I18N.t('aviso.sinPermisoRfq')); return; }
        if (datos && datos.esCotizacion) { Toast.warning(I18N.t('rev.sinDictamen')); return; }

        const nota = await Confirmar.pedir({
            titulo: I18N.t('dlg.devolver.titulo'),
            mensaje: I18N.t('dlg.devolver.mensaje'),
            aceptar: I18N.t('dlg.devolver.si'),
            campo: { etiqueta: I18N.t('dlg.devolver.motivo'),
                     marcador: I18N.t('dlg.devolver.ejemplo') },
        });
        if (nota === null) return;
        if (!String(nota).trim()) { Toast.warning(I18N.t('aviso.motivoHace')); return; }

        bloquear(true);
        try {
            await API.rfqSendBack(rfqAbierto, String(nota).trim());
            cerrar();
            Toast.success(I18N.t('aviso.rfqDevuelta'));
            // Repinta la pantalla de debajo para que el RFQ salga ya con
            // su nuevo estado, sin que haya que recargar a mano.
            if (typeof APP !== 'undefined' && APP.handleRoute) APP.handleRoute();
        } catch (err) {
            if (!err.sesionExpirada) Toast.error(err.message);
        } finally { bloquear(false); }
    }

    /** La cotización entera: la calculadora, abierta con este RFQ dentro.

        "Completa" es literal: las dos hojas —Quote y Spring Calc— con lo que
        el sistema sacó del correo y del plano ya puesto en cada casilla. Antes
        llevaba a la pantalla de la oferta, que es el resultado y no el
        trabajo; y antes de eso ni siquiera existía —el botón la llamaba, el
        clic moría con un ReferenceError y no pasaba nada—.

        La oferta sigue estando: se llega a ella desde la propia calculadora al
        aprobar, y desde la ficha del RFQ. */
    function cotizar() {
        const id = rfqAbierto;
        cerrar();
        APP.navigate('quoting', { rfq: id });
    }

    /**
     * El PDF de lo que se está mirando.
     *
     * Hay DOS PDF distintos y se estaban confundiendo:
     *
     *   - La OFERTA del RFQ: la hace el servidor con los tramos costeados que
     *     esta misma ventana acaba de enseñar. Lleva el número del RFQ, el
     *     cliente, el material del correo y las tres cantidades con su precio.
     *   - El borrador de la CALCULADORA: lo que haya ahora mismo en la hoja.
     *
     * Se miraba primero si existía el marco de la calculadora y, de existir,
     * se le pedía el suyo. Pero el marco existe siempre que alguien haya
     * pasado por Cotización en esta sesión —se queda montado a propósito, para
     * no perder el trabajo al navegar—, así que revisando un RFQ salía el PDF
     * del borrador ajeno: "2026-CUST-001 (DRAFT)", sin cliente, "Material: SS"
     * y "No priced quantities". Nada de eso era del RFQ que se estaba
     * dictaminando.
     *
     * Ahora manda de DÓNDE se abrió la ventana, no qué marcos hay en la
     * página: desde la calculadora, su PDF; desde un RFQ, la oferta. Es la
     * misma distinción que ya hacía "Aprobar".
     */
    async function verPdf() {
        if (datos && datos.esCotizacion) {
            const marco = document.getElementById('quotingMarco');
            if (marco && marco.contentWindow &&
                typeof marco.contentWindow.previewPdf === 'function') {
                try {
                    await marco.contentWindow.previewPdf();
                    return;
                } catch (_) { /* si su PDF falla, se intenta el del servidor */ }
            }
        }
        const id = rfqAbierto || (datos && datos.rfq && datos.rfq.rfq_id);
        if (!id || id === 'quote') {
            Toast.warning(I18N.t('rev.sinPdf'));
            return;
        }
        const w = window.open('', '_blank');
        try {
            const blob = await API.descargarOfertaPdf(id);
            const url = URL.createObjectURL(blob);
            if (w) w.location.href = url;
            else window.open(url, '_blank');
            setTimeout(() => URL.revokeObjectURL(url), 60000);
        } catch (err) {
            if (w) w.close();
            if (!err.sesionExpirada) Toast.error(err.message || 'Error al generar el PDF');
        }
    }

    function convertirCotizacion(q, r) {
        if (!q) return null;
        const p = (q.pns && q.pns[q.activePn || 0]) || {};
        const pNum = p.pn || '1060-022';
        const tipo = p.desc || 'Compression spring';
        const quoteNum = q.number || 'Quote';
        const cliente = (q.header && q.header.customer) || 'Customer';

        const tramos = (r && r.tiers ? r.tiers : []).map(t => ({
            cantidad: t.qty || 0,
            precio_pc: t.sellingPrice || t.price || 0,
            resultado_pct: t.marginPct != null ? t.marginPct : (t.margin || 20),
            objetivo_pct: q.contribution || 20,
            llega: (t.marginPct != null ? t.marginPct : (t.margin || 20)) >= (q.contribution || 20),
            cascada: {
                sell: t.sellingPrice || 0,
                av: t.av || 0,
                av_pct: t.avPct || (t.av && t.sellingPrice ? (t.av / t.sellingPrice) * 100 : 0),
                ccv: t.ccv || 0,
                ccv_pct: t.ccvPct || (t.ccv && t.sellingPrice ? (t.ccv / t.sellingPrice) * 100 : 0),
                ccd: t.ccd || 0,
                ccd_pct: t.ccdPct || (t.ccd && t.sellingPrice ? (t.ccd / t.sellingPrice) * 100 : 0),
                resultado: t.result || (t.sellingPrice && t.ccd ? t.sellingPrice - t.ccd : 0),
                resultado_pct: t.marginPct != null ? t.marginPct : 20,
            },
            material: {
                pc: t.matCost || 0,
                pct: t.matPct || 0,
                lb_comprar: t.wireToBuy || t.matWeight || 0,
                moq_manda: false,
            },
            ruta: (t.ops || []).map(o => ({
                maquina: o.machine || o.name || '—',
                pph: o.pph || 0,
                setup_h: o.setupH || 0,
            })),
            totales: {
                ingreso: (t.sellingPrice || 0) * (t.qty || 0),
                horas: t.machineHours || t.totalHours || 0,
                ccv_hora: t.ccvPerH || 0,
            },
            avisos: {},
        }));

        return {
            rfq: {
                part_number: pNum,
                tipo_resorte: tipo,
                rfq_id: quoteNum,
                quote_number: quoteNum,
                customer: cliente,
                estado: q.status || 'DRAFT',
            },
            comunes: {
                material: p.wire || 'SS',
                material_nombre: p.matName || 'Stainless steel',
                dia_in: p.dia || p.wireDia || 0.205,
                peso_lb_pc: p.weight || 0.295,
                base_lb: p.basePrice || 1.85,
                surcharge_lb: p.surcharge || 1.30,
            },
            tramos: tramos,
            puede_dictaminar: true,
            costeo: { completo: true },
            esCotizacion: true,
        };
    }

    // ------------------------------------------------------------- ciclo

    function pintar() {
        if (!capa || !datos) return;
        capa.innerHTML = plantilla(datos);
        const activo = capa.querySelector('.revision-tramo-card.activo');
        if (activo && window.matchMedia('(max-width: 768px)').matches) {
            activo.scrollIntoView({ block: 'nearest', inline: 'center' });
        }
    }

    async function recargar() {
        if (!rfqAbierto || (datos && datos.esCotizacion)) return;
        datos = await API.rfqRevision(rfqAbierto);
        if (tramoActivo >= (datos.tramos || []).length) tramoActivo = 0;
        pintar();
        if (typeof Notificaciones !== 'undefined' && Notificaciones.refrescar) Notificaciones.refrescar();
    }

    async function abrir(origen, calcData) {
        if (!origen) return;
        if (capa && rfqAbierto === origen) return;
        if (capa) cerrar(true);

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

        if (typeof origen === 'object' && origen !== null) {
            if (origen.rfq && origen.tramos) {
                rfqAbierto = (origen.rfq && origen.rfq.rfq_id) || 'quote';
                datos = origen;
            } else {
                datos = convertirCotizacion(origen, calcData);
                rfqAbierto = (datos && datos.rfq && datos.rfq.rfq_id) || 'quote';
            }
            pintar();
            return;
        }

        if (!API.puede('rfq:leer')) { Toast.warning(I18N.t('aviso.sinPermiso')); cerrar(); return; }

        rfqAbierto = origen;
        try {
            datos = await API.rfqRevision(origen);
            if (!capa || rfqAbierto !== origen) return;
            pintar();
        } catch (err) {
            if (err.sesionExpirada) { cerrar(); return; }
            if (!capa) return;
            capa.innerHTML = `<div class="revision" role="dialog" aria-modal="true">
                <div class="revision-cab"><div class="revision-cab-izq"><span class="revision-cab-pn">${esc(origen)}</span></div>
                    <button type="button" class="revision-cerrar" data-accion="cerrar" aria-label="${esc(t('rev.cerrar'))}">&times;</button></div>
                <div class="revision-cuerpo"><div class="revision-franja revision-franja--error"><span class="revision-franja-icono">⚠</span><div class="revision-franja-texto">${esc(err.message)}</div></div></div>
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
            else if (accion === 'pdf') verPdf();
            else if (accion === 'aprobar') aprobar();
            else if (accion === 'devolver') devolver();
            else if (accion === 'declinar') declinar();
            else if (accion === 'cotizar') cotizar();
            else if (accion === 'recalcular') recalcular(false);
            else if (accion === 'leerPlano') recalcular(true);
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
