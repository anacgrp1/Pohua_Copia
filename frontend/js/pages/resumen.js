/**
 * Resumen — "cómo va todo", la pantalla del Plant Manager.
 *
 * La referencia que pidió ISC es un panel de ventas: cuatro cifras arriba a la
 * izquierda, un globo terráqueo a la derecha, una tabla debajo y un par de
 * gráficas. Aquí se conserva la COMPOSICIÓN y se cambia el contenido, porque
 * este sistema no vende: cotiza resortes. Traducción de cada pieza:
 *
 *     4 tarjetas de cifras   →  RFQs totales, últimos 7 días, clientes y
 *                               cuántos esperan a una persona.
 *     el globo terráqueo     →  el resorte de estrellas de la portada. No es
 *                               decoración prestada: es la marca de la propia
 *                               aplicación, y ocupa el mismo sitio que ocupaba
 *                               un mundo que aquí no significaba nada.
 *     "Sales by Country"     →  la cola de revisión: qué RFQ, de quién, cuánto
 *                               lleva esperando y por qué. Es lo único de esta
 *                               pantalla sobre lo que se puede ACTUAR, así que
 *                               se lleva el sitio de honor y cada fila abre su
 *                               RFQ.
 *     las dos gráficas       →  reparto por estado y materiales más pedidos,
 *                               en barras horizontales.
 *
 * TODAS las cifras salen de `/api/assistant/summary` y `/api/assistant/attention`,
 * que las cuentan en SQL. No hay ni un número calculado en el navegador ni
 * ninguna serie inventada para que la gráfica quede bonita: si la base está
 * vacía, esta pantalla lo dice.
 *
 * Por eso NO hay gráfica de líneas por meses, que es lo más vistoso de la
 * referencia: el backend no da una serie temporal, y dibujarla interpolando
 * sería enseñar una tendencia que nadie ha medido.
 */
