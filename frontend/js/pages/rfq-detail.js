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

    /*
     * «Volver» lleva al Resumen, que es donde están las listas de RFQ
     * («Esperan dictamen», «RFQ ya dictaminadas»). Quien no puede ver el
     * Resumen vuelve a Cotización, que era el destino de antes.
     */
    volver() {
        APP.navigate(API.puede('resumen:ver') ? 'resumen' : 'quoting');
    },

    /** Texto de un correo dentro de HTML: nunca tal cual. */
    esc(valor) {
        const nodo = document.createElement('span');
        nodo.textContent = valor == null ? '' : String(valor);
        return nodo.innerHTML;
    },

    async render(container, params) {
        this.currentRfqId = params.id;
        // Se guarda para poder repintar sin volver a navegar (releerPlano).
        this.contenedor = container;
        container.innerHTML = `<div class="loading-overlay"><div class="spinner"></div> ${
            this.esc(I18N.t('rev.cargando'))}</div>`;
        await this.loadData(container);
    },

    async loadData(container) {
        const esc = this.esc;
        try {
            const rfq = await API.getRFQ(this.currentRfqId);
            // Lo usan los accesos rápidos de la barra de abajo (assistant.js).
            this.rfqActual = rfq;
            const r = rfq.resorte || {};
            const d = rfq.datos_json || {};

            // Los botones de dictamen sólo existen si el usuario puede dictaminar.
            const puedeDictaminar = API.puede('rfq:dictaminar');

            // «Esperando al cliente»: le faltan datos y se le pidieron. No hay
            // nada completo que revisar, así que no se ofrece la ventana de
            // revisión; se dice qué falta y que se le pidió al comprador.
            const esperando = rfq.estado === 'Incomplete';
            const faltan = (d.campos_faltantes || [])
                .map((c) => { const k = 'campo.' + c; const t = I18N.t(k); return t === k ? c : t; });
            const avisoEspera = esperando ? `<div class="detail-panel rfqd-panel--espera">
                    <div class="detail-panel-title">${esc(I18N.t('ficha.esperaTitulo'))}</div>
                    <p class="rfqd-espera-texto">${esc(I18N.t('ficha.esperaTexto'))}</p>
                    ${faltan.length ? `<p class="rfqd-espera-falta">${esc(I18N.t('ficha.esperaFalta', { campos: faltan.join(', ') }))}</p>` : ''}
                </div>` : '';

            // Los motivos, uno por línea y alineados a la izquierda. Eran
            // "badges" —pastillas pensadas para una palabra— con frases
            // enteras dentro: en el teléfono cada motivo salía como una
            // píldora de tres renglones con el texto centrado.
            //
            // Primero lo que dice el Spring Engineering Calculator: es el
            // mismo cálculo de la pestaña Spring Calc, corrido en el servidor
            // con estas cotas. Si la planta no puede enrollar el resorte, eso
            // va arriba y en rojo, porque es lo único que cierra la discusión.
            const sc = rfq.spring_calc;
            const noFactible = SpringCalc.bloquea(sc);
            // Ya cotizado a mano por el PM: se avisa, pero no en rojo.
            const conPm = !!SpringCalc.intervencion(sc);
            const deSpring = SpringCalc.items(sc).map(f => `
                <li class="rfqd-bandera rfqd-bandera--${f.nivel === 'error' ? 'error' : 'aviso'}">
                    ${esc(f.texto)}
                </li>`).join('');
            const banderas = deSpring + (rfq.banderas || []).map(f => `
                <li class="rfqd-bandera rfqd-bandera--${f.nivel === 'ERROR' ? 'error' : 'aviso'}">
                    ${esc(I18N.motivo('factib.', f))}
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
                            onclick="RFQDetailPage.volver()">&larr; ${esc(I18N.t('oferta.volver'))}</button>
                    <div class="rfqd-ident">
                        <h2 class="rfqd-id">${esc(rfq.rfq_id)}
                            <span class="rfqd-version">v${esc(rfq.version)}</span></h2>
                        <span class="badge ${RFQTable.badgeClass(rfq.estado)}"><span class="badge-dot"></span>${esc(I18N.estado(rfq.estado))}</span>
                    </div>
                    <div class="rfqd-acciones">
                        ${esperando ? '' : `<button class="btn btn-secondary" onclick="Revision.abrir('${esc(rfq.rfq_id)}')">${esc(I18N.t('rev.abrir'))}</button>`}
                        <!-- Aprobar y rechazar se deciden en la ventana de revisión,
                             con los números delante; aquí sólo se entra a ella. -->
                        ${rfq.estado === 'Approved' ? (() => {
                            // Aprobado y sin oferta: el botón lo dice y abre directo el
                            // envío. Si ya salió (o está en la bandeja de salida), sólo
                            // se entra a ver la oferta.
                            const of = d.oferta || {};
                            const falta = !of.enviada && !of.encolada;
                            // Mientras la oferta no haya salido, una aprobación hecha
                            // sin querer se puede deshacer: el cliente no ha recibido nada.
                            const deshacer = falta && puedeDictaminar
                                ? `<button class="btn btn-secondary" onclick="RFQDetailPage.deshacerAprobacion()">${esc(I18N.t('ficha.deshacerAprobacion'))}</button>` : '';
                            return `${deshacer}<button class="btn btn-primary" onclick="APP.navigate('quote-review', ${falta
                                ? `{id: '${esc(rfq.rfq_id)}', enviar: '1'}` : `{id: '${esc(rfq.rfq_id)}'}`})">${esc(I18N.t(falta ? 'ficha.enviarOferta' : 'ficha.cotizar'))}</button>`;
                        })() : ''}
                    </div>
                </div>

                ${avisoEspera}

                ${banderas ? `<div class="detail-panel rfqd-panel--aviso${noFactible ? ' rfqd-panel--nofactible' : ''}">
                    <div class="detail-panel-title">${esc(I18N.t('ficha.banderas'))}${noFactible
                        ? ` <span class="rfqd-nofactible">${esc(I18N.t('spring.noFactibleCorto'))}</span>`
                        : conPm ? ` <span class="rfqd-nofactible rfqd-nofactible--pm">${esc(I18N.t('spring.cotizadoAMano'))}</span>` : ''}</div>
                    <ul class="rfqd-banderas">${banderas}</ul>
                </div>` : ''}

                <div class="cards-grid cards-grid--dos">
                    <!-- Datos Comerciales -->
                    <div class="detail-panel">
                        <div class="detail-panel-title">${esc(I18N.t('ficha.comercial'))}</div>
                        ${fila(I18N.t('ficha.cliente'), rfq.cliente_id || d.customer)}
                        ${fila(I18N.t('ficha.parte'), rfq.part_number)}
                        ${fila(I18N.t('ficha.volumen'), rfq.volumen)}
                        ${fila(I18N.t('ficha.material'), rfq.material)}
                        ${fila(I18N.t('ficha.remitente'), d.remitente, ' detail-value--correo')}
                    </div>

                    <!-- Datos del Resorte (Visión) -->
                    <div class="detail-panel">
                        <div class="detail-panel-title">${esc(I18N.t('ficha.fisica'))}</div>
                        ${this.porQueVacio(r, d.lectura_plano)}
                        ${(d.lectura_plano && d.lectura_plano.estado && d.lectura_plano.estado !== 'sin_adjunto'
                            && typeof PlanoCliente !== 'undefined')
                            ? `<p class="rfqd-plano">${PlanoCliente.boton(rfq.rfq_id, 'btn btn-secondary btn-sm')}</p>` : ''}
                        ${this.botonReleer(r, puedeDictaminar)}
                        ${fila(I18N.t('ficha.tipo'), I18N.tipoResorte(r.tipo_resorte), ' detail-value--tipo')}
                        ${fila(I18N.t('ficha.alambre'), mm(r.diametro_alambre_mm))}
                        ${fila(I18N.t('ficha.exterior'), mm(r.diametro_exterior_mm))}
                        ${fila(I18N.t('ficha.libre'), mm(r.longitud_libre_mm))}
                        ${fila(I18N.t('ficha.espiras'), r.numero_espiras_totales)}
                        ${fila(I18N.t('ficha.confianza'), r.confianza ? (r.confianza * 100).toFixed(0) + '%' : '')}
                    </div>
                </div>

                ${rfq.notas ? `<div class="detail-panel">
                    <div class="detail-panel-title">${esc(I18N.t('ficha.notasPm'))}</div>
                    <p class="rfqd-notas">${esc(rfq.notas)}</p>
                </div>` : ''}
            `;
        } catch (err) {
            container.innerHTML = `<div class="detail-panel rfqd-error">${esc(err.message)}</div>`;
        }
    },

    /**
     * El porqué de un fallo, en una línea que se pueda leer.
     *
     * Lo que llega es la excepción tal cual, y cuando falla el modelo eso es
     * un volcado JSON entero —"Error code: 400 - {'type': 'error', 'error':
     * {'type': 'invalid_request_error', 'message': …"— que llenaba la tarjeta
     * de ruido sin decir más que la primera frase. El volcado completo sigue
     * en el registro del servidor, que es donde se va a buscar de verdad.
     */
    motivoCorto(motivo) {
        let texto = String(motivo || '').trim();
        if (!texto) return '';
        // Lo que va antes del volcado: "… failed: Error code: 400" y basta.
        const corte = texto.search(/\s*[-–]\s*[{[]/);
        if (corte > 20) texto = texto.slice(0, corte);
        return texto.length > 160 ? texto.slice(0, 157) + '…' : texto;
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
            texto = I18N.t('plano.fallo', { ficheros, motivo: this.motivoCorto(lectura.motivo) });
        } else if (lectura.estado === 'leido') {
            texto = I18N.t('plano.leidoVacio', { ficheros });
        }
        if (!texto) return '';
        return `<p class="rfqd-sinplano">${esc(texto)}</p>`;
    },

    /**
     * El botón de volver a leer el plano con la IA.
     *
     * Sólo aparece cuando hace falta: si ya hay diámetro de alambre, el plano
     * se leyó y no hay nada que repetir. Y sólo para quien dictamina, porque
     * cada pulsación gasta una llamada al modelo.
     */
    botonReleer(resorte, puedeDictaminar) {
        const esc = this.esc;
        if (!puedeDictaminar) return '';
        const d = resorte ? resorte.diametro_alambre_mm : null;
        if (d || d === 0) return '';
        return `<p class="rfqd-releer">
            <button class="btn btn-secondary btn-sm" id="btnReleerPlano"
                    onclick="RFQDetailPage.releerPlano()">${esc(I18N.t('plano.releer'))}</button>
        </p>`;
    },

    /**
     * Manda releer el plano guardado y repinta la ficha con lo que salga.
     *
     * No vuelve a pedir el fichero a nadie: el sistema ya lo tiene desde que
     * entró el correo. Lo que cambia es que ahora se lee con la API de visión
     * otra vez, con el lector ya arreglado.
     */
    async releerPlano() {
        if (!API.puede('rfq:dictaminar')) {
            Toast.error(I18N.t('aviso.sinPermisoRfq'));
            return;
        }
        const boton = document.getElementById('btnReleerPlano');
        const antes = boton ? boton.textContent : '';
        if (boton) { boton.disabled = true; boton.textContent = I18N.t('plano.releyendo'); }
        try {
            const r = await API.releerPlano(this.currentRfqId);
            const ficheros = (r.ficheros || []).join(', ');
            if (r.estado === 'leido') {
                const hayCotas = r.resorte && r.resorte.diametro_alambre_mm;
                if (hayCotas) Toast.success(I18N.t('plano.releido', { ficheros }));
                else Toast.error(I18N.t('plano.sinCotas'));
                if (this.contenedor) await this.loadData(this.contenedor);
                return;
            }
            if (r.estado === 'sin_adjunto') Toast.error(I18N.t('plano.sinAdjunto'));
            else if (r.estado === 'formato_no_leido') {
                Toast.error(I18N.t('plano.sinFormato', {
                    ficheros, soportados: (r.soportados || []).join(', ') }));
            } else {
                Toast.error(I18N.t('plano.fallo', {
                    ficheros, motivo: this.motivoCorto(r.motivo) }));
            }
        } catch (err) {
            Toast.error(err.message);
        } finally {
            if (boton) { boton.disabled = false; boton.textContent = antes; }
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
            firme: true,        // sólo con un clic de verdad (ver confirmar.js)
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

    /** Una aprobación hecha sin querer: vuelve a revisión (sin tocar al cliente). */
    async deshacerAprobacion() {
        if (!API.puede('rfq:dictaminar')) { Toast.error(I18N.t('aviso.sinPermisoRfq')); return; }
        const nota = await Confirmar.pedirTexto({
            titulo: I18N.t('dlg.deshacer.titulo'),
            mensaje: I18N.t('dlg.deshacer.mensaje'),
            etiqueta: I18N.t('dlg.deshacer.motivo'),
            marcador: I18N.t('dlg.deshacer.ejemplo'),
            obligatorio: true,
            aceptar: I18N.t('dlg.deshacer.si'),
        });
        if (typeof nota !== 'string') return;
        try {
            await API.rfqDeshacerAprobacion(this.currentRfqId, nota);
            Toast.success(I18N.t('aviso.aprobacionDeshecha'));
            APP.navigate('rfq-detail', { id: this.currentRfqId });
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
