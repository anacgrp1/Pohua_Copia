/**
 * El contrato `ISC_SC` (versión 1) del Spring Engineering Calculator.
 *
 * El visor 3D (isc-visor3d.js) no mira dentro de la calculadora: pide los
 * datos del resorte ya calculados por un contrato pequeño y estable, y se
 * suscribe a "acaba de repintar". Ese contrato lo iba a publicar el núcleo
 * de ISC; hasta que lo haga, lo publica este adaptador, que es el ÚNICO
 * sitio de Pohua que conoce los nombres internos de la calculadora
 * (`STATE`, `calcCompression`, `render`, `DS_EMPTY`, `END_TYPES`). El día que
 * el núcleo traiga `window.ISC_SC` de fábrica, este archivo se retira y el
 * visor sigue igual.
 *
 * Se inyecta al servir la calculadora (api/lector.py), con `defer` y ANTES
 * del visor: el visor comprueba `window.ISC_SC` nada más cargar.
 *
 * Qué publica:
 *   ISC_SC.version          1
 *   ISC_SC.datosDelResorte() {listo, contenedor, contenedorGrafica, resorte,
 *                             unidadPantalla}
 *       resorte (mm, N, MPa): {d, OD, D, ID, L0, Ls, L1, Nt, Na, k,
 *                              tauSolido, sentido, extremos:{tipo, esmerilado}}
 *   ISC_SC.alPintar(fn)     fn(datos) tras cada repintado, y una vez al
 *                           suscribirse con lo que haya en pantalla.
 *
 * Sólo el resorte de COMPRESIÓN: extensión y torsión contestan listo=false.
 * Si la calculadora no es la de resortes (la de precios no tiene STATE.comp)
 * no se publica nada, y el visor tampoco hace nada.
 */
(function () {
    'use strict';

    if (window.ISC_SC) return;                                  // ya lo trae el núcleo
    if (typeof window.STATE !== 'object' || !window.STATE || !window.STATE.comp) return;
    if (typeof window.calcCompression !== 'function' || typeof window.render !== 'function') return;

    var oyentes = [];

    function datosDelResorte() {
        var app = document.getElementById('app');
        var cont = app ? app.querySelector('.ds-diag') : null;
        var graf = app ? app.querySelector('.ds-graph') : null;
        var listo = window.STATE.tab === 'compression' && !window.DS_EMPTY && !!cont;
        var resorte = null;
        if (listo) {
            try {
                var I = window.STATE.comp, R = window.calcCompression(I);
                var et = (window.END_TYPES && window.END_TYPES[I.endType]) || {};
                resorte = {
                    d: R.d, OD: R.OD, D: R.D, ID: R.ID,
                    L0: R.L0, Ls: R.Ls,
                    L1: (I.h > 0 && I.h < R.L0) ? I.h : null,
                    Nt: R.Nt, Na: R.Na,
                    k: R.k,                       // N/mm
                    tauSolido: R.tauSolid,        // MPa
                    sentido: 'right',
                    extremos: { tipo: I.endType, esmerilado: !!et.ground }
                };
                if (!(resorte.d > 0 && resorte.OD > resorte.d && resorte.L0 > resorte.Ls && resorte.Nt > 0)) {
                    listo = false; resorte = null;
                }
            } catch (e) {
                listo = false; resorte = null;
            }
        }
        return {
            version: 1,
            listo: listo,
            contenedor: cont,
            contenedorGrafica: graf,
            resorte: resorte,
            unidadPantalla: window.STATE.unit === 'mm' ? 'mm' : 'in'
        };
    }

    function avisar() {
        var d = datosDelResorte();
        for (var i = 0; i < oyentes.length; i++) {
            try { oyentes[i](d); } catch (e) { if (window.console) console.warn('ISC_SC: oyente falló', e); }
        }
    }

    /* Las puertas por las que se repinta la pizarra: `render()` (pestañas,
       unidades, plano nuevo) y `renderComp/Ext/Tors()` (cada dato editado
       llama a la suya directamente). Se envuelven en vez de observar el DOM:
       así el aviso llega con la pizarra ya pintada y una vez por repintado.
       Las casillas se vuelven a enlazar en cada pintado leyendo el nombre
       global, así que a partir del primer repintado usan la envoltura. */
    function envolver(nombre) {
        var original = window[nombre];
        if (typeof original !== 'function') return;
        window[nombre] = function () {
            var salida = original.apply(this, arguments);
            avisar();
            return salida;
        };
    }
    ['render', 'renderComp', 'renderExt', 'renderTors'].forEach(envolver);
    // Un repintado ahora, para que las casillas queden enlazadas a las
    // envolturas desde el principio (el primer pintado fue antes que esto).
    try { window.render(); } catch (e) { /* si falla, el siguiente dato lo hará */ }

    window.ISC_SC = {
        version: 1,
        datosDelResorte: datosDelResorte,
        alPintar: function (fn) {
            if (typeof fn !== 'function') return;
            oyentes.push(fn);
            // Lo que ya hay en pantalla, sin esperar a que alguien teclee.
            setTimeout(function () { try { fn(datosDelResorte()); } catch (e) { /* suyo */ } }, 0);
        }
    };
})();
