/**
 * La portada: las estrellas del fondo se juntan y forman el resorte.
 *
 * No hay dos cosas —un cielo y un muelle dibujado encima—: hay UNA. Las mismas
 * estrellas que estaban repartidas por la pantalla viajan hasta su sitio en la
 * hélice y, al llegar, se enhebran unas con otras y aparecen las espiras.
 *
 * ---------------------------------------------------------------------------
 * Cómo está montado
 * ---------------------------------------------------------------------------
 * Cada estrella lleva DOS posiciones: de dónde viene (un punto al azar de la
 * pantalla, como en el cielo normal) y a dónde va (un punto de la hélice). Lo
 * que se anima es el viaje entre las dos.
 *
 * El resorte es UNA hélice continua y las estrellas van ordenadas a lo largo de
 * ella. Eso es lo que permite dibujar el alambre: se une cada estrella con la
 * siguiente, y como son vecinas sobre la misma curva, la línea que las une ES
 * la espira. Con las estrellas colocadas al azar sobre el cilindro no habría
 * forma de saber a cuál unir cada una.
 *
 * Las estrellas no llegan todas a la vez: cada una arranca con un retraso
 * proporcional a su posición en la hélice, así el muelle se va tejiendo de
 * abajo arriba en vez de aparecer de golpe.
 *
 * Una parte se queda en el cielo (`PROPORCION_LIBRES`). Si viajaran todas, el
 * fondo quedaría vacío y la portada perdería el aire de cielo estrellado.
 *
 * Ya formado, dos movimientos siguen: las estrellas avanzan a lo largo del
 * alambre y el conjunto gira. Los periodos no encajan a propósito, para que el
 * bucle no se perciba.
 */
