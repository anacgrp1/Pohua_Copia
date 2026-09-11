/**
 * Los avisos de la campana, también en el teléfono (Web Push).
 *
 * Qué hace: pedirle permiso al navegador, suscribir ESTE dispositivo en el
 * servicio de push del navegador y registrar la suscripción en el servidor
 * (`POST /api/push/suscribir`). A partir de ahí, cada aviso que entra en la
 * campana llega también al centro de notificaciones del teléfono, con Pohua
 * cerrada; tocarlo abre la ventana de revisión del RFQ (lo pinta sw.js).
 *
 * Dónde se ve: al pie del panel de la campana, una fila con el estado y un
 * botón para activar o quitar los avisos en este dispositivo. Es por
 * dispositivo a propósito: la misma persona activa el teléfono y, si quiere,
 * la compu.
 *
 * Lo que el navegador exige y por qué el código está como está:
 *   - El permiso sólo se puede pedir tras un toque de la persona; por eso se
 *     pide en el clic del botón y nunca solo.
 *   - En iPhone hace falta iOS 16.4+ y que Pohua esté añadida a la pantalla
 *     de inicio; abierta en Safari a secas, `PushManager` no existe y la fila
 *     lo dice en vez de enseñar un botón que no puede funcionar.
 *   - El servidor sin claves VAPID contesta `habilitado:false`: la fila lo
 *     dice y no ofrece el botón.
 */
