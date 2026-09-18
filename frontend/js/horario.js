/**
 * El horario de atención, dicho en el reloj que cada quien tenga puesto.
 *
 * La ventana es UNA: de lunes a viernes, de 6:00 a 18:00 de la planta (Kansas
 * City). Fuera de ella el sistema no abre el buzón —el correo se queda sin
 * leer y entra en el primer ciclo de la apertura siguiente—, así que la
 * pantalla tiene que poder decir dos cosas sin que nadie tenga que
 * preguntarlas: si ahora mismo se está contestando, y a qué hora vuelve.
 *
 * Y "a qué hora" depende de quién mire. Las 6:00 de Kansas son las 7:00 de
 * Querétaro y las 13:00 de Sevran: el mismo instante, tres lecturas. Por eso
 * el servidor manda instantes con su huso (…T06:00:00-05:00) y aquí se pintan
 * en la casa del reloj de arriba —la que sigue al idioma mientras nadie la
 * toque—, con el formato de ESE sitio: 12 horas en América, 24 en Francia.
 *
 * No hay estado propio: se le pasa lo que vino en `GET /api/status`.
 */
const Horario = (() => {
    'use strict';

    // El idioma con el que se escriben las horas de cada casa. Va aquí y no en
    // i18n.js por lo mismo que los formatos del reloj: lo manda el LUGAR, no
    // el idioma de la interfaz.
    const LOCALES = { kc: 'en-US', qro: 'es-MX', sev: 'fr-FR' };

    function casa() {
        try {
            if (typeof Reloj !== 'undefined' && Reloj.actual) return Reloj.actual();
        } catch (err) { /* el reloj todavía no ha arrancado */ }
        return { id: 'kc', zona: 'America/Chicago', ciudad: 'Kansas City' };
    }

    /** Una hora suelta ("6:00 a. m.", "13h00") en la casa del reloj. */
    function hora(iso, { conDia = false } = {}) {
        if (!iso) return '';
        const c = casa();
        const fecha = new Date(iso);
        if (isNaN(fecha.getTime())) return '';
        const opciones = {
            timeZone: c.zona, hour: 'numeric', minute: '2-digit',
            hour12: c.id !== 'sev',      // Francia lo dice en 24 horas
        };
        if (conDia) opciones.weekday = 'short';
        try {
            return new Intl.DateTimeFormat(LOCALES[c.id] || 'en-US', opciones).format(fecha);
        } catch (err) {
            return fecha.toISOString().slice(11, 16);
        }
    }

    /** ¿Cae ese instante en el mismo día que hoy, mirándolo desde el reloj? */
    function esHoy(iso) {
        const c = casa();
        const dia = (f) => {
            try {
                return new Intl.DateTimeFormat('en-CA', { timeZone: c.zona }).format(f);
            } catch (err) { return f.toISOString().slice(0, 10); }
        };
        const fecha = new Date(iso);
        return !isNaN(fecha.getTime()) && dia(fecha) === dia(new Date());
    }

    /** "abre el lun, 6:00 a. m." — con el día sólo si no es hoy. */
    function cuando(iso) {
        return hora(iso, { conDia: !esHoy(iso) });
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
        const e = extremos(h);
        const franja = e ? `${hora(e.desde.toISOString())} – ${hora(e.hasta.toISOString())}`
                         : `${h.desde}:00 – ${h.hasta}:00`;
        return I18N.t('horario.ventana', {
            franja, dias: dias(h.dias), ciudad: casa().ciudad,
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
