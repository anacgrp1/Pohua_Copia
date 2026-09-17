/**
 * Menú de perfil: la ficha de quien ha entrado, arriba a la derecha.
 *
 * Sustituye a la ficha que había en el pie de la barra lateral. Estaba abajo
 * del todo y escondida en el cajón en teléfono, que es justo donde nadie busca
 * su propia cuenta; arriba a la derecha es donde todo el mundo la busca.
 *
 * Qué lleva y qué NO: sólo lo que este sistema hace de verdad. La referencia
 * traía "PRO", "Upgrade account", "Favorite", "Download" y "Add account": aquí
 * no significan nada —no hay planes, ni favoritos, ni varias cuentas por
 * persona— y un menú lleno de puertas que no abren es peor que uno corto.
 *
 * Las entradas de administración (usuarios, sistema) sólo aparecen con el
 * permiso 'usuario:gestionar'. La comprobación de verdad la hace el servidor;
 * esto es para no enseñar puertas cerradas.
 */
const PerfilMenu = (() => {
    'use strict';

    let montado = false;
    let abierto = false;

    function esc(valor) {
        const nodo = document.createElement('span');
        nodo.textContent = valor == null ? '' : String(valor);
        return nodo.innerHTML;
    }

    const ICONOS = {
        editar:   '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="10" r="3"/><path d="M7 20.7a8 8 0 0 1 10 0"/>',
        password: '<path d="M21 2l-2 2m-7.6 7.6a5 5 0 1 1-7.1 7.1 5 5 0 0 1 7.1-7.1zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3"/>',
        usuarios: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
        sistema:  '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
        salir:    '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
    };

    const icono = (d) => `<svg viewBox="0 0 24 24" width="18" height="18" fill="none"
        stroke="currentColor" stroke-width="2" stroke-linecap="round"
        stroke-linejoin="round" aria-hidden="true">${d}</svg>`;

    const caja = () => document.getElementById('perfilMenu');
    const boton = () => document.getElementById('btnPerfilMenu');
    const panel = () => document.getElementById('perfilMenuPanel');

    // ------------------------------------------------------------- contenido

    function pintarBoton() {
        const b = boton();
        const usuario = API.getUsuario();
        if (!b) return;

        if (!usuario) {
            b.innerHTML = `<span class="perfil-menu-texto">
                               <span class="perfil-menu-nombre">${esc(I18N.t('menu.sinSesion'))}</span>
                           </span>`;
            return;
        }
        b.innerHTML = `
            ${Avatar.render(usuario, { tamano: 'sm' })}
            <span class="perfil-menu-texto">
                <span class="perfil-menu-nombre">${esc(usuario.nombre || usuario.correo)}</span>
                <span class="perfil-menu-rol">${esc(usuario.rol || '')}</span>
            </span>
            <svg class="perfil-menu-flecha" viewBox="0 0 24 24" width="14" height="14" fill="none"
                 stroke="currentColor" stroke-width="2" stroke-linecap="round"
                 stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>`;
    }

    function pintarPanel() {
        const p = panel();
        const usuario = API.getUsuario();
        if (!p || !usuario) return;

        const admin = API.puede('usuario:gestionar');
        const entrada = (accion, ico, texto) => `
            <button type="button" class="perfil-menu-item" data-accion="${accion}">
                ${icono(ico)}<span>${esc(texto)}</span>
            </button>`;

        p.innerHTML = `
            <div class="perfil-menu-ficha">
                ${Avatar.render(usuario, { tamano: 'md' })}
                <div class="perfil-menu-ficha-texto">
                    <strong>${esc(usuario.nombre || '—')}</strong>
                    <span>${esc(usuario.correo || '')}</span>
                </div>
                <span class="badge badge-rol">${esc(usuario.rol || '')}</span>
            </div>

            <div class="perfil-menu-grupo">
                ${entrada('editar',   ICONOS.editar,   I18N.t('menu.editar'))}
                ${entrada('password', ICONOS.password, I18N.t('menu.password'))}
            </div>

            ${admin ? `<div class="perfil-menu-grupo">
                ${entrada('usuarios', ICONOS.usuarios, I18N.t('menu.usuarios'))}
                ${entrada('sistema',  ICONOS.sistema,  I18N.t('menu.sistema'))}
            </div>` : ''}

            <div class="perfil-menu-grupo">
                <button type="button" class="perfil-menu-item perfil-menu-item--salir" data-accion="salir">
                    ${icono(ICONOS.salir)}<span>${esc(I18N.t('menu.salir'))}</span>
                </button>
            </div>`;
    }

    // ----------------------------------------------------------- abrir/cerrar

    function abrir() {
        pintarPanel();
        const p = panel();
        if (!p) return;
        p.hidden = false;
        abierto = true;
        boton()?.setAttribute('aria-expanded', 'true');
        p.querySelector('.perfil-menu-item')?.focus({ preventScroll: true });
    }

    function cerrar({ devolverFoco = false } = {}) {
        const p = panel();
        if (!p || !abierto) return;
        p.hidden = true;
        abierto = false;
        boton()?.setAttribute('aria-expanded', 'false');
        if (devolverFoco) boton()?.focus({ preventScroll: true });
    }

    /**
     * Lleva al perfil y, si hace falta, a una pestaña concreta.
     *
     * La pestaña se pasa por el estado de la ruta en vez de por la URL: es una
     * preferencia de navegación, no una dirección que alguien vaya a compartir.
     */
    function irAPerfil(seccion, destino) {
        cerrar();
        APP.navigate('perfil');
        if (!seccion) return;
        // La página se monta de forma asíncrona: se espera a que exista.
        const intentar = (quedan) => {
            const tab = document.querySelector(`.perfil-tab[data-seccion="${seccion}"]`);
            // Sin pestañas (quien no administra sólo tiene "Mi perfil") la
            // sección ya está a la vista: basta con que exista el cuerpo.
            const listo = tab || (seccion === 'perfil' && document.getElementById('perfilCuerpo'));
            if (listo) {
                if (tab && !tab.classList.contains('active')) tab.click();
                if (destino) setTimeout(() => enfocar(destino), 30);
                return;
            }
            if (quedan > 0) setTimeout(() => intentar(quedan - 1), 60);
        };
        setTimeout(() => intentar(20), 60);
    }

    /**
     * "Editar perfil" y "Cambiar contraseña" son dos fichas de la misma
     * sección: cada entrada lleva a la suya, la trae a la vista, la resalta
     * un momento y deja el cursor en su primer campo. Antes las dos
     * aterrizaban arriba del todo, y "Cambiar contraseña" no llevaba a la
     * contraseña.
     */
    function enfocar(destino) {
        const campo = document.getElementById(destino === 'password' ? 'pwActual' : 'perfilNombre');
        if (!campo) return;
        const ficha = campo.closest('.panel') || campo;
        ficha.scrollIntoView({ behavior: 'smooth', block: 'start' });
        ficha.classList.add('panel--resaltado');
        setTimeout(() => ficha.classList.remove('panel--resaltado'), 1600);
        setTimeout(() => campo.focus({ preventScroll: true }), 350);
    }

    function alPulsarItem(accion) {
        switch (accion) {
            case 'editar':   return irAPerfil('perfil', 'editar');
            case 'password': return irAPerfil('perfil', 'password');
            case 'usuarios': return irAPerfil('usuarios');
            case 'sistema':  return irAPerfil('sistema');
            case 'salir':    cerrar(); return APP.cerrarSesion();
        }
    }

    // ------------------------------------------------------------- montaje

    function init() {
        const c = caja();
        if (!c) return;

        pintarBoton();

        if (!montado) {
            montado = true;

            c.addEventListener('click', (ev) => {
                if (ev.target.closest('#btnPerfilMenu')) {
                    ev.stopPropagation();
                    return abierto ? cerrar() : abrir();
                }
                const item = ev.target.closest('.perfil-menu-item');
                if (item) alPulsarItem(item.dataset.accion);
            });

            document.addEventListener('click', (ev) => {
                if (abierto && !ev.target.closest('#perfilMenu')) cerrar();
            });
            document.addEventListener('keydown', (ev) => {
                if (ev.key === 'Escape' && abierto) cerrar({ devolverFoco: true });
            });

            I18N.alCambiar(() => { pintarBoton(); if (abierto) pintarPanel(); });
        }
    }

    /** Lo llama app.js cuando cambia el usuario (entrar, salir, cambiar foto). */
    function refrescar() {
        pintarBoton();
        if (abierto) pintarPanel();
    }

    /** Al salir: fuera el panel y la ficha. */
    function limpiar() {
        cerrar();
        pintarBoton();
    }

    return { init, refrescar, limpiar };
})();
