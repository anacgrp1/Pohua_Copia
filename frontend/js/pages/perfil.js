/**
 * Perfil — los datos de uno mismo y, si eres admin, la gestión del sistema.
 *
 * Absorbe lo que antes era "Settings": no había razón para dos pantallas de
 * configuración, y la anterior mezclaba lo de todos con lo de nadie.
 *
 * Se divide en tres secciones y el reparto de permisos es el punto:
 *
 *   My profile   TODOS. Foto, nombre y contraseña propios. Nada de aquí acepta
 *                un id de usuario: el servidor lo saca del token, así que por
 *                esta puerta no se puede tocar a otra persona.
 *   Users        sólo 'usuario:gestionar' (hoy: admin). Alta, rol, baja y
 *                contraseña temporal de los demás.
 *   System       sólo 'usuario:gestionar'. La configuración con la que corre
 *                el servidor, en SÓLO LECTURA.
 *
 * Las secciones de admin ni se piden al servidor si no hay permiso: quien no
 * lo tenga no verá siquiera las pestañas. La comprobación de verdad la hace el
 * servidor; esto es para no enseñar puertas que no se pueden abrir.
 *
 * La foto se recorta en el navegador a 256x256 antes de subirla. Recortar en
 * el servidor obligaría a meter Pillow y a recibir imágenes de 5 MB de un
 * móvil; recortando aquí sube ~30 KB y el servidor sólo guarda bytes.
 */
