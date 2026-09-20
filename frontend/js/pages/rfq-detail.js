/**
 * La ficha de un RFQ: lo que se extrajo del correo y del plano, y el dictamen.
 *
 * Dos caras, un mismo DOM:
 *
 *   - Compu: la cabecera en una fila —volver, el identificador y el estado,
 *     y los botones a la derecha— y las dos tarjetas lado a lado.
 *   - Teléfono: la cabecera en tres renglones y los botones a todo el ancho,
 *     de 46 px. Antes era una sola fila flexible SIN salto: en 390 px medía
 *     565 y la página entera se iba de lado, así que el identificador quedaba
 *     debajo del botón de volver, el estado encima del título y "Approve
 *     Feasibility" fuera de la pantalla. Una ficha que se lee desde el correo,
 *     en el teléfono, no puede empezar con un desplazamiento horizontal.
 *
 * Todo lo que se pinta aquí viene de un correo de un cliente —el nombre, el
 * remitente, los motivos, las notas—, así que TODO pasa por `esc()`. Un asunto
 * con un `<img onerror=...>` no es un caso raro de laboratorio: es el primer
 * correo raro que llegue.
 */
const RFQDetailPage = {
    currentRfqId: null,

    /** Texto de un correo dentro de HTML: nunca tal cual. */
    esc(valor) {
        const nodo = document.createElement('span');
        nodo.textContent = valor == null ? '' : String(valor);
        return nodo.innerHTML;
    },

    async render(container, params) {
        this.currentRfqId = params.id;
        container.innerHTML = `<div class="loading-overlay"><div class="spinner"></div> ${
            this.esc(I18N.t('rev.cargando'))}</div>`;
        await this.loadData(container);
    },

    async loadData(container) {
        const esc = this.esc;
        try {
            const rfq = await API.getRFQ(this.currentRfqId);
            const r = rfq.resorte || {};
            const d = rfq.datos_json || {};

            // Los botones de dictamen sólo existen si el usuario puede dictaminar.
            const puedeDictaminar = API.puede('rfq:dictaminar');

            // Los motivos, uno por línea y alineados a la izquierda. Eran
            // "badges" —pastillas pensadas para una palabra— con frases
            // enteras dentro: en el teléfono cada motivo salía como una
            // píldora de tres renglones con el texto centrado.
            const banderas = (rfq.banderas || []).map(f => `
                <li class="rfqd-bandera rfqd-bandera--${f.nivel === 'ERROR' ? 'error' : 'aviso'}">
                    ${esc(f.titulo)}
                </li>`).join('');

            const fila = (clave, valor, extra = '') => `
                <div class="detail-row">
                    <span class="detail-key">${esc(clave)}</span>
                    <span class="detail-value${extra}">${esc(valor) || '—'}</span>
                </div>`;

            const mm = (v) => (v || v === 0) ? v + ' mm' : '';

            container.innerHTML = `
                <div class="rfqd-cab">
                    <button class="btn btn-secondary rfqd-volver"
                            onclick="APP.navigate('quoting')">&larr; Back</button>
                    <div class="rfqd-ident">
                        <h2 class="rfqd-id">${esc(rfq.rfq_id)}
                            <span class="rfqd-version">v${esc(rfq.version)}</span></h2>
                        <span class="badge ${RFQTable.badgeClass(rfq.estado)}"><span class="badge-dot"></span>${esc(rfq.estado)}</span>
                    </div>
                    <div class="rfqd-acciones">
                        <button class="btn btn-secondary" onclick="Revision.abrir('${esc(rfq.rfq_id)}')">${esc(I18N.t('rev.abrir'))}</button>
                        ${puedeDictaminar && rfq.estado !== 'Declined' ? `<button class="btn btn-danger" onclick="RFQDetailPage.decline()">Decline</button>` : ''}
                        ${puedeDictaminar && (rfq.estado === 'RequiresReview' || rfq.estado === 'New') ? `<button class="btn btn-success" onclick="RFQDetailPage.approve()">Approve Feasibility</button>` : ''}
                        ${rfq.estado === 'Approved' ? `<button class="btn btn-primary" onclick="APP.navigate('quote-review', {id: '${esc(rfq.rfq_id)}'})">Quote &rarr;</button>` : ''}
                    </div>
                </div>

                ${banderas ? `<div class="detail-panel rfqd-panel--aviso">
                    <div class="detail-panel-title">Review Flags</div>
                    <ul class="rfqd-banderas">${banderas}</ul>
                </div>` : ''}

                <div class="cards-grid cards-grid--dos">
                    <!-- Datos Comerciales -->
                    <div class="detail-panel">
                        <div class="detail-panel-title">Commercial Data</div>
                        ${fila('Customer', rfq.cliente_id || d.customer)}
                        ${fila('Part Number', rfq.part_number)}
                        ${fila('Volume (EAU)', rfq.volumen)}
                        ${fila('Required Material', rfq.material)}
                        ${fila('Sender', d.remitente, ' detail-value--correo')}
                    </div>

                    <!-- Datos del Resorte (Visión) -->
                    <div class="detail-panel">
                        <div class="detail-panel-title">Spring Physics (AI Extracted)</div>
                        ${this.porQueVacio(r, d.lectura_plano)}
                        ${fila('Type', r.tipo_resorte, ' detail-value--tipo')}
                        ${fila('Wire Diameter', mm(r.diametro_alambre_mm))}
                        ${fila('Outer Diameter', mm(r.diametro_exterior_mm))}
                        ${fila('Free Length', mm(r.longitud_libre_mm))}
                        ${fila('Total Coils', r.numero_espiras_totales)}
                        ${fila('AI Confidence', r.confianza ? (r.confianza * 100).toFixed(0) + '%' : '')}
                    </div>
                </div>

                ${rfq.notas ? `<div class="detail-panel">
                    <div class="detail-panel-title">PM Notes</div>
                    <p class="rfqd-notas">${esc(rfq.notas)}</p>
                </div>` : ''}
            `;
        } catch (err) {
            container.innerHTML = `<div class="detail-panel rfqd-error">Error: ${esc(err.message)}</div>`;
        }
    },

    /**
     * Por qué esta tarjeta está vacía.
     *
     * Estos valores no salen del correo: salen de LEER EL PLANO. Vacía, la
     * tarjeta enseñaba seis rayas y la pregunta que dejaba —"¿el correo no
     * traía dibujo, o traía uno y no se miró?"— sólo se podía contestar
     * abriendo el registro del servidor. La respuesta ya se guarda con el RFQ
     * (`lectura_plano`, en app/rfq/flow.py); aquí sólo se dice.
     *
     * Con cotas no se dice nada: los datos hablan solos.
     */
    porQueVacio(resorte, lectura) {
        const esc = this.esc;
        const hayAlgo = resorte && Object.keys(resorte).some(
            (k) => k !== 'tipo_resorte' && resorte[k] !== null && resorte[k] !== undefined && resorte[k] !== '');
        if (hayAlgo || !lectura || !lectura.estado) return '';

        const ficheros = (lectura.ficheros || []).join(', ');
        let texto = '';
        if (lectura.estado === 'sin_adjunto') {
            texto = I18N.t('plano.sinAdjunto');
        } else if (lectura.estado === 'formato_no_leido') {
            texto = I18N.t('plano.sinFormato', {
                ficheros, soportados: (lectura.soportados || []).join(', ') });
        } else if (lectura.estado === 'fallo') {
            texto = I18N.t('plano.fallo', { ficheros, motivo: lectura.motivo || '' });
        } else if (lectura.estado === 'leido') {
            texto = I18N.t('plano.leidoVacio', { ficheros });
        }
        if (!texto) return '';
        return `<p class="rfqd-sinplano">${esc(texto)}</p>`;
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
