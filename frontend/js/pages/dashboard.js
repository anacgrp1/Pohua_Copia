/**
 * Mail — el recorrido del correo, y nada más.
 *
 * ---------------------------------------------------------------------------
 * El recorrido
 * ---------------------------------------------------------------------------
 * Enseña por dónde pasa un correo desde que lo manda el cliente hasta que llega
 * a Sales. Las cinco etapas NO son una metáfora bonita: son las que el sistema
 * recorre de verdad, y cada una lleva la cifra que hay en ella ahora mismo,
 * contada en SQL (`GET /api/assistant/pipeline`).
 *
 *     1. Customer email      correos leídos del buzón
 *     2. Data extracted      RFQs registradas a partir de ellos
 *     3. Needs review        extracción con poca confianza: la mira una persona
 *     4. Awaiting decision   esperando aprobar o rechazar
 *     5. Ready for Sales     aprobadas
 *
 * Las etapas 3 y 4 son las únicas donde el trabajo se PARA a esperar a alguien;
 * el servidor las marca con `espera` y aquí se pintan en ámbar. Ese es el dato
 * que importa cuando alguien abre esta pantalla: no cuánto ha pasado, sino
 * dónde está atascado.
 *
 * La animación: un sobre recorre el camino en bucle. Cuando el servicio está
 * parado, el camino se apaga y el sobre se detiene — si el sistema no está
 * moviendo correos, la pantalla no debe fingir que sí.
 *
 * Las tarjetas de cifras que había aquí arriba se fueron a Monitor: son estado
 * del servicio (correos procesados, errores), no el recorrido de un correo, y
 * su sitio es junto al registro.
 */
