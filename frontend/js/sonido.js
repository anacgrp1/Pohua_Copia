/**
 * El sonido de los avisos.
 *
 * Un aviso que no suena casi no se ve: la campana se pinta en una esquina y
 * quien está en otra pestaña —o en el mismo Pohua, cotizando— no se entera
 * hasta que mira. Esto le pone un tono corto a la llegada de un aviso nuevo.
 *
 * Qué suena y qué no:
 *
 *   - Con Pohua ABIERTA suena esto, que es nuestro: dos notas cortas para un
 *     aviso normal y tres, más graves y más marcadas, para uno crítico. La
 *     diferencia se oye sin mirar la pantalla, que es la gracia.
 *   - Con Pohua CERRADA el aviso lo pinta el sistema (Windows, Android) y el
 *     navegador NO deja poner un sonido propio: la Notifications API nunca
 *     tuvo `sound`. Allí sólo se puede pedir que suene —y que vibre en el
 *     teléfono—, con el sonido que el sistema tenga puesto. Eso se pide en
 *     sw.js; aquí no se puede hacer nada más.
 *
 * Por qué se genera el tono en vez de traer un .mp3:
 *
 *   - No hay fichero que descargar ni que cachear: suena igual sin conexión,
 *     que es la mitad de la razón de que esto sea una PWA.
 *   - No hay "clip" que se corte a medias ni un archivo de 40 KB para 300 ms.
 *   - Se puede cambiar el carácter del tono en una línea.
 *
 * El permiso del navegador: ningún sitio puede sonar antes de que la persona
 * toque la página (política de autoarranque). Por eso el contexto de audio se
 * crea dormido y se despierta con el primer clic o la primera tecla; hasta
 * entonces, `sonar()` no hace nada y no revienta. En la práctica nadie llega a
 * tener un aviso sin haber hecho clic antes: se entra con usuario y
 * contraseña.
 *
 * Se recuerda por equipo (localStorage), no por usuario: el volumen de una
 * oficina compartida es cosa de la máquina, no de la cuenta.
 */
const Sonido = (() => {
    'use strict';

    const CLAVE = 'cgr-sonido';
    const VOLUMEN = 0.16;       // discreto: es una oficina, no un videojuego

    let ctx = null;
    let despierto = false;

    /** Encendido salvo que alguien lo haya apagado en este equipo. */
    function encendido() {
        try {
            return localStorage.getItem(CLAVE) !== 'no';
        } catch (_) {
            return true;        // navegador sin almacenamiento: que suene
        }
    }

    function fijar(si) {
        try {
            localStorage.setItem(CLAVE, si ? 'si' : 'no');
        } catch (_) { /* si no se puede guardar, al menos suena esta sesión */ }
        if (si) despertar();
    }

    function alternar() {
        const nuevo = !encendido();
        fijar(nuevo);
        return nuevo;
    }

    /** El contexto de audio, creado la primera vez que hace falta. */
    function contexto() {
        if (ctx) return ctx;
        const AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return null;
        try { ctx = new AC(); } catch (_) { return null; }
        return ctx;
    }

    /**
     * Despertar el audio con el primer gesto de la persona.
     *
     * Chrome y Safari crean el contexto en `suspended` si nadie ha tocado la
     * página todavía. Un `resume()` dentro del manejador de un clic lo
     * desbloquea para el resto de la sesión.
     */
    function despertar() {
        const c = contexto();
        if (!c) return;
        if (c.state === 'suspended') c.resume().catch(() => {});
        despierto = true;
    }

    /** Una nota: seno suave con entrada y salida, que no chasquee. */
    function nota(c, frecuencia, empieza, dura, volumen) {
        const osc = c.createOscillator();
        const gan = c.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(frecuencia, empieza);
        // Rampa en vez de saltos: un gain que salta de 0 a 0.16 hace "clic".
        gan.gain.setValueAtTime(0.0001, empieza);
        gan.gain.exponentialRampToValueAtTime(volumen, empieza + 0.012);
        gan.gain.exponentialRampToValueAtTime(0.0001, empieza + dura);
        osc.connect(gan).connect(c.destination);
        osc.start(empieza);
        osc.stop(empieza + dura + 0.02);
    }

    /**
     * Sonar por un aviso.
     *
     * @param {string} nivel 'crit' suena distinto; lo demás, el tono normal.
     */
    function sonar(nivel) {
        if (!encendido()) return;
        const c = contexto();
        if (!c) return;
        if (c.state === 'suspended') {
            // Todavía no hubo gesto: se intenta despertar y se deja pasar este
            // aviso en silencio en vez de quedar una nota colgada sonando
            // cuando la persona vuelva.
            c.resume().catch(() => {});
            if (c.state === 'suspended') return;
        }

        const t = c.currentTime + 0.01;
        if (nivel === 'crit') {
            // Tres notas que bajan: se oye como algo que pide atención.
            nota(c, 784.0, t,        0.16, VOLUMEN);         // sol5
            nota(c, 659.3, t + 0.17, 0.16, VOLUMEN);         // mi5
            nota(c, 523.3, t + 0.34, 0.30, VOLUMEN * 1.15);  // do5
        } else {
            // Dos notas que suben: "hay algo nuevo", sin alarma.
            nota(c, 587.3, t,        0.13, VOLUMEN * 0.9);   // re5
            nota(c, 880.0, t + 0.13, 0.22, VOLUMEN);         // la5
        }
    }

    /** El botón "Probar" de la campana: suena aunque esté apagado. */
    function probar(nivel) {
        despertar();
        const antes = encendido();
        try {
            localStorage.setItem(CLAVE, 'si');
            sonar(nivel);
        } catch (_) {
            sonar(nivel);
        } finally {
            if (!antes) { try { localStorage.setItem(CLAVE, 'no'); } catch (_) {} }
        }
    }

    function init() {
        // Un solo gesto basta para toda la sesión.
        const unaVez = () => {
            despertar();
            document.removeEventListener('click', unaVez);
            document.removeEventListener('keydown', unaVez);
        };
        document.addEventListener('click', unaVez);
        document.addEventListener('keydown', unaVez);
    }

    return { init, sonar, probar, encendido, fijar, alternar,
             get listo() { return despierto; } };
})();
