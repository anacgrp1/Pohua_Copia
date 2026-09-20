/**
 * La ventana de aprobación de la calculadora de precios, con el aspecto de
 * Pohua.
 *
 * "Approve" en la barra de abajo de la calculadora aprobaba en seco: un
 * diálogo de confirmación si había banderas, y ya. Quien aprueba decide con
 * los mismos números que la ventana de revisión de los RFQs (js/components/
 * revision.js): los tramos, la cascada de margen del tramo elegido, el
 * material, la ruta y los totales. Esta capa los saca de la propia
 * calculadora —`computeFor(pn)` es lo que ella misma pinta en sus tarjetas—
 * y los pone en una ventana igual que aquélla: compacta en la compu, a
 * pantalla completa en el teléfono.
 *
 * Qué hace cada botón:
 *   Preview PDF   el mismo `previewPdf()` de la barra: el documento tal cual
 *                 saldría, sin guardar, archivar ni aprobar nada.
 *   Send back     deja la cotización en DRAFT con una nota para quien la
 *                 hizo (queda en el diario y en la propia cotización).
 *   Approve       el flujo original de la calculadora, intacto: comprobación
 *                 de permisos, banderas abiertas, bloqueo y PDF archivado.
 *   Open full quote  cierra la ventana: la cotización entera está debajo.
 *
 * POR QUÉ VA POR FUERA. La calculadora es del núcleo (se regenera con
 * scripts/vendorizar_nucleo.py); tocarla aquí se perdería. Se le cambia el
 * manejador del botón y nada más: `onclick` se guarda y se llama desde
 * "Approve" de la ventana. Sólo entra en la calculadora de precios: en la de
 * resortes no hay `#bb-approve` y no hace nada.
 */
