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

    function filaUsuario(u) {
        const yo = API.getUsuario() || {};
        const soyYo = u.id === yo.id;
        return `
        <tr class="${u.activo ? '' : 'usuario--baja'}">
            <td>
                <div class="usuario-celda">
                    ${Avatar.render(u, { tamano: 'sm' })}
                    <div>
                        <strong>${esc(u.nombre)}</strong>${u.externo
                            ? ` <span class="badge badge-externo"
                                      title="${esc(I18N.t('usuarios.externoAyuda'))}"
                                >${esc(I18N.t('usuarios.externo'))}</span>`
                            : ''}
                        <span class="usuario-correo">${esc(u.correo)}</span>
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
            <td data-etiqueta="${esc(I18N.t('usuarios.col.acceso'))}">${u.ultimo_acceso ? esc(u.ultimo_acceso.slice(0, 16)) : '—'}</td>
            <td data-etiqueta="${esc(I18N.t('usuarios.col.estado'))}">
                <span class="badge ${u.activo ? 'badge-ok' : 'badge-baja'}">
                    ${esc(u.activo ? I18N.t('usuarios.activo') : I18N.t('usuarios.baja'))}
                </span>
            </td>
            <td class="usuario-acciones">
                <button type="button" class="btn btn-ghost btn-sm" data-accion="password" data-id="${u.id}"
                        ${soyYo ? `disabled title="${esc(I18N.t('usuarios.noTuPw'))}"` : ''}>
                    ${esc(I18N.t('usuarios.resetear'))}
                </button>
                <button type="button" class="btn btn-ghost btn-sm" data-accion="externo" data-id="${u.id}"
                        title="${esc(I18N.t('usuarios.externoAyuda'))}">
                    ${esc(u.externo ? I18N.t('usuarios.quitarExterno') : I18N.t('usuarios.marcarExterno'))}
                </button>
                <button type="button" class="btn btn-ghost btn-sm" data-accion="baja" data-id="${u.id}"
                        ${soyYo ? `disabled title="${esc(I18N.t('usuarios.noTuBaja'))}"` : ''}>
                    ${esc(u.activo ? I18N.t('usuarios.darBaja') : I18N.t('usuarios.darAlta'))}
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

    async function nuevoUsuario() {
        const opciones = roles.map(r =>
            `<option value="${esc(r.codigo)}">${esc(r.nombre)}</option>`).join('');
        const datos = await Formulario.pedir({
            titulo: I18N.t('dlg.alta.titulo'),
            mensaje: I18N.t('dlg.alta.mensaje'),
            aceptar: I18N.t('dlg.alta.si'),
            campos: [
                { id: 'correo',   etiqueta: I18N.t('perfil.correo'), tipo: 'email', requerido: true },
                { id: 'nombre',   etiqueta: I18N.t('perfil.nombre'), tipo: 'text',  requerido: true },
                { id: 'rol',      etiqueta: I18N.t('perfil.rol'),    tipo: 'select', opciones },
                { id: 'password', etiqueta: I18N.t('dlg.alta.pwTemp'), tipo: 'password',
                  requerido: true, reglas: true },
                { id: 'externo', etiqueta: I18N.t('usuarios.externoCasilla'), tipo: 'checkbox',
                  nota: I18N.t('usuarios.externoAyuda') },
            ],
        });
        if (!datos) return;

        try {
            await API.crearUsuario(datos);
            Toast.success(I18N.t('aviso.usuarioAlta', { nombre: datos.nombre }));
            await cargar();
        } catch (err) {
            if (err && err.sesionExpirada) return;
            Toast.error(err.message);
        }
    }

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

    async function resetear(id) {
        const usuario = usuarios.find(u => u.id === id);
        if (!usuario) return;

        const nueva = await Confirmar.pedirTexto({
            titulo: I18N.t('dlg.reset.titulo'),
            mensaje: I18N.t('dlg.reset.mensaje', { nombre: usuario.nombre }),
            etiqueta: I18N.t('dlg.reset.campo'),
            marcador: I18N.t('dlg.reset.ejemplo'),
            obligatorio: true,
            // Campo de contraseña, no de texto: sale con su ojo y con la lista
            // de requisitos, igual que el alta. Antes era un cuadro de texto a
            // la vista y sin decir qué hacía falta, así que el primer intento
            // se lo rechazaba el servidor.
            tipo: 'password',
            reglas: true,
            aceptar: I18N.t('dlg.reset.titulo'),
            peligro: true,
        });
        if (nueva === null) return;

        try {
            await API.resetearPassword(id, nueva);
            Toast.success(I18N.t('aviso.pwReseteada', { nombre: usuario.nombre }));
        } catch (err) {
            if (err && err.sesionExpirada) return;
            Toast.error(err.message);
        }
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

            const boton = ev.target.closest('[data-accion]');
            if (!boton) return;
            const id = Number(boton.dataset.id);
            if (boton.dataset.accion === 'baja') return alternarBaja(id);
            if (boton.dataset.accion === 'password') return resetear(id);
            if (boton.dataset.accion === 'externo') return alternarExterno(id);
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

    return { render };
})();