const Push = (() => {
    'use strict';

    let servidor = null;        // {habilitado, clave_publica} o null si no se ha preguntado
    let ocupado = false;

    function esc(v) {
        return String(v == null ? '' : v)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function soportado() {
        return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
    }

    /** iPhone/iPad en Safari sin añadir a inicio: no hay push posible. */
    function esIosSinInstalar() {
        const ios = /iPhone|iPad|iPod/.test(navigator.userAgent);
        const instalada = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
        return ios && !instalada;
    }

    function claveAUint8(base64url) {
        const relleno = '='.repeat((4 - (base64url.length % 4)) % 4);
        const base64 = (base64url + relleno).replace(/-/g, '+').replace(/_/g, '/');
        const crudo = atob(base64);
        const salida = new Uint8Array(crudo.length);
        for (let i = 0; i < crudo.length; i++) salida[i] = crudo.charCodeAt(i);
        return salida;
    }

    /**
     * El service worker, o null si no hay ninguno registrado. En localhost la
     * app lo da de baja a propósito (app.js), y `ready` se quedaría esperando
     * para siempre: por eso se pregunta primero si existe.
     */
    async function registro() {
        if (!('serviceWorker' in navigator)) return null;
        const existente = await navigator.serviceWorker.getRegistration();
        if (!existente) return null;
        return navigator.serviceWorker.ready;
    }

    async function suscripcionActual() {
        const reg = await registro();
        if (!reg) return null;
        try { return await reg.pushManager.getSubscription(); } catch (_) { return null; }
    }

    async function consultarServidor() {
        if (servidor) return servidor;
        try {
            servidor = await API.pushClave();
        } catch (err) {
            if (err.sesionExpirada) throw err;
            servidor = { habilitado: false, clave_publica: '', error: err.message };
        }
        return servidor;
    }

    // ------------------------------------------------------------ acciones

    async function activar() {
        if (ocupado) return;
        ocupado = true;
        try {
            const s = await consultarServidor();
            if (!s.habilitado) { Toast.warning(I18N.t('push.servidorApagado')); return; }

            const permiso = await Notification.requestPermission();
            if (permiso !== 'granted') { Toast.warning(I18N.t('push.permisoNegado')); return; }

            const reg = await registro();
            if (!reg) { Toast.warning(I18N.t('push.sinSw')); return; }
            let sub = await reg.pushManager.getSubscription();
            if (!sub) {
                sub = await reg.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: claveAUint8(s.clave_publica),
                });
            }
            await API.pushSuscribir(sub.toJSON());
            Toast.success(I18N.t('push.activado'));
            // Un aviso de prueba al momento: así se ve dónde y cómo llegan.
            try { await API.pushProbar(); } catch (_) { /* la suscripción ya quedó */ }
        } catch (err) {
            if (err.sesionExpirada) return;
            Toast.error(I18N.t('push.error') + ' ' + err.message);
        } finally {
            ocupado = false;
            pintarPie();
        }
    }

    async function desactivar() {
        if (ocupado) return;
        ocupado = true;
        try {
            const sub = await suscripcionActual();
            if (sub) {
                try { await API.pushDesuscribir(sub.endpoint); } catch (err) { if (err.sesionExpirada) return; }
                await sub.unsubscribe();
            }
            Toast.info(I18N.t('push.desactivado'));
        } catch (err) {
            Toast.error(I18N.t('push.error') + ' ' + err.message);
        } finally {
            ocupado = false;
            pintarPie();
        }
    }

    /**
     * Al entrar: si este dispositivo ya estaba suscrito, se vuelve a registrar
     * en el servidor sin preguntar nada. Cubre el cambio de usuario en el
     * mismo teléfono y la renovación de la suscripción por el navegador.
     */
    async function sincronizar() {
        if (!soportado() || !API.puede('notificaciones:ver')) return;
        if (Notification.permission !== 'granted') return;
        const sub = await suscripcionActual();
        if (!sub) return;
        try { await API.pushSuscribir(sub.toJSON()); } catch (_) { /* se reintenta al próximo arranque */ }
    }

    // ------------------------------------------------------------ la fila

    /** El HTML de la fila del pie del panel (la campana lo incrusta). */
    function pie() {
        return `<div class="notif-pie" id="notifPushPie">${contenidoPie(null)}</div>`;
    }

    function contenidoPie(estado) {
        const icono = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg>`;
        if (!soportado() || esIosSinInstalar()) {
            const clave = esIosSinInstalar() ? 'push.iosInstalar' : 'push.noSoportado';
            return `${icono}<span class="notif-pie-texto">${esc(I18N.t(clave))}</span>`;
        }
        if (!estado) {
            return `${icono}<span class="notif-pie-texto">${esc(I18N.t('push.consultando'))}</span>`;
        }
        if (!estado.habilitado) {
            return `${icono}<span class="notif-pie-texto">${esc(I18N.t('push.servidorApagado'))}</span>`;
        }
        if (estado.sinSw) {
            return `${icono}<span class="notif-pie-texto">${esc(I18N.t('push.sinSw'))}</span>`;
        }
        if (estado.suscrito) {
            return `${icono}<span class="notif-pie-texto">${esc(I18N.t('push.enEste'))}</span>
                <button type="button" class="notif-pie-boton" data-push="desactivar">${esc(I18N.t('push.quitar'))}</button>`;
        }
        if (Notification.permission === 'denied') {
            return `${icono}<span class="notif-pie-texto">${esc(I18N.t('push.bloqueado'))}</span>`;
        }
        return `${icono}<span class="notif-pie-texto">${esc(I18N.t('push.invitacion'))}</span>
            <button type="button" class="notif-pie-boton notif-pie-boton--primario" data-push="activar">${esc(I18N.t('push.activar'))}</button>`;
    }

    async function pintarPie() {
        const caja = document.getElementById('notifPushPie');
        if (!caja) return;
        if (!soportado() || esIosSinInstalar()) { caja.innerHTML = contenidoPie(null); return; }
        try {
            const s = await consultarServidor();
            const reg = await registro();
            const sub = reg ? await suscripcionActual() : null;
            const suscrito = !!sub && Notification.permission === 'granted';
            const caja2 = document.getElementById('notifPushPie');   // pudo repintarse mientras
            if (caja2) caja2.innerHTML = contenidoPie({ habilitado: s.habilitado, suscrito, sinSw: !reg });
        } catch (err) {
            if (!err.sesionExpirada) caja.innerHTML = contenidoPie({ habilitado: false });
        }
    }

    // ------------------------------------------------------------ ciclo

    function init() {
        document.addEventListener('click', (ev) => {
            const b = ev.target.closest('[data-push]');
            if (!b) return;
            ev.preventDefault();
            if (b.dataset.push === 'activar') activar();
            else if (b.dataset.push === 'desactivar') desactivar();
        });
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.addEventListener('message', (ev) => {
                const m = ev.data || {};
                if (m.tipo === 'push-renovada' && m.suscripcion && API.getToken()) {
                    API.pushSuscribir(m.suscripcion).catch(() => {});
                }
                // Tocaron la notificación con Pohua abierta: a la ventana del RFQ.
                if (m.tipo === 'abrir' && m.url) {
                    try {
                        const u = new URL(m.url, location.origin);
                        if (u.hash) location.hash = u.hash; else location.assign(u.href);
                    } catch (_) { /* dirección rara: se ignora */ }
                }
            });
        }
        sincronizar();
    }

    /** Al cambiar de usuario se olvida lo consultado: otro rol, otra respuesta. */
    function limpiar() { servidor = null; }

    return { init, limpiar, pie, pintarPie, activar, desactivar, soportado };
})();
