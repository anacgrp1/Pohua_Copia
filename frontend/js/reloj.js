/**
 * El reloj de las tres casas: Kansas City, Querétaro y Sevran.
 *
 * Va fijo, centrado y arriba, entre el título de la página y los controles de
 * la esquina. No es adorno: en esta operación conviven tres husos —la planta
 * de Missouri, la oficina de Querétaro y la de Francia— y "a las cuatro"
 * significa tres horas distintas según quién lo diga. Tener la hora del otro a
 * la vista evita media conversación.
 *
 * Tres modos, uno por casa, y cada uno se escribe como se escribe ALLÍ, no
 * como se escribe en el idioma de la interfaz:
 *
 *   Kansas City (EE. UU.)  mes/día/año   12 h        09/09/2026 · 9:40:40 AM
 *   Querétaro   (México)   día/mes/año   12 h        09/09/2026 · 9:40:40 a. m.
 *   Sevran      (Francia)  día/mes/año   24 h        09/09/2026 · 16h40:40
 *
 * El formato lo manda el LUGAR, no el idioma: un francés que mire la app en
 * inglés sigue queriendo ver 16h40 para Sevran. Por eso las plantillas de
 * abajo están junto a la zona horaria y no en i18n.js.
 *
 * Relación con el selector de idioma: el reloj arranca en la casa que
 * corresponde al idioma (en→Kansas City, es→Querétaro, fr→Sevran) y la sigue
 * mientras nadie lo toque. En cuanto alguien pulsa el reloj, la elección es
 * suya, se guarda y el idioma deja de moverlo. Un clic rota a la siguiente
 * casa; con Mayúsculas, a la anterior.
 */
