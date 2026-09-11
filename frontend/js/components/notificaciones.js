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
                <span class="notif-item-cliente">${esc(p.cliente_id || '—')}${
                    p.part_number ? ' · ' + esc(p.part_number) : ''}</span>
                <span class="notif-item-motivo">${esc(p.bandera || p.estado || '')}</span>
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
        return d.toLocaleDateString(I18N.locale ? I18N.locale() : undefined,
                                    { day: 'numeric', month: 'short' });
    }

    function pintarPanel() {
        const p = panel();
        if (!p) return;

        const hayAvisos = !!(avisos && avisos.avisos && avisos.avisos.length);
        const hayCola = !!(datos && datos.pendientes && datos.pendientes.length);

        const cabecera = (cuenta) => `
            <div class="notif-cabecera">
                <span class="notif-titulo" id="notifTitulo">${esc(I18N.t('notif.titulo'))}</span>
                ${cuenta ? `<span class="notif-cuenta">${esc(cuenta)}</span>` : ''}
                ${hayAvisos ? `<button type="button" class="notif-leertodo" data-leertodo>
                        ${esc(I18N.t('notif.leerTodo'))}</button>` : ''}
                ${botonCerrar()}
            </div>`;

        // Al pie, siempre: los avisos en este dispositivo (Web Push). Lo pinta
        // y lo maneja js/components/push.js; aquí sólo se le deja el hueco.
        const pie = (typeof Push !== 'undefined' && API.puede('notificaciones:ver')) ? Push.pie() : '';
        const pintarPie = () => { if (pie) Push.pintarPie(); };

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
                  + `<div class="notif-lista">${datos.pendientes.map(fila).join('')}</div>`
                : '')
            + pie;
        pintarPie();
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

            if (buzon.status === 'fulfilled') avisos = buzon.value;
            else if (buzon.reason && buzon.reason.sesionExpirada) return;

            pintarGlobo();
            if (abierto) pintarPanel();
        } catch (err) {
            if (err && err.sesionExpirada) return;
            // Un fallo del sondeo no se avisa: la campana se queda como estaba.
            console.warn('No se pudieron leer las notificaciones:', err.message);
        } finally {
            cargando = false;
        }
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
        const c = caja();
        if (c) c.hidden = true;
    }

    return { init, refrescar, limpiar };
})();
