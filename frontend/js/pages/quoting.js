/**
 * Cotización — dos herramientas, dos apartados.
 *
 * Antes esta pantalla era UNA calculadora a pantalla completa, y el Spring
 * Calculator vivía dentro de ella: un marco anidado que se abría como una
 * ventana flotante encima del formulario de precios. Se veía pequeño, con su
 * propia barra de título dentro de otra barra, y —lo peor— dos marcos de
 * profundidad lo dejaban fuera del alcance del tema de Pohua: la calculadora
 * de precios salía oscura y el resorte dentro de ella, blanco.
 *
 * Ahora son dos apartados hermanos, los dos hijos directos de Pohua:
 *
 *     Quote        la calculadora de precios (url_precio)
 *     Spring Calc  la calculadora de resortes (url_resortes)
 *
 * Los botones que los cambian son de Pohua, no de la calculadora: viven en
 * esta página, se pintan con los colores de Pohua y cambian de apartado sin
 * recargar nada. Cada marco conserva su estado mientras se va y se vuelve —se
 * esconden, no se destruyen—, que es lo que la gente espera al cambiar de
 * pestaña a media cotización.
 *
 * EL TRASPASO ENTRE LAS DOS sigue existiendo, y es lo único que había que
 * recablear. Antes se hablaban de padre a hijo; ahora son hermanas y no se
 * ven, así que Pohua hace de centralita:
 *
 *   precio  →  resortes   el plano leído (cotas, fabricabilidad, tipo de
 *                         resorte). Lo pide la propia calculadora al pulsar
 *                         su botón, o esta página al abrir el apartado.
 *   resortes →  precio    el peso por pieza y el dictamen. Al recibirlo se
 *                         vuelve solo a Quote: el peso se usa allí.
 *
 * La calculadora de precios no se tocó para esto: `js/isc-nube.js` intercepta
 * su `openSpringCalc` dentro del marco y lo convierte en un mensaje a Pohua.
 * Lo que aquí llega es ese mensaje, ya con la carga que ella misma construyó.
 */
