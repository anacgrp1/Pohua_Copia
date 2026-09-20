/**
 * CGR Cotizador — Cliente de API
 * Envoltura central de fetch para todas las llamadas a /api/*.
 * Gestiona el token de sesión (Bearer) y los errores de autenticación.
 */
const API = {
    base: '',  // Mismo origen

    // El service worker cachea, por eso el token vive en sessionStorage
    // (no en localStorage) y sólo el correo se recuerda entre sesiones.
    CLAVE_TOKEN:    'cgr_token',
    CLAVE_CADUCA:   'cgr_token_caduca',
    CLAVE_USUARIO:  'cgr_usuario',
    CLAVE_CORREO:   'cgr_correo',

    _usuario: null,

    // ----------------------------------------------------------------------
    // Almacenamiento (siempre protegido: puede fallar en modo privado)
    // ----------------------------------------------------------------------
    _leer(almacen, clave) {
        try {
            return almacen.getItem(clave);
        } catch (err) {
            console.warn('No se pudo leer el almacenamiento:', err.message);
            return null;
        }
    },

    _escribir(almacen, clave, valor) {
        try {
            if (valor === null || valor === undefined) almacen.removeItem(clave);
            else almacen.setItem(clave, valor);
        } catch (err) {
            console.warn('No se pudo escribir en el almacenamiento:', err.message);
        }
    },

    /** Token vigente, o null si no hay sesión o ya caducó. */
    getToken() {
        const token = this._leer(sessionStorage, this.CLAVE_TOKEN);
        if (!token) return null;

        const caduca = parseInt(this._leer(sessionStorage, this.CLAVE_CADUCA) || '0', 10);
        if (caduca && Date.now() >= caduca) {
            this.limpiarSesion();
            return null;
        }
        return token;
    },

    /** Guarda el token y el momento de caducidad (expires_in viene en segundos). */
    guardarToken(token, expiraEnSegundos) {
        this._escribir(sessionStorage, this.CLAVE_TOKEN, token);
        const caduca = expiraEnSegundos ? Date.now() + (expiraEnSegundos * 1000) : '';
        this._escribir(sessionStorage, this.CLAVE_CADUCA, caduca ? String(caduca) : null);
    },

    /** Borra token y usuario del almacenamiento (el correo recordado se conserva). */
    limpiarSesion() {
        this._usuario = null;
        this._escribir(sessionStorage, this.CLAVE_TOKEN, null);
        this._escribir(sessionStorage, this.CLAVE_CADUCA, null);
        this._escribir(sessionStorage, this.CLAVE_USUARIO, null);
    },

    /** Usuario en memoria; si no está, se rehidrata desde sessionStorage. */
    getUsuario() {
        if (this._usuario) return this._usuario;
        const crudo = this._leer(sessionStorage, this.CLAVE_USUARIO);
        if (!crudo) return null;
        try {
            this._usuario = JSON.parse(crudo);
        } catch (err) {
            console.warn('Usuario almacenado ilegible:', err.message);
            this._usuario = null;
        }
        return this._usuario;
    },

    guardarUsuario(usuario) {
        this._usuario = usuario || null;
        let serializado = null;
        try {
            serializado = usuario ? JSON.stringify(usuario) : null;
        } catch (err) {
            console.warn('No se pudo serializar el usuario:', err.message);
        }
        this._escribir(sessionStorage, this.CLAVE_USUARIO, serializado);
    },

    /** Indica si el usuario de la sesión tiene un permiso ("admin" concede todo). */
    puede(permiso) {
        const usuario = this.getUsuario();
        if (!usuario || !Array.isArray(usuario.permisos)) return false;
        return usuario.permisos.includes('admin') || usuario.permisos.includes(permiso);
    },

    /** Correo recordado del último acceso (localStorage, sólo comodidad). */
    getCorreoRecordado() {
        return this._leer(localStorage, this.CLAVE_CORREO) || '';
    },

    recordarCorreo(correo) {
        this._escribir(localStorage, this.CLAVE_CORREO, correo || null);
    },

    // ----------------------------------------------------------------------
    // Petición base
    // ----------------------------------------------------------------------
    async request(method, path, body = null) {
        const opts = {
            method,
            headers: { 'Content-Type': 'application/json' },
        };
        if (body) opts.body = JSON.stringify(body);

        const token = this.getToken();
        if (token) opts.headers['Authorization'] = `Bearer ${token}`;

        const res = await fetch(`${this.base}${path}`, opts);

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            const detalle = err.detail || `HTTP ${res.status}`;

            // 401: la sesión no existe o caducó. Hay que volver al login.
            // En el propio login un 401 sólo significa credenciales malas.
            if (res.status === 401) {
                const esLogin = path.startsWith('/api/auth/login');
                this.limpiarSesion();
                const error = new Error(detalle || 'Tu sesión expiró. Inicia sesión de nuevo.');
                error.name = esLogin ? 'CredencialesInvalidas' : 'SesionExpirada';
                error.status = 401;
                error.sesionExpirada = !esLogin;
                if (!esLogin) {
                    window.dispatchEvent(new CustomEvent('sesion-expirada', { detail: { mensaje: detalle } }));
                }
                throw error;
            }

            // 403: la sesión es válida pero falta permiso. No se cierra la sesión.
            if (res.status === 403) {
                const error = new Error(detalle);
                error.name = 'PermisoDenegado';
                error.status = 403;
                error.permisoDenegado = true;
                throw error;
            }

            const error = new Error(detalle);
            error.status = res.status;
            throw error;
        }

        // 204 y respuestas sin cuerpo
        if (res.status === 204 || res.headers.get('content-length') === '0') return null;
        return res.json().catch(() => null);
    },

    // ----------------------------------------------------------------------
    // Autenticación
    // ----------------------------------------------------------------------
    async login(correo, password) {
        const res = await this.request('POST', '/api/auth/login', { correo, password });
        this.guardarToken(res.access_token, res.expires_in);
        this.guardarUsuario(res.usuario);
        this.recordarCorreo(correo);
        return res.usuario;
    },

    /** Cierra la sesión localmente (el token es sin estado en el servidor). */
    logout() {
        this.limpiarSesion();
    },

    async getMe() {
        const usuario = await this.request('GET', '/api/auth/me');
        this.guardarUsuario(usuario);
        return usuario;
    },

    cambiarPassword(actual, nueva) {
        return this.request('POST', '/api/auth/password', {
            password_actual: actual,
            password_nueva: nueva,
        });
    },

    // Estado y worker
    getStatus()      { return this.request('GET', '/api/status'); },
    runPipeline()    { return this.request('POST', '/api/pipeline/run'); },
    startWorker()    { return this.request('POST', '/api/worker/start'); },
    stopWorker()     { return this.request('POST', '/api/worker/stop'); },

    // RFQs
    listRFQs(params = {}) {
        const qs = new URLSearchParams(params).toString();
        return this.request('GET', `/api/rfqs${qs ? '?' + qs : ''}`);
    },
    getRFQ(rfqId)    { return this.request('GET', `/api/rfqs/${rfqId}`); },
    approveRFQ(rfqId, body = {}) {
        return this.request('POST', `/api/rfqs/${rfqId}/approve`, body);
    },
    declineRFQ(rfqId, body = {}) {
        return this.request('POST', `/api/rfqs/${rfqId}/decline`, body);
    },
    // La ventana de revisión del PM: el RFQ ya costeado por tramos.
    rfqRevision(rfqId) { return this.request('GET', `/api/rfqs/${rfqId}/revision`); },
    // Con lo que la calculadora abre este RFQ: el PN ya armado.
    rfqCotizacionInicial(rfqId) {
        return this.request('GET', `/api/rfqs/${rfqId}/cotizacion-inicial`);
    },
    // Devolver con nota: ni aprueba ni declina, y no sale correo al cliente.
    rfqSendBack(rfqId, nota) {
        return this.request('POST', `/api/rfqs/${rfqId}/send-back`, { nota });
    },

    // Los avisos en el teléfono (Web Push).
    pushClave()            { return this.request('GET', '/api/push/clave'); },
    pushSuscribir(sub)     { return this.request('POST', '/api/push/suscribir', { suscripcion: sub }); },
    pushDesuscribir(endpoint) { return this.request('DELETE', '/api/push/suscribir', { endpoint }); },
    pushProbar()           { return this.request('POST', '/api/push/probar'); },

    // La oferta al cliente: vista previa, PDF y envío.
    rfqOferta(rfqId) { return this.request('GET', `/api/rfqs/${rfqId}/oferta`); },
    rfqEnviarOferta(rfqId, body = {}) {
        return this.request('POST', `/api/rfqs/${rfqId}/oferta`, body);
    },
    /** El PDF de la oferta, como Blob. Con fetch y no con un enlace directo,
     *  por lo mismo que la foto (ver `descargarFoto`): la sesión viaja en la
     *  cabecera y un enlace no la manda. */
    async descargarOfertaPdf(rfqId) {
        const token = this.getToken();
        const res = await fetch(`${this.base}/api/rfqs/${rfqId}/oferta/pdf`, {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            const error = new Error(err.detail || `HTTP ${res.status}`);
            error.status = res.status;
            if (res.status === 401) { this.limpiarSesion(); error.sesionExpirada = true; }
            throw error;
        }
        return res.blob();
    },

    // Precios
    computePrice(data) { return this.request('POST', '/api/price', data); },

    // Cotización: qué piezas del núcleo de ISC hay puestas y cuáles faltan.
    quotingDiagnostico() { return this.request('GET', '/api/quoting/diagnostico'); },

    // La cookie que deja entrar al lector montado. Un iframe no manda la
    // cabecera Authorization, así que la puerta de /quoting/lector se abre con
    // esto antes de enseñar ninguna de las tres caras.
    abrirSesionLector() { return this.request('POST', '/api/quoting/sesion'); },
    cerrarSesionLector() { return this.request('DELETE', '/api/quoting/sesion'); },

    // ----------------------------------------------------------------------
    // Perfil propio y usuarios
    // ----------------------------------------------------------------------
    cambiarMiNombre(nombre) { return this.request('PATCH', '/api/me', { nombre }); },

    subirMiFoto(tipo, datosBase64) {
        return this.request('POST', '/api/me/photo', { tipo, datos_base64: datosBase64 });
    },
    borrarMiFoto() { return this.request('DELETE', '/api/me/photo'); },

    /** URL de la foto de un usuario.
     *
     * Lleva el sello de actualización para que el navegador la cachee hasta
     * que la foto cambie de verdad; sin él habría que elegir entre descargarla
     * en cada pantalla o quedarse con la antigua tras cambiarla.
     *
     * OJO: esta dirección NO se puede poner en el `src` de un <img>. Ver
     * `descargarFoto()`, justo debajo.
     */
    urlFoto(usuarioId, sello) {
        const v = sello ? `?v=${encodeURIComponent(sello)}` : '';
        return `${this.base}/api/users/${usuarioId}/photo${v}`;
    },

    /** La foto de un usuario, como Blob.
     *
     * POR QUÉ NO UN <img src> DIRECTO, que es lo que había antes y por lo que
     * la foto nunca aparecía aunque se subiera bien:
     *
     * la sesión de esta aplicación viaja en la cabecera `Authorization`, y una
     * etiqueta <img> NO manda cabeceras: el navegador pide la imagen "a pelo",
     * el servidor no ve token y contesta 401. La imagen estaba guardada y era
     * correcta; simplemente el que la pedía no iba identificado.
     *
     * Las salidas posibles eran tres. Meter el token en la dirección se
     * descarta: acaba en el historial, en los registros del servidor y en la
     * cabecera Referer de cualquier enlace. Abrir el endpoint sin sesión
     * también: son las caras del equipo, no material público. Queda ésta:
     * pedirla con fetch —que sí manda la cabecera— y enseñar el resultado.
     */
    async descargarFoto(usuarioId, sello) {
        const token = this.getToken();
        // El sello VA en la dirección, y no es cosmético: la respuesta lleva
        // `Cache-Control: private, max-age=300`, así que sin él el navegador
        // servía la foto ANTERIOR de su propia caché durante cinco minutos.
        // Ése era el fallo de "la cambio y no se ve hasta que recargo": la
        // imagen nueva estaba guardada y bien, pero nadie llegaba a pedirla.
        // Al cambiar la foto cambia `foto_actualizada`, con él la dirección, y
        // con ella la entrada de caché.
        const res = await fetch(this.urlFoto(usuarioId, sello), {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) {
            const error = new Error(`HTTP ${res.status}`);
            error.status = res.status;
            throw error;
        }
        return res.blob();
    },

    listarUsuarios() { return this.request('GET', '/api/users'); },
    listarRoles()    { return this.request('GET', '/api/roles'); },
    crearUsuario(datos) { return this.request('POST', '/api/users', datos); },
    cambiarUsuario(id, cambios) { return this.request('PATCH', `/api/users/${id}`, cambios); },
    /** El servidor genera la temporal y la devuelve una vez ({password_temporal, dispositivos…}). */
    restablecerPassword(id, notificar = false) {
        return this.request('POST', `/api/users/${id}/password/reset`, { notificar: !!notificar });
    },
    /** Manda al teléfono de la persona la temporal que el administrador tiene a la vista. */
    notificarPassword(id, passwordTemporal) {
        return this.request('POST', `/api/users/${id}/password/notificar`, { password_temporal: passwordTemporal });
    },

    configuracionSistema() { return this.request('GET', '/api/system/config'); },
    /** La comprobación del flujo, tal y como la ve el servidor desplegado. */
    comprobarFlujo(conBuzon = true) {
        return this.request('GET', `/api/system/preflight?buzon=${conBuzon ? 'true' : 'false'}`);
    },

    // Registro del servicio
    getLogs(lines = 300) { return this.request('GET', `/api/logs?lines=${lines}`); },

    // ----------------------------------------------------------------------
    // Asistente
    // ----------------------------------------------------------------------
    // Los tres primeros son agregados de la base de datos: no cuestan API.
    assistantSummary()   { return this.request('GET', '/api/assistant/summary'); },
    assistantAttention() { return this.request('GET', '/api/assistant/attention'); },
    assistantPipeline()  { return this.request('GET', '/api/assistant/pipeline'); },
    // Quién pidió más en los últimos días. SQL puro, no gasta API.
    assistantTopClientes(dias = 7) {
        return this.request('GET', `/api/assistant/top-clientes?dias=${dias}`);
    },

    // ----------------------------------------------------------------------
    // Notificaciones (COT-77)
    // ----------------------------------------------------------------------
    // El buzón de avisos del PM. No es lo mismo que `assistantAttention`: eso
    // es la cola de lo que espera AHORA, deducida del estado de cada RFQ; esto
    // son los avisos como hechos con fecha, que se marcan como leídos y siguen
    // existiendo después de que el RFQ se dictamine.
    notificaciones(sinLeer = true, limite = 50) {
        const q = `?sin_leer=${sinLeer ? 'true' : 'false'}&limite=${limite}`;
        return this.request('GET', '/api/notificaciones' + q);
    },
    notificacionLeer(id) {
        return this.request('POST', `/api/notificaciones/${id}/leer`);
    },
    notificacionesLeerTodo() {
        return this.request('POST', '/api/notificaciones/leer-todo');
    },

    // El chat es el único que gasta API de Anthropic.
    assistantAsk(pregunta) {
        return this.request('POST', '/api/assistant/ask', { pregunta });
    },

    /** Descarga el CSV de RFQs.
     *
     * No pasa por `request()` porque la respuesta es un fichero, no JSON, y
     * porque el token va en la cabecera: no se puede resolver con un enlace
     * normal sin meter la sesión en la URL.
     */
    async descargarCSV() {
        const token = this.getToken();
        const res = await fetch(`${this.base}/api/assistant/export`, {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) {
            if (res.status === 401) {
                this.limpiarSesion();
                window.dispatchEvent(new CustomEvent('sesion-expirada', { detail: {} }));
            }
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }

        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const enlace = document.createElement('a');
        enlace.href = url;
        enlace.download = `rfqs-${new Date().toISOString().slice(0, 10)}.xlsx`;
        document.body.appendChild(enlace);
        enlace.click();
        enlace.remove();
        // Sin revoke, el blob se queda en memoria hasta recargar la página.
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
};
