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
    pendiente: null,          // carga que espera a que el marco termine de cargar
    centralitaPuesta: false,

    // ---------------------------------------------------------------- pintar

    async render(contenedor) {
        this.contenedor = contenedor;
        this.vista = 'precio';
        this.resortesListo = false;
        this.pendiente = null;

        contenedor.innerHTML = `
            <div class="quoting">
                <div id="quotingAviso"></div>
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

        this.centralita();
        this.seguirTema();
        contenedor.querySelector('#quotingMarco')
            .addEventListener('load', (ev) => this.vestir(ev.target));
        await this.cargar();
        await this.montar();
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

        window.addEventListener('message', (ev) => {
            const d = ev.data || {};
            const precio = this.contenedor && this.contenedor.querySelector('#quotingMarco');
            const resortes = this.contenedor && this.contenedor.querySelector('#quotingResortes');
            const dePrecio = precio && ev.source === precio.contentWindow;
            const deResortes = resortes && ev.source === resortes.contentWindow;

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
    detener() { /* los marcos se van con el contenedor */ },

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