const Hero = (() => {
    'use strict';

    const CONFIG = {
        // Estrellas de referencia para una ventana grande; el número real se
        // escala con el área, como en el campo de estrellas de la aplicación.
        estrellasReferencia: 900,
        areaReferencia: 1600 * 900,
        minimo: 260,
        maximo: 950,

        // Cuántas se quedan de fondo sin unirse al resorte.
        proporcionLibres: 0.18,

        vueltas: 6,
        radioProp: 0.22,       // proporción del lado menor
        altoProp: 0.62,
        perspectiva: 0.30,     // achatamiento de cada vuelta
        grosor: 7,             // dispersión de las estrellas alrededor del alambre

        formacionMs: 2600,     // lo que tarda una estrella en llegar
        escalonadoMs: 1500,    // diferencia entre la primera y la última en salir
        saltoMaxMs: 50,        // recorte por fotograma: un parón no salta la formación

        periodoGiro: 13000,
        periodoRespiro: 8000,
        pasoMin: 0.84,
        pasoMax: 1.14,
        avanceWire: 0.012,     // vueltas por segundo que recorren las estrellas

        radioMax: 1.6,
        dprMaximo: 2,

        // --- Estrellas que siguen al puntero ---
        // Sólo las del fondo: las de la hélice están formando el resorte y
        // sacarlas de ahí desharía las espiras.
        radioIman: 320,        // px: a partir de aquí el puntero deja de tirar
        fuerzaIman: 0.15,      // cuánto se acerca por fotograma (0 = nada, 1 = de golpe)
        regreso: 0.03,         // cuánto vuelve a su sitio cuando el puntero se va
        orbita: 34,            // px: separación alrededor del puntero, para que
                               // no se amontonen todas en el mismo punto
    };

    // Niveles de opacidad en que se agrupa el dibujo. Más niveles = degradado
    // más fino y más órdenes de dibujo; con 8 y 10 el ojo no distingue los
    // escalones y el coste baja dos órdenes de magnitud.
    const NIVELES_LINEA = 8;
    const NIVELES_PUNTO = 10;

    // Se crean una vez y se vacían en cada fotograma: crear 18 arrays por
    // fotograma sería trabajo para el recolector de basura 60 veces por segundo.
    const caminos = Array.from({ length: NIVELES_LINEA }, () => []);
    const puntos = Array.from({ length: NIVELES_PUNTO }, () => []);

    // Posición del puntero, en píxeles CSS del lienzo. `activo` distingue
    // "el ratón está fuera" de "el ratón está en la esquina 0,0".
    const puntero = { x: 0, y: 0, activo: false };

    let lienzo = null, ctx = null;
    let ancho = 0, alto = 0;
    let estrellas = [];
    let animacion = null;
    // Reloj propio, en milisegundos. No es el reloj del navegador: sólo avanza
    // con los fotogramas que de verdad se pintan, y cada salto se recorta. Así
    // el tiempo que la pestaña pasa oculta o ahogada (una recarga en un móvil
    // lento, otra pestaña delante) no se come la formación del resorte: la
    // animación empieza siempre desde cero cuando el usuario la está mirando.
    let reloj = 0;
    let ultimoInstante = 0;
    let temporizadorTamano = null;
    let tinta = '226, 232, 240';

    const sinMovimiento = () =>
        window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function cuantas() {
        const proporcion = (ancho * alto) / CONFIG.areaReferencia;
        return Math.min(CONFIG.maximo,
               Math.max(CONFIG.minimo, Math.round(CONFIG.estrellasReferencia * proporcion)));
    }

    // Blancas en los dos temas, como el campo de estrellas del resto de la
    // aplicación (js/starfield.js): son las mismas estrellas y tienen que
    // verse iguales al pasar de la portada a dentro.
    function leerTinta() {
        tinta = '226, 232, 240';
    }

    function ajustar() {
        const caja = lienzo.parentElement;
        ancho = caja.clientWidth;
        alto = caja.clientHeight;
        if (!ancho || !alto) return false;

        const dpr = Math.min(window.devicePixelRatio || 1, CONFIG.dprMaximo);
        lienzo.width = Math.floor(ancho * dpr);
        lienzo.height = Math.floor(alto * dpr);
        lienzo.style.width = ancho + 'px';
        lienzo.style.height = alto + 'px';
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        return true;
    }

    function crear() {
        const total = cuantas();
        const libres = Math.round(total * CONFIG.proporcionLibres);
        const enHelice = total - libres;

        estrellas = new Array(total);
        for (let i = 0; i < total; i++) {
            const deHelice = i < enHelice;
            const x0 = Math.random() * ancho;
            const y0 = Math.random() * alto;

            estrellas[i] = {
                // De dónde viene: repartida por la pantalla, como el cielo.
                x0, y0,
                // Dónde cae en la hélice: ordenadas, para poder unir vecinas.
                u: deHelice ? i / Math.max(1, enHelice - 1) : null,
                // Desviación respecto al alambre: le da grosor al muelle.
                dx: (Math.random() - 0.5) * CONFIG.grosor,
                dy: (Math.random() - 0.5) * CONFIG.grosor,
                radio: 0.5 + Math.random() * CONFIG.radioMax,
                // Sitio propio alrededor del puntero: sin esto todas caerían
                // exactamente encima del cursor y se verían como un borrón.
                anguloOrbita: Math.random() * Math.PI * 2,
                distanciaOrbita: CONFIG.orbita * (0.35 + Math.random() * 0.9),
                brillo: Math.random(),
                sentido: Math.random() > 0.5 ? 1 : -1,
                // Retraso de salida: proporcional a su sitio, más un poco de
                // azar para que no se vea una línea de salida perfecta.
                retraso: deHelice
                    ? (i / Math.max(1, enHelice)) * CONFIG.escalonadoMs + Math.random() * 260
                    : 0,
                // Arrancan ya colocadas: si empezaran en (0,0) se vería a
                // todas las de fondo cruzando la pantalla en el primer
                // fotograma.
                x: x0, y: y0, formada: 0,
            };
        }
    }

    /** Punto de la hélice para el parámetro u ∈ [0,1]. */
    function puntoHelice(u, giro, paso, geo) {
        const t = u * CONFIG.vueltas * Math.PI * 2;
        const angulo = t + giro;
        return {
            x: geo.cx + geo.radio * Math.sin(angulo),
            y: geo.cy - (geo.altoTotal * paso) / 2 + u * geo.altoTotal * paso
               + geo.radioY * Math.cos(angulo),
            // cos del ángulo: +1 delante, -1 detrás. Sirve para apagar lo que
            // pasa por el otro lado del cilindro.
            cara: Math.cos(angulo),
        };
    }

    const suavizar = (p) => 1 - Math.pow(1 - p, 3);   // rápido al principio

    /**
     * Apagado hacia los bordes de la pantalla.
     *
     * Antes lo hacía una máscara CSS sobre el lienzo, pero eso obliga al
     * navegador a aplicar la máscara sobre una superficie animada a pantalla
     * completa en cada fotograma. Aquí es una multiplicación más sobre una
     * opacidad que ya se estaba calculando: sale gratis.
     */
    function desvanecer(x, y, geo) {
        const dx = (x - geo.cx) / (ancho * 0.5);
        const dy = (y - geo.cy) / (alto * 0.5);
        const d = Math.sqrt(dx * dx + dy * dy);
        if (d < 0.55) return 1;
        return Math.max(0, 1 - (d - 0.55) / 0.55);
    }

    // `instante` aquí es el reloj propio, no el del navegador.
    function dibujar(instante) {
        if (!ctx || !ancho) return;
        const transcurrido = instante;

        ctx.clearRect(0, 0, ancho, alto);

        const menor = Math.min(ancho, alto);
        const geo = {
            cx: ancho / 2,
            cy: alto / 2,
            radio: menor * CONFIG.radioProp,
            radioY: menor * CONFIG.radioProp * CONFIG.perspectiva,
            altoTotal: alto * CONFIG.altoProp,
        };

        const giro = (instante / CONFIG.periodoGiro) * Math.PI * 2;
        const faseRespiro = (instante % CONFIG.periodoRespiro) / CONFIG.periodoRespiro;
        const paso = CONFIG.pasoMin
                   + (CONFIG.pasoMax - CONFIG.pasoMin) * (1 - Math.cos(faseRespiro * Math.PI * 2)) / 2;

        // Cuánto han avanzado las estrellas a lo largo del alambre.
        const recorrido = (instante / 1000) * CONFIG.avanceWire;

        // ---- 1. Posición de cada estrella --------------------------------
        for (const e of estrellas) {
            if (e.u === null) {
                // Las de fondo suben despacio, como el cielo.
                e.y0 -= 0.12;
                if (e.y0 < 0) { e.y0 = alto; e.x0 = Math.random() * ancho; }

                // ...salvo las que tenga cerca el puntero: ésas lo siguen.
                //
                // Se mueve `x`/`y` (lo que se pinta) y NO `x0`/`y0` (su sitio
                // en el cielo). Así, en cuanto el ratón se va, cada una sabe a
                // dónde volver; si se moviera el sitio, el cielo se
                // desordenaría un poco más con cada pasada del ratón.
                let destinoX = e.x0, destinoY = e.y0, tiron = CONFIG.regreso;
                e.atraida = 0;

                if (puntero.activo) {
                    const dx = puntero.x - e.x;
                    const dy = puntero.y - e.y;
                    const distancia = Math.hypot(dx, dy);
                    if (distancia < CONFIG.radioIman) {
                        // La fuerza cae con la distancia: las de al lado del
                        // cursor lo siguen de cerca, las del borde apenas se
                        // enteran. Con fuerza constante, todo el grupo saltaría
                        // a la vez y parecería un enjambre.
                        const cerca = 1 - distancia / CONFIG.radioIman;
                        destinoX = puntero.x + Math.cos(e.anguloOrbita) * e.distanciaOrbita;
                        destinoY = puntero.y + Math.sin(e.anguloOrbita) * e.distanciaOrbita;
                        tiron = CONFIG.fuerzaIman * cerca * cerca;
                        e.atraida = cerca;
                        // Gira despacio alrededor del cursor mientras lo sigue.
                        e.anguloOrbita += 0.02;
                    }
                }

                e.x += (destinoX - e.x) * tiron;
                e.y += (destinoY - e.y) * tiron;
                e.formada = 0; e.cara = 1;
                continue;
            }

            const avance = Math.max(0, Math.min(1,
                (transcurrido - e.retraso) / CONFIG.formacionMs));
            e.formada = suavizar(avance);

            // `u` avanza con el tiempo: una vez formadas, las estrellas
            // recorren el alambre. El módulo las devuelve al principio.
            const u = (e.u + recorrido) % 1;
            const destino = puntoHelice(u, giro, paso, geo);
            e.cara = destino.cara;

            e.x = e.x0 + (destino.x + e.dx - e.x0) * e.formada;
            e.y = e.y0 + (destino.y + e.dy - e.y0) * e.formada;
        }

        // ---- 2. El alambre ------------------------------------------------
        // Uniendo cada estrella con la SIGUIENTE de la hélice aparecen las
        // espiras. Va antes que los puntos para que las estrellas queden encima.
        //
        // Se dibuja AGRUPANDO por opacidad. Cada `beginPath`+`stroke` es una
        // orden al motor de dibujo, y con ~900 segmentos sueltos eran 900
        // órdenes por fotograma: medido, bajaba a 17 fps en un monitor grande.
        // Redondeando la opacidad a unos pocos niveles, todos los segmentos que
        // comparten nivel entran en un mismo trazo: de 900 órdenes a 6.
        ctx.lineWidth = 1;
        for (const camino of caminos) { camino.length = 0; }

        let previa = null;
        for (const e of estrellas) {
            if (e.u === null) { previa = null; continue; }
            if (previa) {
                // Sólo se une lo ya formado, y sin cruzar el salto del módulo:
                // si una estrella volvió al principio del alambre, la línea
                // cruzaría toda la figura de arriba abajo.
                const formado = Math.min(previa.formada, e.formada);
                const salto = Math.hypot(e.x - previa.x, e.y - previa.y) > geo.radio;
                if (formado > 0.05 && !salto) {
                    const alfa = 0.42 * formado * (0.30 + 0.70 * Math.max(0, e.cara))
                               * desvanecer(e.x, e.y, geo);
                    const nivel = Math.min(NIVELES_LINEA - 1,
                                           Math.round(alfa * (NIVELES_LINEA - 1) / 0.42));
                    caminos[nivel].push(previa.x, previa.y, e.x, e.y);
                }
            }
            previa = e;
        }

        for (let n = 1; n < NIVELES_LINEA; n++) {
            const puntos = caminos[n];
            if (!puntos.length) continue;
            ctx.strokeStyle = `rgba(${tinta}, ${(0.42 * n / (NIVELES_LINEA - 1)).toFixed(3)})`;
            ctx.beginPath();
            for (let i = 0; i < puntos.length; i += 4) {
                ctx.moveTo(puntos[i], puntos[i + 1]);
                ctx.lineTo(puntos[i + 2], puntos[i + 3]);
            }
            ctx.stroke();
        }

        // ---- 3. Las estrellas ---------------------------------------------
        // Mismo agrupado por opacidad: un `fill` por nivel en lugar de uno por
        // estrella.
        for (const grupo of puntos) { grupo.length = 0; }

        for (const e of estrellas) {
            e.brillo += 0.01 * e.sentido;
            if (e.brillo <= 0.25) { e.brillo = 0.25; e.sentido = 1; }
            else if (e.brillo >= 1) { e.brillo = 1; e.sentido = -1; }

            // Ya en la hélice, las de detrás se apagan: eso es lo que hace que
            // el cilindro se vea como un volumen y no como un anillo plano.
            const profundidad = e.u === null ? 1
                              : 1 - e.formada * 0.6 * (1 - Math.max(0, e.cara));

            // Las que sigue el puntero se encienden. Sin esto el efecto está
            // pero no se percibe: unas cuantas estrellas tenues moviéndose
            // despacio pasan desapercibidas sobre un cielo lleno de ellas.
            const encendido = 1 + 0.9 * (e.atraida || 0);
            const alfa = Math.min(1, e.brillo * profundidad * encendido)
                       * desvanecer(e.x, e.y, geo);
            const nivel = Math.min(NIVELES_PUNTO - 1, Math.round(alfa * (NIVELES_PUNTO - 1)));
            puntos[nivel].push(e.x, e.y,
                               e.radio * (1 + 0.35 * e.formada + 0.5 * (e.atraida || 0)));
        }

        for (let n = 1; n < NIVELES_PUNTO; n++) {
            const grupo = puntos[n];
            if (!grupo.length) continue;
            ctx.fillStyle = `rgba(${tinta}, ${(n / (NIVELES_PUNTO - 1)).toFixed(3)})`;
            ctx.beginPath();
            for (let i = 0; i < grupo.length; i += 3) {
                const x = grupo[i], y = grupo[i + 1], r = grupo[i + 2];
                // moveTo antes de cada arco: si no, el trazado une el final de
                // un círculo con el principio del siguiente y salen radios.
                ctx.moveTo(x + r, y);
                ctx.arc(x, y, r, 0, Math.PI * 2);
            }
            ctx.fill();
        }
    }

    function animar(instante) {
        if (!ultimoInstante) ultimoInstante = instante;
        // El recorte a 50 ms evita que un parón (pestaña oculta, hilo ocupado)
        // se traduzca en un salto de la animación al volver.
        reloj += Math.min(instante - ultimoInstante, CONFIG.saltoMaxMs);
        ultimoInstante = instante;
        dibujar(reloj);
        animacion = requestAnimationFrame(animar);
    }

    function arrancar() {
        if (animacion !== null) return;
        if (sinMovimiento()) {
            // Sin movimiento: el resorte ya formado y quieto. Se pinta con un
            // instante muy avanzado para saltarse la formación.
            reloj = CONFIG.formacionMs + CONFIG.escalonadoMs + 1;
            dibujar(reloj);
            return;
        }
        animacion = requestAnimationFrame(animar);
    }

    function parar() {
        if (animacion !== null) {
            cancelAnimationFrame(animacion);
            animacion = null;
        }
        // Al reanudar, el primer fotograma vuelve a fijar la referencia.
        ultimoInstante = 0;
    }

    function rehacer({ desdeCero = false } = {}) {
        parar();
        leerTinta();
        if (!ajustar()) return;
        crear();
        if (desdeCero) { reloj = 0; ultimoInstante = 0; }
        arrancar();
    }

    function init(elemento) {
        lienzo = elemento;
        if (!lienzo || !lienzo.getContext) return;
        ctx = lienzo.getContext('2d', { alpha: true });
        if (!ctx) return;

        rehacer({ desdeCero: true });

        // El puntero se escucha en el CONTENEDOR, no en el lienzo: el lienzo
        // lleva `pointer-events: none` para que los clics lleguen al botón que
        // hay encima, así que él nunca recibiría estos eventos.
        const zona = lienzo.parentElement?.parentElement || lienzo.parentElement;
        if (zona && !zona.dataset.punteroConectado) {
            zona.dataset.punteroConectado = '1';

            zona.addEventListener('pointermove', (ev) => {
                // Sólo ratón y lápiz: en una pantalla táctil el dedo tapa
                // justo lo que atraería, y además dispararía al tocar el botón.
                if (ev.pointerType === 'touch') return;
                const caja = lienzo.getBoundingClientRect();
                puntero.x = ev.clientX - caja.left;
                puntero.y = ev.clientY - caja.top;
                puntero.activo = true;
            }, { passive: true });

            zona.addEventListener('pointerleave', () => { puntero.activo = false; });
        }

        if (!init.conectado) {
            init.conectado = true;

            window.addEventListener('resize', () => {
                clearTimeout(temporizadorTamano);
                // Al redimensionar NO se repite la formación: sería un fogonazo
                // cada vez que alguien ajusta la ventana.
                temporizadorTamano = setTimeout(() => rehacer(), 180);
            }, { passive: true });

            document.addEventListener('visibilitychange', () => {
                if (document.hidden) parar(); else arrancar();
            });

            new MutationObserver(leerTinta).observe(document.documentElement,
                { attributes: true, attributeFilter: ['data-tema'] });
        }
    }

    return { init, parar, rehacer };
})();
