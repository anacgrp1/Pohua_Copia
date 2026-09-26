/**
 * Notificaciones: la campana de la esquina, a la izquierda del idioma.
 *
 * Qué avisa y qué NO. Avisa de lo único que en este sistema espera a una
 * persona: RFQs parados en revisión o con banderas. Eso ya lo sabe la base y lo
 * sirve `GET /api/assistant/attention`, ordenado por gravedad y por antigüedad;
 * no hay consulta nueva ni llamada a ninguna IA, así que la campana no cuesta
 * nada tenerla encendida.
 *
 * No inventa categorías. Una campana que además dijera "nuevo correo",
 * "cotización enviada" o "sistema actualizado" estaría enseñando avisos que
 * nadie genera; sonaría a producto terminado y no avisaría de nada real.
 *
 * El número del globo es el de RFQs que esperan, y cuando hay críticas el globo
 * se pinta del color de error. Si no hay nada, no hay globo: una campana con un
 * cero permanente se deja de mirar a los dos días.
 *
 * Sólo existe con la sesión abierta —en la portada y en el login no hay nada de
 * lo que avisar— y sólo para quien puede ver RFQs.
 */
const Notificaciones = (() => {
    'use strict';

    const REFRESCO_MS = 60000;   // un minuto: son cosas de días, no de segundos

    let abierto = false;
    let temporizador = null;
    let datos = null;      // la cola de espera (/api/assistant/attention)
    let avisos = null;     // el buzón de avisos (/api/notificaciones)
    let cargando = false;
    let vistos = null;     // los ids de avisos ya conocidos, para el sonido

    function esc(valor) {
        const nodo = document.createElement('span');
        nodo.textContent = valor == null ? '' : String(valor);
        return nodo.innerHTML;
    }

    const caja   = () => document.getElementById('notificaciones');
    const boton  = () => document.getElementById('btnNotificaciones');
    const panel  = () => document.getElementById('notifPanel');
    const globo  = () => document.getElementById('notifGlobo');

    /** En el teléfono el panel es un cajón que entra por la derecha. */
    const enTelefono = () =>
        window.matchMedia && window.matchMedia('(max-width: 768px)').matches;

    // ------------------------------------------------------------- contenido

    function pintarGlobo() {
        const g = globo();
        const b = boton();
        if (!g || !b) return;

        // El globo cuenta AVISOS cuando el usuario los recibe, y sólo cae a la
        // cola de espera si no tiene el permiso.
        //
        // No se suman: un RFQ que sale a revisión genera un aviso Y entra en la
        // cola, así que sumarlos contaría dos veces lo mismo. De los dos, el
        // aviso es el que responde a lo que pregunta una campana —qué hay
        // nuevo desde que miré—, porque se marca como leído; la cola no,
        // porque un RFQ sale de ella cuando se resuelve, no cuando lo ves.
        const fuente = avisos || datos;
        const total = fuente ? fuente.total : 0;
        const criticas = fuente ? fuente.criticas : 0;

        g.hidden = !total;
        // Más de 9 se queda en "9+": tres cifras no caben en el globo y el
        // número exacto no cambia lo que hay que hacer.
        g.textContent = total > 9 ? '9+' : String(total);
        g.classList.toggle('notif-globo--critico', criticas > 0);

        b.setAttribute('aria-label', total
            ? I18N.t('notif.pendientes', { n: total })
            : I18N.t('notif.vacio'));
        b.setAttribute('title', b.getAttribute('aria-label'));
    }

    function fila(p) {
        const dias = Number(p.dias_esperando) || 0;
        const nivel = p.criticas ? 'critico' : (p.avisos ? 'aviso' : 'normal');
        return `
            <button type="button" class="notif-item notif-item--${nivel}"
                    data-rfq="${esc(p.rfq_id)}">
                <span class="notif-item-cabecera">
                    <span class="notif-item-rfq">${esc(p.rfq_id)}</span>
                    <span class="notif-item-dias">${esc(I18N.t('notif.dias', { n: dias }))}</span>
                </span>
                <span class="notif-item-cliente">${esc(p.cliente_nombre || p.cliente_id || '—')}${
                    p.part_number ? ' · ' + esc(p.part_number) : ''}</span>
                <span class="notif-item-motivo">${esc(p.bandera
                    || I18N.t('motivo.' + (p.motivo === 'validacion' ? 'validacion' : 'revision')))}</span>
            </button>`;
    }

    /** Una fila del buzón de avisos (COT-77). */
    function filaAviso(a) {
        const nivel = a.nivel === 'crit' ? 'critico'
                    : (a.nivel === 'warn' ? 'aviso' : 'normal');
        return `
            <button type="button" class="notif-item notif-item--${nivel}"
                    data-rfq="${esc(a.rfq_id)}" data-aviso="${esc(a.id)}">
                <span class="notif-item-cabecera">
                    <span class="notif-item-rfq">${esc(a.rfq_id)}</span>
                    <span class="notif-item-dias">${esc(fecha(a.creada_en))}</span>
                </span>
                <span class="notif-item-cliente">${esc(a.titulo)}</span>
                <span class="notif-item-motivo">${esc(a.detalle || '')}</span>
            </button>`;
    }

    /** La fecha del aviso, corta y en el idioma activo. */
    function fecha(iso) {
        if (!iso) return '';
        const d = new Date(iso);
        if (isNaN(d)) return '';
        return d.toLocaleDateString(I18N.locale || undefined,
                                    { day: 'numeric', month: 'short' });
    }

    function pintarPanel() {
        const p = panel();
        if (!p) return;

        const hayAvisos = !!(avisos && avisos.avisos && avisos.avisos.length);
        // La cola son TODOS los RFQ sin dictamen. Los que ya tienen su aviso
        // arriba no se repiten abajo: el mismo RFQ dos veces en la campana
        // es ruido, no información.
        const avisados = new Set(hayAvisos ? avisos.avisos.map((a) => a.rfq_id) : []);
        const cola = ((datos && datos.pendientes) || []).filter((p) => !avisados.has(p.rfq_id));
        const hayCola = cola.length > 0;

        const cabecera = (cuenta) => `
            <div class="notif-cabecera">
                <span class="notif-titulo" id="notifTitulo">${esc(I18N.t('notif.titulo'))}</span>
                ${cuenta ? `<span class="notif-cuenta">${esc(cuenta)}</span>` : ''}
                ${hayAvisos ? `<button type="button" class="notif-leertodo" data-leertodo>
                        ${esc(I18N.t('notif.leerTodo'))}</button>` : ''}
                ${botonCerrar()}
            </div>`;

        // Al pie, siempre: el sonido de este equipo y los avisos en este
        // dispositivo (Web Push). El de push lo pinta y lo maneja
        // js/components/push.js; aquí sólo se le deja el hueco.
        const hayPush = typeof Push !== 'undefined' && API.puede('notificaciones:ver');
        const pie = pieSonido() + (hayPush ? Push.pie() : '');
        // OJO: la condición es `hayPush`, no `pie`. Desde que el pie lleva
        // también el sonido, `pie` nunca está vacío, y con `if (pie)` se
        // llamaba a Push.pintarPie() en navegadores sin push: un
        // TypeError que se llevaba por delante el repintado del panel.
        const pintarPie = () => { if (hayPush) Push.pintarPie(); };

        if (cargando && !datos && !avisos) {
            p.innerHTML = cabecera('') + `<p class="notif-vacio">${
                esc(I18N.t('notif.cargando'))}</p>` + pie;
            pintarPie();
            return;
        }
        if (!hayAvisos && !hayCola) {
            p.innerHTML = cabecera('') + `<p class="notif-vacio">${
                esc(I18N.t('notif.vacio'))}</p>` + pie;
            pintarPie();
            return;
        }

        // Dos secciones, y sólo se pinta el rótulo cuando están las dos: con
        // una sola lista, un encabezado encima de otro encabezado es ruido.
        const dos = hayAvisos && hayCola;
        const rotulo = (clave) => dos
            ? `<p class="notif-seccion">${esc(I18N.t(clave))}</p>` : '';

        const cuenta = avisos ? I18N.t('notif.pendientes', { n: avisos.total })
                              : (datos ? I18N.t('notif.pendientes', { n: datos.total }) : '');

        p.innerHTML = cabecera(cuenta)
            + (hayAvisos
                ? rotulo('notif.avisos')
                  + `<div class="notif-lista">${avisos.avisos.map(filaAviso).join('')}</div>`
                : '')
            + (hayCola
                ? rotulo('notif.cola')
                  + `<div class="notif-lista">${cola.map(fila).join('')}</div>`
                : '')
            + pie;
        pintarPie();
    }

    /**
     * El sonido, al pie del panel: interruptor y una prueba.
     *
     * Va aquí y no en Perfil porque es del EQUIPO, no de la cuenta: la misma
     * persona quiere sonido en su máquina y silencio en la de la sala de
     * juntas. Y porque se decide justo cuando molesta, que es mirando la
     * campana.
     */
    function pieSonido() {
        if (typeof Sonido === 'undefined') return '';
        const activo = Sonido.encendido();
        const icono = activo
            ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M19 5a9 9 0 0 1 0 14"/></svg>`
            : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>`;
        return `<div class="notif-pie" id="notifSonidoPie">
            ${icono}
            <span class="notif-pie-texto">${esc(I18N.t(activo ? 'sonido.activo' : 'sonido.apagado'))}</span>
            ${activo ? `<button type="button" class="notif-pie-boton" data-sonido="probar"
                        title="${esc(I18N.t('sonido.probarTitulo'))}">${esc(I18N.t('sonido.probar'))}</button>` : ''}
            <button type="button" class="notif-pie-boton${activo ? '' : ' notif-pie-boton--primario'}"
                    data-sonido="alternar">${esc(I18N.t(activo ? 'sonido.apagar' : 'sonido.encender'))}</button>
        </div>`;
    }

    /**
     * La ✕ del cajón. Sólo se pinta —y el CSS sólo la enseña— en el teléfono:
     * en computadora el panel se cierra pulsando fuera, como cualquier
     * desplegable, y una aspa ahí sobraría.
     */
    function botonCerrar() {
        return `<button type="button" class="notif-cerrar" data-cerrar
                        aria-label="${esc(I18N.t('notif.cerrar'))}"
                        title="${esc(I18N.t('notif.cerrar'))}">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                         stroke-width="2" stroke-linecap="round" aria-hidden="true">
                        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                </button>`;
    }

    // ------------------------------------------------------------- datos

    async function refrescar() {
        if (cargando) return;
        if (!API.getToken() || !API.puede('rfq:leer')) return;
        cargando = true;
        try {
            // `allSettled` y no `all`: son dos fuentes independientes y una
            // caída no debe llevarse por delante la otra. Si el buzón de
            // avisos falla, la campana sigue enseñando la cola de espera.
            const puedeAvisos = API.puede('notificaciones:ver');
            const [cola, buzon] = await Promise.allSettled([
                API.assistantAttention(),
                puedeAvisos ? API.notificaciones(true, 20) : Promise.resolve(null),
            ]);

            if (cola.status === 'fulfilled') datos = cola.value;
            else if (cola.reason && cola.reason.sesionExpirada) return;

            if (buzon.status === 'fulfilled') { avisos = buzon.value; sonarLoNuevo(); }
            else if (buzon.reason && buzon.reason.sesionExpirada) return;

            pintarGlobo();
            if (abierto) pintarPanel();
            if (cola.status === 'fulfilled' && (!puedeAvisos || buzon.status === 'fulfilled')) {
                cerrarLasDelSistema();
            }
        } catch (err) {
            if (err && err.sesionExpirada) return;
            // Un fallo del sondeo no se avisa: la campana se queda como estaba.
            console.warn('No se pudieron leer las notificaciones:', err.message);
        } finally {
            cargando = false;
        }
    }

    /**
     * Quita del teléfono y del escritorio los avisos de RFQ ya dictaminados.
     *
     * La campana se vacía sola al aprobar o declinar (el servidor da sus
     * avisos por atendidos), pero la notificación que el sistema pintó por
     * Web Push se quedaba en el centro de notificaciones —y con
     * `requireInteraction`, sin irse nunca—. Aquí se cierra toda la que sea de
     * un RFQ que ya no espera nada: ni aviso pendiente ni sitio en la cola.
     */
    async function cerrarLasDelSistema() {
        try {
            if (!('serviceWorker' in navigator)) return;
            const registro = await navigator.serviceWorker.getRegistration();
            if (!registro || !registro.getNotifications) return;
            const vivos = new Set();
            ((avisos && avisos.avisos) || []).forEach((a) => a.rfq_id && vivos.add(a.rfq_id));
            ((datos && datos.pendientes) || []).forEach((p) => p.rfq_id && vivos.add(p.rfq_id));
            const pintadas = await registro.getNotifications();
            pintadas.forEach((n) => {
                const rfq = n.data && n.data.rfq_id;
                if (rfq && !vivos.has(rfq)) n.close();
            });
        } catch (_) { /* sin service worker, no hay nada que cerrar */ }
    }

    /**
     * Suena si ha llegado un aviso que no estaba en el sondeo anterior.
     *
     * Se comparan IDS y no el total: si alguien marca uno como leído y llega
     * otro en el mismo minuto, el total no se mueve y el aviso nuevo pasaría
     * callado. Con los ids eso no ocurre.
     *
     * La primera vuelta no suena. Al entrar por la mañana hay avisos
     * esperando desde ayer y no son novedad; que la aplicación salude con un
     * tono cada vez que se recarga la página es justo la forma de que alguien
     * apague el sonido el primer día.
     *
     * De varios a la vez manda el más grave: un crítico entre tres normales
     * tiene que sonar a crítico.
     */
    function sonarLoNuevo() {
        const lista = (avisos && avisos.avisos) || [];
        const ahora = new Set(lista.map(a => a.id));

        if (vistos === null) { vistos = ahora; return; }

        const nuevos = lista.filter(a => !vistos.has(a.id));
        vistos = ahora;
        if (!nuevos.length) return;
        if (typeof Sonido === 'undefined') return;

        Sonido.sonar(nuevos.some(a => a.nivel === 'crit') ? 'crit' : 'aviso');
    }

    // ------------------------------------------------------------- apertura

    /**
     * Abrir y cerrar es una clase en el contenedor, no `hidden` en el panel.
     *
     * Con `hidden` el navegador pone display:none y una transición sobre algo
     * que no se está pintando no ocurre: el cajón del teléfono aparecería de
     * golpe en vez de entrar deslizándose. Con la clase, el panel sigue en el
     * árbol y se mueve con transform; en computadora esa misma clase hace de
     * interruptor del display, que es lo que quiere un desplegable.
     */
    function abrir() {
        const c = caja();
        if (!c) return;
        pintarPanel();
        c.classList.add('notif--abierto');
        abierto = true;
        boton()?.setAttribute('aria-expanded', 'true');
        // El cajón ocupa la pantalla: detrás no se desplaza nada.
        if (enTelefono()) document.body.classList.add('notif-abierta');
        refrescar();
    }

    function cerrar({ devolverFoco = false } = {}) {
        const c = caja();
        if (!c || !abierto) return;
        c.classList.remove('notif--abierto');
        document.body.classList.remove('notif-abierta');
        abierto = false;
        boton()?.setAttribute('aria-expanded', 'false');
        if (devolverFoco) boton()?.focus({ preventScroll: true });
    }

    /**
     * Marcar como leído es optimista: se quita de la lista y se baja el globo
     * antes de que el servidor conteste.
     *
     * Es lo correcto aquí porque el usuario ya se fue al RFQ y no va a ver el
     * resultado; y si la llamada falla, el siguiente sondeo (un minuto) lo
     * vuelve a traer. Esperar sólo lograría que la campana se quedase con el
     * número viejo mientras se pinta otra pantalla.
     */
    async function marcarLeido(id) {
        if (!id || !avisos) return;
        avisos = {
            ...avisos,
            total: Math.max(0, avisos.total - 1),
            avisos: avisos.avisos.filter((a) => a.id !== id),
        };
        pintarGlobo();
        try {
            await API.notificacionLeer(id);
        } catch (err) {
            if (err && err.sesionExpirada) return;
            console.warn('No se pudo marcar el aviso como leído:', err.message);
        }
    }

    async function leerTodo() {
        if (!avisos) return;
        avisos = { total: 0, criticas: 0, avisos: [] };
        pintarGlobo();
        pintarPanel();
        try {
            await API.notificacionesLeerTodo();
        } catch (err) {
            if (err && err.sesionExpirada) return;
            console.warn('No se pudieron marcar los avisos:', err.message);
            refrescar();   // se deshace solo: lo que diga el servidor manda
        }
    }

    function irA(rfq) {
        cerrar();
        location.hash = '#/rfq/' + encodeURIComponent(rfq);
    }

    // ------------------------------------------------------------- ciclo

    /** Se llama al entrar y al cambiar de usuario. */
    function init() {
        const c = caja();
        if (!c) return;

        // Aprobado o declinado aquí mismo (js/api.js): la campana se pone al
        // día en el acto, sin esperar al siguiente sondeo.
        if (!init.oyendo) {
            init.oyendo = true;
            window.addEventListener('pohua:rfq-dictaminado', () => setTimeout(refrescar, 300));
        }

        // Sin permiso para ver RFQs no hay nada que notificar, y la campana se
        // queda escondida en vez de enseñar un panel vacío para siempre.
        if (!API.getToken() || !API.puede('rfq:leer')) {
            limpiar();
            return;
        }

        c.hidden = false;
        pintarGlobo();

        if (!init.conectado) {
            init.conectado = true;

            boton()?.addEventListener('click', (ev) => {
                ev.stopPropagation();
                abierto ? cerrar() : abrir();
            });

            panel()?.addEventListener('click', (ev) => {
                const son = ev.target.closest('[data-sonido]');
                if (son) {
                    // Sin esto el panel se cierra solo: al repintarlo aquí,
                    // el botón que se acaba de pulsar deja de estar en el
                    // documento, y cuando el clic llega al manejador de
                    // "clic fuera" su `closest('#notificaciones')` ya da null.
                    ev.stopPropagation();
                    // El clic ya es el gesto que el navegador pide para dejar
                    // sonar, así que la prueba se oye en el mismo momento.
                    if (son.dataset.sonido === 'probar') Sonido.probar('aviso');
                    else if (Sonido.alternar()) Sonido.probar('aviso');
                    pintarPanel();
                    return;
                }
                if (ev.target.closest('[data-cerrar]')) { cerrar({ devolverFoco: true }); return; }
                if (ev.target.closest('[data-leertodo]')) { leerTodo(); return; }
                const item = ev.target.closest('.notif-item');
                if (!item) return;
                // Abrir un aviso lo da por leído. El "cuándo" que se guarda es
                // lo que mide si el buzón se está atendiendo, así que se marca
                // al abrirlo y no al cerrarlo ni en un barrido nocturno.
                if (item.dataset.aviso) marcarLeido(Number(item.dataset.aviso));
                irA(item.dataset.rfq);
            });

            document.getElementById('notifVelo')?.addEventListener('click', () => cerrar());

            // Al pasar de teléfono a computadora (girar el móvil, redimensionar
            // la ventana) el cajón se cierra: abierto, en computadora se
            // quedaría como un desplegable colgando sin que nadie lo pidiera.
            window.addEventListener('resize', () => { if (abierto) cerrar(); },
                                    { passive: true });

            document.addEventListener('click', (ev) => {
                if (abierto && !ev.target.closest('#notificaciones')) cerrar();
            });
            document.addEventListener('keydown', (ev) => {
                if (ev.key === 'Escape' && abierto) cerrar({ devolverFoco: true });
            });

            I18N.alCambiar(() => { pintarGlobo(); if (abierto) pintarPanel(); });

            // Con la pestaña de fondo no se sondea: nadie está mirando.
            document.addEventListener('visibilitychange', () => {
                if (document.hidden) detener(); else arrancar();
            });
        }

        arrancar();
        refrescar();
    }

    function arrancar() {
        if (temporizador !== null) return;
        if (!API.getToken()) return;
        temporizador = setInterval(refrescar, REFRESCO_MS);
    }

    function detener() {
        if (temporizador !== null) { clearInterval(temporizador); temporizador = null; }
    }

    /** Al cerrar sesión: se apaga y se olvida lo que sabía. */
    function limpiar() {
        detener();
        cerrar();
        datos = null;
        avisos = null;
        vistos = null;      // otro usuario, otro buzón: nada es "nuevo" todavía
        const c = caja();
        if (c) c.hidden = true;
    }

    return { init, refrescar, limpiar };
})();