const QuotingPage = {

    diagnostico: null,
    errorCarga: null,
    vista: 'precio',
    urlResortes: null,
    resortesListo: false,
    montado: false,           // ¿los marcos ya están puestos en el contenedor?
    pendiente: null,          // carga que espera a que el marco termine de cargar
    centralitaPuesta: false,
    rfqPendiente: null,       // RFQ que hay que abrir en cuanto la hoja esté lista
    consulta: false,          // se abre sólo para mirarlo: no toca el borrador
    rfqAbierto: null,         // el que ya se abrió, para no repetirlo
    hojaLista: false,

    // ---------------------------------------------------------------- pintar

    async render(contenedor, params) {
        /* Volver a Cotización NO vuelve a montar nada.
         *
         * Cada pantalla de Pohua se repinta al entrar, y para las demás está
         * bien: vuelven a pedir sus datos y se ven al día. Aquí dentro vive
         * una calculadora entera con una cotización a medio escribir, y
         * repintar significaba tirar los marcos y cargarla otra vez desde
         * cero: varios segundos de espera, el borrador recuperándose solo, y
         * el sitio por donde ibas perdido. Salir a mirar el Monitor y volver
         * costaba más que hacer el trabajo.
         *
         * Los marcos se quedan montados en su contenedor —que sigue en el
         * documento, sólo escondido— y al volver se enseña la pestaña que
         * estaba abierta. Nada que recargar. */
        const pedido = params && params.rfq;
        // `consulta` = se abre para MIRARLO, no para seguir trabajándolo. El
        // borrador de quien estuviera calculando se aparta y se devuelve al
        // salir (ver `isc-nube.js`), así que un caso cerrado nunca se mezcla
        // con un cálculo en curso.
        this.consulta = !!(params && params.consulta);

        if (this.montado && contenedor === this.contenedor &&
            contenedor.querySelector('#quotingMarcos')) {
            // Entrar sin RFQ es entrar a una hoja limpia: lo del RFQ que
            // estuviera abierto se guarda (ver `isc-nube.js`) y vuelve al
            // reabrir ese RFQ.
            if (!pedido && this.rfqAbierto) this.limpiarHoja();
            this.cambiar(pedido ? 'precio' : this.vista);
            this.pintarVolver();
            if (pedido) this.abrirRfq(pedido, this.consulta);
            return;
        }

        this.contenedor = contenedor;
        this.vista = 'precio';
        this.resortesListo = false;
        this.pendiente = null;
        this.montado = false;
        this.hojaLista = false;
        this.rfqAbierto = null;

        contenedor.innerHTML = `
            <div class="quoting">
                <div id="quotingAviso"></div>
                <div class="quoting-barra">
                    <nav class="quoting-tabs" role="tablist" id="quotingTabs" hidden>
                        <button type="button" class="quoting-tab active" data-vista="precio"
                                role="tab" aria-selected="true">
                            ${this.icono('precio')}<span>Quote</span>
                        </button>
                        <button type="button" class="quoting-tab" data-vista="resortes"
                                role="tab" aria-selected="false">
                            ${this.icono('resortes')}<span>Spring Calc</span>
                        </button>
                    </nav>
                    <!-- La vuelta a la ventana de revisión. Sólo sale cuando se
                         entró desde un RFQ: en una cotización a mano no hay
                         ningún sitio al que volver. -->
                    <button type="button" class="btn btn-secondary quoting-volver"
                            id="quotingVolver" hidden></button>
                </div>
                <div class="quoting-marcos" id="quotingMarcos">
                    <iframe class="quoting-marco" id="quotingMarco"
                            title="${this.esc(I18N.t('quoting.tab.precio'))}"
                            referrerpolicy="same-origin"></iframe>
                </div>
            </div>`;

        contenedor.querySelector('#quotingTabs').addEventListener('click', (ev) => {
            const b = ev.target.closest('[data-vista]');
            if (b) this.cambiar(b.dataset.vista);
        });

        contenedor.querySelector('#quotingVolver').addEventListener('click', () => {
            if (this.rfqAbierto) Revision.abrir(this.rfqAbierto);
        });

        this.centralita();
        this.seguirTema();
        contenedor.querySelector('#quotingMarco')
            .addEventListener('load', (ev) => this.vestir(ev.target));
        await this.cargar();
        await this.montar();
        // Montado de verdad sólo si el marco sobrevivió: cuando no hay
        // calculadora (o falta el permiso) `montar()` lo quita y deja el
        // aviso, y eso SÍ conviene volver a intentarlo al entrar de nuevo.
        this.montado = !!contenedor.querySelector('#quotingMarco');
        this.pintarVolver();
        if (pedido) this.abrirRfq(pedido);
    },

    /**
     * Abrir un RFQ en la hoja: se pide al servidor y se manda al marco.
     *
     * El momento importa. El `load` del marco llega mucho antes de que la
     * calculadora exista de verdad —es un documento grande que se arma solo—,
     * así que un mensaje mandado ahí se pierde sin ruido. Se espera a que
     * `isc-nube.js` avise con "hoja-lista"; si ya avisó, se manda en el acto.
     */
    async abrirRfq(id, consulta) {
        if (!id || this.rfqAbierto === id) return;
        if (consulta !== undefined) this.consulta = !!consulta;
        try {
            const datos = await API.rfqCotizacionInicial(id);
            if (datos && datos.error) {
                Toast.warning(I18N.t('quoting.rfqParcial', { motivo: datos.error }));
            }
            this.rfqAbierto = id;
            this.pintarVolver();
            datos.ficheros = await this.bajarPlanos(id, datos.planos);
            this.rfqPendiente = datos;
            this.entregarRfq();
        } catch (err) {
            if (err && err.sesionExpirada) return;
            Toast.error(I18N.t('quoting.rfqFallo', { motivo: err.message }));
        }
    },

    /**
     * Los planos del correo, bajados aquí y no dentro del marco.
     *
     * La calculadora vive en un marco que no tiene la sesión de Pohua —su
     * `fetch` no lleva el token—, así que los ficheros los baja esta página,
     * que sí la tiene, y se los pasa ya hechos `File` por `postMessage`. El
     * clon estructurado mueve ficheros sin convertirlos a texto.
     *
     * Si uno falla no se cancela nada: la hoja abre igual y el plano se sube
     * a mano, que es lo que se hacía antes con todos.
     */
    async bajarPlanos(id, lista) {
        const fuera = [];
        for (const p of (lista || [])) {
            try {
                const blob = await API.descargarPlano(id, p.nombre);
                fuera.push(new File([blob], p.nombre,
                                    { type: blob.type || 'application/octet-stream' }));
            } catch (err) {
                if (err && err.sesionExpirada) return fuera;
                console.warn('No se pudo bajar el plano ' + p.nombre + ': ' + err.message);
            }
        }
        return fuera;
    },

    /**
     * El botón de volver a la ventana de revisión.
     *
     * "Abrir cotización completa" es un viaje de ida: se sale de la ventana
     * donde se dictamina y se entra en la hoja. Para aprobar, devolver o
     * rechazar hay que volver, y hasta ahora el camino de vuelta era
     * acordarse del RFQ y buscarlo en la lista.
     *
     * La ventana se vuelve a pedir al servidor al abrirse, así que si el
     * costeo cambió mientras tanto, lo que se ve al volver es lo nuevo.
     */
    pintarVolver() {
        const b = this.contenedor && this.contenedor.querySelector('#quotingVolver');
        if (!b) return;
        if (!this.rfqAbierto) { b.hidden = true; return; }
        b.textContent = I18N.t('quoting.volverRevision', { rfq: this.rfqAbierto });
        b.hidden = false;
        this.pintarConsulta();
    },

    /**
     * La cinta de "esto es un caso cerrado, sólo lo estás mirando".
     *
     * Sin ella, un RFQ dictaminado abierto en la hoja se ve EXACTAMENTE igual
     * que uno en curso: mismas casillas, mismos números, mismo botón de
     * recalcular. Alguien podría ponerse a trabajar encima de una cotización
     * que ya se aprobó hace tres semanas sin darse cuenta de nada.
     *
     * Dice además que el borrador está a salvo, porque si no lo dijera la
     * reacción sensata sería salir corriendo a guardar lo que estuviera
     * haciendo.
     */
    pintarConsulta() {
        const caja = this.contenedor && this.contenedor.querySelector('#quotingAviso');
        if (!caja) return;
        if (!this.consulta || !this.rfqAbierto) {
            const vieja = caja.querySelector('.quoting-consulta');
            if (vieja) vieja.remove();
            return;
        }
        if (caja.querySelector('.quoting-consulta')) return;
        const cinta = document.createElement('div');
        cinta.className = 'quoting-consulta';
        cinta.innerHTML = `
            <span class="quoting-consulta-texto"></span>
            <button type="button" class="btn btn-secondary btn-sm"
                    id="quotingSalirConsulta"></button>`;
        cinta.querySelector('.quoting-consulta-texto').textContent =
            I18N.t('quoting.consulta', { rfq: this.rfqAbierto });
        const boton = cinta.querySelector('#quotingSalirConsulta');
        boton.textContent = I18N.t('quoting.volverCalculo');
        boton.addEventListener('click', () => this.salirConsulta());
        caja.appendChild(cinta);
    },

    /** Deja la calculadora en blanco: se sale del RFQ que hubiera abierto. */
    limpiarHoja() {
        this.postAlMarco({ source: 'pohua', tipo: 'limpiar' });
        this.consulta = false;
        this.rfqAbierto = null;
        this.rfqPendiente = null;
        this.pintarVolver();
        this.pintarConsulta();
    },

    postAlMarco(mensaje) {
        const marco = this.contenedor && this.contenedor.querySelector('#quotingMarco');
        try {
            if (marco && marco.contentWindow) marco.contentWindow.postMessage(mensaje, '*');
        } catch (_) { /* sin marco no hay hoja que limpiar */ }
    },

    /**
     * Un RFQ dictaminado —aprobado o declinado— ya no tiene nada que seguir
     * escribiendo: su borrador se olvida y, si es el que está abierto, la hoja
     * queda limpia.
     */
    olvidarRfq(ids) {
        const lista = (Array.isArray(ids) ? ids : [ids]).filter(Boolean);
        if (!lista.length) return;
        if (this.rfqAbierto && !this.consulta && lista.includes(this.rfqAbierto)) {
            this.rfqAbierto = null;
            this.pintarVolver();
        }
        this.postAlMarco({ source: 'pohua', tipo: 'olvidar-rfqs', ids: lista });
    },

    /**
     * La hoja dice de qué RFQ guarda borrador; se olvidan los que ya se
     * dictaminaron, aunque fuera en otra computadora. Uno que ya no existe
     * (404) también: no hay adónde volver.
     */
    async revisarGuardados(ids) {
        const cerrados = [];
        for (const id of (ids || []).slice(0, 50)) {
            try {
                const r = await API.getRFQ(id);
                if (r && ['Approved', 'Declined'].includes(r.estado)) cerrados.push(id);
            } catch (err) {
                if (err && err.sesionExpirada) return;
                if (err && err.status === 404) cerrados.push(id);
            }
        }
        this.olvidarRfq(cerrados);
    },

    /** Devuelve el borrador de trabajo y sale de la consulta. */
    salirConsulta() {
        const marco = this.contenedor && this.contenedor.querySelector('#quotingMarco');
        try {
            if (marco && marco.contentWindow) {
                marco.contentWindow.postMessage(
                    { source: 'pohua', tipo: 'salir-consulta' }, '*');
            }
        } catch (_) { /* si el marco no está, el borrador sigue guardado */ }
        this.consulta = false;
        this.rfqAbierto = null;
        this.pintarVolver();
        this.pintarConsulta();
    },

    entregarRfq() {
        if (!this.hojaLista || !this.rfqPendiente) return;
        const marco = this.contenedor && this.contenedor.querySelector('#quotingMarco');
        if (!marco || !marco.contentWindow) return;
        try {
            marco.contentWindow.postMessage(
                { source: 'pohua', tipo: 'cargar-rfq', datos: this.rfqPendiente,
                  consulta: !!this.consulta }, '*');
            this.rfqPendiente = null;
        } catch (_) { /* el marco aún no está: se reintenta al próximo aviso */ }
    },

    icono(cual) {
        return cual === 'precio'
            ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="2" width="16" height="20" rx="2"/><line x1="8" y1="6" x2="16" y2="6"/><line x1="8" y1="11" x2="8" y2="11"/><line x1="12" y1="11" x2="12" y2="11"/><line x1="16" y1="11" x2="16" y2="11"/><line x1="8" y1="16" x2="8" y2="16"/><line x1="12" y1="16" x2="12" y2="16"/><line x1="16" y1="16" x2="16" y2="16"/></svg>`
            : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 5h14M5 9h14M5 13h14M5 17h14" opacity=".35"/><path d="M6 6c4-2 8 2 12 0M6 11c4-2 8 2 12 0M6 16c4-2 8 2 12 0"/></svg>`;
    },

    async cargar() {
        try {
            this.diagnostico = await API.quotingDiagnostico();
            this.errorCarga = null;
        } catch (err) {
            if (err && err.sesionExpirada) throw err;
            this.diagnostico = null;
            this.errorCarga = err.message;
        }
    },

    // ---------------------------------------------------------------- montar

    /**
     * La cookie del lector.
     *
     * El iframe pide su página como una navegación normal y no lleva la
     * cabecera Authorization, así que sin esto contestaría 401 y se vería un
     * marco con un error en vez de la calculadora.
     */
    puerta() {
        if (!this._puerta) {
            this._puerta = API.abrirSesionLector().catch((err) => {
                this._puerta = null;      // que el siguiente intento reintente
                throw err;
            });
        }
        return this._puerta;
    },

    async montar() {
        const marco = this.contenedor.querySelector('#quotingMarco');
        if (!marco) return;

        const calc = this.diagnostico && this.diagnostico.piezas.calculadoras;
        if (!calc || !calc.ok) {
            // Sin calculadora no se enseña un marco vacío: parecería una
            // avería. Se dice qué falta, que es información. Y si lo que
            // falta es el PERMISO (el diagnóstico contestó 403), se dice eso:
            // antes salía el aviso del HTML del núcleo, que no tenía que ver.
            marco.remove();
            const caja = this.contenedor.querySelector('#quotingAviso');
            const sinPermiso = !API.puede('precio:calcular');
            if (caja) caja.innerHTML += `
                <div class="quoting-pendiente">
                    <p>${this.esc(I18N.t(sinPermiso ? 'quoting.sinPermiso' : 'quoting.pendiente.precio'))}</p>
                </div>`;
            return;
        }

        try {
            await this.puerta();
        } catch (err) {
            if (err && err.sesionExpirada) return;
            marco.outerHTML = this.aviso('mal', I18N.t('quoting.sinPuerta'), err.message);
            return;
        }
        marco.src = calc.url_precio;
        this.urlResortes = calc.url_resortes || null;

        // Las pestañas sólo aparecen cuando hay las dos calculadoras: una sola
        // pestaña no es una elección, es un adorno.
        const tabs = this.contenedor.querySelector('#quotingTabs');
        if (tabs && this.urlResortes) tabs.hidden = false;
    },

    // ------------------------------------------------------------- apartados

    /** El marco de resortes, creado la primera vez que se pide. */
    marcoResortes(url) {
        let marco = this.contenedor && this.contenedor.querySelector('#quotingResortes');
        const destino = url || this.urlResortes;
        if (!destino) return null;
        if (!marco) {
            marco = document.createElement('iframe');
            marco.className = 'quoting-marco';
            marco.id = 'quotingResortes';
            marco.title = I18N.t('quoting.tab.resortes');
            marco.referrerPolicy = 'same-origin';
            marco.hidden = true;
            marco.addEventListener('load', () => {
                this.resortesListo = true;
                this.vestir(marco);
                if (this.pendiente) {
                    const carga = this.pendiente;
                    this.pendiente = null;
                    // Un respiro: la calculadora de resortes engancha sus
                    // escuchadores al arrancar, no al terminar de cargar.
                    setTimeout(() => this.enviarA(marco, carga), 400);
                }
            });
            this.contenedor.querySelector('#quotingMarcos').appendChild(marco);
        }
        if (marco.dataset.url !== destino) {
            this.resortesListo = false;
            marco.dataset.url = destino;
            marco.src = destino;
        }
        return marco;
    },

    cambiar(vista) {
        if (vista === this.vista) return;
        if (vista === 'resortes' && !this.urlResortes) return;
        this.vista = vista;

        const precio = this.contenedor.querySelector('#quotingMarco');
        const resortes = vista === 'resortes' ? this.marcoResortes() :
                         this.contenedor.querySelector('#quotingResortes');
        if (precio) precio.hidden = vista !== 'precio';
        if (resortes) resortes.hidden = vista !== 'resortes';

        this.contenedor.querySelectorAll('.quoting-tab').forEach((b) => {
            const suya = b.dataset.vista === vista;
            b.classList.toggle('active', suya);
            b.setAttribute('aria-selected', suya ? 'true' : 'false');
        });

        // Al abrir resortes se le pide a la calculadora de precios lo que haya
        // leído del plano: es la misma entrega que hacía su botón, y así el
        // resorte no empieza en blanco cuando ya hay una cotización abierta.
        if (vista === 'resortes' && precio && precio.contentWindow) {
            try {
                precio.contentWindow.postMessage({ source: 'pohua', tipo: 'pedir-resorte' }, '*');
            } catch (_) { /* todavía no ha cargado: no pasa nada */ }
        }
    },

    // ------------------------------------------------------------ centralita

    /**
     * El puente entre las dos calculadoras, ahora que son hermanas.
     *
     * Sólo se escucha a los marcos de esta página (`ev.source`), y sólo los
     * dos tipos de mensaje del traspaso. Lo que llegue de cualquier otro sitio
     * se ignora sin mirarlo.
     */
    centralita() {
        if (this.centralitaPuesta) return;
        this.centralitaPuesta = true;

        // Aprobado o declinado desde cualquier pantalla (ver `api.js`).
        window.addEventListener('pohua:rfq-dictaminado', (ev) => {
            this.olvidarRfq(ev.detail && ev.detail.rfq);
        });

        window.addEventListener('message', (ev) => {
            const d = ev.data || {};
            const precio = this.contenedor && this.contenedor.querySelector('#quotingMarco');
            const resortes = this.contenedor && this.contenedor.querySelector('#quotingResortes');
            const dePrecio = precio && ev.source === precio.contentWindow;
            const deResortes = resortes && ev.source === resortes.contentWindow;

            // Un aviso de dentro del marco, dicho por Pohua. En el teléfono
            // el aviso de la calculadora se queda al final del documento —no
            // se persigue nada por el scroll, que era lo que parpadeaba—, así
            // que su texto sube aquí y se enseña donde se ven los demás.
            // La calculadora terminó de arrancar: ya se le puede mandar el RFQ.
            if (dePrecio && d.source === 'isc-nube' && d.tipo === 'hoja-lista') {
                this.hojaLista = true;
                this.entregarRfq();
                return;
            }

            if (dePrecio && d.source === 'isc-nube' && d.tipo === 'rfqs-guardados') {
                this.revisarGuardados(d.ids);
                return;
            }

            if ((dePrecio || deResortes) && d.source === 'isc-nube' && d.tipo === 'aviso') {
                if (d.texto) Toast.info(String(d.texto).slice(0, 300));
                return;
            }

            // La calculadora de precios pide abrir el apartado de resortes
            // (su botón "Spring Calc", o el aviso de después de leer un plano).
            if (dePrecio && d.source === 'isc-nube') {
                if (d.tipo === 'abrir-resortes') {
                    this.marcoResortes(this.resolver(d.url));
                    this.cambiar('resortes');
                } else if (d.tipo === 'a-resortes') {
                    const marco = this.marcoResortes(this.resolver(d.url));
                    if (!marco) return;
                    if (this.resortesListo) this.enviarA(marco, d.carga);
                    else this.pendiente = d.carga;
                }
                return;
            }

            // El resorte manda su peso y su dictamen: van a la cotización.
            //
            // Y se vuelve a Quote SÓLO si lo mandó una persona con el botón
            // "Usar el peso en la cotización". La calculadora de resortes
            // también lo manda ella sola cada vez que recalcula
            // (`automatico:true`), y con eso el apartado se cerraba en cuanto
            // el resorte terminaba de dimensionarse: no daba tiempo ni a
            // verlo. Lo automático llega a la cotización igual, calladito.
            if (deResortes && d.source === 'spring-calculator') {
                if (precio && precio.contentWindow) {
                    try { precio.contentWindow.postMessage(d, '*'); } catch (_) {}
                }
                if (d.type === 'springWeight' && !d.automatico) this.cambiar('precio');
            }
        });
    },

    /** La dirección que pidió la calculadora, resuelta contra la del lector. */
    resolver(url) {
        if (!url) return this.urlResortes;
        try { return new URL(url, new URL(this.urlResortes, location.href)).href; }
        catch (_) { return this.urlResortes; }
    },

    enviarA(marco, carga) {
        if (!marco || !marco.contentWindow || !carga) return;
        try { marco.contentWindow.postMessage(carga, '*'); } catch (_) {}
    },

    /**
     * El tema y el idioma, empujados al marco.
     *
     * `isc-tema.js` los lee solo subiendo por los marcos, y con esto además se
     * los damos hechos en cuanto carga: un marco que aún no había pintado
     * cuando se cambió el interruptor se quedaba con el tema anterior.
     */
    vestir(marco) {
        this.reforzar(marco);
        try {
            const v = marco.contentWindow;
            if (!v) return;
            if (v.ISCTema && v.ISCTema.aplicar) v.ISCTema.aplicar();
            v.postMessage({ source: 'pohua', tipo: 'tema' }, '*');
        } catch (_) { /* otro origen: se queda con lo que él mismo deduzca */ }
    },

    /**
     * Las capas de Pohua dentro de la calculadora, pase lo que pase.
     *
     * Quien las mete normalmente es el servidor: `api/lector.py` añade los
     * <script> al vuelo cuando sirve el HTML de la calculadora. Eso funciona
     * mientras el servidor y el navegador vayan a la par, y deja de funcionar
     * justo cuando más se nota: si el despliegue lleva el JavaScript nuevo
     * pero un `lector.py` anterior, la calculadora se sirve SIN la capa y por
     * fuera todo parece correcto —el archivo está, se descarga si lo pides—
     * pero dentro del marco no corre nadie. Lo que se ve entonces es que el
     * botón Aprobar no abre nada, sin un solo error en la consola.
     *
     * Así que Pohua lo comprueba por su cuenta: mira el documento del marco
     * —mismo origen, se puede— y añade la que falte. Si el servidor ya las
     * puso, no hace nada: se reconocen por su propio <script src>.
     */
    reforzar(marco) {
        // `isc-nube.js` va en la lista aunque sea la más vieja: es la que mide
        // el marco y lo pone a pantalla cuando se abre una capa. Sin ella, la
        // ventana de aprobación se dibuja dentro de un marco de 320 px y se ve
        // recortada, que es peor que no verla.
        const CAPAS = ['isc-tema.js', 'isc-nube.js', 'isc-idioma.js', 'isc-contrato.js',
                       'isc-visor3d.js', 'isc-aprobacion.js', 'isc-selects.js'];
        try {
            const doc = marco.contentDocument;
            if (!doc || !doc.head || !doc.getElementById) return;
            // Sólo en la calculadora: si el marco acabó enseñando otra cosa
            // (la propia Pohua, un error del servidor), no se le añade nada.
            if (!doc.querySelector('#botbar, .sheet, #app')) return;
            CAPAS.forEach((nombre) => {
                if (doc.querySelector(`script[src*="${nombre}"]`)) return;
                const s = doc.createElement('script');
                s.src = this.dondeViven(nombre);
                s.defer = true;
                doc.head.appendChild(s);
                console.info('Pohua añadió al marco la capa que faltaba:', nombre);
            });
        } catch (_) { /* otro origen: el servidor es el único que puede */ }
    },

    /**
     * El interruptor de tema de Pohua, empujado a los dos marcos.
     *
     * Cada calculadora ya vigila el `data-tema` de Pohua por su cuenta
     * (js/isc-tema.js), pero un marco que cargó a destiempo podía perderse el
     * cambio y quedarse en claro dentro de Pohua oscuro. Esto lo repasa desde
     * este lado, que es el que sabe con certeza cuándo cambió.
     */
    seguirTema() {
        if (this._temaPuesto) return;
        this._temaPuesto = true;
        new MutationObserver(() => {
            if (!this.contenedor) return;
            this.contenedor.querySelectorAll('iframe').forEach((m) => this.vestir(m));
        }).observe(document.documentElement,
                   { attributes: true, attributeFilter: ['data-tema'] });
    },

    /**
     * Dónde vive un archivo de la capa, preguntándoselo a la propia página.
     *
     * Escribir "/js/isc-tema.js" a mano parece inofensivo y es justo la clase
     * de cosa que se rompe cuando la aplicación se sirve bajo otra ruta. Se
     * deduce del <script> de esta misma página, que el navegador ya resolvió.
     */
    dondeViven(nombre) {
        const mio = document.querySelector('script[src*="pages/quoting.js"]') ||
                    document.querySelector('script[src*="app.js"]');
        try { return new URL('../' + nombre, mio.src).href; }
        catch (_) { return '/js/' + nombre; }
    },

    /** Al cambiar de página no queda nada corriendo, pero sí que repasar temas. */
    /* El router llama a esto al salir de la pantalla. No se desmonta nada: los
       marcos se quedan vivos y escondidos para poder volver a ellos tal y como
       se dejaron. Se sueltan solos cuando se cierra la sesión, que es cuando
       Pohua vacía las vistas. */
    detener() { /* los marcos siguen montados a propósito */ },

    /** Al cerrar sesión no puede quedarse la cotización de nadie en memoria. */
    limpiar() {
        this.montado = false;
        this.contenedor = null;
        this.diagnostico = null;
        this._puerta = null;
    },

    // ------------------------------------------------------------- utilidades

    aviso(tono, titulo, texto) {
        return `
            <div class="quoting-cabecera ${tono}">
                <strong>${this.esc(titulo)}</strong>
                ${texto ? `<p>${this.esc(texto)}</p>` : ''}
            </div>`;
    },

    /** Nada de lo que llega del servidor entra en innerHTML sin pasar por aquí. */
    esc(valor) {
        const nodo = document.createElement('span');
        nodo.textContent = valor == null ? '' : String(valor);
        return nodo.innerHTML;
    },
};
