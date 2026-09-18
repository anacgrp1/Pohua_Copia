/**
 * Monitor — las cifras del servicio y su registro.
 *
 * Arriba las tarjetas de estado (servicio, correos procesados, RFQs, errores) y
 * debajo el registro. Estaban en Mail, pero ahí competían con el recorrido del
 * correo: son dos lecturas distintas —una es "cómo va el sistema", la otra "por
 * dónde va un correo"— y mezclarlas obligaba a elegir cuál mirar. Aquí, además,
 * la cifra de errores queda justo encima de las líneas que los explican.
 *
 * Antes esta página decía "log tailing requires WebSocket support (under
 * construction)" y no enseñaba nada. Ahora lee de verdad `GET /api/logs`, que
 * devuelve la cola de app.log ya troceada por nivel.
 *
 * No hace falta WebSocket: se relee cada pocos segundos. Para un registro es
 * de sobra, y evita dejar una conexión abierta por cada pestaña abierta.
 *
 * El asistente no está aquí: vive en la barra fija de toda la aplicación
 * (js/components/assistant.js).
 */
const MonitorPage = (() => {
    'use strict';

    const REFRESCO_MS = 5000;
    const LINEAS = 400;

    let temporizador = null;
    let cargando = false;
    let pegadoAbajo = true;   // ¿el usuario está mirando el final del registro?

    /** Los mensajes salen de correos de clientes: nunca a innerHTML en crudo. */
    function esc(valor) {
        const nodo = document.createElement('span');
        nodo.textContent = valor == null ? '' : String(valor);
        return nodo.innerHTML;
    }

    function pintar(datos) {
        const caja = document.getElementById('monitorLog');
        if (!caja) return;

        if (!datos.disponible) {
            caja.innerHTML = `<p class="log-vacio">${esc(datos.aviso || I18N.t('monitor.sinFichero'))}</p>`;
            return;
        }
        if (!datos.lineas.length) {
            caja.innerHTML = `<p class="log-vacio">${esc(I18N.t('monitor.vacio'))}</p>`;
            return;
        }

        caja.innerHTML = datos.lineas.map(l => {
            const nivel = (l.nivel || 'INFO').toLowerCase();
            // La marca llega como "2026-09-07 11:02:03,123": sobra la fecha
            // (son todas del día) y sobran los milisegundos.
            const hora = (l.marca || '').slice(11, 19);
            return `<div class="log-linea log-linea--${esc(nivel)}">`
                 + `<span class="log-hora">${esc(hora)}</span>`
                 + `<span class="log-nivel">${esc(l.nivel || '')}</span>`
                 + `<span class="log-origen">${esc((l.origen || '').replace(/^cotizador\./, ''))}</span>`
                 + `<span class="log-mensaje">${esc(l.mensaje)}</span>`
                 + `</div>`;
        }).join('');

        // Sólo salta al final si el usuario ya estaba ahí: si subió a leer algo,
        // el refresco no debe arrastrarlo de vuelta abajo.
        if (pegadoAbajo) caja.scrollTop = caja.scrollHeight;

        const meta = document.getElementById('logTotal');
        if (meta) meta.textContent = I18N.t('monitor.lineas', { n: datos.total });
    }

    async function refrescar({ silencioso = true } = {}) {
        if (cargando) return;
        cargando = true;
        try {
            pintar(await API.getLogs(LINEAS));
        } catch (err) {
            if (err && err.sesionExpirada) return;
            // Un fallo del sondeo no se avisa cada 5 segundos: sería una lluvia
            // de mensajes. Sólo si el refresco lo pidió el usuario.
            if (!silencioso) Toast.error(I18N.t('aviso.logFallo', { motivo: err.message }));
        } finally {
            cargando = false;
        }
    }

    // ------------------------------------------------------------- tarjetas

    /**
     * Los cuatro colores de la fila de abajo del brand book de CGR, uno por
     * tarjeta y en el mismo orden que en el libro: gris, azul frío, verde y
     * naranja. Fijos: el color identifica la tarjeta, no su estado. Que el
     * servicio esté en marcha o parado se lee en la propia cifra —"Running" /
     * "Stopped"— y en el icono, que cambia con ella; si además cambiara el
     * color, la fila entera se recolocaría visualmente cada vez que arranca o
     * se detiene el worker.
     */
    const COLORES = {
        status:    'var(--cgr-gris)',
        processed: 'var(--cgr-azul-frio)',
        rfqs:      'var(--cgr-verde)',
        errors:    'var(--cgr-naranja)',
    };

    const ICONOS = {
        // El del servicio cambia con el estado: visto bueno cuando corre,
        // pausa cuando está parado. Es la señal que antes daba el color.
        corriendo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
        parado:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="10" y1="9" x2="10" y2="15"/><line x1="14" y1="9" x2="14" y2="15"/></svg>',
        // En espera no es ni lo uno ni lo otro: el servicio está levantado,
        // pero fuera del horario de atención. Un reloj lo dice sin palabras.
        espera:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
        correo:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>',
        documento: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
        aviso:     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
    };

    async function cargarTarjetas() {
        try {
            const estado = await API.getStatus();
            // La primera tarjeta lleva DOS cosas: si el servicio está
            // levantado y si ahora mismo toca contestar. Fuera del horario de
            // atención decía "En marcha" mientras el buzón llevaba la noche
            // entera sin tocarse, que es la lectura contraria a la verdad.
            const h = estado.horario;
            const r = (typeof Horario !== 'undefined' && h) ? Horario.resumen(h)
                                                            : { enEspera: false, detalle: '' };
            const enEspera = estado.running && r.enEspera;
            const tarjetas = [
                {
                    id: 'status',
                    icono: !estado.running ? ICONOS.parado
                         : (enEspera ? ICONOS.espera : ICONOS.corriendo),
                    valor: !estado.running ? I18N.t('estado.parado')
                         : (enEspera ? I18N.t('horario.enEspera') : I18N.t('estado.corriendo')),
                    etiqueta: estado.running && r.detalle ? r.detalle : I18N.t('tarjeta.estado'),
                    color: COLORES.status,
                },
                {
                    id: 'processed',
                    icono: ICONOS.correo,
                    valor: estado.total_processed,
                    etiqueta: I18N.t('tarjeta.correos'),
                    color: COLORES.processed,
                },
                {
                    id: 'rfqs',
                    icono: ICONOS.documento,
                    valor: estado.total_rfqs,
                    etiqueta: I18N.t('tarjeta.rfqs'),
                    color: COLORES.rfqs,
                },
                {
                    id: 'errors',
                    icono: ICONOS.aviso,
                    valor: estado.total_errors,
                    etiqueta: I18N.t('tarjeta.errores'),
                    color: COLORES.errors,
                },
            ];
            const rejilla = document.getElementById('monitorCards');
            if (rejilla) StatusCard.render(rejilla, tarjetas);
        } catch (err) {
            if (err && err.sesionExpirada) return;
            Toast.error(I18N.t('aviso.estadoFallo', { motivo: err.message }));
        }
    }

    function plantilla() {
        return `
        <div class="kpi-fila" id="monitorCards"></div>

        <section class="monitor-logs">
            <div class="monitor-logs-head">
                <span class="status-dot running"></span>
                <span class="monitor-logs-titulo">${esc(I18N.t('monitor.titulo'))}</span>
                <span class="monitor-logs-meta" id="logTotal"></span>
                <button type="button" class="btn btn-secondary btn-icon" id="logRefrescar"
                        title="${esc(I18N.t('monitor.refrescar'))}" aria-label="${esc(I18N.t('monitor.refrescar'))}">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none"
                         stroke="currentColor" stroke-width="2">
                        <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                    </svg>
                </button>
            </div>
            <div class="monitor-log" id="monitorLog" tabindex="0">
                <p class="log-vacio">${esc(I18N.t('monitor.cargando'))}</p>
            </div>
        </section>`;
    }

    async function render(contenedor) {
        contenedor.innerHTML = plantilla();

        const caja = document.getElementById('monitorLog');
        if (caja) {
            // 40 px de margen: no hay que estar clavado en el píxel final para
            // que cuente como "mirando el final".
            caja.addEventListener('scroll', () => {
                pegadoAbajo = caja.scrollHeight - caja.scrollTop - caja.clientHeight < 40;
            }, { passive: true });
        }
        document.getElementById('logRefrescar')
            ?.addEventListener('click', () => refrescar({ silencioso: false }));

        pegadoAbajo = true;
        await Promise.all([cargarTarjetas(), refrescar()]);

        detener();
        temporizador = setInterval(() => {
            cargarTarjetas();
            refrescar();
        }, REFRESCO_MS);
    }

    /** Corta el sondeo al salir de la página. La llama el router. */
    function detener() {
        if (temporizador !== null) {
            clearInterval(temporizador);
            temporizador = null;
        }
    }

    return { render, detener };
})();
