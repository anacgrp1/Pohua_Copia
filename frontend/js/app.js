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
        // El aviso de cookies sale en el primer contacto, antes de entrar.
        if (typeof Legal !== 'undefined') Legal.banner();

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
                    // Una recarga sola cuando entra un despliegue nuevo.
                    //
                    // El service worker se instala y toma el mando enseguida
                    // (skipWaiting + clients.claim en sw.js), pero la pestaña
                    // que ya estaba abierta sigue ejecutando el JavaScript que
                    // cargó al principio. Ahí es donde aparecía el peor fallo:
                    // media aplicación del despliegue nuevo y media del viejo,
                    // y un método que la mitad vieja no tenía cortando en seco
                    // lo que estuvieras haciendo.
                    //
                    // `controllerchange` avisa justo cuando el nuevo toma el
                    // mando. Se recarga UNA vez —el pestillo evita el bucle— y
                    // la pestaña queda entera en la versión nueva sin que nadie
                    // tenga que vaciar cachés a mano.
                    let recargando = false;
                    navigator.serviceWorker.addEventListener('controllerchange', () => {
                        if (recargando) return;
                        recargando = true;
                        console.log('Despliegue nuevo: recargando la aplicación.');
                        location.reload();
                    });

                    const registro = await navigator.serviceWorker.register('/sw.js');
                    // Comprobación explícita de actualización: el navegador ya
                    // la hace al navegar, pero esta aplicación se queda abierta
                    // horas en la misma pestaña. Sin esto, quien no recarga se
                    // queda con el service worker del despliegue anterior.
                    registro.update().catch(() => {});
                    // Y cada media hora, por si la pestaña se queda abierta
                    // toda la jornada: es lo que pasa en la planta.
                    setInterval(() => registro.update().catch(() => {}), 30 * 60 * 1000);
                    console.log('Service Worker registrado');
                } catch (err) {
                    console.error('Falló el registro del Service Worker:', err);
                }
            }
        }

        // Init componentes
        Toast.init();
        // Oír lo que otras pestañas avisan de los RFQ (ver `API.avisarRfq`).
        API._canal();
        Assistant.init();
        PerfilMenu.init();
        this.seguirHorario();
        this.medirEsquina();

        // Al cambiar de idioma se repinta lo que está en pantalla: el título,
        // el estado del servicio y la página actual, que se genera desde JS y
        // no lleva marcas data-i18n.
        // El botón del tema dice lo que hará, en el idioma puesto.
        I18N.alCambiar(() => {
            const boton = document.getElementById('btnTema');
            if (!boton || typeof Tema === 'undefined') return;
            const texto = I18N.t('tema.cambiarA.' + (Tema.actual() === 'light' ? 'dark' : 'light'));
            boton.title = texto;
            boton.setAttribute('aria-label', texto);
        });

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
            this.exigirAvisoLegal();
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
    /**
     * Quien no aceptó la versión vigente del aviso de privacidad y de los
     * términos lo hace antes de seguir (js/components/legal.js). Un poco
     * después que el de la contraseña, para quedar encima de él.
     */
    exigirAvisoLegal() {
        const yo = API.getUsuario();
        if (!yo || !yo.legal_pendiente || typeof Legal === 'undefined') return;
        setTimeout(() => Legal.exigirAceptacion(), 350);
    },

    exigirPasswordPropia() {
        const yo = API.getUsuario();
        if (!yo || !yo.debe_cambiar_password) return;
        if (typeof Password === 'undefined' || !Password.pedirCambioInicial) return;
        setTimeout(() => Password.pedirCambioInicial(), 300);
    },

    /**
     * Vacía las pantallas montadas.
     *
     * Las vistas no se destruyen al navegar —volver a Cotización encuentra la
     * calculadora tal y como se dejó, sin recargarla—, así que al salir hay
     * que vaciarlas a mano: lo que quedara dentro es trabajo de quien acaba de
     * cerrar la sesión, y la siguiente persona que entre en este navegador no
     * tiene por qué verlo.
     */
    vaciarVistas() {
        document.querySelectorAll('.page-view').forEach((vista) => {
            vista.innerHTML = '';
            vista.classList.remove('active');
        });
        this.currentPage = null;
    },

    /** Reacciona a un 401: limpia la sesión y regresa al login. */
    sesionExpirada() {
        const pantalla = document.getElementById('loginScreen');
        if (pantalla && !pantalla.hidden) return; // ya estamos en el login

        this.detenerSondeo();
        if (typeof Notificaciones !== 'undefined') Notificaciones.limpiar();
        if (typeof Revision !== 'undefined') Revision.cerrar();
        if (typeof QuotingPage !== 'undefined') QuotingPage.limpiar?.();
        this.vaciarVistas();
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

        // Cada recogida por separado y tolerando fallos.
        //
        // Antes iban en fila: si una fallaba, las de después no corrían y
        // —lo grave— `API.logout()` tampoco, así que pulsar "Cerrar sesión"
        // dejaba la sesión abierta y la pantalla a medias. Y fallar es fácil:
        // basta con que el navegador sirva de su caché un componente de la
        // versión anterior mientras el resto ya es nuevo; ahí un método que
        // todavía no existe tiraba todo el cierre.
        //
        // Salir tiene que salir siempre. Lo que no se pueda recoger se anota
        // en la consola y se sigue.
        const recoger = (nombre, fn) => {
            try { fn(); } catch (err) { console.warn('Al cerrar sesión, ' + nombre + ':', err.message); }
        };
        const actual = this.pages[this.currentPage];
        recoger('la página', () => { if (actual && typeof actual.detener === 'function') actual.detener(); });
        recoger('el asistente', () => Assistant?.limpiar?.());
        recoger('el menú de perfil', () => PerfilMenu?.limpiar?.());
        recoger('el aviso de contraseña', () => Password?.quitarAviso?.());
        recoger('las notificaciones', () => Notificaciones?.limpiar?.());
        recoger('la ventana de revisión', () => Revision?.cerrar?.());
        recoger('los avisos del teléfono', () => Push?.limpiar?.());
        recoger('la cotización', () => QuotingPage?.limpiar?.());
        recoger('las vistas', () => this.vaciarVistas());
        API.logout();
        // Salida a mano: se vuelve a la portada. La sesión expirada sí va
        // directa al login, porque ahí hay un mensaje que leer.
        this.mostrarHome();
        // El aviso va DESPUÉS de montar la portada: los avisos viven fuera de
        // la pantalla que se reemplaza, así que sobreviven al cambio.
        Toast.success(I18N.t('aviso.sesionCerrada'));
    },

    /** El logo de la barra lateral lleva a la portada, con la sesión abierta.
     *
     * Antes llevaba a la pantalla principal (`inicio()`), y a propósito no a
     * la portada, para que no pareciera que se había cerrado la sesión. Desde
     * 2026-09-25 la portada ES la pantalla de espera de Pohua (pedido de
     * ventas): el resorte de estrellas mientras no se está trabajando, y un
     * botón «Continuar» que devuelve a donde se estaba. La sesión no se toca.
     */
    conectarLogo() {
        const logo = document.getElementById('logoSidebar');
        if (!logo || logo.dataset.conectado) return;
        logo.dataset.conectado = '1';
        logo.addEventListener('click', () => this.mostrarPortada());
    },

    /**
     * La portada como pantalla de espera, ya dentro de la aplicación.
     *
     * El logo de la barra lateral lleva aquí: la misma portada del principio
     * —los logos, el nombre y el resorte de estrellas— pero SIN cerrar la
     * sesión. Es donde se deja Pohua cuando no se está trabajando en ella (la
     * pantalla de la planta, la computadora que lee el correo): un cielo con
     * el resorte en vez de una tabla a medio leer. El botón, que aquí dice
     * «Continuar» y no «Entrar», devuelve a la página en la que se estaba.
     * El sondeo del estado y los avisos siguen corriendo por detrás.
     */
    mostrarPortada() {
        if (!API.getToken()) {
            this.mostrarHome();
            return;
        }
        const layout = document.querySelector('.app-layout');
        const home = document.getElementById('homeScreen');
        if (!home) return;

        this.cerrarMenu();
        if (layout) layout.hidden = true;
        for (const id of ['mobileToggle', 'perfilMenu', 'notificaciones']) {
            const el = document.getElementById(id);
            if (el) el.hidden = true;
        }
        home.hidden = false;
        HomePage.render(home, {
            conSesion: true,
            onLogin: () => this.volverDeLaPortada(),
        });
    },

    volverDeLaPortada() {
        // ocultarLogin() esconde la portada y vuelve a enseñar el esqueleto;
        // pintarUsuario() devuelve el menú del perfil y la campana.
        this.ocultarLogin();
        this.pintarUsuario();
        this.aplicarPermisos();
        this.handleRoute();
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
        this.vigilarReloj();
    },

    /**
     * El reloj no puede pisar el título de la página.
     *
     * Va centrado en la ventana, y el CSS lo baja bajo la barra de la esquina
     * por debajo de 1100 px. Pero el choque depende del título, no sólo del
     * ancho: «Detalle de RFQ» o un título en francés es más largo que
     * «Monitor», y a 1860 px ya quedaba debajo del reloj. Así que se mide:
     * si el título llega a donde empieza el reloj, se baja (`reloj-abajo`,
     * las mismas reglas que en pantallas estrechas).
     */
    vigilarReloj() {
        if (this.relojVigilado) return;
        this.relojVigilado = true;
        const raiz = document.documentElement;
        const comprobar = () => {
            const reloj = document.getElementById('reloj');
            const layout = document.querySelector('.app-layout');
            const titulo = document.getElementById('pageTitle');
            if (!reloj || !layout || layout.hidden || !titulo) {
                raiz.classList.remove('reloj-abajo');
                return;
            }
            // Se mide en su sitio de siempre: sin la clase puesta.
            raiz.classList.remove('reloj-abajo');
            const r = reloj.getBoundingClientRect();
            const bloque = titulo.parentElement || titulo;
            const rango = document.createRange();
            let derecha = 0;
            for (const el of [titulo, document.getElementById('pageSubtitle')]) {
                if (!el || !el.textContent.trim()) continue;
                rango.selectNodeContents(el);
                derecha = Math.max(derecha, rango.getBoundingClientRect().right);
            }
            const arriba = bloque.getBoundingClientRect();
            const choca = r.width > 0 && derecha > r.left - 16 && arriba.top < r.bottom;
            raiz.classList.toggle('reloj-abajo', choca);
        };
        this.comprobarReloj = () => requestAnimationFrame(comprobar);
        window.addEventListener('resize', this.comprobarReloj, { passive: true });
        I18N.alCambiar(this.comprobarReloj);
        if (window.ResizeObserver) {
            const reloj = document.getElementById('reloj');
            if (reloj) new ResizeObserver(this.comprobarReloj).observe(reloj);
        }
        this.comprobarReloj();
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
        this.exigirAvisoLegal();

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

        // La ventana de revisión del PM. Se abre con «Revisar» en la ficha del
        // RFQ; los enlaces con #/rfq/<id> llevan a esa ficha.
        Revision.init();
        // Los avisos en el teléfono: registra este dispositivo si ya lo estaba.
        if (typeof Push !== 'undefined') Push.init();
        // El tono de los avisos: queda a la espera del primer clic, que es lo
        // que el navegador pide para dejar sonar a un sitio.
        if (typeof Sonido !== 'undefined') Sonido.init();

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
        // La fila de accesos rápidos del asistente es de la SECCIÓN: en
        // Monitor no pinta nada un "Exportar a Excel".
        if (typeof Assistant !== 'undefined') Assistant.alCambiarSeccion?.();

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
        if (this.comprobarReloj) this.comprobarReloj();
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

            // Tres estados, no dos: parado, en marcha y EN ESPERA. El tercero
            // es "el servicio está levantado pero ahora no toca leer" —fuera
            // del horario de atención—, y sin él la barra decía "en marcha"
            // mientras el buzón llevaba doce horas sin tocarse, o parecía que
            // algo se había colgado.
            const h = status.horario;
            const espera = typeof Horario !== 'undefined' ? Horario.resumen(h) : { enEspera: false };
            this.pintarHorario(h, status.running);

            if (status.running && espera.enEspera) {
                if (dot) dot.className = 'status-dot espera';
                if (lbl) {
                    lbl.textContent = h.proxima_apertura
                        ? I18N.t('barra.enEspera', { cuando: Horario.cuando(h.proxima_apertura) })
                        : I18N.t('horario.fuera');
                    lbl.title = espera.titulo;
                }
                if (btn) {
                    btn.dataset.corriendo = '1';
                    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg> ${I18N.t('boton.detener')}`;
                    btn.className = 'btn btn-secondary';
                }
            } else if (status.running) {
                if (dot) dot.className = 'status-dot running';
                if (lbl) {
                    lbl.textContent = I18N.t('barra.servicioCorriendo');
                    lbl.title = espera.titulo || '';
                }
                if (btn) {
                    btn.dataset.corriendo = '1';
                    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg> ${I18N.t('boton.detener')}`;
                    btn.className = 'btn btn-secondary';
                }
            } else {
                if (dot) dot.className = 'status-dot';
                if (lbl) { lbl.textContent = I18N.t('barra.servicioParado'); lbl.title = espera.titulo || ''; }
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
    },

    /**
     * La pastilla del horario, junto a los botones del tablero.
     *
     * Ahí es donde alguien pulsa "Ejecutar ciclo" y donde, si no se dice, uno
     * se queda pensando por qué no entra nada. Sólo existe en el tablero: en
     * el resto de pantallas no hay hueco ni falta hace.
     */
    pintarHorario(h, corriendo) {
        const caja = document.getElementById('flujoHorario');
        if (!caja) return;
        if (!h || !h.activo || typeof Horario === 'undefined') { caja.hidden = true; return; }

        const r = Horario.resumen(h);
        caja.hidden = false;
        caja.classList.toggle('flujo-horario--espera', r.enEspera && corriendo !== false);
        caja.title = r.titulo;
        // textContent, no innerHTML: los textos salen de plantillas propias,
        // pero el hueco lo rellenan horas de Intl y el nombre de una ciudad,
        // y no hay razón para abrir la puerta.
        caja.textContent = '';
        const valor = document.createElement('span');
        valor.className = 'flujo-horario-valor';
        valor.textContent = r.valor;
        const detalle = document.createElement('span');
        detalle.className = 'flujo-horario-detalle';
        detalle.textContent = r.detalle;
        caja.append(valor, detalle);
    },

    /**
     * Repinta el horario cuando el reloj cambia de casa.
     *
     * Las horas del horario se dicen en la casa que tenga puesta el reloj de
     * arriba, así que rotarlo tiene que moverlas con él: las 6:00 de Kansas
     * son las 7:00 de Querétaro y las 13:00 de Sevran. Del cambio de idioma no
     * hay que ocuparse aquí: I18N.alCambiar ya vuelve a llamar a updateStatus.
     */
    seguirHorario() {
        if (typeof Reloj === 'undefined' || !Reloj.alCambiar) return;
        Reloj.alCambiar(() => { if (API.getToken()) this.updateStatus(); });
    }
};

// Arrancar la app cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', () => APP.init());