(function () {
    'use strict';

    var ID = 'nube-aprobacion';
    var abierta = null;      // { raiz, pn, tramo } mientras está en pantalla
    var aprobarOriginal = null;

    function $(id) { return document.getElementById(id); }
    function esc(s) {
        return String(s === null || s === undefined ? '' : s)
            .replace(/[&<>"']/g, function (c) {
                return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
            });
    }
    function num(v) { var n = Number(v); return isFinite(n) ? n : null; }
    function dinero(v, dec) {
        if (v === null || v === undefined || !isFinite(v)) return '—';
        if (dec === undefined) dec = Math.abs(v) >= 1 ? 3 : 4;
        return (v < 0 ? '-' : '') + '$' + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });
    }
    function entero(v) { return (v === null || v === undefined || !isFinite(v)) ? '—' : Math.round(v).toLocaleString('en-US'); }
    function porc(v) { return (v === null || v === undefined || !isFinite(v)) ? '—' : v.toFixed(1) + '%'; }
    function h1(v) { return (v === null || v === undefined || !isFinite(v)) ? '—' : (Math.round(v * 10) / 10).toString(); }

    function calculadoraLista() {
        return typeof window.Q === 'function' && typeof window.computeFor === 'function' && $('bb-approve');
    }

    // ------------------------------------------------------------ estilos

    function estilos() {
        if ($('nube-aprobacion-css')) return;
        var css = [
            /* El velo es oscuro en los dos temas, a propósito. Antes se
               mezclaba con el fondo de la página: en claro quedaba un gris
               azulado del mismo tono que la ventana, y la ventana dejaba de
               despegarse del fondo. Oscurecer por detrás funciona igual en
               claro que en oscuro, que es lo que hace cualquier diálogo.

               --ap-relieve es el gris de los botones neutros: se calcula
               desde la tinta y el papel del tema, así que en claro sale un
               poco más oscuro que la ventana y en oscuro un poco más claro.
               Con el fondo de la página (--n-sutil) los botones se perdían en
               claro, porque ese color ES el de la página. */
            '#' + ID + '{position:fixed;inset:0;z-index:9500;display:flex;align-items:center;justify-content:center;',
            ' padding:16px;background:rgba(2,6,23,.55);backdrop-filter:blur(3px);font-family:inherit;',
            ' --ap-relieve:var(--n-sutil,#f8fafc);',
            ' --ap-relieve:color-mix(in srgb,var(--n-tinta,#0f172a) 8%,var(--n-papel,#fff))}',
            '#' + ID + ' .ap-caja{width:min(820px,100%);max-height:calc(100vh - 32px);overflow:auto;display:flex;flex-direction:column;',
            ' background:var(--n-papel,#fff);color:var(--n-tinta,#0f172a);border:1px solid var(--n-linea,#cbd5e1);border-radius:14px;',
            ' box-shadow:0 24px 64px rgba(0,0,0,.45);font-size:13px}',
            '#' + ID + ' .ap-cab{display:flex;align-items:center;gap:12px;padding:12px 16px;background:var(--navy,#1b3d79);color:#fff;',
            ' border-radius:14px 14px 0 0;position:sticky;top:0;z-index:1}',
            '#' + ID + ' .ap-cab b{font-size:15px}',
            '#' + ID + ' .ap-cab .ap-quien{margin-left:auto;font-size:12px;opacity:.92;white-space:nowrap}',
            '#' + ID + ' .ap-x{background:transparent;border:0;color:#fff;font-size:20px;line-height:1;cursor:pointer;padding:2px 6px;border-radius:6px}',
            '#' + ID + ' .ap-x:hover{background:rgba(255,255,255,.15)}',
            '#' + ID + ' .ap-cuerpo{padding:12px 16px 4px;display:flex;flex-direction:column;gap:10px}',
            '#' + ID + ' .ap-eti{font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--n-apagado,#64748b)}',
            '#' + ID + ' .ap-chips{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center}',
            '#' + ID + ' .ap-chips span{white-space:nowrap}',
            '#' + ID + ' .ap-tramos{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px}',
            '#' + ID + ' .ap-tramo{text-align:left;border:1px solid var(--n-linea,#cbd5e1);background:var(--ap-relieve);color:inherit;',
            ' border-radius:10px;padding:8px 10px;cursor:pointer;font:inherit}',
            '#' + ID + ' .ap-tramo.on{border-color:var(--n-info-solido,#148ec2);box-shadow:0 0 0 2px var(--n-info-linea,rgba(20,142,194,.38));',
            ' background:var(--n-info-fondo,rgba(20,142,194,.14))}',
            '#' + ID + ' .ap-tramo small{display:block;color:var(--n-apagado,#64748b);font-size:11px}',
            '#' + ID + ' .ap-tramo .ap-precio{display:flex;justify-content:space-between;align-items:baseline;gap:8px;margin-top:2px}',
            '#' + ID + ' .ap-tramo .ap-precio b{font-size:16px}',
            '#' + ID + ' .ap-ok{color:var(--n-ok-tinta,#16a34a);font-weight:700}',
            '#' + ID + ' .ap-mal{color:var(--n-mal-tinta,#dc2626);font-weight:700}',
            '#' + ID + ' .ap-bandera{border-radius:8px;padding:8px 10px;border:1px solid;font-size:12px}',
            '#' + ID + ' .ap-bandera.warn{background:var(--n-avi-fondo,rgba(245,158,11,.14));border-color:var(--n-avi-linea,rgba(245,158,11,.5));color:var(--n-tinta,inherit)}',
            '#' + ID + ' .ap-bandera.err{background:var(--n-mal-fondo,rgba(220,38,38,.12));border-color:var(--n-mal-linea,rgba(220,38,38,.5))}',
            '#' + ID + ' .ap-bandera.info{background:var(--n-info-fondo,rgba(59,130,246,.10));border-color:var(--n-info-linea,rgba(59,130,246,.4))}',
            '#' + ID + ' .ap-fila{display:grid;grid-template-columns:repeat(5,1fr);border:1px solid var(--n-linea,#cbd5e1);border-radius:10px;overflow:hidden}',
            '#' + ID + ' .ap-celda{padding:8px 10px;border-left:1px solid var(--n-linea,#cbd5e1)}',
            '#' + ID + ' .ap-celda:first-child{border-left:0}',
            '#' + ID + ' .ap-celda b{display:block;font-size:15px;margin:2px 0}',
            '#' + ID + ' .ap-celda small{color:var(--n-apagado,#64748b)}',
            '#' + ID + ' .ap-celda.res{background:var(--n-ok-fondo,rgba(22,163,74,.12))}',
            '#' + ID + ' .ap-celda.res b{color:var(--n-ok-tinta,#16a34a)}',
            '#' + ID + ' .ap-tres{display:grid;grid-template-columns:1fr 1.3fr 1fr;gap:8px}',
            '#' + ID + ' .ap-panel{border:1px solid var(--n-linea,#cbd5e1);border-radius:10px;padding:8px 10px}',
            '#' + ID + ' .ap-panel table{width:100%;border-collapse:collapse;margin-top:4px}',
            '#' + ID + ' .ap-panel td{padding:3px 0;vertical-align:top}',
            '#' + ID + ' .ap-panel td:last-child{text-align:right;font-weight:700;white-space:nowrap}',
            '#' + ID + ' .ap-panel td small{color:var(--n-apagado,#64748b);font-weight:400}',
            '#' + ID + ' .ap-pie{display:flex;flex-direction:column;gap:10px;padding:12px 16px 16px;',
            ' border-top:1px solid var(--n-linea,#cbd5e1)}',
            '#' + ID + ' .ap-pie-ver{display:flex;align-items:center;gap:12px}',
            '#' + ID + ' .ap-pie-acciones{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap}',
            '#' + ID + ' .ap-nota{font-size:11px;line-height:1.35;color:var(--n-apagado,#64748b);flex:1 1 auto;min-width:0}',
            '#' + ID + ' .ap-btn{font:inherit;font-weight:600;min-height:40px;padding:9px 18px;border-radius:10px;',
            ' border:1px solid var(--n-linea,#cbd5e1);',
            ' background:var(--ap-relieve);color:inherit;cursor:pointer}',
            '#' + ID + ' .ap-btn:hover{filter:brightness(1.08)}',
            '#' + ID + ' .ap-btn:focus-visible{outline:2px solid var(--n-info-solido,#148ec2);outline-offset:2px}',
            '#' + ID + ' .ap-btn[disabled]{opacity:.5;cursor:not-allowed}',
            '#' + ID + ' .ap-btn.primario{background:var(--navy,#1b3d79);border-color:transparent;color:#fff}',
            '#' + ID + ' .ap-btn.aprobar{background:var(--n-ok-solido,#16a34a);border-color:transparent;color:#fff}',
            '#' + ID + ' .ap-devolver{display:flex;gap:8px;width:100%;margin-top:2px;flex-wrap:wrap}',
            '#' + ID + ' .ap-devolver textarea{flex:1;font:inherit;padding:8px;border-radius:8px;border:1px solid var(--n-linea,#cbd5e1);',
            ' background:var(--n-papel,#fff);color:var(--n-tinta,inherit);resize:vertical;min-height:56px}',
            '@media (max-width:820px){',
            ' #' + ID + '{padding:0;align-items:stretch}',
            ' #' + ID + ' .ap-caja{width:100%;max-height:100vh;border-radius:0;border:0}',
            ' #' + ID + ' .ap-cab{border-radius:0;flex-wrap:wrap;padding-right:48px}',
            ' #' + ID + ' .ap-x{position:absolute;right:10px;top:10px}',
            ' #' + ID + ' .ap-cab .ap-quien{margin-left:0;flex-basis:100%;white-space:normal}',
            ' #' + ID + ' .ap-fila{grid-template-columns:1fr}',
            ' #' + ID + ' .ap-celda{border-left:0;border-top:1px solid var(--n-linea,#cbd5e1);display:flex;justify-content:space-between;align-items:center;gap:8px}',
            ' #' + ID + ' .ap-celda:first-child{border-top:0}',
            ' #' + ID + ' .ap-celda b{margin:0}',
            ' #' + ID + ' .ap-tres{grid-template-columns:1fr}',
            ' #' + ID + ' .ap-pie{position:sticky;bottom:0;background:var(--n-papel,#fff)}',
            ' #' + ID + ' .ap-cab{background:var(--navy,#1b3d79)}',
            // En el teléfono cada botón ocupa su línea: son decisiones, y una
            // fila de tres del ancho de un pulgar es una equivocación
            // esperando a pasar.
            ' #' + ID + ' .ap-pie-ver{flex-direction:column;align-items:stretch;gap:6px}',
            ' #' + ID + ' .ap-pie-acciones{flex-direction:column;gap:8px}',
            ' #' + ID + ' .ap-pie .ap-btn{width:100%;text-align:center;min-height:44px}',
            ' #' + ID + ' .ap-nota{text-align:center;margin:0}',
            '}',
        ].join('');
        var s = document.createElement('style');
        s.id = 'nube-aprobacion-css';
        s.textContent = css;
        document.head.appendChild(s);
    }

    // ------------------------------------------------------------ datos

    function pnActiva(q) {
        var pns = (q && q.pns) || [];
        return pns[q.activePn] || pns[0] || null;
    }

    function nombreMaterial(codigo) {
        var c = String(codigo || '').toUpperCase();
        if (!c) return '—';
        var leyenda = (typeof shared !== 'undefined' && shared && shared.dbs && shared.dbs.materialLegend) || {};
        var largo = leyenda[c];
        if (!largo) return c;
        return c + ' — ' + largo.replace(/\s*\(.*\)\s*$/, '');
    }

    function nombreCliente(q) {
        var codigo = q && q.header && q.header.customerCode;
        if (!codigo) return 'no customer';
        try { return typeof custName === 'function' ? custName(codigo) : codigo; } catch (e) { return codigo; }
    }

    function faltantes(q) {
        try { return typeof faltaParaAprobar === 'function' ? (faltaParaAprobar(q) || []) : []; } catch (e) { return []; }
    }

    function opsDeTramo(tramoCrudo) {
        var ops = (tramoCrudo && tramoCrudo.routing) || [];
        try { if (window.ENGINE && ENGINE.opsUsed) return ENGINE.opsUsed(ops); } catch (e) {}
        return ops.filter(function (o) { return o.machine && (o.pph || o.setupH); });
    }

    // ------------------------------------------------------------ pintado

    function pintar() {
        if (!abierta) return;
        var q = Q();
        var pn = pnActiva(q);
        var raiz = abierta.raiz;
        if (!q || !pn) { raiz.querySelector('.ap-cuerpo').innerHTML = '<p>No quote open.</p>'; return; }

        var res = computeFor(pn, q);
        var tramos = res.tiers || [];
        var conDatos = [];
        tramos.forEach(function (t, i) { if (t) conDatos.push(i); });
        if (abierta.tramo === null || !tramos[abierta.tramo]) {
            abierta.tramo = tramos[pn.selTier] ? pn.selTier : (conDatos.length ? conDatos[0] : null);
        }
        var i = abierta.tramo;
        var t = i === null ? null : tramos[i];
        var crudo = i === null ? null : pn.tiers[i];
        var falta = faltantes(q);
        var m = pn.material || {};

        var cab = raiz.querySelector('.ap-cab');
        cab.querySelector('.ap-titulo').innerHTML = '<b>' + esc(pn.pn || 'PN') + '</b> · ' + esc(pn.desc || q.header.desc || '');
        cab.querySelector('.ap-quien').textContent = 'Quote ' + (q.number || '— draft —') + (q.ver > 1 ? ' v' + q.ver : '') + ' · ' + nombreCliente(q);

        var html = '';
        // Todos los tramos: lo que no cambia con la cantidad.
        html += '<div class="ap-chips"><span class="ap-eti">All tiers</span>' +
            '<span>' + esc(nombreMaterial(m.code)) + '</span>' +
            (num(m.diaIn) !== null ? '<span>Ø ' + esc(m.diaIn) + ' in</span>' : '') +
            (num(m.weightLb) !== null ? '<span>' + esc(m.weightLb) + ' lb/pc</span>' : '') +
            (num(m.basePerLb) !== null ? '<span>Base ' + dinero(num(m.basePerLb), 2) + '/lb</span>' : '') +
            (num(m.surchPerLb) ? '<span>Surcharge ' + dinero(num(m.surchPerLb), 2) + '/lb</span>' : '') +
            '</div>';

        // Tarjetas de tramo.
        if (conDatos.length) {
            html += '<div class="ap-tramos">' + conDatos.map(function (k) {
                var tt = tramos[k];
                var margen = tt.sell ? tt.pnl.result / tt.sell * 100 : null;
                return '<button type="button" class="ap-tramo ' + (k === i ? 'on' : '') + '" data-tramo="' + k + '">' +
                    '<small>Tier ' + (k + 1) + (k === pn.selTier ? ' ★' : '') + ' · ' + entero(tt.qty) + ' pcs</small>' +
                    '<span class="ap-precio"><b>' + dinero(tt.sell) + '/pc</b><span class="' + (margen !== null && margen >= 0 ? 'ap-ok' : 'ap-mal') + '">' + porc(margen) + '</span></span>' +
                    '</button>';
            }).join('') + '</div>';
        } else {
            html += '<div class="ap-bandera warn">No volume tiers entered.</div>';
        }

        // Lo que falta para aprobar, y las banderas del cálculo.
        if (falta.length) {
            html += '<div class="ap-bandera err">Cannot approve yet — needs ' + esc(falta.join(', ')) + '.</div>';
        }
        (res.flags || []).forEach(function (f) {
            var tipo = f.t === 'err' ? 'err' : (f.t === 'warn' ? 'warn' : 'info');
            html += '<div class="ap-bandera ' + tipo + '">' + (tipo === 'err' ? '⛔ ' : tipo === 'warn' ? '⚠ ' : 'ℹ ') + esc(f.m) + '</div>';
        });

        if (t) {
            var p = t.pnl;
            var objetivo = t.contribPct;
            var resPct = t.sell ? p.result / t.sell * 100 : null;
            // La cascada del margen, por pieza.
            html += '<div class="ap-eti" style="margin-top:2px">Margin waterfall · per piece · ' + entero(t.qty) + ' pcs</div>' +
                '<div class="ap-fila">' +
                celda('Selling price', dinero(t.sell), '100%') +
                celda('AV', dinero(p.av), porc(p.avPct)) +
                celda('C/CV', dinero(p.ccv), porc(p.ccvPct)) +
                celda('C/CD', dinero(p.ccd), porc(p.ccdPct)) +
                celda('Result · target ' + porc(objetivo), dinero(p.result), porc(resPct), 'res') +
                '</div>';

            // Material, ruta y totales del tramo.
            var ops = opsDeTramo(crudo);
            html += '<div class="ap-tres">' +
                '<div class="ap-panel"><div class="ap-eti">Material this tier</div><table>' +
                '<tr><td>$/pc</td><td>' + dinero(t.mat) + ' <small>· ' + porc(t.sell ? t.mat / t.sell * 100 : null) + '</small></td></tr>' +
                '<tr><td>Wire to buy</td><td>' + entero(t.lbBuy) + ' lb</td></tr>' +
                (t.comp ? '<tr><td>Components</td><td>' + dinero(t.comp) + '</td></tr>' : '') +
                (t.subMk ? '<tr><td>Subcontracting</td><td>' + dinero(t.subMk + t.subTransp) + '</td></tr>' : '') +
                '</table></div>' +
                '<div class="ap-panel"><div class="ap-eti">Route · ' + h1(t.hours) + ' machine h</div><table>' +
                (ops.length ? ops.map(function (o) {
                    return '<tr><td>' + esc(o.machine) + '</td><td>' + (num(o.pph) !== null ? entero(num(o.pph)) + ' pc/h' : '—') +
                        ' <small>· setup ' + h1(num(o.setupH) || 0) + ' h</small></td></tr>';
                }).join('') : '<tr><td colspan="2"><small>No operations.</small></td></tr>') +
                '</table></div>' +
                '<div class="ap-panel"><div class="ap-eti">Tier totals</div><table>' +
                '<tr><td>Revenue</td><td>' + dinero(t.revenue, 0) + '</td></tr>' +
                '<tr><td>C/CV per h</td><td>' + dinero(p.ccvHr, 2) + '</td></tr>' +
                (t.floorBinds ? '<tr><td>ISC floor</td><td>' + dinero(t.floorJob, 0) + ' <small>/ job</small></td></tr>' : '') +
                '</table></div>' +
                '</div>';
        }

        raiz.querySelector('.ap-cuerpo').innerHTML = html;

        var puedeAprobar = !falta.length && q.status === 'DRAFT' && (typeof isAdmin !== 'function' || isAdmin());
        var btnAprobar = raiz.querySelector('[data-ap="aprobar"]');
        btnAprobar.disabled = !puedeAprobar;
        btnAprobar.title = falta.length ? 'Needs ' + falta.join(', ') : '';
        raiz.querySelector('[data-ap="devolver"]').disabled = q.status !== 'DRAFT';
    }

    function celda(etiqueta, valor, pct, clase) {
        return '<div class="ap-celda ' + (clase || '') + '"><small>' + esc(etiqueta) + '</small><b>' + valor + '</b><small>' + pct + '</small></div>';
    }

    // ------------------------------------------------------------ acciones

    function abrir() {
        if (abierta) { pintar(); return; }
        estilos();
        var raiz = document.createElement('div');
        raiz.id = ID;
        raiz.className = 'nube-aprobacion';
        raiz.setAttribute('role', 'dialog');
        raiz.setAttribute('aria-modal', 'true');
        raiz.innerHTML =
            '<div class="ap-caja">' +
            '<div class="ap-cab"><span class="ap-titulo"></span><span class="ap-quien"></span>' +
            '<button type="button" class="ap-x" data-ap="cerrar" title="Close" aria-label="Close">×</button></div>' +
            '<div class="ap-cuerpo"></div>' +
            '<div class="ap-pie">' +
            // Arriba lo de MIRAR, que no cambia nada y se usa antes de
            // decidir; abajo, juntas y separadas de ella, las tres que sí
            // deciden. Mezcladas en una sola fila, "Preview PDF" quedaba al
            // lado de "Approve" y la mano se equivocaba.
            '<div class="ap-pie-ver">' +
            '<button type="button" class="ap-btn" data-ap="pdf">Preview PDF</button>' +
            '<span class="ap-nota">Approve locks the quote and files the PDF. ' +
            'Send back keeps it as a draft with your note.</span>' +
            '</div>' +
            '<div class="ap-pie-acciones">' +
            '<button type="button" class="ap-btn" data-ap="devolver">Send back</button>' +
            '<button type="button" class="ap-btn primario" data-ap="cerrar">Open full quote</button>' +
            '<button type="button" class="ap-btn aprobar" data-ap="aprobar">Approve</button>' +
            '</div>' +
            '</div></div>';
        document.body.appendChild(raiz);
        abierta = { raiz: raiz, tramo: null };

        raiz.addEventListener('click', function (ev) {
            var tramo = ev.target.closest('[data-tramo]');
            if (tramo) { abierta.tramo = Number(tramo.dataset.tramo); pintar(); return; }
            var b = ev.target.closest('[data-ap]');
            if (b) { accion(b.dataset.ap, b); return; }
            if (ev.target === raiz) cerrar();
        });
        document.addEventListener('keydown', alTecla, true);
        pintar();
    }

    function cerrar() {
        if (!abierta) return;
        document.removeEventListener('keydown', alTecla, true);
        abierta.raiz.remove();
        abierta = null;
    }

    function alTecla(ev) {
        if (ev.key === 'Escape') { ev.preventDefault(); ev.stopPropagation(); cerrar(); }
    }

    function accion(cual, boton) {
        if (cual === 'cerrar') { cerrar(); return; }
        if (cual === 'pdf') {
            if (typeof previewPdf === 'function') previewPdf();
            return;
        }
        if (cual === 'aprobar') {
            if (boton.disabled) return;
            cerrar();
            // El flujo original de la calculadora, con sus comprobaciones.
            if (aprobarOriginal) aprobarOriginal.call($('bb-approve'));
            return;
        }
        if (cual === 'devolver') {
            var pie = abierta.raiz.querySelector('.ap-pie');
            if (pie.querySelector('.ap-devolver')) return;
            var caja = document.createElement('div');
            caja.className = 'ap-devolver';
            caja.innerHTML = '<textarea placeholder="What has to change before this can be approved?" aria-label="Note for the quoter"></textarea>' +
                '<button type="button" class="ap-btn" data-ap="devolver-si">Send back</button>' +
                '<button type="button" class="ap-btn" data-ap="devolver-no">Cancel</button>';
            pie.appendChild(caja);
            caja.querySelector('textarea').focus();
            return;
        }
        if (cual === 'devolver-no') {
            var c = abierta.raiz.querySelector('.ap-devolver');
            if (c) c.remove();
            return;
        }
        if (cual === 'devolver-si') {
            var area = abierta.raiz.querySelector('.ap-devolver textarea');
            var nota = (area && area.value || '').trim();
            if (!nota) { if (area) area.focus(); return; }
            devolver(nota);
        }
    }

    /**
     * "Send back": la cotización sigue siendo un borrador; la nota queda en
     * ella (`sentBack`) y en el diario, que es donde la calculadora deja
     * constancia de todo lo demás. La barra de abajo la enseña mientras no
     * se resuelva.
     */
    function devolver(nota) {
        var q = Q();
        var quien = (typeof CUR !== 'undefined' && CUR && CUR.email) || '—';
        q.sentBack = { note: nota, by: quien, at: new Date().toISOString().slice(0, 16).replace('T', ' ') };
        try { if (typeof journal === 'function') journal('QUOTE', 'Quote ' + (q.number || '(draft)') + ' sent back by ' + quien + ' — ' + nota); } catch (e) {}
        try { if (typeof queueDraft === 'function') queueDraft(); } catch (e) {}
        try { if (typeof SFS !== 'undefined' && SFS.write && q.number) SFS.write(); } catch (e) {}
        cerrar();
        if (typeof toast === 'function') toast('Sent back — the quote stays a draft with your note.');
        pintarDevuelta();
    }

    /** La nota de "send back" a la vista en la barra de abajo. */
    function pintarDevuelta() {
        var q = typeof Q === 'function' ? Q() : null;
        var sitio = $('bb-falta');
        if (!sitio) return;
        var vieja = $('nube-devuelta');
        if (vieja) vieja.remove();
        if (!q || !q.sentBack || q.status !== 'DRAFT') return;
        var s = document.createElement('span');
        s.id = 'nube-devuelta';
        s.className = 'small';
        s.style.cssText = 'margin-right:10px;color:var(--n-avi-tinta,#f59e0b)';
        s.textContent = 'Sent back by ' + q.sentBack.by + ': ' + q.sentBack.note;
        sitio.parentNode.insertBefore(s, sitio);
    }

    // ------------------------------------------------------------ arranque

    function enganchar() {
        var b = $('bb-approve');
        if (!b || b.dataset.nubeAprobacion) return;
        b.dataset.nubeAprobacion = '1';
        aprobarOriginal = b.onclick;
        b.onclick = null;
        b.addEventListener('click', function (ev) { ev.preventDefault(); abrir(); });
        // Al cambiar de cotización la barra se repinta; la nota de send back también.
        if (typeof renderBottom === 'function') {
            var original = renderBottom;
            try { window.renderBottom = function () { var r = original.apply(this, arguments); pintarDevuelta(); return r; }; } catch (e) {}
        }
        pintarDevuelta();
    }

    var intentos = 0;
    (function esperar() {
        if (calculadoraLista()) { enganchar(); return; }
        if (++intentos < 200) setTimeout(esperar, 50);
    })();

    window.NubeAprobacion = { abrir: abrir, cerrar: cerrar };
})();