const Reloj = (() => {
    'use strict';

    const CLAVE = 'cgr-reloj';

    /**
     * Las tres casas, en el mismo orden que los idiomas (EN, ES, FR): al
     * rotar se recorre ese orden, que es el que ya conoce quien usa el
     * selector de idioma.
     */
    const CASAS = [
        {
            id: 'kc',
            idioma: 'en',
            zona: 'America/Chicago',
            ciudad: 'Kansas City',
            codigo: 'KC',
            // Missouri: mes/día/año y 12 horas con AM/PM.
            fecha: p => `${p.month}/${p.day}/${p.year}`,
            hora:  p => `${doce(p)}:${p.minute}:${p.second} ${p.hour < 12 ? 'AM' : 'PM'}`,
        },
        {
            id: 'qro',
            idioma: 'es',
            zona: 'America/Mexico_City',
            ciudad: 'Querétaro',
            codigo: 'QRO',
            // México: día/mes/año y 12 horas en su forma conversacional,
            // "a. m." / "p. m." con punto y espacio, que es como se escribe.
            fecha: p => `${p.day}/${p.month}/${p.year}`,
            hora:  p => `${doce(p)}:${p.minute}:${p.second} ${p.hour < 12 ? 'a. m.' : 'p. m.'}`,
        },
        {
            id: 'sev',
            idioma: 'fr',
            zona: 'Europe/Paris',
            ciudad: 'Sevran',
            codigo: 'SEV',
            // Francia: día/mes/año y 24 horas. La "h" separa hora y minuto
            // (16h40, nunca 16:40); los segundos van detrás con dos puntos,
            // que es lo que hace un reloj digital francés cuando los enseña.
            fecha: p => `${p.day}/${p.month}/${p.year}`,
            hora:  p => `${p.hour2}h${p.minute}:${p.second}`,
        },
    ];

    /** La hora de 24 en la de 12, con el 0 convertido en 12 y no en 0. */
    function doce(p) {
        return p.hour % 12 || 12;
    }

    let indice = 0;          // casa que se está enseñando
    let fijadaPorMano = false; // ¿la eligió alguien, o la sigue mandando el idioma?
    let temporizador = null;

    const boton  = () => document.getElementById('btnReloj');
    const elFecha  = () => document.getElementById('relojFecha');
    const elHora   = () => document.getElementById('relojHora');
    const elCiudad = () => document.getElementById('relojCiudad');
    const elCodigo = () => document.getElementById('relojCodigo');

    /**
     * Los números de la fecha y la hora en una zona dada.
     *
     * Se piden a Intl en inglés y en 24 horas —el formato de salida lo pone
     * luego cada casa— porque lo único que se necesita de aquí son las cifras
     * ya trasladadas al huso correcto, incluido el horario de verano, que
     * cambia en fechas distintas a un lado y otro del Atlántico.
     */
    function partes(fecha, zona) {
        const fmt = new Intl.DateTimeFormat('en-US', {
            timeZone: zona,
            hourCycle: 'h23',
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
        });
        const p = {};
        for (const parte of fmt.formatToParts(fecha)) p[parte.type] = parte.value;
        // Algunos motores devuelven "24" para la medianoche aun pidiendo h23.
        if (p.hour === '24') p.hour = '00';
        p.hour2 = p.hour;              // con cero delante, para el formato francés
        p.hour = parseInt(p.hour, 10); // como número, para decidir AM/PM
        return p;
    }

    /** "GMT-05:00" de la zona, para el globito de ayuda. */
    function desfase(fecha, zona) {
        try {
            const fmt = new Intl.DateTimeFormat('en-US', { timeZone: zona, timeZoneName: 'longOffset' });
            const parte = fmt.formatToParts(fecha).find(p => p.type === 'timeZoneName');
            return parte ? parte.value : '';
        } catch (err) {
            return '';
        }
    }

    function pintar() {
        const casa = CASAS[indice];
        const ahora = new Date();
        const p = partes(ahora, casa.zona);
        const fecha = casa.fecha(p);
        const hora = casa.hora(p);

        const f = elFecha(); if (f) f.textContent = fecha;
        const h = elHora();  if (h) h.textContent = hora;
        const c = elCiudad(); if (c) c.textContent = casa.ciudad;
        const k = elCodigo(); if (k) k.textContent = casa.codigo;

        const b = boton();
        if (b) {
            b.dataset.casa = casa.id;
            // El título explica qué pasa al pulsar; la etiqueta accesible dice
            // qué se está viendo. Son dos cosas distintas y por eso no se usa
            // data-i18n-titulo, que pondría el mismo texto en las dos.
            const off = desfase(ahora, casa.zona);
            b.setAttribute('title', `${I18N.t('reloj.boton')} — ${casa.ciudad}${off ? ' (' + off + ')' : ''}`);
            b.setAttribute('aria-label', `${casa.ciudad}: ${fecha}, ${hora}`);
        }
    }

    /**
     * El siguiente tic, cuadrado con el segundo del sistema.
     *
     * Con un setInterval de 1000 el reloj se va desfasando y acaba saltándose
     * un segundo de vez en cuando; midiendo lo que falta para el siguiente
     * segundo redondo, cada cambio cae donde debe.
     */
    function programar() {
        detener();
        const falta = 1000 - (Date.now() % 1000);
        temporizador = setTimeout(() => { pintar(); programar(); }, falta + 10);
    }

    function detener() {
        if (temporizador) { clearTimeout(temporizador); temporizador = null; }
    }

    function fijar(id, { guardarlo = true } = {}) {
        const i = CASAS.findIndex(c => c.id === id);
        if (i < 0) return;
        indice = i;
        if (guardarlo) {
            fijadaPorMano = true;
            try { localStorage.setItem(CLAVE, id); } catch (err) { /* modo privado */ }
        }
        pintar();
    }

    function rotar(atras = false) {
        const paso = atras ? CASAS.length - 1 : 1;
        fijar(CASAS[(indice + paso) % CASAS.length].id);
    }

    /** La casa que le toca a un idioma. */
    function porIdioma(codigo) {
        return (CASAS.find(c => c.idioma === codigo) || CASAS[0]).id;
    }

    function leerGuardada() {
        try {
            const v = localStorage.getItem(CLAVE);
            return CASAS.some(c => c.id === v) ? v : null;
        } catch (err) {
            return null;
        }
    }

    /**
     * El reloj sale dentro de la aplicación y en ningún otro sitio.
     *
     * En la portada estorbaba: ahí el nombre "Pohua" va centrado arriba, justo
     * donde vive el reloj, y los dos se pisaban. Pero la regla no es "en la
     * portada no" sino al revés, y por dos motivos:
     *
     *   - Fuera de la aplicación no sirve para nada. La hora de Kansas City
     *     importa cuando se está trabajando un RFQ con ellos, no mirando la
     *     pantalla de entrada.
     *   - En el primer pintado no se sabe todavía qué pantalla toca: la portada
     *     y la aplicación arrancan las dos escondidas y alguien lo decide un
     *     instante después. Con la regla al revés, ese instante enseñaba el
     *     reloj sobre el título y luego lo quitaba: un parpadeo.
     *
     * Se mira el atributo `hidden` de `.app-layout` y no la sesión ni la ruta:
     * quien decide qué pantalla se enseña es la aplicación, y este módulo sólo
     * tiene que enterarse. El observador lo hace sin que nadie tenga que
     * acordarse de avisar al reloj al cambiar de pantalla.
     */
    function enLaAplicacion() {
        const app = document.querySelector('.app-layout');
        return !!app && !app.hidden;
    }

    function ajustarVisibilidad() {
        const caja = document.getElementById('reloj');
        if (!caja) return;
        const fuera = !enLaAplicacion();
        caja.hidden = fuera;
        // Escondido no se pinta: un temporizador cada segundo para algo que
        // nadie ve gasta batería y no cambia nada.
        if (fuera) detener();
        else { pintar(); programar(); }
    }

    function init() {
        const b = boton();
        if (!b) return;

        const guardada = leerGuardada();
        if (guardada) {
            fijadaPorMano = true;
            fijar(guardada, { guardarlo: false });
        } else {
            fijar(porIdioma(typeof I18N !== 'undefined' ? I18N.idioma : 'en'), { guardarlo: false });
        }

        b.addEventListener('click', (ev) => rotar(ev.shiftKey));

        // Mientras nadie haya elegido a mano, el reloj acompaña al idioma; el
        // globito se repinta siempre, que también está traducido.
        if (typeof I18N !== 'undefined') {
            I18N.alCambiar((codigo) => {
                if (!fijadaPorMano) fijar(porIdioma(codigo), { guardarlo: false });
                else pintar();
            });
        }

        // Con la pestaña de fondo no hay nada que enseñar: se para el tic y al
        // volver se repinta de golpe, para no enseñar la hora de hace un rato.
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) detener();
            else ajustarVisibilidad();   // que no reviva el tic estando en la portada
        });

        const app = document.querySelector('.app-layout');
        if (app) {
            new MutationObserver(ajustarVisibilidad)
                .observe(app, { attributes: true, attributeFilter: ['hidden'] });
        }

        // Ajustar decide si además hay que arrancar el tic, así que sustituye
        // al pintar()+programar() que había aquí: en la portada no se arranca.
        ajustarVisibilidad();
    }

    return { init, fijar, rotar, CASAS };
})();

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', Reloj.init);
} else {
    Reloj.init();
}
