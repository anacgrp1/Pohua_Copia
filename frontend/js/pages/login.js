/**
 * Pantalla de Acceso (Login)
 *
 * Los textos llevan data-i18n además de I18N.t(). Los dos hacen falta: t() los
 * pone bien en el primer pintado, y la marca deja que I18N.aplicar() los cambie
 * después sin volver a montar el formulario. Volver a montarlo borraría el
 * correo y la contraseña ya escritos: cambiar de idioma no puede costarle a
 * nadie lo que llevaba tecleado.
 */
const LoginPage = {
    onExito: null,
    cargando: false,

    /**
     * Dibuja el formulario de acceso.
     * @param {HTMLElement} container contenedor de la pantalla
     * @param {Object} opciones { onExito: función a ejecutar tras autenticar }
     */
    render(container, opciones = {}) {
        this.onExito = opciones.onExito || null;
        this.cargando = false;

        const correoRecordado = API.getCorreoRecordado();

        container.innerHTML = `
            <div class="login-card">
                <div class="login-brand">
                    <button type="button" class="logo-boton" id="logoInicio"
                            data-i18n-titulo="login.volver"
                            title="${I18N.t('login.volver')}" aria-label="${I18N.t('login.volver')}">
                        <span class="logo-lockup">
                            <img src="/assets/isc-logo.png" alt="ISC" class="logo-lockup__isc">
                            <img src="/assets/logo.png" alt="CGR" class="logo-lockup__cgr">
                        </span>
                    </button>
                    <div>
                        <div class="login-brand-name">Pohua</div>
                        <div class="login-brand-sub">RFQ Quoter</div>
                    </div>
                </div>

                <h1 class="login-title" data-i18n="login.titulo">${I18N.t('login.titulo')}</h1>
                <p class="login-subtitle" data-i18n="login.ayuda">${I18N.t('login.ayuda')}</p>

                <form id="loginForm" novalidate>
                    <div class="form-group">
                        <label class="form-label" for="loginCorreo"
                               data-i18n="login.correo">${I18N.t('login.correo')}</label>
                        <input type="email" class="form-input" id="loginCorreo"
                               autocomplete="username" data-i18n-ph="login.marcadorCorreo"
                               placeholder="${I18N.t('login.marcadorCorreo')}"
                               value="${correoRecordado}">
                    </div>

                    <div class="form-group">
                        <label class="form-label" for="loginPassword"
                               data-i18n="login.password">${I18N.t('login.password')}</label>
                        <input type="password" class="form-input" id="loginPassword"
                               autocomplete="current-password" data-i18n-ph="login.marcadorPassword"
                               placeholder="${I18N.t('login.marcadorPassword')}">
                    </div>

                    <div class="login-error" id="loginError" hidden></div>

                    <button type="submit" class="btn btn-primary login-submit" id="loginSubmit"
                            data-i18n="login.entrar">${I18N.t('login.entrar')}</button>
                </form>
            </div>
        `;

        // Los logos son un botón de vuelta a la portada.
        const logo = document.getElementById('logoInicio');
        if (logo) {
            logo.addEventListener('click', () => {
                if (typeof APP !== 'undefined' && APP.mostrarHome) APP.mostrarHome();
            });
        }

        // El submit del formulario cubre tanto el botón como la tecla Enter.
        document.getElementById('loginForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.entrar();
        });

        this.enfocar();
    },

    /** Coloca el cursor en el primer campo vacío. */
    enfocar() {
        const correo = document.getElementById('loginCorreo');
        const password = document.getElementById('loginPassword');
        if (!correo || !password) return;
        (correo.value ? password : correo).focus();
    },

    /**
     * Enseña un error bajo el formulario.
     *
     * `clave` es opcional y sólo la traen los errores nuestros. Cuando la hay,
     * se deja marcada en el elemento para que el mensaje cambie de idioma con
     * el resto de la pantalla. Los que vienen del servidor no tienen clave y se
     * quedan tal cual: traducirlos a ciegas sería inventárselos.
     */
    mostrarError(mensaje, clave = '') {
        const caja = document.getElementById('loginError');
        if (!caja) return;
        if (clave) caja.dataset.i18n = clave; else delete caja.dataset.i18n;
        caja.textContent = mensaje;
        caja.hidden = !mensaje;
    },

    setCargando(activo) {
        this.cargando = activo;
        const btn = document.getElementById('loginSubmit');
        const correo = document.getElementById('loginCorreo');
        const password = document.getElementById('loginPassword');
        if (!btn) return;

        btn.disabled = activo;
        // Con el spinner dentro no puede llevar data-i18n: escribiría
        // textContent y se llevaría el spinner por delante. Como el botón sólo
        // está así unos segundos, se retraduce solo al terminar.
        if (activo) {
            delete btn.dataset.i18n;
            btn.innerHTML = `<span class="spinner"></span> ${I18N.t('login.entrando')}`;
        } else {
            btn.dataset.i18n = 'login.entrar';
            btn.textContent = I18N.t('login.entrar');
        }
        if (correo) correo.disabled = activo;
        if (password) password.disabled = activo;
    },

    async entrar() {
        if (this.cargando) return;

        const correo = (document.getElementById('loginCorreo').value || '').trim();
        const password = document.getElementById('loginPassword').value || '';

        if (!correo || !password) {
            this.mostrarError(I18N.t('login.faltan'), 'login.faltan');
            return;
        }

        this.mostrarError('');
        this.setCargando(true);

        try {
            const usuario = await API.login(correo, password);
            Toast.success(I18N.t('aviso.bienvenida', { nombre: usuario.nombre }));
            if (this.onExito) this.onExito(usuario);
        } catch (err) {
            this.setCargando(false);
            const { texto, clave } = this.mensajeLegible(err);
            this.mostrarError(texto, clave);
            const campoPassword = document.getElementById('loginPassword');
            if (campoPassword) {
                campoPassword.value = '';
                campoPassword.focus();
            }
        }
    },

    /**
     * Convierte el error de red o de API en algo entendible.
     *
     * Devuelve el texto y, cuando es nuestro, su clave de idioma. El mensaje
     * del servidor gana al nuestro: dice algo más concreto. Pero entonces no
     * hay clave, y ese texto ya no cambia de idioma: es lo que hay hasta que el
     * backend responda con códigos en vez de frases.
     */
    mensajeLegible(err) {
        const nuestro = (clave) => ({ texto: I18N.t(clave), clave });
        const suyo = (mensaje, clave) => (mensaje ? { texto: mensaje, clave: '' } : nuestro(clave));

        if (!err) return nuestro('login.fallo');
        if (err.status === 401) return suyo(err.message, 'login.malas');
        if (err.status === 503) return suyo(err.message, 'login.sinServicio');
        if (err instanceof TypeError) return nuestro('login.sinRed');
        return suyo(err.message, 'login.fallo');
    }
};
