/**
 * El horario de atención, dicho en el reloj que cada quien tenga puesto.
 *
 * La ventana es UNA: de lunes a viernes, de 7:00 a 17:00 de la planta (Kansas
 * City). Fuera de ella el sistema no abre el buzón —el correo se queda sin
 * leer y entra en el primer ciclo de la apertura siguiente—, así que la
 * pantalla tiene que poder decir dos cosas sin que nadie tenga que
 * preguntarlas: si ahora mismo se está contestando, y a qué hora vuelve.
 *
 * Las horas del horario se dicen SIEMPRE en la hora de la planta, con su
 * ciudad: «abre lun 7:00 a. m. (Kansas City)». Antes se convertían a la casa
 * del reloj de arriba, y en Querétaro el horario de 7:00 salía como «abre
 * 6:00», que parecía un horario mal puesto (ISC, 2026-09-27). Del reloj se
 * toma sólo la forma de escribir la hora: 12 horas en América, 24 en Francia.
 *
 * No hay estado propio: se le pasa lo que vino en `GET /api/status`.
 */
const Horario = (() => {
    'use strict';

    // El idioma con el que se escriben las horas de cada casa. Va aquí y no en
    // i18n.js por lo mismo que los formatos del reloj: lo manda el LUGAR, no
    // el idioma de la interfaz.
    const LOCALES = { kc: 'en-US', qro: 'es-MX', sev: 'fr-FR' };

    // La planta: la zona del horario, tal como la manda el servidor.
    let planta = { zona: 'America/Chicago', ciudad: 'Kansas City' };
    function recordarPlanta(h) {
        if (h && h.zona) planta = { zona: h.zona, ciudad: h.ciudad || h.zona };
    }

    function casa() {
        try {
            if (typeof Reloj !== 'undefined' && Reloj.actual) return Reloj.actual();
        } catch (err) { /* el reloj todavía no ha arrancado */ }
        return { id: 'kc', zona: 'America/Chicago', ciudad: 'Kansas City' };
    }

    /** Una hora suelta ("7:00 a. m.", "7h00") en la hora de la planta. */
    function hora(iso, { conDia = false } = {}) {
        if (!iso) return '';
        const c = casa();
        const fecha = new Date(iso);
        if (isNaN(fecha.getTime())) return '';
        const opciones = {
            timeZone: planta.zona, hour: 'numeric', minute: '2-digit',
            hour12: c.id !== 'sev',      // Francia lo dice en 24 horas
        };
        if (conDia) opciones.weekday = 'short';
        try {
            return new Intl.DateTimeFormat(LOCALES[c.id] || 'en-US', opciones).format(fecha);
        } catch (err) {
            return fecha.toISOString().slice(11, 16);
        }
    }

    /** ¿Cae ese instante en el mismo día que hoy, en la planta? */
    function esHoy(iso) {
        const dia = (f) => {
            try {
                return new Intl.DateTimeFormat('en-CA', { timeZone: planta.zona }).format(f);
            } catch (err) { return f.toISOString().slice(0, 10); }
        };
        const fecha = new Date(iso);
        return !isNaN(fecha.getTime()) && dia(fecha) === dia(new Date());
    }

    /** "lun 7:00 a. m. (Kansas City)" — con el día sólo si no es hoy. */
    function cuando(iso) {
        const texto = hora(iso, { conDia: !esHoy(iso) });
        return texto ? `${texto} (${planta.ciudad})` : '';
    }

    /**
     * Los dos extremos de la ventana de HOY, como instantes.
     *
     * Se reconstruyen a partir de `ahora_local`, que viene con el huso de la
     * planta: de ahí salen el día y el desfase, y con las horas de apertura y
     * cierre se arma cada extremo. Así la ventana se puede enseñar en
     * cualquier reloj sin que el servidor tenga que mandar cuatro fechas.
     */
    function extremos(h) {
        if (!h || !h.ahora_local) return null;
        const marca = String(h.ahora_local);
        const dia = marca.slice(0, 10);
        const huso = marca.slice(19) || 'Z';          // "-05:00"
        const dosCifras = (n) => String(n).padStart(2, '0');
        const desde = new Date(`${dia}T${dosCifras(h.desde)}:00:00${huso}`);
        // 24:00 no existe en ISO: es la medianoche del día siguiente.
        const cierre = h.hasta >= 24
            ? new Date(new Date(`${dia}T00:00:00${huso}`).getTime() + 24 * 3600 * 1000)
            : new Date(`${dia}T${dosCifras(h.hasta)}:00:00${huso}`);
        if (isNaN(desde.getTime()) || isNaN(cierre.getTime())) return null;
        return { desde, hasta: cierre };
    }

    /** "Horario de atención: 7:00 a. m. – 7:00 p. m., lunes a viernes (hora de Querétaro)". */
    function ventana(h) {
        if (!h) return '';
        recordarPlanta(h);
        const e = extremos(h);
        const franja = e ? `${hora(e.desde.toISOString())} – ${hora(e.hasta.toISOString())}`
                         : `${h.desde}:00 – ${h.hasta}:00`;
        return I18N.t('horario.ventana', {
            franja, dias: dias(h.dias), ciudad: planta.ciudad,
        });
    }

    /** "lunes a viernes", o la lista de días si alguien cambia la configuración. */
    function dias(lista) {
        const d = Array.isArray(lista) && lista.length ? lista : [1, 2, 3, 4, 5];
        if (String(d) === '1,2,3,4,5') return I18N.t('horario.lunVie');
        // 2026-01-05 fue lunes: sumando días salen los nombres en su idioma.
        const c = casa();
        return d.map(n => {
            const f = new Date(Date.UTC(2026, 0, 4 + n, 12));
            try {
                return new Intl.DateTimeFormat(LOCALES[c.id] || 'en-US', { weekday: 'short' }).format(f);
            } catch (err) { return String(n); }
        }).join(', ');
    }

    /**
     * Lo que hay que enseñar, en una sola llamada.
     *
     *   { enEspera, titulo, valor, detalle }
     *
     * `enEspera` es "el servicio está en marcha pero ahora no toca leer": ni
     * parado ni trabajando, que es justo el estado que antes no se podía
     * contar y hacía pensar que el sistema se había quedado colgado.
     */
    function resumen(h) {
        recordarPlanta(h);
        if (!h || !h.activo) return { enEspera: false, titulo: '', valor: '', detalle: '' };
        if (h.abierto) {
            const e = extremos(h);
            const cierre = h.proximo_cierre || (e && e.hasta.toISOString());
            return {
                enEspera: false,
                titulo: ventana(h),
                valor: I18N.t('horario.enHorario'),
                detalle: cierre ? I18N.t('horario.hasta', { cuando: cuando(cierre) }) : '',
            };
        }
        const abre = h.proxima_apertura ? cuando(h.proxima_apertura) : '';
        return {
            enEspera: true,
            titulo: `${ventana(h)}\n${I18N.t('horario.esperan')}`,
            valor: I18N.t('horario.enEspera'),
            detalle: abre ? I18N.t('horario.abre', { cuando: abre }) : I18N.t('horario.fuera'),
        };
    }

    return { resumen, ventana, cuando, hora, dias };
})();
