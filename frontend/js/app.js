/**
 * CGR Cotizador — Lógica principal (router SPA y estado global)
 */

const APP = {
    pages: {
        'mail': DashboardPage,
        'quoting': QuotingPage,
        'rfq-detail': RFQDetailPage,
        'quote-review': QuoteReviewPage,
        'resumen': ResumenPage,
        'monitor': MonitorPage,
        'perfil': PerfilPage
    },

    currentPage: null,
    arrancada: false,     // ¿ya se conectaron los eventos de la SPA?
    statusTimer: null,    // temporizador del sondeo de estado

    async init() {
        // Registrar el service worker (PWA)
        // El service worker sirve el CSS y el JS desde la caché ANTES de ir a la
        // red. Eso es lo que se quiere en producción (la PWA abre al instante y
        // funciona sin conexión) y es justo lo que no se quiere trabajando en
        // local: guardas un archivo, refrescas, y sigues viendo el de antes.
        //
        // Así que en localhost no se registra, y si quedó registrado de una vez
        // anterior se da de baja y se borran sus cachés. Sin esto hay que ir a
        // las herramientas del navegador a desregistrarlo a mano.
        const enLocal = ['localhost', '127.0.0.1', '::1'].includes(location.hostname);

        if ('serviceWorker' in navigator) {
            if (enLocal) {
                try {
                    const registros = await navigator.serviceWorker.getRegistrations();
                    for (const registro of registros) await registro.unregister();
                    if (window.caches) {
                        const nombres = await caches.keys();
                        await Promise.all(nombres.map((n) => caches.delete(n)));
                    }
                    if (registros.length) {
                        console.log('Service Worker dado de baja (entorno local).');
                    }
                } catch (err) {
                    console.warn('No se pudo dar de baja el Service Worker:', err);
                }
            } else {
                try {
                    const registro = await navigator.serviceWorker.register('/sw.js');
                    // Comprobación explícita de actualización: el navegador ya
                    // la hace al navegar, pero esta aplicación se queda abierta
                    // horas en la misma pestaña. Sin esto, quien no recarga se
                    // queda con el service worker del despliegue anterior.
                    registro.update().catch(() => {});
                    console.log('Service Worker registrado');
                } catch (err) {
                    console.error('Falló el registro del Service Worker:', err);
                }
            }
        }

        // Init componentes
        Toast.init();
        Assistant.init();
        PerfilMenu.init();
        this.medirEsquina();

        // Al cambiar de idioma se repinta lo que está en pantalla: el título,
        // el estado del servicio y la página actual, que se genera desde JS y
        // no lleva marcas data-i18n.
        I18N.alCambiar(() => {
            // La portada y el login se traducen solos: llevan data-i18n y de
            // ellos ya se encargó I18N.aplicar(). Y no se vuelven a montar a
            // propósito — montarlos otra vez reiniciaría la animación del
            // resorte y borraría lo que hubiera escrito en el formulario.
            if (!this.arrancada || document.querySelector('.app-layout')?.hidden) return;

            this.pintarTitulo();
            this.updateStatus();
            Assistant.init({ rehacer: true });
            PerfilMenu.refrescar();
            if (this.currentPage) this.handleRoute();
        });

        // Si el token caduca o el backend responde 401, volvemos al login
        // sin recargar la página.
        window.addEventListener('sesion-expirada', () => this.sesionExpirada());

        // Sin sesión válida se entra por la pantalla de inicio, y de ahí al
        // login. Con sesión expirada se va derecho al login: quien ya estaba
        // dentro no tiene por qué volver a pasar por la portada.
        if (!(await this.verificarSesion())) {
            this.mostrarHome();
            return;
        }

        this.arrancar();
    },

    // ----------------------------------------------------------------------
    // Sesión
    // ----------------------------------------------------------------------

    /** Comprueba que hay token y que sigue siendo válido contra /api/auth/me. */
    async verificarSesion() {
        if (!API.getToken()) return false;
        try {
            await API.getMe();
            return true;
        } catch (err) {
            console.warn('Sesión no válida:', err.message);
            API.limpiarSesion();
            return false;
        }
    },

    /** Portada: logos, resorte animado y el botón que lleva al login. */
    mostrarHome() {
        const layout = document.querySelector('.app-layout');
        const home = document.getElementById('homeScreen');
        const login = document.getElementById('loginScreen');

        if (layout) layout.hidden = true;
        if (login) login.hidden = true;
        const toggle = document.getElementById('mobileToggle');
        if (toggle) toggle.hidden = true;
        const menu = document.getElementById('perfilMenu');
        if (menu) menu.hidden = true;
        // La campana tampoco pinta nada aquí: sin sesión no hay RFQs que avisar.
        const campana = document.getElementById('notificaciones');
        if (campana) campana.hidden = true;

        if (!home) {
            // Sin la portada en el HTML, se pasa directo al login en vez de
            // dejar la pantalla en blanco.
            this.mostrarLogin();
            return;
        }

        home.hidden = false;
        HomePage.render(home, { onLogin: () => this.mostrarLogin() });
    },

    ocultarHome() {
        const home = document.getElementById('homeScreen');
        if (home) {
            home.hidden = true;
            home.innerHTML = '';
        }
        // La animación del resorte se para al salir: nadie la está viendo.
        if (typeof HomePage !== 'undefined') HomePage.detener();
    },

    mostrarLogin(mensaje = '') {
        const layout = document.querySelector('.app-layout');
        const pantalla = document.getElementById('loginScreen');
        this.ocultarHome();
        if (layout) layout.hidden = true;
        if (document.getElementById('mobileToggle')) {
            document.getElementById('mobileToggle').hidden = true;
        }
        const menuPerfil = document.getElementById('perfilMenu');
        if (menuPerfil) menuPerfil.hidden = true;
        const campana = document.getElementById('notificaciones');
        if (campana) campana.hidden = true;
        if (!pantalla) {
            console.error('No se encontró el contenedor de login.');
            return;
        }
        pantalla.hidden = false;

        LoginPage.render(pantalla, {
            onExito: () => this.sesionIniciada()
        });
        if (mensaje) LoginPage.mostrarError(mensaje);
    },

    ocultarLogin() {
        const layout = document.querySelector('.app-layout');
        const pantalla = document.getElementById('loginScreen');
        this.ocultarHome();
        if (pantalla) {
            pantalla.hidden = true;
            pantalla.innerHTML = '';
        }
        if (layout) layout.hidden = false;
        const toggle = document.getElementById('mobileToggle');
        if (toggle) toggle.hidden = false;
    },

    /** Se ejecuta cuando el login termina bien. */
    sesionIniciada() {
        this.ocultarLogin();
        if (this.arrancada) {
            // La SPA ya estaba montada: sólo refrescamos usuario, permisos y vista.
            this.pintarUsuario();
            this.aplicarPermisos();
            this.updateStatus();
            this.iniciarSondeo();
            this.handleRoute();
            this.exigirPasswordPropia();
        } else {
            this.arrancar();
        }
    },

    /**
     * Quien entra con la contraseña temporal que le puso quien administra
     * pone la suya antes de nada (js/components/password.js). Se espera un
     * instante a que la vista esté montada: el diálogo se abre encima de la
     * aplicación, no encima del login.
     */
    exigirPasswordPropia() {
        const yo = API.getUsuario();
        if (!yo || !yo.debe_cambiar_password || typeof Password === 'undefined') return;
        setTimeout(() => Password.pedirCambioInicial(), 300);
    },

    /** Reacciona a un 401: limpia la sesión y regresa al login. */
    sesionExpirada() {
        const pantalla = document.getElementById('loginScreen');
        if (pantalla && !pantalla.hidden) return; // ya estamos en el login

        this.detenerSondeo();
        if (typeof Notificaciones !== 'undefined') Notificaciones.limpiar();
        if (typeof Revision !== 'undefined') Revision.cerrar();
        API.limpiarSesion();
        Toast.warning(I18N.t('aviso.sesionExpirada'));
        this.mostrarLogin(I18N.t('aviso.sesionExpirada'));
    },

    async cerrarSesion() {
        const salir = await Confirmar.pedir({
            titulo: I18N.t('dlg.salir.titulo'),
            mensaje: I18N.t('dlg.salir.mensaje'),
            aceptar: I18N.t('dlg.salir.titulo'),
        });
        if (!salir) return;

        this.detenerSondeo();
        const actual = this.pages[this.currentPage];
        if (actual && typeof actual.detener === 'function') actual.detener();
        Assistant.limpiar();
        PerfilMenu.limpiar();
        if (typeof Password !== 'undefined') Password.quitarAviso();
        Notificaciones.limpiar();
        Revision.cerrar();
        if (typeof Push !== 'undefined') Push.limpiar();
        API.logout();
        // Salida a mano: se vuelve a la portada. La sesión expirada sí va
        // directa al login, porque ahí hay un mensaje que leer.
        this.mostrarHome();
        // El aviso va DESPUÉS de montar la portada: los avisos viven fuera de
        // la pantalla que se reemplaza, así que sobreviven al cambio.
        Toast.success(I18N.t('aviso.sesionCerrada'));
    },

    /** El logo de la barra lateral lleva a la pantalla principal de la app.
     *
     * "Principal" es la misma que al entrar: el primer apartado del menú de esa
     * persona (`inicio()`). Antes era Mail a secas, y para el pm eso significaba
     * que el logo lo sacaba de su pantalla de mando.
     *
     * Ojo: NO lleva a la portada de antes del login. Estando dentro, salir a
     * esa pantalla parecería que se cerró la sesión; desde el login, el logo sí
     * vuelve a la portada.
     */
    conectarLogo() {
        const logo = document.getElementById('logoSidebar');
        if (!logo || logo.dataset.conectado) return;
        logo.dataset.conectado = '1';
        logo.addEventListener('click', () => this.navigate(this.inicio()));
    },

    /** Muestra nombre, correo y rol del usuario en la barra lateral. */
    /**
     * Publica el ancho de la barra de la esquina en --hueco-esquina.
     *
     * La cabecera reserva ese hueco para que el título no quede debajo de los
     * botones. No vale una constante: el ancho cambia con el nombre del
     * usuario, con el idioma y con el tamaño de pantalla, así que se mide.
     */
    medirEsquina() {
        const barra = document.querySelector('.barra-esquina');
        if (!barra) return;
        const publicar = () => {
            const ancho = barra.offsetWidth;
            document.documentElement.style.setProperty(
                '--hueco-esquina', `calc(${ancho}px + var(--sp-8))`);
        };
        publicar();
        if (window.ResizeObserver) {
            new ResizeObserver(publicar).observe(barra);
        } else {
            window.addEventListener('resize', publicar, { passive: true });
        }
    },

    /** Refresca la ficha del usuario, que vive en el menú de arriba. */
    pintarUsuario() {
        const usuario = API.getUsuario();
        const menu = document.getElementById('perfilMenu');
        // El menú sólo tiene sentido con sesión: en la portada y el login no
        // hay nada que enseñar.
        if (menu) menu.hidden = !usuario;
        if (usuario && typeof PerfilMenu !== 'undefined') PerfilMenu.refrescar();
        if (usuario && typeof Notificaciones !== 'undefined') Notificaciones.init();
    },

    /**
     * Oculta los controles marcados con data-permiso cuando el usuario
     * no tiene ese permiso (por ejemplo arrancar o detener el worker).
     */
    aplicarPermisos(raiz = document) {
        raiz.querySelectorAll('[data-permiso]').forEach(el => {
            el.hidden = !API.puede(el.dataset.permiso);
        });

        // El orden del menú de admin (Monitor arriba, Resumen abajo) es una
        // clase en la barra: el resto lo hace el CSS con `order`.
        const nav = document.querySelector('.sidebar-nav');
        if (nav) nav.classList.toggle('sidebar-nav--admin', API.puede('monitor:ver'));
    },

    iniciarSondeo() {
        this.detenerSondeo();
        this.statusTimer = setInterval(() => this.updateStatus(), 10000);
    },

    detenerSondeo() {
        if (this.statusTimer) {
            clearInterval(this.statusTimer);
            this.statusTimer = null;
        }
    },

    // ----------------------------------------------------------------------
    // Arranque de la SPA (sólo con sesión válida)
    // ----------------------------------------------------------------------
    arrancar() {
        this.ocultarLogin();
        this.pintarUsuario();
        this.aplicarPermisos();
        this.conectarLogo();
        this.exigirPasswordPropia();

        if (this.arrancada) {
            this.updateStatus();
            this.iniciarSondeo();
            this.handleRoute();
            return;
        }
        this.arrancada = true;

        // Routing
        window.addEventListener('popstate', () => this.handleRoute());

        // Navegación lateral
        document.querySelectorAll('.sidebar-nav .nav-item').forEach(el => {
            el.addEventListener('click', (e) => {
                const page = e.currentTarget.dataset.page;
                if (page) this.navigate(page);
            });
        });

        // Menú móvil
        // --- Menú lateral en móvil ---------------------------------------
        // Antes el botón sólo ABRÍA: para cerrar había que acertar en el velo
        // de fondo. Ahora es un interruptor de verdad, con su estado anunciado
        // (aria-expanded) y las tres salidas que espera cualquiera: el propio
        // botón, el velo y la tecla Escape.
        const toggle = document.getElementById('mobileToggle');
        if (toggle) toggle.onclick = () => this.alternarMenu();

        const overlay = document.getElementById('mobileOverlay');
        if (overlay) overlay.onclick = () => this.cerrarMenu();

        document.addEventListener('keydown', (ev) => {
            if (ev.key === 'Escape') this.cerrarMenu();
        });

        // Botón de salir
        // Salir y llegar al perfil se hacen desde el menú de arriba a la
        // derecha (js/components/perfil-menu.js).
        PerfilMenu.init();

        // La campana de la esquina. Va aquí y no en el arranque general porque
        // necesita sesión y permisos: en la portada no hay nada que avisar.
        Notificaciones.init();

        // La ventana de revisión del PM. Se abre desde la campana, desde la
        // cola del Resumen y desde cualquier enlace con #/rfq/<id>.
        Revision.init();
        // Los avisos en el teléfono: registra este dispositivo si ya lo estaba.
        if (typeof Push !== 'undefined') Push.init();

        // Controles del servicio.
        //
        // Ya no viven en la cabecera: los dibuja la página de Mail, así que se
        // crean y se destruyen al navegar. Por eso se escuchan por delegación
        // desde el documento en vez de asignar onclick a un elemento concreto:
        // con onclick, volver a Mail dejaría los botones nuevos sin conectar.
        document.addEventListener('click', (ev) => {
            if (ev.target.closest('#btnRunCycle')) this.correrCiclo();
            if (ev.target.closest('#btnToggleWorker')) this.alternarServicio();
        });

        // Sondeo de estado
        this.updateStatus();
        this.iniciarSondeo();

        // Ruta inicial
        this.handleRoute();
    },

    navigate(page, params = {}) {
        const search = new URLSearchParams(params).toString();
        const url = `/${page}${search ? '?' + search : ''}`;
        window.history.pushState({ page, params }, '', url);
        this.handleRoute();
    },

    /**
     * La pantalla a la que se llega al entrar, y a la que se cae si la URL no
     * nombra ninguna página válida.
     *
     * NO es fija: es EL PRIMER APARTADO DEL MENÚ que esa persona puede ver, que
     * es lo mismo que ve arriba del todo en la barra lateral. Así no hay dos
     * sitios que decidan "dónde empieza uno" y se contradigan.
     *
     *     admin   → Monitor   (arriba del todo para él; el Resumen se le va
     *                          al final de la lista)
     *     pm      → Resumen   (la pantalla de mando: cómo va todo)
     *     quoter  → Mail      (no tiene ninguna de las dos)
     *
     * Ojo: esto NO fuerza la pantalla de inicio siempre. Si la URL ya nombra
     * una página se respeta, que es lo que hace falta cuando alguien abre un
     * enlace directo a un RFQ y de camino le caduca la sesión: tras entrar
     * vuelve a su RFQ, no al principio.
     */
    inicio() {
        if (API.puede('monitor:ver')) return 'monitor';
        if (API.puede('resumen:ver')) return 'resumen';
        return 'mail';
    },

    async handleRoute() {
        // Leer la URL
        const path = window.location.pathname.replace(/^\/+/, '');
        const page = path.split('/')[0] || this.inicio();
        const params = Object.fromEntries(new URLSearchParams(window.location.search));

        if (!this.pages[page]) {
            console.error('Página no encontrada:', page);
            this.navigate(this.inicio());
            return;
        }

        // Páginas con permiso propio. Ocultar el botón del menú no basta: la
        // dirección se puede teclear. El servidor rechaza igualmente la
        // petición, pero llegar a una pantalla que sólo puede dar error es una
        // forma fea de enterarse.
        const PERMISO_DE = { 'monitor': 'monitor:ver', 'resumen': 'resumen:ver' };
        const permiso = PERMISO_DE[page];
        if (permiso && !API.puede(permiso)) {
            Toast.warning(I18N.t('aviso.sinPermiso'));
            this.navigate(this.inicio());
            return;
        }

        // Barra lateral
        document.querySelectorAll('.sidebar-nav .nav-item').forEach(el => {
            el.classList.toggle('active', el.dataset.page === page);
        });

        // Cerrar el menú móvil al navegar
        this.cerrarMenu();

        // Parar lo que la página anterior tuviera en marcha. Sin esto, salir de
        // Monitor deja su sondeo de logs corriendo para siempre, y volver a
        // entrar arranca un segundo: dos peticiones por tick, luego tres…
        const anterior = this.pages[this.currentPage];
        if (anterior && typeof anterior.detener === 'function') anterior.detener();

        // Ocultar todas las vistas y mostrar la activa
        document.querySelectorAll('.page-view').forEach(el => el.classList.remove('active'));
        const viewContainer = document.getElementById(`page-${page}`);
        if (!viewContainer) {
            console.error('No existe el contenedor de la vista:', `page-${page}`);
            return;
        }
        viewContainer.classList.add('active');

        // Títulos
        // El título se guarda en el propio nodo para poder repintarlo al
        // cambiar de idioma sin volver a navegar.
        const claves = {
            'mail': 'mail', 'quoting': 'quoting', 'rfq-detail': 'rfqDetalle',
            'resumen': 'resumen',
            'quote-review': 'cotizacion', 'monitor': 'monitor', 'perfil': 'perfil',
        };
        this.claveTitulo = claves[page] || null;
        this.pintarTitulo();

        this.currentPage = page;
        // Qué página está en pantalla, para el CSS que depende de ella (en el
        // teléfono, la burbuja del asistente se esconde en Quoting).
        document.body.dataset.pagina = page;

        // Renderizar la página
        try {
            await this.pages[page].render(viewContainer, params);
            // Los controles que dibuja la página también respetan los permisos.
            this.aplicarPermisos(viewContainer);
        } catch (err) {
            if (err && err.sesionExpirada) return;
            console.error('Error al renderizar la página:', err);
            Toast.error(I18N.t('aviso.paginaFallo'));
        }
    },

    /** ¿Está desplegado el menú lateral? */
    menuAbierto() {
        return document.getElementById('sidebar')?.classList.contains('open') === true;
    },

    abrirMenu() {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('mobileOverlay');
        const toggle = document.getElementById('mobileToggle');
        if (!sidebar) return;

        sidebar.classList.add('open');
        overlay?.classList.add('active');
        toggle?.setAttribute('aria-expanded', 'true');
        // Sin esto, al desplazarse con el menú abierto se mueve la página de
        // debajo y el menú parece despegarse.
        document.body.classList.add('menu-abierto');

        // El foco entra en el menú: si no, el tabulador sigue recorriendo la
        // página de detrás, que está tapada.
        sidebar.querySelector('.nav-item')?.focus({ preventScroll: true });
    },

    cerrarMenu() {
        const sidebar = document.getElementById('sidebar');
        if (!sidebar || !sidebar.classList.contains('open')) return;

        sidebar.classList.remove('open');
        document.getElementById('mobileOverlay')?.classList.remove('active');
        const toggle = document.getElementById('mobileToggle');
        toggle?.setAttribute('aria-expanded', 'false');
        document.body.classList.remove('menu-abierto');
        // El foco vuelve al botón: si se queda dentro de un menú oculto, el
        // lector de pantalla se pierde.
        toggle?.focus({ preventScroll: true });
    },

    alternarMenu() {
        if (this.menuAbierto()) this.cerrarMenu();
        else this.abrirMenu();
    },

    claveTitulo: null,

    /** Pinta el título de la página en el idioma actual. */
    pintarTitulo() {
        const t = document.getElementById('pageTitle');
        const sub = document.getElementById('pageSubtitle');
        if (!t || !sub) return;
        if (!this.claveTitulo) { t.textContent = 'Pohua'; sub.textContent = ''; return; }
        t.textContent = I18N.t(`pagina.${this.claveTitulo}.titulo`);
        sub.textContent = I18N.t(`pagina.${this.claveTitulo}.sub`);
    },

    async correrCiclo() {
        try {
            Toast.info(I18N.t('aviso.cicloEnMarcha'));
            const res = await API.runPipeline();
            Toast.success(I18N.t('aviso.cicloHecho', {
                correos: res.messages_found, procesados: res.new_processed, errores: res.errors }));
            this.updateStatus();
            if (this.currentPage === 'mail') this.pages['mail'].render(
                document.getElementById('page-mail'));
        } catch (err) {
            if (err.sesionExpirada) return;
            Toast.error(I18N.t('aviso.cicloFallo', { motivo: err.message }));
        }
    },

    async alternarServicio() {
        const btn = document.getElementById('btnToggleWorker');
        // El estado se lee de un atributo, NO del texto del botón: con el texto,
        // traducir la interfaz o cambiar la etiqueta invertiría la acción.
        const corriendo = btn?.dataset.corriendo === '1';
        try {
            if (corriendo) {
                await API.stopWorker();
                Toast.success(I18N.t('aviso.servicioDetenido'));
            } else {
                await API.startWorker();
                Toast.success(I18N.t('aviso.servicioArrancado'));
            }
            this.updateStatus();
        } catch (err) {
            if (err.sesionExpirada) return;
            Toast.error(err.message);
        }
    },

    async updateStatus() {
        // Sin sesión no se pregunta nada. Esta comprobación es la que impide
        // que tocar el selector de idioma en la portada eche al login: pedir el
        // estado sin token da 401, el 401 dispara 'sesion-expirada' y eso monta
        // la pantalla de acceso encima de la portada.
        if (!API.getToken()) return;
        try {
            const status = await API.getStatus();
            const dot = document.getElementById('workerDot');
            const lbl = document.getElementById('workerLabel');
            // El botón sólo existe estando en Mail: fuera de ahí no hay nada
            // que actualizar y no es un error.
            const btn = document.getElementById('btnToggleWorker');

            if (status.running) {
                if (dot) dot.className = 'status-dot running';
                if (lbl) lbl.textContent = I18N.t('barra.servicioCorriendo', { n: status.interval_minutes });
                if (btn) {
                    btn.dataset.corriendo = '1';
                    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg> ${I18N.t('boton.detener')}`;
                    btn.className = 'btn btn-secondary';
                }
            } else {
                if (dot) dot.className = 'status-dot';
                if (lbl) lbl.textContent = I18N.t('barra.servicioParado');
                if (btn) {
                    btn.dataset.corriendo = '0';
                    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/></svg> ${I18N.t('boton.arrancar')}`;
                    btn.className = 'btn btn-primary';
                }
            }
        } catch (err) {
            if (err.sesionExpirada) return;
            console.warn('No se pudo obtener el estado:', err.message);
        }
    }
};

// Arrancar la app cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', () => APP.init());