const DashboardPage = (() => {
    'use strict';

    const REFRESCO_MS = 15000;

    let temporizador = null;

    function esc(valor) {
        const nodo = document.createElement('span');
        nodo.textContent = valor == null ? '' : String(valor);
        return nodo.innerHTML;
    }

    // ======================================================================
    // EL DIAGRAMA
    // ======================================================================
    // Cinco nodos unidos por enlaces, con sobres viajando por ellos: la lectura
    // de un diagrama de red, que es exactamente lo que es —un correo saltando
    // de una estación a la siguiente—.
    //
    // Se dibuja en SVG y se anima con requestAnimationFrame en vez de con CSS:
    // los sobres tienen que seguir el recorrido REAL entre nodo y nodo, y esas
    // coordenadas dependen del ancho disponible. Con animaciones CSS habría que
    // regenerar los @keyframes en cada cambio de tamaño.
    //
    // Qué es real y qué es ilustrativo, que conviene no confundirlo:
    //   - Las cifras de cada nodo son las de la base de datos.
    //   - Cuántos sobres van por cada enlace sale de esas mismas cifras, así
    //     que un tramo con más trabajo se ve más cargado.
    //   - La velocidad NO significa nada: es sólo movimiento.

    // Las etapas las manda el servidor (`GET /api/assistant/pipeline`) y son
    // las que se dibujan: si mañana hay una más, aparece sola. Esta lista es
    // sólo el mínimo para pintar algo antes de la primera respuesta. Antes era
    // fija, y al añadir "Waiting on customer" en el servidor los nodos se
    // corrieron uno: cada círculo enseñaba la cifra de la etapa siguiente.
    const NODOS_POR_DEFECTO = ['cliente', 'extraccion', 'incompletas', 'revision', 'dictamen', 'sales', 'oferta'];
    let NODOS = NODOS_POR_DEFECTO;

    const ICONOS = {
        cliente:     '<path d="M4 4h16v16H4z"/><polyline points="4 7 12 13 20 7"/>',
        extraccion:  '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="15" x2="15" y2="15"/>',
        incompletas: '<circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
        revision:    '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
        dictamen:    '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
        sales:       '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
        oferta:      '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
    };

    const RADIO_NODO = 26;      // radio del círculo de cada estación
    const MAX_SOBRES = 4;       // por enlace: más es ruido, no información

    /* Lo que ocupa un sobre de verdad en pantalla: 18 px de ancho más el
       resplandor. Dos sobres a menos de esto se leen como una sola figura
       dentada —los picos de las solapas, uno detrás de otro—, que es justo lo
       que se veía. Es la distancia MÍNIMA entre centros, y manda sobre el
       número de sobres: antes que apretarlos, se ponen menos. */
    const SEPARACION_MIN = 52;

    /* Ritmo, en píxeles por segundo, igual en todos los tramos.
       Antes cada sobre llevaba su propia velocidad (`0.34 + (k % 3) * 0.05`)
       Y estaba dicha en VUELTAS por segundo, lo que traía dos cosas malas:
         - dentro de un tramo, el rápido alcanzaba al lento y acababan
           encimados, por muy bien repartidos que salieran;
         - entre tramos, uno corto y uno largo se recorrían en el mismo
           tiempo, así que el corto iba visiblemente más despacio.
       Con una sola velocidad en píxeles, las distancias que se ven al
       arrancar son las mismas un minuto después, y todo el diagrama avanza
       al mismo paso. */
    const VELOCIDAD_PX = 56;

    let datos = null;           // última respuesta del servidor
    let geometria = null;       // posiciones calculadas para el ancho actual
    let sobres = [];
    let animacion = null;
    let ultimoInstante = 0;

    const sinMovimiento = () =>
        window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    /**
     * Coloca los nodos según el sitio que haya.
     *
     * En horizontal cabe todo en una fila; por debajo de 720 px las etiquetas
     * quedarían en una letra por línea, así que el diagrama gira a vertical.
     * Los enlaces salen de ahí, no al revés: así el mismo código de animación
     * sirve para las dos disposiciones.
     */
    function construirGeometria(ancho) {
        const vertical = ancho < 720;
        const puntos = [];

        if (vertical) {
            const alto = 128;
            const x = 46;
            for (let i = 0; i < NODOS.length; i++) {
                puntos.push({ x, y: 52 + i * alto });
            }
            return {
                vertical,
                puntos,
                ancho: ancho,
                alto: 52 + (NODOS.length - 1) * alto + 46,
            };
        }

        const margen = 78;
        const util = ancho - margen * 2;
        for (let i = 0; i < NODOS.length; i++) {
            puntos.push({ x: margen + (util * i) / (NODOS.length - 1), y: 46 });
        }
        return { vertical, puntos, ancho, alto: 132 };
    }

    /** Los tramos entre nodos, ya recortados para no meterse bajo el círculo. */
    function enlaces(g) {
        const tramos = [];
        for (let i = 0; i < g.puntos.length - 1; i++) {
            const a = g.puntos[i];
            const b = g.puntos[i + 1];
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const largo = Math.hypot(dx, dy) || 1;
            const hueco = RADIO_NODO + 6;
            tramos.push({
                x1: a.x + (dx / largo) * hueco,
                y1: a.y + (dy / largo) * hueco,
                x2: b.x - (dx / largo) * hueco,
                y2: b.y - (dy / largo) * hueco,
            });
        }
        return tramos;
    }

    /**
     * Cuántos sobres van por cada enlace.
     *
     * Sale de la cifra de la etapa a la que lleva el enlace: donde hay más
     * trabajo, el tramo se ve más cargado. Un enlace hacia una etapa a cero se
     * queda sin sobres, que es la verdad: por ahí no está pasando nada.
     */
    function cuantosSobres(total, maximo, largo) {
        if (!total) return 0;
        // Cuántos caben sin pisarse. Un tramo corto —o el diagrama en
        // vertical, donde los tramos son la mitad de largos— admite menos, y
        // ese límite es el que manda: un sobre solo dice lo mismo que cuatro
        // amontonados, y se lee.
        const caben = Math.max(1, Math.floor((largo || 0) / SEPARACION_MIN));
        const tope = Math.min(MAX_SOBRES, caben);
        if (maximo <= 0) return 1;
        return Math.max(1, Math.min(tope, Math.round((total / maximo) * MAX_SOBRES)));
    }

    function crearSobres(g) {
        const tramos = enlaces(g);
        const totales = datos.etapas.map(e => e.total || 0);
        // El máximo se toma entre las etapas de DESTINO (de la 2 en adelante).
        // Incluyendo la primera —los correos leídos, que son cientos frente a
        // unas pocas RFQs— todos los demás tramos salían con un solo sobre.
        const maximo = Math.max(...totales.slice(1), 1);

        sobres = [];
        for (let i = 0; i < tramos.length; i++) {
            const t = tramos[i];
            const largo = Math.hypot(t.x2 - t.x1, t.y2 - t.y1) || 1;
            // El enlace i lleva a la etapa i+1: su carga es la de destino.
            const cuantos = cuantosSobres(totales[i + 1], maximo, largo);
            // Una sola velocidad para todo el tramo, sacada del ritmo en
            // píxeles. Compartirla es lo que mantiene la separación: si dos
            // sobres del mismo tramo van a distinta velocidad, el hueco entre
            // ellos se cierra solo, y ningún reparto inicial lo evita.
            const velocidad = VELOCIDAD_PX / largo;   // vueltas por segundo
            for (let k = 0; k < cuantos; k++) {
                sobres.push({
                    tramo: i,
                    // Repartidos a partes iguales. El +0.5 los aparta de los
                    // extremos: ahí la opacidad es 0 y el primer fotograma
                    // saldría con el tramo vacío.
                    t: (k + 0.5) / cuantos,
                    velocidad,
                    espera: datos.etapas[i + 1]?.espera && totales[i + 1] > 0,
                });
            }
        }
    }

    function dibujar(contenedor) {
        if (!datos) return;
        const svg = contenedor.querySelector('.flujo-svg');
        if (!svg) return;

        NODOS = datos.etapas.map(e => e.clave);   // la geometría sigue a las etapas reales
        const g = construirGeometria(svg.clientWidth || contenedor.clientWidth || 900);
        geometria = g;
        svg.setAttribute('viewBox', `0 0 ${g.ancho} ${g.alto}`);
        svg.setAttribute('height', g.alto);

        const tramos = enlaces(g);

        const lineas = tramos.map((t, i) => {
            const etapa = datos.etapas[i + 1];
            const parado = etapa && etapa.espera && etapa.total > 0;
            return `<line class="enlace ${parado ? 'enlace--espera' : ''}"
                          x1="${t.x1.toFixed(1)}" y1="${t.y1.toFixed(1)}"
                          x2="${t.x2.toFixed(1)}" y2="${t.y2.toFixed(1)}"/>`;
        }).join('');

        const nodos = datos.etapas.map((e, i) => {
            const punto = g.puntos[i];
            if (!punto) return '';

            // La etiqueta se traduce por la CLAVE de la etapa, que es estable;
            // el texto en inglés que manda el servidor queda de red de
            // seguridad por si algún día aparece una etapa sin traducir.
            const cEtiqueta = 'etapa.' + e.clave;
            const tEtiqueta = I18N.t(cEtiqueta);
            const etiqueta = tEtiqueta === cEtiqueta ? (e.etiqueta || '') : tEtiqueta;

            const cDetalle = cEtiqueta + '.det';
            const tDetalle = I18N.t(cDetalle, { n: numeroDe(e) });
            const detalle = tDetalle === cDetalle ? (e.detalle || '') : tDetalle;
            const clases = ['nodo'];
            if (e.espera && e.total > 0) clases.push('nodo--espera');
            if (!e.total) clases.push('nodo--vacio');

            // En vertical el texto va al lado del nodo; en horizontal, debajo.
            const tx = g.vertical ? punto.x + RADIO_NODO + 16 : punto.x;
            const ty = g.vertical ? punto.y - 6 : punto.y + RADIO_NODO + 24;
            const anclaje = g.vertical ? 'start' : 'middle';

            return `<g class="${clases.join(' ')}">
                <circle class="nodo-halo" cx="${punto.x}" cy="${punto.y}" r="${RADIO_NODO + 6}"/>
                <circle class="nodo-caja" cx="${punto.x}" cy="${punto.y}" r="${RADIO_NODO}"/>
                <g class="nodo-icono" transform="translate(${punto.x - 11} ${punto.y - 11}) scale(0.92)"
                   fill="none" stroke="currentColor" stroke-width="2"
                   stroke-linecap="round" stroke-linejoin="round">${ICONOS[e.clave] || ''}</g>
                <text class="nodo-total" x="${tx}" y="${ty}" text-anchor="${anclaje}">${e.total}</text>
                <text class="nodo-etiqueta" x="${tx}" y="${ty + 17}" text-anchor="${anclaje}">${esc(etiqueta)}</text>
                <title>${esc(etiqueta)}${detalle ? ' — ' + esc(detalle) : ''}</title>
            </g>`;
        }).join('');

        svg.innerHTML = `<g class="enlaces">${lineas}</g>
                         <g class="nodos">${nodos}</g>
                         <g class="sobres"></g>`;

        crearSobres(g);
        pintarSobres(svg, tramos);
    }

    /** Crea (una vez) el nodo SVG de cada sobre y lo coloca. */
    function pintarSobres(svg, tramos) {
        const capa = svg.querySelector('.sobres');
        if (!capa) return;

        const moviendo = datos.corriendo && sobres.length > 0;
        capa.innerHTML = moviendo ? sobres.map((s, i) => `
            <g class="sobre ${s.espera ? 'sobre--espera' : ''}" data-sobre="${i}">
                <rect x="-9" y="-7" width="18" height="14" rx="3"/>
                <polyline points="-9,-7 0,0 9,-7" fill="none"
                          stroke="currentColor" stroke-width="1.5"
                          stroke-linecap="round" stroke-linejoin="round"/>
            </g>`).join('') : '';

        colocarSobres(svg, tramos);
    }

    function colocarSobres(svg, tramos) {
        const nodos = svg.querySelectorAll('[data-sobre]');
        for (let i = 0; i < nodos.length; i++) {
            const s = sobres[i];
            const t = tramos[s.tramo];
            if (!t) continue;
            const x = t.x1 + (t.x2 - t.x1) * s.t;
            const y = t.y1 + (t.y2 - t.y1) * s.t;
            nodos[i].setAttribute('transform', `translate(${x.toFixed(1)} ${y.toFixed(1)})`);
            // Se desvanece en los extremos: así "entra" y "sale" del nodo en
            // lugar de aparecer de golpe pegado al círculo.
            const borde = Math.min(s.t, 1 - s.t);
            nodos[i].setAttribute('opacity', Math.min(1, borde * 8).toFixed(2));
        }
    }

    function animar(instante) {
        const svg = document.querySelector('.flujo-svg');
        if (!svg || !geometria) { animacion = null; return; }

        if (!ultimoInstante) ultimoInstante = instante;
        // Delta en segundos, con tope: al volver de una pestaña en segundo
        // plano el salto puede ser de minutos y los sobres darían un tirón.
        const delta = Math.min((instante - ultimoInstante) / 1000, 0.1);
        ultimoInstante = instante;

        for (const s of sobres) {
            s.t += s.velocidad * delta;
            if (s.t > 1) s.t -= 1;
        }
        colocarSobres(svg, enlaces(geometria));
        animacion = requestAnimationFrame(animar);
    }

    function arrancarAnimacion() {
        if (animacion !== null || sinMovimiento()) return;
        if (!datos || !datos.corriendo) return;
        ultimoInstante = 0;
        animacion = requestAnimationFrame(animar);
    }

    function pararAnimacion() {
        if (animacion !== null) {
            cancelAnimationFrame(animacion);
            animacion = null;
        }
    }

    /**
     * El número que va dentro del detalle de cada etapa.
     *
     * El servidor manda el detalle ya redactado ("12 in the last 7 days"), que
     * sirve de red de seguridad; para traducirlo hace falta la cifra suelta, y
     * se saca de ese mismo texto.
     */
    function numeroDe(etapa) {
        const encontrado = /\d+/.exec(etapa.detalle || '');
        return encontrado ? encontrado[0] : '';
    }

    function pintarRecorrido(d, contenedor) {
        datos = d;
        dibujar(contenedor);

        const estado = document.getElementById('flujoEstado');
        if (estado) {
            estado.textContent = d.corriendo
                ? (d.ultimo_ciclo
                    ? I18N.t('flujo.ultimoCiclo', { hora: d.ultimo_ciclo })
                    : I18N.t('flujo.corriendo'))
                : I18N.t('flujo.parado');
            estado.classList.toggle('flujo-estado--parado', !d.corriendo);
        }

        pararAnimacion();
        arrancarAnimacion();
    }

    async function cargarRecorrido(contenedor) {
        try {
            pintarRecorrido(await API.assistantPipeline(), contenedor);
        } catch (err) {
            if (err && err.sesionExpirada) return;
            const caja = contenedor.querySelector('.flujo-pista');
            if (caja) caja.innerHTML =
                `<p class="flujo-error">${esc(I18N.t('flujo.error', { motivo: err.message }))}</p>`;
        }
    }

    // -------------------------------------------------------------- montaje

    function plantilla() {
        return `
            <section class="flujo">
                <div class="flujo-head">
                    <h2 class="flujo-titulo">${esc(I18N.t('flujo.titulo'))}</h2>
                    <span class="flujo-estado" id="flujoEstado"></span>
                </div>

                <div class="flujo-pista">
                    <svg class="flujo-svg" xmlns="http://www.w3.org/2000/svg"
                         width="100%" preserveAspectRatio="xMidYMid meet"
                         role="img" aria-label="${esc(I18N.t('flujo.alt'))}"></svg>
                </div>

                <!-- Los controles del servicio viven aquí, no en la cabecera:
                     son acciones de esta pantalla, y desde arriba salían
                     también en Quoting, Monitor y Settings, donde no pintan
                     nada. -->
                <div class="flujo-controles">
                    <!-- El horario de atención, aquí y no en otro sitio: es la
                         pantalla donde se pulsa "Ejecutar ciclo" y donde, si
                         nadie lo dice, uno se pregunta por qué no entra nada.
                         Lo rellena APP.pintarHorario con el estado real. -->
                    <span class="flujo-horario" id="flujoHorario" hidden></span>
                    <button class="btn btn-secondary" id="btnRunCycle"
                            data-permiso="worker:operar" title="${esc(I18N.t('boton.correrCiclo.ayuda'))}">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                             stroke-linecap="round" stroke-linejoin="round">
                            <polygon points="5 3 19 12 5 21 5 3"/>
                        </svg>
                        ${esc(I18N.t('boton.correrCiclo'))}
                    </button>
                    <button class="btn btn-primary" id="btnToggleWorker"
                            data-permiso="worker:operar" data-corriendo="0">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                             stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/>
                        </svg>
                        ${esc(I18N.t('boton.arrancar'))}
                    </button>
                </div>
            </section>`;
    }

    let alRedimensionar = null;
    let alCambiarVisibilidad = null;

    async function render(contenedor) {
        // detener() va ANTES de cargar, no después: cargarRecorrido() arranca la
        // animación al pintar, y llamarlo luego la mataba en el mismo instante
        // —los sobres se quedaban clavados en su posición inicial—.
        detener();
        contenedor.innerHTML = plantilla();

        await cargarRecorrido(contenedor);
        // Los botones se acaban de crear: hay que devolverles el estado real
        // del servicio, si no se quedan en "Start Service" aunque esté corriendo.
        APP.updateStatus();

        // Al cambiar de tamaño hay que recalcular las posiciones: el diagrama
        // pasa de horizontal a vertical por debajo de 720 px.
        let temporizadorTamano = null;
        alRedimensionar = () => {
            clearTimeout(temporizadorTamano);
            temporizadorTamano = setTimeout(() => {
                pararAnimacion();
                dibujar(contenedor);
                arrancarAnimacion();
            }, 150);
        };
        window.addEventListener('resize', alRedimensionar, { passive: true });

        // Con la pestaña de fondo no hay nada que ver: se para el dibujo.
        alCambiarVisibilidad = () => {
            if (document.hidden) pararAnimacion();
            else arrancarAnimacion();
        };
        document.addEventListener('visibilitychange', alCambiarVisibilidad);

        temporizador = setInterval(() => cargarRecorrido(contenedor), REFRESCO_MS);
    }

    /** Suelta todo al salir de la página: temporizador, animación y escuchas. */
    function detener() {
        if (temporizador !== null) {
            clearInterval(temporizador);
            temporizador = null;
        }
        pararAnimacion();
        if (alRedimensionar) {
            window.removeEventListener('resize', alRedimensionar);
            alRedimensionar = null;
        }
        if (alCambiarVisibilidad) {
            document.removeEventListener('visibilitychange', alCambiarVisibilidad);
            alCambiarVisibilidad = null;
        }
    }

    return { render, detener };
})();
