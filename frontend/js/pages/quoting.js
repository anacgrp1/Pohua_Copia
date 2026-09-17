/**
 * Cotización — la calculadora, y nada más.
 *
 * Aquí había una fila de pestañas —Conexiones, Calculadora de precios,
 * Ingeniería de resortes, Lector de planos— y sobraba: las tres herramientas
 * ya son una sola ventana dentro de la calculadora. El Spring Calculator se
 * abre con su botón y los planos se leen desde el propio formulario, que es
 * como se usa en la planta. Repetir esa navegación por fuera obligaba a
 * elegir dos veces lo mismo.
 *
 * Así que la pantalla es la calculadora a pantalla completa.
 *
 * El diagnóstico de las piezas ya no se pinta aquí. Sirvió para montar todo
 * esto, pero en una pantalla de producción era una tira permanente que nadie
 * va a leer dos veces, y avisaba de cosas que la propia calculadora ya dice
 * donde importan: su píldora del parser enseña si el lector está en vivo o en
 * demo, justo al lado del botón que lee el plano.
 *
 * Sigue estando entero en `GET /api/quoting/diagnostico` para cuando algo no
 * cuadre; lo que se quitó es que ocupe sitio cuando todo va bien.
 *
 * Lo único que sí se enseña es cuando NO hay calculadora que montar: ahí un
 * marco vacío parecería una avería, y hay que decir qué falta.
 */
const QuotingPage = {

    diagnostico: null,
    errorCarga: null,

    // ---------------------------------------------------------------- pintar

    async render(contenedor) {
        this.contenedor = contenedor;
        contenedor.innerHTML = `
            <div class="quoting">
                <div id="quotingAviso"></div>
                <iframe class="quoting-marco" id="quotingMarco"
                        title="${this.esc(I18N.t('quoting.tab.precio'))}"
                        referrerpolicy="same-origin"></iframe>
            </div>`;

        await this.cargar();
        await this.montar();
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
