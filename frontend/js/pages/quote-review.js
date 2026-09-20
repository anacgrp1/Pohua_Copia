/**
 * Quote — la oferta al cliente.
 *
 * Es la pantalla a la que se llega cuando el Plant Manager ya aprobó: enseña
 * los tramos costeados (los mismos que vio en la ventana de revisión), lo que
 * irá en el correo —destinatario, plazo, incoterm, validez— y deja dos cosas:
 * ver el PDF antes de mandarlo, y mandarlo.
 *
 * Los precios no se calculan aquí: vienen de `/api/rfqs/{id}/oferta`, que
 * costea con el catálogo de Neon y dice si el número es fiable. Si el costeo
 * es orientativo (al catálogo le falta el precio del alambre, la tarifa de
 * una máquina…), mandar exige confirmarlo a sabiendas.
 *
 * Con `ENVIO_AUTOMATICO` apagado el servidor genera el PDF y construye el
 * correo pero no lo manda: la pantalla lo avisa antes de que alguien crea que
 * el cliente ya lo recibió.
 */
const QuoteReviewPage = {
    currentRfqId: null,
    oferta: null,

    esc(v) {
        return String(v == null ? '' : v)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    },

    dinero(v, dec) {
        if (typeof v !== 'number' || !isFinite(v)) return '—';
        if (dec == null) dec = Math.abs(v) < 10 ? 4 : 2;
        return '$' + v.toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec });
    },

    /**
     * Por qué la oferta no está lista, en el idioma de Pohua.
     *
     * El servidor manda cada motivo con su CÓDIGO y sus datos además de la
     * frase en español (app/rfq/oferta.py → pricing/mensajes.py). Aquí se
     * arma la frase, y los motivos del costeo que van dentro —"El costeo es
     * orientativo: <esto>"— se traducen uno a uno en vez de pegarse tal cual,
     * que era lo que dejaba media pantalla en español.
     */
    motivos(o) {
        const lista = o.motivos_i18n;
        if (!Array.isArray(lista) || !lista.length) return o.motivos || [];
        return lista.map((m) => {
            const dentro = (m.faltantes || []).map(f => this.unMotivo(f)).join('; ');
            const datos = Object.assign({}, m.datos || {});
            if (dentro) datos.detalle = dentro;
            return this.unMotivo(m, datos);
        });
    },

    /** Un motivo: por su código si se conoce, y si no, tal como vino. */
    unMotivo(m, datos) {
        if (!m) return '';
        if (typeof m === 'string') return m;
        const clave = 'costeo.' + m.codigo;
        const texto = I18N.t(clave, datos || m.datos || {});
        return texto === clave ? (m.texto || m.codigo || '') : texto;
    },

    async render(container, params) {
        this.currentRfqId = params.id;
        container.innerHTML = `<div class="loading-overlay"><div class="spinner"></div> ${I18N.t('oferta.cargando')}</div>`;
        await this.loadData(container);
    },

    async loadData(container) {
        const id = this.currentRfqId;
        // Las clases .rfqd-* son las de la ficha del RFQ, a propósito: es la
        // misma cabecera —volver, identificador, estado y botones— y en el
        // teléfono tiene que partirse igual, en tres renglones.
        const volver = `<button class="btn btn-secondary rfqd-volver" onclick="APP.navigate('rfq-detail', {id: '${this.esc(id)}'})">&larr; ${I18N.t('oferta.volver')}</button>`;
        try {
            const o = await API.rfqOferta(id);
            this.oferta = o;
            const e = this.esc.bind(this);
            const linea = (o.pdf && o.pdf.lines && o.pdf.lines[0]) || {};
            const tramos = linea.tiers || [];
            const puedeEnviar = o.puede_enviar && API.puede('rfq:dictaminar');
            const aprobado = o.estado === 'Approved';
            const anterior = o.oferta_anterior;

            const tarjetas = tramos.map((t, i) => `
                <div class="status-card" style="--card-accent:${i === 0 ? 'var(--color-success)' : 'var(--cgr-azul-frio)'};--card-accent-bg:${i === 0 ? 'var(--color-success-bg)' : 'var(--color-info-bg)'}">
                    <div class="card-label">${Math.round(t.qty).toLocaleString()} pcs</div>
                    <div class="card-value">${this.dinero(t.price)}</div>
                    <div class="card-label">USD / ${I18N.t('oferta.pieza')} · ${this.dinero(t.qty * t.price, 2)} ${I18N.t('oferta.lote')}</div>
                </div>`).join('');

            const motivos = this.motivos(o).map(m => `<li>${e(m)}</li>`).join('');
            const fila = (k, v) => `<div class="detail-row"><span class="detail-key">${e(k)}</span><span class="detail-value" style="word-break:break-word">${v}</span></div>`;

            container.innerHTML = `
                <div class="rfqd-cab">
                    ${volver}
                    <div class="rfqd-ident">
                        <h2 class="rfqd-id">${I18N.t('oferta.titulo')}: ${e(id)}</h2>
                        <span class="badge ${aprobado ? 'badge-approved' : 'badge-review'}"><span class="badge-dot"></span>${e(o.estado)}</span>
                    </div>
                    <div class="rfqd-acciones">
                        <button class="btn btn-secondary" onclick="QuoteReviewPage.verPdf()" ${tramos.length ? '' : 'disabled'}>${I18N.t('oferta.verPdf')}</button>
                        ${puedeEnviar ? `<button class="btn btn-primary" onclick="QuoteReviewPage.enviar()" ${aprobado && tramos.length ? '' : 'disabled'}>${I18N.t('oferta.enviar')}</button>` : ''}
                    </div>
                </div>

                ${!o.envio_habilitado ? `<div class="detail-panel oferta-aviso oferta-aviso--info">${I18N.t('oferta.envioApagado')}</div>` : ''}
                ${motivos ? `<div class="detail-panel oferta-aviso oferta-aviso--warn"><div class="detail-panel-title">${I18N.t('oferta.pendiente')}</div><ul>${motivos}</ul></div>` : ''}
                ${anterior ? `<div class="detail-panel oferta-aviso ${anterior.enviada ? 'oferta-aviso--ok' : 'oferta-aviso--info'}">
                    ${I18N.t(anterior.enviada ? 'oferta.yaEnviada' : 'oferta.yaGenerada')}
                    <b>${e(anterior.destinatario || '')}</b> · ${e((anterior.fecha || '').replace('T', ' ').slice(0, 16))}${anterior.por ? ' · ' + e(anterior.por) : ''}
                </div>` : ''}

                <div class="cards-grid">
                    ${tarjetas || `<div class="detail-panel" style="grid-column:1/-1;color:var(--text-muted)">${I18N.t('oferta.sinTramos')}</div>`}
                </div>

                <div class="cards-grid cards-grid--dos">
                    <div class="detail-panel">
                        <div class="detail-panel-title">${I18N.t('oferta.correo')}</div>
                        ${fila(I18N.t('oferta.para'), e(o.correo.destinatario || '—'))}
                        ${fila(I18N.t('oferta.asunto'), e(o.correo.asunto_original || '—'))}
                        ${fila(I18N.t('oferta.proyecto'), e(o.correo.nombre_proyecto || '—'))}
                        ${fila(I18N.t('oferta.plazo'), e(o.correo.lead_time))}
                        ${fila('Incoterm', e(o.correo.incoterm))}
                        ${fila(I18N.t('oferta.validez'), e(o.correo.validez_oferta))}
                        ${fila(I18N.t('oferta.terminos'), e(o.pdf.paymentTerms))}
                    </div>
                    <div class="detail-panel">
                        <div class="detail-panel-title">${I18N.t('oferta.laPieza')}</div>
                        ${fila('Part', e(linea.partNo || '—'))}
                        ${fila(I18N.t('oferta.descripcion'), e(linea.description || '—'))}
                        ${fila(I18N.t('oferta.material'), e(linea.material || '—'))}
                        ${fila('Wire Ø', e(linea.wireDia || '—'))}
                        ${fila(I18N.t('oferta.observaciones'), e(linea.remarks || '—').replace(/\n/g, '<br>'))}
                    </div>
                </div>
                <p style="color:var(--text-muted);font-size:12px">${I18N.t('oferta.nota')}</p>
            `;
        } catch (err) {
            if (err.sesionExpirada) return;
            container.innerHTML = `
                <div class="rfqd-cab">
                    ${volver}
                    <div class="rfqd-ident">
                        <h2 class="rfqd-id">${I18N.t('oferta.titulo')}: ${this.esc(id)}</h2>
                    </div>
                </div>
                <div class="detail-panel" style="color:var(--color-error);border-color:var(--color-error)">${this.esc(err.message)}</div>`;
        }
    },

    /** El PDF, en una pestaña nueva. La pestaña se abre ANTES de pedirlo:
     *  abrirla después de un await la bloquea el navegador como emergente. */
    async verPdf() {
        const pestana = window.open('', '_blank');
        try {
            const blob = await API.descargarOfertaPdf(this.currentRfqId);
            const url = URL.createObjectURL(blob);
            if (pestana) pestana.location = url; else window.open(url, '_blank');
            setTimeout(() => URL.revokeObjectURL(url), 60000);
        } catch (err) {
            if (pestana) pestana.close();
            if (err.sesionExpirada) return;
            Toast.error(err.message);
        }
    },

    async enviar() {
        if (!API.puede('rfq:dictaminar')) { Toast.error(I18N.t('aviso.sinPermisoRfq')); return; }
        const o = this.oferta || {};
        const c = o.correo || {};
        const valores = await Confirmar.montarFormulario({
            titulo: I18N.t('oferta.dlg.titulo'),
            mensaje: I18N.t(o.envio_habilitado ? 'oferta.dlg.mensaje' : 'oferta.dlg.mensajeApagado'),
            aceptar: I18N.t('oferta.enviar'),
            campos: [
                { id: 'destinatario', etiqueta: I18N.t('oferta.para'), tipo: 'email', valor: c.destinatario || '', requerido: true },
                { id: 'lead_time', etiqueta: I18N.t('oferta.plazo'), valor: c.lead_time || '' },
                { id: 'incoterm', etiqueta: 'Incoterm', valor: c.incoterm || '' },
                { id: 'validez_dias', etiqueta: I18N.t('oferta.validezDias'), tipo: 'number', valor: (o.pdf && o.pdf.validDays) || 30 },
                { id: 'comentarios', etiqueta: I18N.t('oferta.comentarios'), marcador: I18N.t('oferta.comentariosEj') },
            ],
        });
        if (!valores) return;

        const cuerpo = {
            destinatario: valores.destinatario,
            lead_time: valores.lead_time || null,
            incoterm: valores.incoterm || null,
            validez_dias: valores.validez_dias ? Number(valores.validez_dias) : null,
            comentarios: valores.comentarios || null,
            forzar: false,
        };

        // Si el costeo es orientativo, se pregunta a sabiendas antes de forzar.
        // Se mira el CÓDIGO y no el texto: buscar la palabra "orientativo" en
        // una frase sólo funcionaba mientras esa frase viniera en español.
        const orientativa = (o.motivos_i18n || []).some(m => m && m.codigo === 'OFERTA_ORIENTATIVA')
            || (o.motivos || []).some(m => /orientativo|indicative/i.test(m));
        if (!o.listo && orientativa) {
            const forzar = await Confirmar.pedir({
                titulo: I18N.t('oferta.dlg.forzarTitulo'),
                mensaje: I18N.t('oferta.dlg.forzarMensaje') + '\n\n' + this.motivos(o).join('\n'),
                aceptar: I18N.t('oferta.dlg.forzarSi'),
                peligro: true,
            });
            if (!forzar) return;
            cuerpo.forzar = true;
        }

        try {
            const r = await API.rfqEnviarOferta(this.currentRfqId, cuerpo);
            Toast.success(I18N.t(r.enviado ? 'oferta.aviso.enviada' : 'oferta.aviso.generada'));
            this.loadData(document.getElementById('page-quote-review'));
        } catch (err) {
            if (err.sesionExpirada) return;
            Toast.error(err.message);
        }
    },
};
