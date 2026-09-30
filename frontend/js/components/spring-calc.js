/**
 * El dictamen del Spring Engineering Calculator, dicho en Pohua.
 *
 * El servidor corre el MISMO cálculo que la pestaña Spring Calc
 * (pricing/spring_calc.py → pricing/nucleo/resortes.js) y lo manda con el
 * RFQ como `spring_calc`. Esto lo convierte en líneas para «Review Flags» de
 * la ficha y para los avisos de la ventana de revisión, en el idioma puesto.
 *
 *   - `bloqueos`: lo que la planta NO puede hacer (alambre ≥ 15 mm, ninguna
 *     bobinadora lo admite). Van en rojo y deshabilitan «Aprobar».
 *   - `banderas`: las observaciones de ingeniería de la calculadora (índice,
 *     pandeo, paso…). Informan, no bloquean. El servidor las manda ya en los
 *     tres idiomas, con el diccionario de la propia calculadora.
 */
const SpringCalc = (() => {
    'use strict';

    function numero(v, dec) {
        if (typeof v !== 'number' || !isFinite(v)) return '—';
        return v.toLocaleString(I18N.locale || undefined, { maximumFractionDigits: dec == null ? 3 : dec });
    }

    function enIdioma(textos, respaldo) {
        if (textos && typeof textos === 'object') {
            return textos[I18N.idioma] || textos.en || respaldo || '';
        }
        return respaldo || '';
    }

    /** True si el Spring Calc dice que la planta no puede hacer este resorte. */
    function bloquea(sc) {
        return !!sc && sc.factible === false;
    }

    function textoBloqueo(b) {
        if (!b) return '';
        if (b.codigo === 'alambre_maximo') {
            return I18N.t('spring.bloqueo.alambre_maximo', {
                valor: numero(b.valor), pulg: numero(b.limite_pulg, 2), mm: numero(b.limite_mm, 0) });
        }
        if (b.codigo === 'sin_maquina') {
            return I18N.t(b.od ? 'spring.bloqueo.sin_maquina' : 'spring.bloqueo.sin_maquinaSinOd', {
                alambre: numero(b.alambre), od: numero(b.od), max: numero(b.alambre_max_taller) });
        }
        return b.codigo || '';
    }

    /** La línea de resumen: score, banda y bobinadora. Vacía si no hay nada. */
    function resumen(sc) {
        if (!sc || !sc.evaluado) return '';
        const partes = [];
        if (bloquea(sc)) {
            partes.push(I18N.t('spring.noFactible'));
        } else if (typeof sc.score === 'number') {
            partes.push(I18N.t('spring.puntaje', {
                score: sc.score, banda: enIdioma(sc.banda_textos, sc.banda) })
                + (sc.solo_geometria ? ' ' + I18N.t('spring.soloGeometria') : ''));
        }
        if (sc.maquina && sc.maquina.mejor) {
            partes.push(I18N.t('spring.maquina', { maq: sc.maquina.mejor }));
        }
        return partes.length ? I18N.t('spring.titulo') + ': ' + partes.join(' · ') : '';
    }

    /**
     * Las líneas para «Review Flags», de más grave a menos:
     * `{ nivel: 'error' | 'warn' | 'info', texto }`.
     */
    function items(sc) {
        if (!sc || !sc.evaluado) return [];
        const lista = [];
        for (const b of (sc.bloqueos || [])) {
            lista.push({ nivel: 'error', texto: I18N.t('spring.titulo') + ': ' + textoBloqueo(b) });
        }
        const linea = resumen(sc);
        if (linea && !bloquea(sc)) lista.push({ nivel: 'info', texto: linea });
        const orden = { crit: 0, warn: 1, info: 2 };
        const banderas = (sc.banderas || []).slice()
            .sort((a, b) => (orden[a.nivel] ?? 3) - (orden[b.nivel] ?? 3));
        for (const f of banderas) {
            const texto = enIdioma(f.textos, f.titulo);
            if (!texto) continue;
            lista.push({ nivel: f.nivel === 'crit' ? 'error' : (f.nivel === 'warn' ? 'warn' : 'info'),
                         texto: I18N.t('spring.titulo') + ': ' + texto });
        }
        return lista;
    }

    return { bloquea, items, resumen, textoBloqueo };
})();