const PerfilPage = (() => {
    'use strict';

    const LADO_FOTO = 256;   // px del lado del recorte cuadrado
    const CALIDAD = 0.9;

    let seccion = 'perfil';
    let usuarios = [];
    let roles = [];

    function esc(valor) {
        const nodo = document.createElement('span');
        nodo.textContent = valor == null ? '' : String(valor);
        return nodo.innerHTML;
    }

    const puedeGestionar = () => API.puede('usuario:gestionar');

    // ====================================================================
    // Foto: recorte en el navegador
    // ====================================================================

    /**
     * Lee el fichero elegido y devuelve { tipo, base64 } de un cuadrado de
     * 256x256 recortado por el centro.
     *
     * Se recorta por el centro y no se deforma: una foto de carnet apaisada
     * estirada a cuadrado deja a la persona irreconocible.
     */
    function recortar(fichero) {
        return new Promise((resolver, rechazar) => {
            if (!fichero.type.startsWith('image/')) {
                return rechazar(new Error(I18N.t('foto.noEsImagen')));
            }
            // Tope de entrada: no del resultado (que siempre es pequeño), sino
            // de lo que el navegador tiene que decodificar en memoria.
            if (fichero.size > 12 * 1024 * 1024) {
                return rechazar(new Error(I18N.t('foto.demasiado')));
            }

            const lector = new FileReader();
            lector.onerror = () => rechazar(new Error(I18N.t('foto.noSeLee')));
            lector.onload = () => {
                const img = new Image();
                img.onerror = () => rechazar(new Error(I18N.t('foto.noSeDecodifica')));
                img.onload = () => {
                    try {
                        const lienzo = document.createElement('canvas');
                        lienzo.width = lienzo.height = LADO_FOTO;
                        const ctx = lienzo.getContext('2d');

                        // Fondo opaco ANTES de dibujar. El lienzo nace
                        // transparente y WebP conserva el canal alfa: una
                        // imagen con transparencia se guardaba con agujeros y
                        // el avatar se veía a través de ellos. Una foto de
                        // perfil es una foto, no una calcomanía.
                        ctx.fillStyle = '#ffffff';
                        ctx.fillRect(0, 0, LADO_FOTO, LADO_FOTO);

                        const lado = Math.min(img.width, img.height);
                        const x = (img.width - lado) / 2;
                        const y = (img.height - lado) / 2;
                        ctx.drawImage(img, x, y, lado, lado, 0, 0, LADO_FOTO, LADO_FOTO);

                        // WebP pesa la mitad que PNG a la misma calidad. Si el
                        // navegador no lo soporta, toDataURL devuelve PNG y el
                        // tipo se lee del propio resultado, no se supone.
                        const url = lienzo.toDataURL('image/webp', CALIDAD);
                        const tipo = (url.match(/^data:([^;]+);/) || [, 'image/png'])[1];
                        resolver({ tipo, base64: url.split(',')[1] });
                    } catch (err) {
                        rechazar(new Error(I18N.t('foto.noSeProcesa')));
                    }
                };
                img.src = lector.result;
            };
            lector.readAsDataURL(fichero);
        });
    }

    async function elegirFoto(ev) {
        const fichero = ev.target.files && ev.target.files[0];
        // El input se limpia siempre: si no, elegir el mismo fichero dos veces
        // seguidas no dispara 'change' y parece que no funciona.
        ev.target.value = '';
        if (!fichero) return;

        try {
            const { tipo, base64 } = await recortar(fichero);
            await API.subirMiFoto(tipo, base64);
            await refrescarSesion();
            Toast.success(I18N.t('aviso.fotoPuesta'));
            pintar();
        } catch (err) {
            if (err && err.sesionExpirada) return;
            Toast.error(err.message);
        }
    }

    async function quitarFoto() {
        const seguro = await Confirmar.pedir({
            titulo: I18N.t('dlg.foto.titulo'),
            mensaje: I18N.t('dlg.foto.mensaje'),
            aceptar: I18N.t('dlg.foto.si'),
        });
        if (!seguro) return;
        try {
            await API.borrarMiFoto();
            await refrescarSesion();
            Toast.success(I18N.t('aviso.fotoQuitada'));
            pintar();
        } catch (err) {
            if (err && err.sesionExpirada) return;
            Toast.error(err.message);
        }
    }

    /** Relee el usuario del servidor para que el avatar del menú se actualice. */
    async function refrescarSesion() {
        try {
            const yo = await API.getMe();
            API.guardarUsuario(yo);
            APP.pintarUsuario?.();
        } catch (err) {
            if (!(err && err.sesionExpirada)) {
                console.warn('No se pudo releer el perfil:', err.message);
            }
        }
    }

    // ====================================================================
    // Sección: mi perfil
    // ====================================================================

    /**
     * "Mi perfil": una columna, dos fichas, y se rellena de arriba abajo.
     *
     * Antes eran tres fichas en una rejilla que las repartía sola: la foto y
     * los datos quedaban una al lado de la otra, la contraseña se caía a una
     * tercera columna que no existía y debajo de la foto —mucho más baja que
     * el formulario— quedaba un hueco enorme. Para editar había que ir en
     * zigzag.
     *
     * Ahora la foto y los datos son UNA ficha: las dos cosas son "quién soy",
     * se guardan en la misma pantalla y ahora se recorren en orden —foto,
     * nombre, correo, rol, guardar—. La contraseña va aparte y debajo, porque
     * es otra operación con su propio botón: mezclarla con los datos haría
     * dudar de qué guarda cada "Guardar".
     *
     * La columna tiene un ancho máximo. Un campo de texto de 1.200 px de largo
     * para escribir un nombre no es aprovechar la pantalla, es que el ojo
     * pierda de vista dónde empieza la línea.
     */
    function vistaPerfil() {
        const yo = API.getUsuario() || {};
        return `
        <div class="perfil-columna">
            <section class="panel">
                <h3 class="panel-titulo">${esc(I18N.t('perfil.datos'))}</h3>
                <form id="formPerfil" class="perfil-form" autocomplete="off">

                    <div class="perfil-identidad">
                        ${Avatar.render(yo, { tamano: 'lg' })}
                        <div class="perfil-identidad-acciones">
                            <label class="btn btn-secondary" for="fotoInput">${esc(I18N.t('perfil.cambiarFoto'))}</label>
                            <input type="file" id="fotoInput" accept="image/*" hidden>
                            ${yo.tiene_foto
                                ? `<button type="button" class="btn btn-ghost" id="quitarFoto">${esc(I18N.t('perfil.quitarFoto'))}</button>`
                                : ''}
                            <p class="perfil-nota">${esc(I18N.t('perfil.notaFoto', { lado: LADO_FOTO }))}</p>
                        </div>
                    </div>

                    <div class="form-group">
                        <label class="form-label" for="perfilNombre">${esc(I18N.t('perfil.nombre'))}</label>
                        <input class="form-input" id="perfilNombre" maxlength="120"
                               value="${esc(yo.nombre || '')}" required>
                    </div>

                    <div class="form-group">
                        <label class="form-label" for="perfilCorreo">${esc(I18N.t('perfil.correo'))}</label>
                        <input class="form-input" id="perfilCorreo" value="${esc(yo.correo || '')}"
                               disabled title="${esc(I18N.t('perfil.notaCorreo'))}">
                        <p class="perfil-nota">${esc(I18N.t('perfil.notaCorreo'))}</p>
                    </div>

                    <div class="form-group">
                        <label class="form-label">${esc(I18N.t('perfil.rol'))}</label>
                        <p class="perfil-rol"><span class="badge badge-rol">${esc(yo.rol || '—')}</span></p>
                    </div>

                    <div class="perfil-acciones">
                        <button type="submit" class="btn btn-primary">${esc(I18N.t('perfil.guardar'))}</button>
                    </div>
                </form>
            </section>

            <section class="panel">
                <h3 class="panel-titulo">${esc(I18N.t('perfil.password'))}</h3>
                <form id="formPassword" class="perfil-form" autocomplete="off">
                    <div class="form-group">
                        <label class="form-label" for="pwActual">${esc(I18N.t('perfil.pwActual'))}</label>
                        <input class="form-input" id="pwActual" type="password"
                               autocomplete="current-password" required>
                    </div>
                    <!-- data-reglas: debajo del campo sale la lista de lo que
                         tiene que cumplir, y cada requisito se pone en verde
                         solo mientras se escribe (js/components/password.js).
                         Sustituye a la nota de una línea que sólo hablaba de
                         la longitud y callaba las otras dos condiciones. -->
                    <div class="form-group">
                        <label class="form-label" for="pwNueva">${esc(I18N.t('perfil.pwNueva'))}</label>
                        <input class="form-input" id="pwNueva" type="password"
                               autocomplete="new-password" minlength="12" required
                               data-reglas>
                    </div>
                    <div class="form-group">
                        <label class="form-label" for="pwRepetir">${esc(I18N.t('perfil.pwRepetir'))}</label>
                        <input class="form-input" id="pwRepetir" type="password"
                               autocomplete="new-password" required
                               data-reglas data-igual-que="pwNueva">
                    </div>
                    <div class="perfil-acciones">
                        <button type="submit" class="btn btn-primary">${esc(I18N.t('perfil.cambiarPw'))}</button>
                    </div>
                </form>
            </section>
        </div>`;
    }

    async function guardarNombre(ev) {
        ev.preventDefault();
        const nombre = document.getElementById('perfilNombre').value.trim();
        if (!nombre) { Toast.error(I18N.t('aviso.nombreVacio')); return; }
        try {
            await API.cambiarMiNombre(nombre);
            await refrescarSesion();
            Toast.success(I18N.t('aviso.perfilGuardado'));
            pintar();
        } catch (err) {
            if (err && err.sesionExpirada) return;
            Toast.error(err.message);
        }
    }

    async function cambiarPassword(ev) {
        ev.preventDefault();
        const actual = document.getElementById('pwActual').value;
        const nueva = document.getElementById('pwNueva').value;
        const repetir = document.getElementById('pwRepetir').value;

        // Se comprueba aquí y no en el servidor porque el servidor sólo recibe
        // una contraseña nueva: la repetición existe para cazar erratas.
        if (nueva !== repetir) { Toast.error(I18N.t('aviso.pwNoCoinciden')); return; }
        if (nueva === actual)  { Toast.error(I18N.t('aviso.pwIgual')); return; }

        try {
            await API.cambiarPassword(actual, nueva);
            Toast.success(I18N.t('aviso.pwCambiada'));
            document.getElementById('formPassword').reset();
        } catch (err) {
            if (err && err.sesionExpirada) return;
            Toast.error(err.message);
        }
    }

    // ====================================================================
    // Sección: usuarios (admin)
    // ====================================================================
    //
    // Cómo se gestiona una contraseña aquí, de principio a fin:
    //
    //   Alta          se piden correo, nombre y apellido, y rol. La contraseña
    //                 NO se pide: la genera el servidor y se enseña UNA vez en
    //                 un diálogo con "Copiar". Quien administra se la hace
    //                 llegar a la persona.
    //   Primer acceso la persona entra con la temporal y Pohua le pide la
    //                 suya antes de nada (js/components/password.js). Hasta
    //                 que la cambie, en esta lista sale con "Temporary".
    //   Olvido        sólo el administrador restablece: el servidor genera
    //                 otra temporal, se la enseña y, si la persona tiene los
    //                 avisos activados en el teléfono, se la manda ahí con un
    //                 botón. Nadie más ve nunca una contraseña de nadie.
    //
    // Las acciones de cada fila (restablecer, externo, baja) viven en un menú
    // "⋯" y no en tres botones a la vista: tres enlaces de texto por fila se
    // leían como columnas y en el teléfono se comían la ficha.

    const ICONO = {
        puntos: '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>',
        llave:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>',
        globo:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
        baja:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="18" y1="8" x2="23" y2="13"/><line x1="23" y1="8" x2="18" y2="13"/></svg>',
        alta:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><polyline points="17 11 19 13 23 9"/></svg>',
        copiar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
        movil:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg>',
        ok:     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>',
    };

    function filaUsuario(u) {
        const yo = API.getUsuario() || {};
        const soyYo = u.id === yo.id;
        return `
        <tr class="${u.activo ? '' : 'usuario--baja'}" data-usuario="${u.id}">
            <td>
                <div class="usuario-celda">
                    ${Avatar.render(u, { tamano: 'sm' })}
                    <div class="usuario-nombre">
                        <strong>${esc(u.nombre)}${soyYo ? ` <span class="usuario-yo">${esc(I18N.t('usuarios.tu'))}</span>` : ''}</strong>
                        <span class="usuario-correo">${esc(u.correo)}</span>
                        <span class="usuario-marcas">
                            ${u.externo ? `<span class="badge badge-externo" title="${esc(I18N.t('usuarios.externoAyuda'))}">${esc(I18N.t('usuarios.externo'))}</span>` : ''}
                            ${u.debe_cambiar_password ? `<span class="badge badge-temporal" title="${esc(I18N.t('usuarios.temporalAyuda'))}">${esc(I18N.t('usuarios.temporal'))}</span>` : ''}
                        </span>
                    </div>
                </div>
            </td>
            <td data-etiqueta="${esc(I18N.t('usuarios.col.rol'))}">
                <select class="form-select usuario-rol" data-id="${u.id}"
                        ${soyYo ? `disabled title="${esc(I18N.t('usuarios.noTuRol'))}"` : ''}>
                    ${roles.map(r => `<option value="${esc(r.codigo)}"
                        ${r.codigo === u.rol ? 'selected' : ''}>${esc(r.nombre)}</option>`).join('')}
                </select>
            </td>
            <td data-etiqueta="${esc(I18N.t('usuarios.col.acceso'))}">${u.ultimo_acceso ? esc(u.ultimo_acceso.slice(0, 16)) : `<span class="usuario-nunca">${esc(I18N.t('usuarios.nunca'))}</span>`}</td>
            <td data-etiqueta="${esc(I18N.t('usuarios.col.estado'))}">
                <span class="badge ${u.activo ? 'badge-ok' : 'badge-baja'}">
                    ${esc(u.activo ? I18N.t('usuarios.activo') : I18N.t('usuarios.baja'))}
                </span>
            </td>
            <td class="usuario-acciones">
                <button type="button" class="btn-icono usuario-menu-boton" data-menu="${u.id}"
                        aria-haspopup="menu" aria-expanded="false"
                        title="${esc(I18N.t('usuarios.acciones'))}" aria-label="${esc(I18N.t('usuarios.accionesDe', { nombre: u.nombre }))}">
                    ${ICONO.puntos}
                </button>
            </td>
        </tr>`;
    }

    function vistaUsuarios() {
        if (!usuarios.length) {
            return `<section class="panel"><p class="perfil-nota">${esc(I18N.t('usuarios.ninguno'))}</p></section>`;
        }
        return `
        <section class="panel">
            <div class="panel-cabecera">
                <h3 class="panel-titulo">${esc(I18N.t('usuarios.titulo'))}</h3>
                <button type="button" class="btn btn-primary btn-sm" id="btnNuevoUsuario">${esc(I18N.t('usuarios.alta'))}</button>
            </div>
            <p class="perfil-nota usuarios-nota">${esc(I18N.t('usuarios.nota'))}</p>
            <div class="tabla-caja">
                <table class="tabla-usuarios">
                    <thead>
                        <tr><th>${esc(I18N.t('usuarios.col.usuario'))}</th>
                            <th>${esc(I18N.t('usuarios.col.rol'))}</th>
                            <th>${esc(I18N.t('usuarios.col.acceso'))}</th>
                            <th>${esc(I18N.t('usuarios.col.estado'))}</th><th></th></tr>
                    </thead>
                    <tbody>${usuarios.map(filaUsuario).join('')}</tbody>
                </table>
            </div>
        </section>`;
    }

    // ------------------------------------------------------------ el menú ⋯

    let menuAbierto = null;   // { menu, boton } o null

    function cerrarMenu() {
        if (!menuAbierto) return;
        menuAbierto.menu.remove();
        menuAbierto.boton.setAttribute('aria-expanded', 'false');
        menuAbierto = null;
        document.removeEventListener('mousedown', alPulsarFuera, true);
        document.removeEventListener('keydown', alTeclaMenu, true);
        window.removeEventListener('resize', cerrarMenu);
        window.removeEventListener('scroll', seguirMenu, true);
    }

    /** Al desplazar la página el menú sigue a su botón (se recoloca, no se cierra:
     *  en el teléfono la propia llegada al botón desplaza suavemente). */
    function seguirMenu() {
        if (menuAbierto) colocarMenu(menuAbierto.menu, menuAbierto.boton);
    }

    function alPulsarFuera(ev) {
        if (!menuAbierto) return;
        if (menuAbierto.menu.contains(ev.target) || menuAbierto.boton.contains(ev.target)) return;
        cerrarMenu();
    }

    function alTeclaMenu(ev) {
        if (!menuAbierto) return;
        const items = [...menuAbierto.menu.querySelectorAll('[role="menuitem"]:not([disabled])')];
        const i = items.indexOf(document.activeElement);
        if (ev.key === 'Escape') { ev.preventDefault(); const b = menuAbierto.boton; cerrarMenu(); b.focus(); }
        else if (ev.key === 'ArrowDown') { ev.preventDefault(); (items[i + 1] || items[0])?.focus(); }
        else if (ev.key === 'ArrowUp') { ev.preventDefault(); (items[i - 1] || items[items.length - 1])?.focus(); }
        else if (ev.key === 'Tab') { cerrarMenu(); }
    }

    /**
     * El menú de una fila. Se cuelga del <body> y se coloca con `fixed`
     * junto al botón: dentro de la tabla lo recortaría el `overflow` de la
     * caja que la hace deslizable en pantallas estrechas.
     */
    function abrirMenu(boton) {
        const id = Number(boton.dataset.menu);
        const u = usuarios.find(x => x.id === id);
        if (!u) return;
        if (menuAbierto && menuAbierto.boton === boton) { cerrarMenu(); return; }
        cerrarMenu();

        const yo = API.getUsuario() || {};
        const soyYo = u.id === yo.id;
        const item = (accion, icono, texto, { peligro = false, deshabilitado = '', nota = '' } = {}) => `
            <button type="button" role="menuitem" class="acciones-item ${peligro ? 'acciones-item--peligro' : ''}"
                    data-accion="${accion}" data-id="${u.id}"
                    ${deshabilitado ? `disabled title="${esc(deshabilitado)}"` : ''}>
                <span class="acciones-icono">${icono}</span>
                <span class="acciones-texto">${esc(texto)}${nota ? `<small>${esc(nota)}</small>` : ''}</span>
            </button>`;

        const menu = document.createElement('div');
        menu.className = 'acciones-menu';
        menu.setAttribute('role', 'menu');
        menu.innerHTML = `
            <div class="acciones-cabecera">${esc(u.nombre)}</div>
            ${item('password', ICONO.llave, I18N.t('usuarios.resetear'), {
                deshabilitado: soyYo ? I18N.t('usuarios.noTuPw') : '',
                nota: I18N.t('usuarios.resetearNota') })}
            ${item('externo', ICONO.globo,
                u.externo ? I18N.t('usuarios.quitarExterno') : I18N.t('usuarios.marcarExterno'),
                { nota: I18N.t('usuarios.externoNota') })}
            <div class="acciones-separador"></div>
            ${item('baja', u.activo ? ICONO.baja : ICONO.alta,
                u.activo ? I18N.t('usuarios.darBaja') : I18N.t('usuarios.darAlta'),
                { peligro: u.activo, deshabilitado: soyYo ? I18N.t('usuarios.noTuBaja') : '',
                  nota: I18N.t(u.activo ? 'usuarios.darBajaNota' : 'usuarios.darAltaNota') })}`;

        menu.addEventListener('click', (ev) => {
            const b = ev.target.closest('[data-accion]');
            if (!b || b.disabled) return;
            const accion = b.dataset.accion;
            cerrarMenu();
            if (accion === 'baja') alternarBaja(id);
            else if (accion === 'password') resetear(id);
            else if (accion === 'externo') alternarExterno(id);
        });

        document.body.appendChild(menu);
        colocarMenu(menu, boton);
        boton.setAttribute('aria-expanded', 'true');
        menuAbierto = { menu, boton };
        document.addEventListener('mousedown', alPulsarFuera, true);
        document.addEventListener('keydown', alTeclaMenu, true);
        window.addEventListener('resize', cerrarMenu);
        window.addEventListener('scroll', seguirMenu, true);
        requestAnimationFrame(() => menu.querySelector('[role="menuitem"]:not([disabled])')?.focus({ preventScroll: true }));
    }

    function colocarMenu(menu, boton) {
        const r = boton.getBoundingClientRect();
        const ancho = menu.offsetWidth, alto = menu.offsetHeight;
        const margen = 8;
        // Alineado al borde derecho del botón; si no cabe abajo, arriba.
        let x = Math.min(r.right - ancho, window.innerWidth - ancho - margen);
        x = Math.max(margen, x);
        let y = r.bottom + 6;
        if (y + alto > window.innerHeight - margen) y = Math.max(margen, r.top - alto - 6);
        menu.style.left = `${Math.round(x)}px`;
        menu.style.top = `${Math.round(y)}px`;
    }

    // ------------------------------------------------------------ alta

    async function nuevoUsuario() {
        const opciones = roles.map(r =>
            `<option value="${esc(r.codigo)}">${esc(r.nombre)}</option>`).join('');
        const datos = await Formulario.pedir({
            titulo: I18N.t('dlg.alta.titulo'),
            mensaje: I18N.t('dlg.alta.mensaje'),
            aceptar: I18N.t('dlg.alta.si'),
            campos: [
                { id: 'correo',   etiqueta: I18N.t('perfil.correo'),   tipo: 'email', requerido: true },
                { id: 'nombre',   etiqueta: I18N.t('dlg.alta.nombre'),  tipo: 'text',  requerido: true },
                { id: 'apellido', etiqueta: I18N.t('dlg.alta.apellido'), tipo: 'text', requerido: true },
                { id: 'rol',      etiqueta: I18N.t('perfil.rol'),      tipo: 'select', opciones },
                { id: 'externo',  etiqueta: I18N.t('usuarios.externoCasilla'), tipo: 'checkbox',
                  nota: I18N.t('usuarios.externoAyuda') },
            ],
        });
        if (!datos) return;

        try {
            const creado = await API.crearUsuario(datos);
            await cargar();
            dialogoTemporal(creado, creado.password_temporal, null);
        } catch (err) {
            if (err && err.sesionExpirada) return;
            Toast.error(err.message);
        }
    }

    // ------------------------------------------------------------ cambios

    async function cambiarRol(select) {
        const id = Number(select.dataset.id);
        const usuario = usuarios.find(u => u.id === id);
        const nuevo = select.value;
        if (!usuario || nuevo === usuario.rol) return;

        const seguro = await Confirmar.pedir({
            titulo: I18N.t('dlg.rol.titulo'),
            mensaje: I18N.t('dlg.rol.mensaje', { nombre: usuario.nombre, rol: nuevo }),
            aceptar: I18N.t('dlg.rol.si'),
        });
        if (!seguro) { select.value = usuario.rol; return; }

        try {
            await API.cambiarUsuario(id, { rol: nuevo });
            Toast.success(I18N.t('aviso.rolCambiado'));
            await cargar();
        } catch (err) {
            if (err && err.sesionExpirada) return;
            select.value = usuario.rol;
            Toast.error(err.message);
        }
    }

    async function alternarBaja(id) {
        const usuario = usuarios.find(u => u.id === id);
        if (!usuario) return;

        const dando = !usuario.activo;
        const seguro = await Confirmar.pedir({
            titulo: I18N.t(dando ? 'dlg.alta2.titulo' : 'dlg.baja.titulo'),
            mensaje: I18N.t(dando ? 'dlg.alta2.mensaje' : 'dlg.baja.mensaje',
                            { nombre: usuario.nombre }),
            aceptar: I18N.t(dando ? 'usuarios.darAlta' : 'usuarios.darBaja'),
            peligro: !dando,
        });
        if (!seguro) return;

        try {
            await API.cambiarUsuario(id, { activo: dando });
            Toast.success(I18N.t(dando ? 'aviso.usuarioActivado' : 'aviso.usuarioDesactivado'));
            await cargar();
        } catch (err) {
            if (err && err.sesionExpirada) return;
            Toast.error(err.message);
        }
    }

    /**
     * Pone o quita la marca de externo.
     *
     * Sin diálogo de confirmación: no cambia lo que la persona puede hacer
     * —eso lo decide el rol— y se deshace con el mismo botón. Pedir permiso
     * para algo reversible y sin consecuencias sólo entorpece.
     */
    async function alternarExterno(id) {
        const usuario = usuarios.find(u => u.id === id);
        if (!usuario) return;
        const nuevo = !usuario.externo;
        try {
            await API.cambiarUsuario(id, { externo: nuevo });
            Toast.success(I18N.t(nuevo ? 'aviso.marcadoExterno' : 'aviso.desmarcadoExterno',
                                 { nombre: usuario.nombre }));
            await cargar();
        } catch (err) {
            if (err && err.sesionExpirada) return;
            Toast.error(err.message);
        }
    }

    // ------------------------------------------------------------ contraseña

    /**
     * Restablecer: se confirma (la actual deja de valer), el servidor genera
     * la temporal y se enseña en el diálogo de abajo, con "Copiar" y "Mandar
     * al teléfono". La casilla del diálogo de confirmación la manda ya en el
     * mismo viaje.
     */
    async function resetear(id) {
        const usuario = usuarios.find(u => u.id === id);
        if (!usuario) return;

        const datos = await Formulario.pedir({
            titulo: I18N.t('dlg.reset.titulo'),
            mensaje: I18N.t('dlg.reset.mensaje', { nombre: usuario.nombre }),
            aceptar: I18N.t('dlg.reset.si'),
            campos: [
                { id: 'notificar', etiqueta: I18N.t('dlg.reset.notificar', { nombre: usuario.nombre }),
                  tipo: 'checkbox', valor: true, nota: I18N.t('dlg.reset.notificarNota') },
            ],
        });
        if (!datos) return;

        try {
            const r = await API.restablecerPassword(id, datos.notificar);
            await cargar();
            dialogoTemporal(usuario, r.password_temporal, r.notificada ? r : null);
        } catch (err) {
            if (err && err.sesionExpirada) return;
            Toast.error(err.message);
        }
    }

    async function copiar(texto) {
        try {
            if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(texto);
            } else {
                const t = document.createElement('textarea');
                t.value = texto; t.setAttribute('readonly', '');
                t.style.position = 'fixed'; t.style.opacity = '0';
                document.body.appendChild(t); t.select();
                document.execCommand('copy'); t.remove();
            }
            return true;
        } catch (_) { return false; }
    }

    /**
     * La contraseña temporal, a la vista una sola vez.
     *
     * `envio` es el resultado de mandarla al teléfono, si ya se mandó al
     * restablecer; si no, el diálogo ofrece mandarla. Se cierra sólo con el
     * botón: un clic fuera no debe llevarse una contraseña que todavía no se
     * ha copiado.
     */
    function dialogoTemporal(usuario, password, envio) {
        const fondo = document.createElement('div');
        fondo.className = 'dialogo-fondo';
        const idTitulo = 'dlg-pw-' + Date.now();
        fondo.innerHTML = `
            <div class="dialogo dialogo--temporal" role="dialog" aria-modal="true" aria-labelledby="${idTitulo}">
                <div class="dialogo-cabecera">
                    <span class="dialogo-icono">${ICONO.llave}</span>
                    <h2 class="dialogo-titulo" id="${idTitulo}">${esc(I18N.t('dlg.temporal.titulo', { nombre: usuario.nombre }))}</h2>
                </div>
                <p class="dialogo-mensaje">${esc(I18N.t('dlg.temporal.mensaje', { nombre: usuario.nombre }))}</p>
                <div class="pw-temporal">
                    <code class="pw-temporal-valor" id="pwTemporalValor">${esc(password)}</code>
                    <button type="button" class="btn btn-secondary btn-sm" data-pw="copiar">${ICONO.copiar}<span>${esc(I18N.t('dlg.temporal.copiar'))}</span></button>
                </div>
                <div class="pw-temporal-envio" id="pwTemporalEnvio"></div>
                <div class="dialogo-acciones">
                    <button type="button" class="btn btn-ghost" data-pw="notificar">${ICONO.movil}<span>${esc(I18N.t('dlg.temporal.notificar'))}</span></button>
                    <button type="button" class="btn btn-primary" data-pw="cerrar">${esc(I18N.t('dlg.temporal.listo'))}</button>
                </div>
            </div>`;
        document.body.appendChild(fondo);

        const estado = fondo.querySelector('#pwTemporalEnvio');
        const btnNotificar = fondo.querySelector('[data-pw="notificar"]');
        const btnCopiar = fondo.querySelector('[data-pw="copiar"]');
        const focoPrevio = document.activeElement;

        function pintarEnvio(r) {
            if (!r) { estado.innerHTML = `<p class="dialogo-nota">${esc(I18N.t('dlg.temporal.enPersona'))}</p>`; return; }
            if (r.dispositivos === 0) {
                estado.innerHTML = `<p class="dialogo-nota pw-temporal-aviso">${esc(I18N.t('dlg.temporal.sinDispositivos', { nombre: usuario.nombre }))}</p>`;
                btnNotificar.disabled = true;
                return;
            }
            const ok = r.entregados > 0;
            estado.innerHTML = `<p class="dialogo-nota ${ok ? 'pw-temporal-ok' : 'pw-temporal-aviso'}">${ok ? ICONO.ok : ''} ${
                esc(I18N.t(ok ? 'dlg.temporal.enviada' : 'dlg.temporal.noLlego', { n: r.entregados, total: r.dispositivos }))}</p>`;
            if (ok) btnNotificar.disabled = true;
        }
        pintarEnvio(envio);

        function cerrar() {
            document.removeEventListener('keydown', alTecla, true);
            fondo.classList.add('cerrando');
            setTimeout(() => fondo.remove(), 150);
            if (focoPrevio && focoPrevio.focus) focoPrevio.focus({ preventScroll: true });
        }
        function alTecla(ev) {
            if (ev.key === 'Escape') { ev.preventDefault(); cerrar(); }
        }

        btnCopiar.addEventListener('click', async () => {
            const ok = await copiar(password);
            Toast[ok ? 'success' : 'warning'](I18N.t(ok ? 'dlg.temporal.copiada' : 'dlg.temporal.noCopiada'));
        });
        btnNotificar.addEventListener('click', async () => {
            btnNotificar.disabled = true;
            try {
                const r = await API.notificarPassword(usuario.id, password);
                pintarEnvio(r);
                if (r.dispositivos > 0 && r.entregados === 0) btnNotificar.disabled = false;
            } catch (err) {
                if (err && err.sesionExpirada) return;
                Toast.error(err.message);
                btnNotificar.disabled = false;
            }
        });
        fondo.querySelector('[data-pw="cerrar"]').addEventListener('click', cerrar);
        document.addEventListener('keydown', alTecla, true);
        requestAnimationFrame(() => btnCopiar.focus({ preventScroll: true }));
    }

    // ====================================================================
    // Sección: sistema (admin, sólo lectura)
    // ====================================================================

    let configuracion = null;

    function vistaSistema() {
        if (!configuracion) {
            return `<section class="panel"><p class="perfil-nota">${esc(I18N.t('sistema.cargando'))}</p></section>`;
        }
        const filas = configuracion.entradas.map(e => `
            <tr>
                <td><code>${esc(e.clave)}</code></td>
                <td class="config-valor ${e.vacio ? 'config-valor--vacio' : ''}">
                    ${e.vacio
                        ? `<em>${esc(I18N.t('sistema.sinPoner'))}</em>`
                        : (e.sensible ? '<span class="config-oculto">••••••••</span>' : esc(e.valor))}
                </td>
            </tr>`).join('');

        // El estado del esquema. Va arriba y no abajo: cuando algo falla al
        // leer o guardar, saber si la base se quedó atrás respecto al código es
        // lo primero que hay que mirar, no lo último.
        const esquema = configuracion.esquema || {};
        let aviso = '';
        if (esquema.disponible === false) {
            aviso = `<p class="perfil-nota perfil-nota--alerta">${
                esc(I18N.t('sistema.esquemaSinLeer', { motivo: esquema.motivo || '' }))}</p>`;
        } else if ((esquema.pendientes || []).length) {
            aviso = `<p class="perfil-nota perfil-nota--alerta">${
                esc(I18N.t('sistema.esquemaAtrasado', {
                    n: esquema.pendientes.length,
                    archivos: esquema.pendientes.join(', '),
                }))}</p>`;
        } else if ((esquema.aplicadas || []).length) {
            aviso = `<p class="perfil-nota perfil-nota--ok">${
                esc(I18N.t('sistema.esquemaAlDia', { n: esquema.aplicadas.length }))}</p>`;
        }

        return `
        <section class="panel">
            <h3 class="panel-titulo">${esc(I18N.t('sistema.titulo'))}</h3>
            ${aviso}
            <p class="perfil-nota perfil-nota--destacada">${esc(configuracion.nota)}</p>
            <div class="tabla-caja">
                <table class="tabla-config">
                    <thead><tr><th>${esc(I18N.t('sistema.ajuste'))}</th><th>${esc(I18N.t('sistema.valor'))}</th></tr></thead>
                    <tbody>${filas}</tbody>
                </table>
            </div>
        </section>`;
    }

    // ====================================================================
    // Montaje
    // ====================================================================

    function pestanas() {
        const items = [['perfil', I18N.t('perfil.tab.mio')]];
        if (puedeGestionar()) {
            items.push(['usuarios', I18N.t('perfil.tab.usuarios')],
                       ['sistema',  I18N.t('perfil.tab.sistema')]);
        }
        if (items.length === 1) return '';   // sin pestañas si sólo hay una
        return `<nav class="perfil-tabs" role="tablist">
            ${items.map(([clave, texto]) => `
                <button type="button" class="perfil-tab ${seccion === clave ? 'active' : ''}"
                        data-seccion="${clave}" role="tab"
                        aria-selected="${seccion === clave}">${esc(texto)}</button>`).join('')}
        </nav>`;
    }

    function pintar() {
        const cuerpo = document.getElementById('perfilCuerpo');
        if (!cuerpo) return;
        cerrarMenu();
        const tabs = document.getElementById('perfilTabs');
        if (tabs) tabs.outerHTML = `<div id="perfilTabs">${pestanas()}</div>`;

        cuerpo.innerHTML = seccion === 'usuarios' ? vistaUsuarios()
                         : seccion === 'sistema'  ? vistaSistema()
                         : vistaPerfil();

        if (seccion === 'perfil') {
            document.getElementById('fotoInput')?.addEventListener('change', elegirFoto);
            document.getElementById('quitarFoto')?.addEventListener('click', quitarFoto);
            document.getElementById('formPerfil')?.addEventListener('submit', guardarNombre);
            document.getElementById('formPassword')?.addEventListener('submit', cambiarPassword);
        }
    }

    async function cargar() {
        if (!puedeGestionar()) return;
        try {
            const [u, r] = await Promise.all([API.listarUsuarios(), API.listarRoles()]);
            usuarios = u;
            roles = r;
        } catch (err) {
            if (err && err.sesionExpirada) return;
            Toast.error(I18N.t('aviso.usuariosFallo', { motivo: err.message }));
        }
        if (seccion === 'usuarios') pintar();
    }

    async function cargarConfiguracion() {
        if (!puedeGestionar()) return;
        try {
            configuracion = await API.configuracionSistema();
        } catch (err) {
            if (err && err.sesionExpirada) return;
            Toast.error(I18N.t('aviso.configFallo', { motivo: err.message }));
        }
        if (seccion === 'sistema') pintar();
    }

    async function render(contenedor) {
        seccion = 'perfil';

        // El subtítulo dice la verdad según quién mire: a un pm no se le
        // anuncian "users and system settings" que no va a ver.
        const sub = document.getElementById('pageSubtitle');
        if (sub) {
            sub.textContent = I18N.t(puedeGestionar()
                ? 'pagina.perfil.subAdmin' : 'pagina.perfil.sub');
        }

        contenedor.innerHTML = `
            <div id="perfilTabs">${pestanas()}</div>
            <div id="perfilCuerpo"></div>`;

        // Delegación desde el contenedor: las secciones se repintan enteras, así
        // que enganchar a cada botón obligaría a reenganchar en cada repintado.
        //
        // UNA sola vez por contenedor: render() vuelve a llamarse cada vez que
        // se entra en la página (desde el menú de arriba, por ejemplo), y
        // colgar un segundo oyente hacía que cada clic se atendiera dos veces:
        // el menú "⋯" se abría y se cerraba en el mismo clic.
        if (contenedor.dataset.perfilOyentes) { pintar(); cargar(); cargarConfiguracion(); return; }
        contenedor.dataset.perfilOyentes = '1';
        contenedor.addEventListener('click', async (ev) => {
            const tab = ev.target.closest('.perfil-tab');
            if (tab) {
                seccion = tab.dataset.seccion;
                if (seccion === 'usuarios' && !usuarios.length) await cargar();
                if (seccion === 'sistema' && !configuracion) await cargarConfiguracion();
                pintar();
                return;
            }
            if (ev.target.closest('#btnNuevoUsuario')) return nuevoUsuario();

            const menu = ev.target.closest('[data-menu]');
            if (menu) { ev.preventDefault(); return abrirMenu(menu); }
        });

        contenedor.addEventListener('change', (ev) => {
            const select = ev.target.closest('.usuario-rol');
            if (select) cambiarRol(select);
        });

        pintar();
        // Se precargan en segundo plano para que las pestañas no parpadeen.
        cargar();
        cargarConfiguracion();
    }

    /** Al salir de la página no puede quedar un menú colgado del <body>. */
    function detener() { cerrarMenu(); }

    return { render, detener };
})();
