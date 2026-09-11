/**
 * CGR Cotizador — Fondo estrellado (canvas).
 *
 * Dibuja el campo de estrellas detrás de toda la aplicación: pantalla de
 * acceso y aplicación una vez dentro. Las estrellas suben despacio y parpadean.
 *
 * Adaptaciones respecto al fragmento original:
 *
 *  1. NO se toca `overflow` de html/body. El original lo ponía en `hidden` para
 *     evitar barras de desplazamiento; aquí eso dejaría las tablas de RFQ sin
 *     poder desplazarse. El canvas va `position: fixed`, que resuelve lo mismo
 *     sin romper el scroll.
 *  2. NO se fija el color de fondo. El de la aplicación es --bg-base, y el
 *     resplandor azul y rosa de la marca se pinta en CSS por debajo.
 *  3. Se tiene en cuenta la densidad de pantalla (devicePixelRatio). Sin eso,
 *     en pantallas Retina o con escalado de Windows, las estrellas se ven
 *     borrosas: el canvas se dibuja a menos píxeles de los que ocupa.
 *  4. El número de estrellas se calcula según el tamaño de la ventana. 400
 *     fijas es correcto en un monitor grande y demasiadas en un teléfono.
 *  5. Al redimensionar se recolocan. En el original conservaban sus antiguas
 *     coordenadas, así que al agrandar la ventana quedaba media pantalla vacía.
 *  6. Se respeta `prefers-reduced-motion` y se detiene la animación con la
 *     pestaña en segundo plano.
 */