const ResumenPage = (() => {
    'use strict';

    let resumen = null;
    let atencion = null;
    let decididas = null;
    let cargando = false;

    function esc(valor) {
        const nodo = document.createElement('span');
        nodo.textContent = valor == null ? '' : String(valor);
        return nodo.innerHTML;
    }

    const ICONOS = {
        total:     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
        semana:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
        clientes:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/></svg>',
        esperando: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
        // La estrella va RELLENA, no de contorno como las demás: es una marca
        // de pertenencia ("este cliente es de los grandes"), no un icono de
        // categoría, y de contorno se confundía con un botón de favorito.
        estrella:  '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2.6l2.9 5.9 6.5.9-4.7 4.6 1.1 6.4-5.8-3-5.8 3 1.1-6.4L2.6 9.4l6.5-.9z"/></svg>',
    };

    // ---------------------------------------------------------------- datos

    async function cargar(silencio) {
        if (cargando) return;
        cargando = true;
        try {
            // Las dos a la vez: son independientes y en serie se nota la espera.
            // Las tres a la vez: son independientes y en serie se nota la
            // espera. La de decididas se pide con `catch` propio porque es la
            // menos importante de las tres: que falle no puede dejar la
            // pantalla sin las cifras ni sin la cola de revisión.
            [resumen, atencion, decididas] = await Promise.all([
                API.assistantSummary(),
                API.assistantAttention(),
                API.rfqsDecididos(25)
                    .then((d) => (d && d.rfqs) || [])
                    .catch(() => []),
            ]);
        } catch (err) {
            if (err && err.sesionExpirada) return;
            // El repaso de fondo no avisa de un fallo pasajero: la pantalla
            // se queda con lo último que tenía y lo reintenta en 15 s.
            if (!silencio) Toast.error(I18N.t('aviso.resumenFallo', { motivo: err.message }));
        } finally {
            cargando = false;
        }
    }

    // -------------------------------------------------------------- piezas

    function tarjetas() {
        const r = resumen || {};
        const a = atencion || {};
        return [
            { id: 'total',     icono: ICONOS.total,     valor: r.total ?? 0,
              etiqueta: I18N.t('resumen.total'),     color: 'var(--cgr-azul-frio)' },
            { id: 'semana',    icono: ICONOS.semana,    valor: r.ultimos_7_dias ?? 0,
              etiqueta: I18N.t('resumen.semana'),    color: 'var(--cgr-verde)' },
            { id: 'clientes',  icono: ICONOS.clientes,  valor: r.clientes ?? 0,
              etiqueta: I18N.t('resumen.clientes'),  color: 'var(--cgr-gris)' },
            { id: 'esperando', icono: ICONOS.esperando, valor: a.total ?? 0,
              etiqueta: I18N.t('resumen.esperando'), color: 'var(--cgr-naranja)' },
        ];
    }

    /**
     * Barras horizontales, proporcionales al mayor de la lista.
     *
     * A propósito no es una gráfica de verdad: son cuatro o cinco valores y una
     * barra con su número al lado se lee mejor —y se lee IGUAL en un teléfono—
     * que un lienzo con ejes. Y no hace falta cargar ninguna librería.
     */
    function barras(filas, clave, vacio) {
        if (!filas || !filas.length) {
            return `<p class="resumen-vacio">${esc(vacio)}</p>`;
        }
        const mayor = Math.max(...filas.map(f => f.total)) || 1;
        return `<ul class="resumen-barras">${filas.map(f => `
            <li>
                <span class="resumen-barra-nombre">${esc((clave === 'estado' ? I18N.estado(f[clave]) : f[clave]) || '—')}</span>
                <span class="resumen-barra-pista">
                    <span class="resumen-barra-valor"
                          style="width:${Math.max(3, Math.round(f.total / mayor * 100))}%"></span>
                </span>
                <span class="resumen-barra-cifra">${esc(f.total)}</span>
            </li>`).join('')}</ul>`;
    }

    /**
     * Por qué espera: la bandera del sistema si la hay y, si no, lo que le
     * falta al RFQ (validar la cotización o revisar la factibilidad). Antes
     * aquí salía el estado a secas —"New"— que no dice qué hay que hacer.
     */
    function motivoDe(p) {
        return I18N.motivoPendiente(p);
    }

    function filaEspera(p) {
        const dias = Number(p.dias_esperando) || 0;
        const nivel = p.criticas ? 'critico' : (p.avisos ? 'aviso' : 'normal');
        return `
            <tr class="resumen-fila resumen-fila--${nivel}" data-rfq="${esc(p.rfq_id)}" tabindex="0">
                <td data-etiqueta="${esc(I18N.t('resumen.col.rfq'))}">
                    <strong>${esc(p.rfq_id)}</strong>
                </td>
                <td data-etiqueta="${esc(I18N.t('resumen.col.cliente'))}">
                    ${esc(p.cliente_nombre || p.cliente_id || '—')}${p.part_number ? ' · ' + esc(p.part_number) : ''}
                </td>
                <td data-etiqueta="${esc(I18N.t('resumen.col.espera'))}">
                    ${esc(I18N.t('notif.dias', { n: dias }))}
                </td>
                <td data-etiqueta="${esc(I18N.t('resumen.col.motivo'))}">
                    ${esc(motivoDe(p))}
                </td>
            </tr>`;
    }

    /**
     * Los clientes estrella: el Top 12 que hace la mitad de las ventas.
     *
     * Qué contesta este panel, que es lo que lo hace informativo y no una
     * lista de nombres: **a quién le toca una llamada**. Por eso el dato de
     * cada fila no es cuántas RFQs lleva —eso sube muy despacio y no cambia
     * nada hoy— sino CUÁNTO HACE de la última. Una cuenta grande callada tres
     * meses es una señal; que tenga 4 RFQs en total no lo es.
     *
     * Van ordenados por esa misma señal: los que escribieron hace menos
     * arriba, los que no han escrito nunca al final. Se enseñan TODOS, con o
     * sin RFQs: el que falta es justo el que hay que mirar.
     *
     * Los nombres no se recortan. En una lista de clientes el nombre es EL
     * dato; "Ruskin - Air Distribution Technolo…" obliga a adivinar, y una
     * fila más alta se perdona antes que un cliente sin identificar.
     */
    function cuandoFue(c) {
        if (c.dias === null || c.dias === undefined) return I18N.t('resumen.sinRfq');
        if (c.dias <= 0) return I18N.t('resumen.hoy');
        return I18N.t('resumen.haceDias', { n: c.dias });
    }

    function estrellas(filas) {
        if (!filas || !filas.length) {
            return `<p class="resumen-vacio">${esc(I18N.t('resumen.sinEstrella'))}</p>`;
        }
        return `<ul class="resumen-estrellas">${filas.map(c => {
            const quieto = !c.total;
            const cuenta = c.total === 1
                ? I18N.t('resumen.unRfq')
                : I18N.t('resumen.rfqsDe', { n: c.total || 0 });
            return `
            <li class="resumen-estrella${quieto ? ' resumen-estrella--quieto' : ''}">
                <span class="resumen-estrella-marca" aria-hidden="true">${ICONOS.estrella}</span>
                <span class="resumen-estrella-texto">
                    <span class="resumen-estrella-nombre">${esc(c.razon_social || c.cliente_id)}</span>
                    <span class="resumen-estrella-dato">
                        <span class="resumen-estrella-cuando">${esc(cuandoFue(c))}</span>
                        ${quieto ? '' : `<span class="resumen-estrella-sep" aria-hidden="true">·</span>
                        <span>${esc(cuenta)}</span>`}
                    </span>
                </span>
            </li>`;
        }).join('')}</ul>`;
    }

    /**
     * Los RFQ ya dictaminados: aprobados y declinados, juntos.
     *
     * Van juntos a propósito. Quien busca un caso viejo se acuerda del cliente
     * y de cuándo fue, no de en cuál de los dos acabó; dos listas separadas
     * obligan a mirar en las dos.
     *
     * Y se abren en CONSULTA: la hoja aparta el borrador de trabajo antes de
     * cargar el caso y lo devuelve al salir, así que mirar una cotización
     * cerrada nunca se mezcla con un cálculo en curso.
     */
    function filaDecidida(r) {
        const aprobado = r.estado === 'Approved';
        const clase = aprobado ? 'badge-approved' : 'badge-declined';
        const cuando = (r.fecha_registro || '').slice(0, 10);
        // El nombre y no el código: un RFQ cuyo cliente no está en la cartera
        // no tiene código, y salía como "—" aunque el correo dijera quién era.
        const cliente = r.cliente_nombre || r.cliente_id || '';
        // En el teléfono la fila es una ficha y estos tres datos van en UNA
        // línea bajo el número: se arma aquí con sólo los que hay, para que un
        // dato vacío no deje un "·" colgando ni un "—" suelto.
        const linea = [cliente, r.part_number, cuando].filter(Boolean)
            .map((v) => `<span class="resumen-decidida-item">${esc(v)}</span>`)
            .join('<span class="resumen-decidida-sep" aria-hidden="true">·</span>');
        return `
            <tr>
                <td class="resumen-decidida-id"><code>${esc(r.rfq_id)}</code>${linea
                    ? `<span class="resumen-decidida-linea">${linea}</span>` : ''}</td>
                <td class="resumen-decidida-dato">${esc(cliente || '—')}</td>
                <td class="resumen-decidida-dato">${esc(r.part_number || '—')}</td>
                <td class="resumen-decidida-dato">${esc(cuando || '—')}</td>
                <td class="resumen-decidida-estado"><span class="badge ${clase}"><span class="badge-dot"></span>${esc(I18N.estado(r.estado))}</span></td>
                <td class="resumen-decidida-accion">
                    ${r.oferta === 'pendiente' ? `<button type="button" class="btn btn-primary btn-sm"
                            data-enviar-oferta="${esc(r.rfq_id)}">${esc(I18N.t('oferta.enviarAhora'))}</button>` : ''}
                    <button type="button" class="btn btn-secondary btn-sm"
                            data-decidida="${esc(r.rfq_id)}">${esc(I18N.t('resumen.verHoja'))}</button>
                </td>
            </tr>`;
    }

    function panelDecididas() {
        const filas = decididas || [];
        return `
            <section class="panel" id="resumenDecididas">
                <div class="panel-cabecera">
                    <h3 class="panel-titulo">${esc(I18N.t('resumen.decididas'))}</h3>
                    <span class="resumen-estrellas-nota">${esc(I18N.t('resumen.decididasNota'))}</span>
                </div>
                ${filas.length ? `
                <div class="tabla-caja">
                    <table class="tabla-usuarios resumen-tabla resumen-decididas">
                        <thead>
                            <tr>
                                <th>${esc(I18N.t('resumen.col.rfq'))}</th>
                                <th>${esc(I18N.t('resumen.col.cliente'))}</th>
                                <th>${esc(I18N.t('resumen.col.parte'))}</th>
                                <th>${esc(I18N.t('resumen.col.fecha'))}</th>
                                <th>${esc(I18N.t('resumen.col.estado'))}</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>${filas.map(filaDecidida).join('')}</tbody>
                    </table>
                </div>` : `<p class="resumen-vacio">${esc(I18N.t('resumen.sinDecididas'))}</p>`}
            </section>`;
    }

    /** La cola de lo que espera dictamen. Se repinta sola (ver `vigilar`). */
    function panelEspera() {
        const a = atencion || {};
        const pendientes = a.pendientes || [];
        return `
                <section class="panel" id="resumenEspera">
                    <div class="panel-cabecera">
                        <h3 class="panel-titulo">${esc(I18N.t('resumen.espera'))}</h3>
                        ${a.criticas
                            ? `<span class="badge badge-critico">${esc(I18N.t('resumen.criticas', { n: a.criticas }))}</span>`
                            : ''}
                    </div>
                    ${pendientes.length ? `
                    <div class="tabla-caja">
                        <table class="tabla-usuarios resumen-tabla">
                            <thead>
                                <tr>
                                    <th>${esc(I18N.t('resumen.col.rfq'))}</th>
                                    <th>${esc(I18N.t('resumen.col.cliente'))}</th>
                                    <th>${esc(I18N.t('resumen.col.espera'))}</th>
                                    <th>${esc(I18N.t('resumen.col.motivo'))}</th>
                                </tr>
                            </thead>
                            <tbody>${pendientes.map(filaEspera).join('')}</tbody>
                        </table>
                    </div>` : `<p class="resumen-vacio">${esc(I18N.t('resumen.nadaEspera'))}</p>`}
                </section>`;
    }

    /** Los dos repartos (por estado y por material). */
    function panelRepartos() {
        const r = resumen || {};
        return `
            <div class="resumen-dos" id="resumenRepartos">
                <section class="panel">
                    <h3 class="panel-titulo">${esc(I18N.t('resumen.porEstado'))}</h3>
                    ${barras(r.por_estado, 'estado', I18N.t('resumen.sinDatos'))}
                </section>
                <section class="panel">
                    <h3 class="panel-titulo">${esc(I18N.t('resumen.materiales'))}</h3>
                    ${barras(r.materiales, 'material', I18N.t('resumen.sinDatos'))}
                </section>
            </div>`;
    }

    function plantilla() {
        const r = resumen || {};

        return `
        <div class="resumen">

            <!-- Las cuatro cifras, en UNA fila y a todo el ancho: exactamente
                 la misma tira que el Monitor. Lo pidió ISC así: una sola
                 pieza de cifras en toda la aplicación, no dos maneras de
                 enseñar lo mismo según la pantalla. -->
            <div class="kpi-fila resumen-kpis" id="resumenKpis"></div>

            <!-- Debajo, en dos columnas: la cola de revisión —lo único
                 accionable de la pantalla, y por eso la ancha— y el resorte
                 de estrellas a la derecha, en el sitio que en la referencia
                 ocupaba el globo terráqueo.
                 En el teléfono se apilan y el resorte pasa el último. -->
            <div class="resumen-medio">
                ${panelEspera()}

                <section class="panel resumen-marca">
                    <div class="resumen-lienzo">
                        <canvas id="resumenCanvas" aria-hidden="true"></canvas>
                    </div>
                    <p class="resumen-sello">
                        ${esc(I18N.t('resumen.ultima'))}
                        <strong>${esc(r.ultima_rfq ? r.ultima_rfq.slice(0, 16) : '—')}</strong>
                    </p>
                </section>
            </div>

            <!-- Los dos repartos, uno al lado del otro. -->
            ${panelRepartos()}

            ${panelDecididas()}

            <!-- Los clientes estrella, a todo el ancho: son doce nombres
                 largos y en media columna se partían en dos líneas cada uno. -->
            <section class="panel">
                <div class="panel-cabecera">
                    <h3 class="panel-titulo">${esc(I18N.t('resumen.estrella'))}</h3>
                    <!-- Cuánto del trabajo viene de estas cuentas. Es la cifra
                         que da sentido al panel: el Top 12 es ~la mitad de las
                         ventas, y aquí se ve si también lo es de lo que entra.
                         Con la base vacía dice "sin RFQs todavía" en vez de un
                         0 % que parecería un mal dato. -->
                    <span class="resumen-estrellas-nota">${esc(
                        r.total
                            ? I18N.t('resumen.cuota', { n: r.rfqs_estrella || 0, t: r.total })
                            : I18N.t('resumen.cuotaVacia'))}</span>
                </div>
                ${estrellas(r.estrella)}
            </section>
        </div>`;
    }

    // -------------------------------------------------------------- montaje

    async function render(contenedor) {
        // Antes de nada: si se vuelve a entrar, el resorte anterior sigue
        // pintando sobre un lienzo que ya no está en el documento.
        detener();

        await cargar();
        contenedor.innerHTML = plantilla();

        const rejilla = contenedor.querySelector('#resumenKpis');
        if (rejilla) StatusCard.render(rejilla, tarjetas());

        // El lienzo se mide con el contenedor ya en pantalla: antes tendría
        // ancho 0 y no se dibujaría nada.
        requestAnimationFrame(() => {
            const lienzo = contenedor.querySelector('#resumenCanvas');
            if (lienzo && typeof Hero !== 'undefined') Hero.init(lienzo);
        });

        // Cada fila abre su RFQ —en su ficha, como en toda la aplicación—.
        // Con teclado también: la tabla es la lista de cosas que hay que
        // atender y no puede depender del ratón. Por delegación en el
        // contenedor: la cola se repinta sola y sus filas cambian.
        const abrir = (fila) => {
            if (fila && fila.dataset.rfq) {
                APP.navigate('rfq-detail', { id: fila.dataset.rfq });
            }
        };
        contenedor.addEventListener('click', (ev) => abrir(ev.target.closest('.resumen-fila')));
        contenedor.addEventListener('keydown', (ev) => {
            if (ev.key !== 'Enter' && ev.key !== ' ') return;
            const fila = ev.target.closest('.resumen-fila');
            if (!fila) return;
            ev.preventDefault();
            abrir(fila);
        });
        vigilar(contenedor);

        // Los ya dictaminados se abren en la hoja, en CONSULTA: el borrador
        // de trabajo se aparta y se devuelve al salir, así que mirar un caso
        // cerrado no se mezcla con lo que alguien esté calculando.
        contenedor.addEventListener('click', (ev) => {
            // Aprobado sin oferta: al envío directo (ver quote-review.js).
            const enviar = ev.target.closest('[data-enviar-oferta]');
            if (enviar) {
                ev.preventDefault();
                APP.navigate('quote-review', { id: enviar.dataset.enviarOferta, enviar: '1' });
                return;
            }
            const boton = ev.target.closest('[data-decidida]');
            if (!boton) return;
            ev.preventDefault();
            APP.navigate('quoting', { rfq: boton.dataset.decidida, consulta: '1' });
        });
    }

    // ------------------------------------------------------------ al día

    /*
     * La pantalla se mantiene al día sola.
     *
     * Un RFQ dictaminado (aquí, en otra pestaña o en otra computadora) sale
     * de «Esperan dictamen» y entra en «RFQ ya dictaminadas» sin recargar:
     * al momento con el aviso `pohua:rfq-dictaminado` (ver `API.avisarRfq`)
     * y, para lo que pase en otra computadora, con un repaso cada 15 s
     * mientras la pantalla está a la vista. Sólo se repintan las piezas con
     * datos —cifras, cola, repartos, dictaminadas—; el resorte sigue girando.
     */
    const REPASO_MS = 15000;
    let repaso = null;
    let contenedorVivo = null;
    let huellaDatos = '';

    const huella = () => {
        try { return JSON.stringify([resumen, atencion, decididas]); } catch (_) { return ''; }
    };

    async function refrescar() {
        const c = contenedorVivo;
        if (!c || !c.isConnected || document.hidden || cargando) return;
        await cargar(true);
        if (contenedorVivo !== c || !c.isConnected) return;
        const h = huella();
        if (h === huellaDatos) return;
        huellaDatos = h;
        const cambiar = (id, html) => {
            const viejo = c.querySelector('#' + id);
            if (!viejo) return;
            const caja = document.createElement('div');
            caja.innerHTML = html.trim();
            if (caja.firstElementChild) viejo.replaceWith(caja.firstElementChild);
        };
        cambiar('resumenEspera', panelEspera());
        cambiar('resumenDecididas', panelDecididas());
        cambiar('resumenRepartos', panelRepartos());
        const rejilla = c.querySelector('#resumenKpis');
        if (rejilla) StatusCard.render(rejilla, tarjetas());
    }

    const alCambiarUnRfq = () => setTimeout(refrescar, 300);
    const alVolverAVerse = () => { if (!document.hidden) refrescar(); };

    function vigilar(contenedor) {
        contenedorVivo = contenedor;
        huellaDatos = huella();
        repaso = setInterval(refrescar, REPASO_MS);
        window.addEventListener('pohua:rfq-dictaminado', alCambiarUnRfq);
        document.addEventListener('visibilitychange', alVolverAVerse);
    }

    /** La llama el router al salir. Sin esto el resorte sigue pintando. */
    function detener() {
        if (typeof Hero !== 'undefined') Hero.parar();
        if (repaso) { clearInterval(repaso); repaso = null; }
        window.removeEventListener('pohua:rfq-dictaminado', alCambiarUnRfq);
        document.removeEventListener('visibilitychange', alVolverAVerse);
        contenedorVivo = null;
    }

    return { render, detener };
})();
