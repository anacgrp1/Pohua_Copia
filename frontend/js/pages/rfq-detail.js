/**
 * RFQ Detail Page
 */
const RFQDetailPage = {
    currentRfqId: null,

    async render(container, params) {
        this.currentRfqId = params.id;
        container.innerHTML = `<div class="loading-overlay"><div class="spinner"></div> Loading details…</div>`;
        await this.loadData(container);
    },

    async loadData(container) {
        try {
            const rfq = await API.getRFQ(this.currentRfqId);
            const r = rfq.resorte || {};
            const d = rfq.datos_json || {};

            // Los botones de dictamen sólo existen si el usuario puede dictaminar.
            const puedeDictaminar = API.puede('rfq:dictaminar');

            let flagsHtml = rfq.banderas.map(f => 
                `<div class="badge badge-${f.nivel === 'ERROR' ? 'declined' : 'review'}" style="margin-right:8px;margin-bottom:8px">
                    <span class="badge-dot"></span>${f.titulo}
                 </div>`
            ).join('');

            container.innerHTML = `
                <div style="display:flex;gap:16px;margin-bottom:20px;align-items:center">
                    <button class="btn btn-secondary" onclick="APP.navigate('quoting')">&larr; Back</button>
                    <h2 style="margin:0">${rfq.rfq_id} <span style="font-weight:400;color:var(--text-muted);font-size:16px">v${rfq.version}</span></h2>
                    <span class="badge ${RFQTable.badgeClass(rfq.estado)}"><span class="badge-dot"></span>${rfq.estado}</span>
                    <div style="margin-left:auto;display:flex;gap:8px;flex-wrap:wrap">
                        <button class="btn btn-secondary" onclick="Revision.abrir('${rfq.rfq_id}')">${I18N.t('rev.abrir')}</button>
                        ${puedeDictaminar && rfq.estado !== 'Declined' ? `<button class="btn btn-danger" onclick="RFQDetailPage.decline()">Decline</button>` : ''}
                        ${puedeDictaminar && (rfq.estado === 'RequiresReview' || rfq.estado === 'New') ? `<button class="btn btn-success" onclick="RFQDetailPage.approve()">Approve Feasibility</button>` : ''}
                        ${rfq.estado === 'Approved' ? `<button class="btn btn-primary" onclick="APP.navigate('quote-review', {id: '${rfq.rfq_id}'})">Quote &rarr;</button>` : ''}
                    </div>
                </div>

                ${flagsHtml ? `<div class="detail-panel" style="border-color:var(--color-warning);background:rgba(245,158,11,0.05)"><div class="detail-panel-title" style="color:var(--color-warning)">Review Flags</div>${flagsHtml}</div>` : ''}

                <div class="cards-grid cards-grid--dos">
                    <!-- Datos Comerciales -->
                    <div class="detail-panel">
                        <div class="detail-panel-title">Commercial Data</div>
                        <div class="detail-row"><span class="detail-key">Customer</span><span class="detail-value">${rfq.cliente_id || d.customer || '—'}</span></div>
                        <div class="detail-row"><span class="detail-key">Part Number</span><span class="detail-value">${rfq.part_number || '—'}</span></div>
                        <div class="detail-row"><span class="detail-key">Volume (EAU)</span><span class="detail-value">${rfq.volumen || '—'}</span></div>
                        <div class="detail-row"><span class="detail-key">Required Material</span><span class="detail-value">${rfq.material || '—'}</span></div>
                        <div class="detail-row"><span class="detail-key">Sender</span><span class="detail-value" style="word-break:break-all">${d.remitente || '—'}</span></div>
                    </div>

                    <!-- Datos del Resorte (Visión) -->
                    <div class="detail-panel">
                        <div class="detail-panel-title">Spring Physics (AI Extracted)</div>
                        <div class="detail-row"><span class="detail-key">Type</span><span class="detail-value" style="text-transform:capitalize">${r.tipo_resorte || '—'}</span></div>
                        <div class="detail-row"><span class="detail-key">Wire Diameter</span><span class="detail-value">${r.diametro_alambre_mm ? r.diametro_alambre_mm + ' mm' : '—'}</span></div>
                        <div class="detail-row"><span class="detail-key">Outer Diameter</span><span class="detail-value">${r.diametro_exterior_mm ? r.diametro_exterior_mm + ' mm' : '—'}</span></div>
                        <div class="detail-row"><span class="detail-key">Free Length</span><span class="detail-value">${r.longitud_libre_mm ? r.longitud_libre_mm + ' mm' : '—'}</span></div>
                        <div class="detail-row"><span class="detail-key">Total Coils</span><span class="detail-value">${r.numero_espiras_totales || '—'}</span></div>
                        <div class="detail-row"><span class="detail-key">AI Confidence</span><span class="detail-value">${r.confianza ? (r.confianza * 100).toFixed(0) + '%' : '—'}</span></div>
                    </div>
                </div>

                ${rfq.notas ? `<div class="detail-panel"><div class="detail-panel-title">PM Notes</div><p style="white-space:pre-wrap">${rfq.notas}</p></div>` : ''}
            `;
        } catch (err) {
            container.innerHTML = `<div class="detail-panel" style="color:var(--color-error)">Error: ${err.message}</div>`;
        }
    },

    async approve() {
        if (!API.puede('rfq:dictaminar')) {
            Toast.error(I18N.t('aviso.sinPermisoRfq'));
            return;
        }
        const aprobar = await Confirmar.pedir({
            titulo: I18N.t('dlg.aprobar.titulo'),
            mensaje: I18N.t('dlg.aprobar.mensaje'),
            aceptar: I18N.t('dlg.aprobar.si'),
        });
        if (!aprobar) return;

        try {
            await API.approveRFQ(this.currentRfqId, {});
            Toast.success(I18N.t('aviso.rfqAprobada'));
            APP.navigate('quote-review', { id: this.currentRfqId });
        } catch (err) {
            if (err.sesionExpirada) return;
            Toast.error(err.message);
        }
    },

    async decline() {
        if (!API.puede('rfq:dictaminar')) {
            Toast.error(I18N.t('aviso.sinPermisoRfq'));
            return;
        }
        const nota = await Confirmar.pedirTexto({
            titulo: I18N.t('dlg.rechazar.titulo'),
            mensaje: I18N.t('dlg.rechazar.mensaje'),
            etiqueta: I18N.t('dlg.rechazar.motivo'),
            marcador: I18N.t('dlg.rechazar.ejemplo'),
            obligatorio: true,
            aceptar: I18N.t('dlg.rechazar.si'),
            peligro: true,
        });
        if (nota === null) return;   // cancelado

        try {
            await API.declineRFQ(this.currentRfqId, { nota: nota, enviar_correo: true });
            Toast.success(I18N.t('aviso.rfqRechazada'));
            this.loadData(document.getElementById('page-rfq-detail'));
        } catch (err) {
            if (err.sesionExpirada) return;
            Toast.error(err.message);
        }
    }
};