const Starfield = (() => {
    'use strict';

    const CONFIG = {
        // Estrellas de referencia para una ventana de escritorio (1920x1080).
        // El número real se escala con el área de la ventana.
        estrellasReferencia: 400,
        areaReferencia: 1920 * 1080,
        minimo: 90,
        maximo: 520,

        radioMax: 1.5,          // px
        velocidadMin: 0.1,      // px por fotograma
        velocidadMax: 0.6,
        parpadeoPaso: 0.01,
        opacidadMin: 0.2,

        // Más de 2x apenas se nota y multiplica el trabajo de dibujo.
        dprMaximo: 2,
    };

    let canvas = null;
    let ctx = null;
    let estrellas = [];
    let animacion = null;
    let ancho = 0;    // en píxeles CSS, no del lienzo
    let alto = 0;
    let temporizadorResize = null;

    // Las estrellas son BLANCAS en los dos temas: son las mismas estrellas, y
    // cambiarlas de color al cambiar de tema las convertía en otra cosa. Lo
    // único que se ajusta es la fuerza, porque el fondo claro tiene menos
    // recorrido por debajo del blanco que el oscuro por encima.
    const TINTA = '255, 255, 255';
    let fuerza = 1;

    const sinMovimiento = () =>
        window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function leerTinta() {
        const claro = document.documentElement.dataset.tema === 'light';
        // En claro van a plena opacidad: el fondo lavanda deja poco margen por
        // encima y bajarlas las borraría. En oscuro se conserva el parpadeo de
        // siempre, que ahí sí luce.
        fuerza = claro ? 1 : 1;
    }

    function cuantasEstrellas() {
        const proporcion = (ancho * alto) / CONFIG.areaReferencia;
        const calculadas = Math.round(CONFIG.estrellasReferencia * proporcion);
        return Math.min(CONFIG.maximo, Math.max(CONFIG.minimo, calculadas));
    }

    /** Ajusta el lienzo al tamaño de la ventana, con la densidad de pantalla. */
    function ajustarLienzo() {
        ancho = window.innerWidth;
        alto = window.innerHeight;

        const dpr = Math.min(window.devicePixelRatio || 1, CONFIG.dprMaximo);

        // El lienzo tiene dos tamaños: el de dibujo (en píxeles reales) y el
        // que ocupa en la página (en píxeles CSS). Si sólo se fija el primero,
        // el navegador lo estira y las estrellas salen borrosas.
        canvas.width = Math.floor(ancho * dpr);
        canvas.height = Math.floor(alto * dpr);
        canvas.style.width = ancho + 'px';
        canvas.style.height = alto + 'px';

        // Con esto el resto del código trabaja en píxeles CSS y se olvida del dpr.
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function crearEstrellas() {
        const total = cuantasEstrellas();
        estrellas = new Array(total);
        for (let i = 0; i < total; i++) {
            estrellas[i] = {
                x: Math.random() * ancho,
                y: Math.random() * alto,
                radio: Math.random() * CONFIG.radioMax,
                velocidad: Math.random() * (CONFIG.velocidadMax - CONFIG.velocidadMin)
                           + CONFIG.velocidadMin,
                opacidad: Math.random(),
                // Dirección del parpadeo: +1 se enciende, -1 se apaga.
                sentido: Math.random() > 0.5 ? 1 : -1,
            };
        }
    }

    function dibujar(mover) {
        ctx.clearRect(0, 0, ancho, alto);

        for (let i = 0; i < estrellas.length; i++) {
            const estrella = estrellas[i];

            if (mover) {
                estrella.y -= estrella.velocidad;
                // Al salir por arriba, vuelve a entrar por abajo en otra columna.
                if (estrella.y < 0) {
                    estrella.y = alto;
                    estrella.x = Math.random() * ancho;
                }

                estrella.opacidad += CONFIG.parpadeoPaso * estrella.sentido;
                if (estrella.opacidad <= CONFIG.opacidadMin) {
                    estrella.opacidad = CONFIG.opacidadMin;
                    estrella.sentido = 1;
                } else if (estrella.opacidad >= 1) {
                    estrella.opacidad = 1;
                    estrella.sentido = -1;
                }
            }

            ctx.beginPath();
            ctx.arc(estrella.x, estrella.y, estrella.radio, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(' + TINTA + ', ' + (estrella.opacidad * fuerza) + ')';
            ctx.fill();
        }
    }

    function animar() {
        dibujar(true);
        animacion = requestAnimationFrame(animar);
    }

    function arrancarAnimacion() {
        if (animacion !== null) return;
        if (sinMovimiento()) {
            dibujar(false);   // se pintan quietas, pero se ven
            return;
        }
        animacion = requestAnimationFrame(animar);
    }

    function detenerAnimacion() {
        if (animacion !== null) {
            cancelAnimationFrame(animacion);
            animacion = null;
        }
    }

    function rehacer() {
        detenerAnimacion();
        leerTinta();
        ajustarLienzo();
        crearEstrellas();
        arrancarAnimacion();
    }

    function alRedimensionar() {
        // En móvil, mostrar u ocultar la barra de direcciones dispara resize
        // continuamente. Sólo se rehace si el cambio es apreciable.
        const cambioAncho = Math.abs(window.innerWidth - ancho);
        const cambioAlto = Math.abs(window.innerHeight - alto);
        if (cambioAncho < 80 && cambioAlto < 140) return;

        clearTimeout(temporizadorResize);
        temporizadorResize = setTimeout(rehacer, 200);
    }

    function init() {
        canvas = document.getElementById('starfield');
        if (!canvas || !canvas.getContext) return;

        ctx = canvas.getContext('2d', { alpha: true });
        if (!ctx) return;

        rehacer();

        // Al cambiar de tema se repinta con la tinta nueva. Sólo cambia el
        // color: las estrellas siguen donde estaban y no dan un salto.
        new MutationObserver(() => {
            leerTinta();
            if (animacion === null) dibujar(false);
        }).observe(document.documentElement,
                   { attributes: true, attributeFilter: ['data-tema'] });

        window.addEventListener('resize', alRedimensionar, { passive: true });

        // Con la pestaña en segundo plano no hay nada que dibujar. El navegador
        // ya frena requestAnimationFrame, pero pararlo del todo es gratis.
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                detenerAnimacion();
            } else {
                arrancarAnimacion();
            }
        });

        // Si cambia la preferencia de movimiento sobre la marcha.
        if (window.matchMedia) {
            const consulta = window.matchMedia('(prefers-reduced-motion: reduce)');
            const alCambiar = () => rehacer();
            if (consulta.addEventListener) {
                consulta.addEventListener('change', alCambiar);
            } else if (consulta.addListener) {
                consulta.addListener(alCambiar);   // Safari antiguo
            }
        }
    }

    /**
     * Para y reanuda el campo desde fuera.
     *
     * Lo usa la portada: allí las estrellas las dibuja su propio lienzo (el que
     * las convierte en el resorte), así que este queda invisible. Ocultarlo con
     * `opacity: 0` NO basta: el navegador seguiría repintando un lienzo a
     * pantalla completa 60 veces por segundo para nada, y en un monitor grande
     * eso se lleva la mitad de los fotogramas.
     */
    function pausar() { detenerAnimacion(); }
    function reanudar() { arrancarAnimacion(); }

    return { init, rehacer, pausar, reanudar };
})();

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', Starfield.init);
} else {
    Starfield.init();
}
