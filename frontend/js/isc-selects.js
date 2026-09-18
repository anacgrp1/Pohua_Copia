/**
 * Los desplegables de la calculadora, como los del resto de Pohua.
 *
 * EL PROBLEMA. Un `<select>` nativo lo pinta el SISTEMA OPERATIVO, no la
 * página: su lista se abre en blanco con letra negra aunque la aplicación esté
 * en oscuro, con el tipo de letra de Windows, sin espacio entre opciones y
 * cortando los nombres largos ("SS — Stainless Stee"). En una pantalla donde
 * se eligen materiales, clientes y máquinas todo el día, esa lista es la mitad
 * del trabajo.
 *
 * QUÉ HACE ESTO. Deja el `<select>` donde está —invisible, pero vivo— y pinta
 * encima un botón y una lista propios. El `<select>` sigue siendo la fuente de
 * la verdad: al elegir se le pone el valor y se le dispara `change`, así que
 * toda la lógica de la calculadora (`onchange`, `value`, `options`) funciona
 * sin enterarse de que hay otra cosa delante.
 *
 * Por eso no se reescribe ni una línea del núcleo: esto es una capa, como el
 * tema y el idioma, y sobrevive a `scripts/vendorizar_nucleo.py`.
 *
 * LO QUE GANA QUIEN LO USA:
 *   - La lista respeta el tema, en claro y en oscuro.
 *   - Buscador en cuanto hay más de ocho opciones: escribir "302" encuentra
 *     el acero entre catorce materiales sin leerlos todos.
 *   - Teclado completo: ↑ ↓ para moverse, Enter para elegir, Esc para salir,
 *     y escribir salta a lo que empieza así.
 *   - Se lee entero. Un nombre largo se parte en dos líneas en la lista en vez
 *     de cortarse, que es donde de verdad importa distinguirlos.
 *   - En el teléfono la lista sube desde abajo y ocupa el ancho: se toca con
 *     el pulgar sin apuntar.
 *
 * TRES DETALLES QUE HACEN QUE NO SE ROMPA:
 *   1. Las opciones se leen AL ABRIR, no al montar. La calculadora las
 *      rellena sola (clientes, materiales, máquinas) y muchas veces después
 *      de que esto ya haya pasado por ahí.
 *   2. `select.value = "X"` desde el código NO dispara `change`. Se le pone a
 *      cada select una propiedad `value` propia que hace lo de siempre y
 *      además refresca la etiqueta; si no, el botón enseñaría lo anterior.
 *   3. La lista se cuelga del <body> y se coloca con `fixed`: dentro de la
 *      tarjeta la recortaría el `overflow` de las tablas.
 */
(function () {
    'use strict';

    var CON_BUSCADOR = 8;      // a partir de aquí, buscador
    var abierto = null;        // { caja, sel, pop } del que esté desplegado

    /** "Buscar…" en el idioma de Pohua, sin depender de que I18N exista aquí. */
    function textoBuscar() {
        var i = 'en';
        try { i = (window.parent && window.parent.I18N && window.parent.I18N.idioma) || i; } catch (e) {}
        return { es: 'Buscar…', fr: 'Rechercher…' }[i] || 'Search…';
    }

    function esc(s) {
        var n = document.createElement('span');
        n.textContent = s == null ? '' : String(s);
        return n.innerHTML;
    }

    // ------------------------------------------------------------- estilos

    function estilos() {
        if (document.getElementById('nsel-css')) return;
        var css = document.createElement('style');
        css.id = 'nsel-css';
        css.textContent = [
            '.nsel{position:relative;display:block;width:100%}',
            '.nsel>select{position:absolute;inset:0;width:100%;height:100%;opacity:0;',
            '  pointer-events:none;margin:0}',
            '.nsel-btn{display:flex;align-items:center;gap:8px;width:100%;',
            '  font:inherit;font-size:.95rem;text-align:left;cursor:pointer;',
            '  padding:6px 8px;border-radius:7px;',
            '  border:1px solid var(--n-linea,#cbd5e1);background:var(--n-papel,#fff);',
            '  color:var(--n-tinta,#0f172a);',
            '  transition:border-color .12s ease,box-shadow .12s ease}',
            '.nsel-btn:hover:not([disabled]){border-color:var(--n-info-solido,#148ec2)}',
            '.nsel-btn[aria-expanded="true"],.nsel-btn:focus-visible{outline:none;',
            '  border-color:var(--n-info-solido,#148ec2);',
            '  box-shadow:0 0 0 3px var(--n-info-fondo,rgba(20,142,194,.18))}',
            '.nsel-btn[disabled]{opacity:.55;cursor:not-allowed}',
            '.nsel-txt{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
            '.nsel-txt.vacio{color:var(--n-apagado,#64748b)}',
            '.nsel-flecha{flex:none;width:14px;height:14px;opacity:.65;transition:transform .15s ease}',
            '.nsel-btn[aria-expanded="true"] .nsel-flecha{transform:rotate(180deg)}',
            /* dentro de las tablas, tan compacto como lo era el nativo */
            'td .nsel-btn{padding:4px 6px;font-size:.86rem}',

            '.nsel-pop{position:fixed;z-index:9600;display:flex;flex-direction:column;',
            '  max-height:min(54vh,380px);overflow:hidden;',
            '  background:var(--n-papel,#fff);color:var(--n-tinta,#0f172a);',
            '  border:1px solid var(--n-linea,#cbd5e1);border-radius:10px;',
            '  box-shadow:0 12px 32px rgba(0,0,0,.28);',
            '  animation:nselEntra .12s ease-out}',
            '@keyframes nselEntra{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:none}}',
            '.nsel-buscar{flex:none;padding:8px;border-bottom:1px solid var(--n-linea,#cbd5e1)}',
            '.nsel-buscar input{width:100%;font:inherit;font-size:.9rem;padding:6px 8px;',
            '  border-radius:6px;border:1px solid var(--n-linea,#cbd5e1);',
            '  background:var(--n-sutil,#f8fafc);color:inherit}',
            '.nsel-buscar input:focus{outline:none;border-color:var(--n-info-solido,#148ec2)}',
            '.nsel-lista{flex:1;overflow-y:auto;padding:4px;min-height:0}',
            '.nsel-op{display:block;width:100%;text-align:left;font:inherit;font-size:.9rem;',
            '  padding:7px 10px;border:0;border-radius:6px;background:transparent;color:inherit;',
            '  cursor:pointer;line-height:1.35;word-break:break-word}',
            '.nsel-op:hover,.nsel-op.marcada{background:var(--n-sutil,#f1f5f9)}',
            '.nsel-op.elegida{background:var(--n-info-fondo,rgba(20,142,194,.14));font-weight:700}',
            '.nsel-op[disabled]{opacity:.5;cursor:not-allowed}',
            '.nsel-grupo{padding:8px 10px 2px;font-size:10px;font-weight:700;letter-spacing:.07em;',
            '  text-transform:uppercase;color:var(--n-apagado,#64748b)}',
            '.nsel-nada{padding:12px 10px;font-size:.85rem;color:var(--n-apagado,#64748b)}',

            /* En el teléfono la lista sube desde abajo, a lo ancho. */
            '@media (max-width:820px){',
            ' .nsel-pop{left:8px!important;right:8px!important;width:auto!important;',
            '   top:auto!important;bottom:0;max-height:70vh;border-radius:14px 14px 0 0;',
            '   animation:nselSube .16s ease-out}',
            ' .nsel-op{padding:11px 12px;font-size:.95rem}',
            '}',
            '@keyframes nselSube{from{transform:translateY(12px);opacity:0}to{transform:none;opacity:1}}',

            /* --- el campo de archivos --- */
            '.narch{display:block;width:100%}',
            '.narch>input[type="file"]{position:absolute;width:1px;height:1px;opacity:0;',
            '  pointer-events:none}',
            '.narch-zona{display:flex;align-items:center;gap:10px;width:100%;cursor:pointer;',
            '  padding:8px 12px;border-radius:8px;',
            '  border:1px dashed var(--n-linea,#cbd5e1);background:var(--n-sutil,#f8fafc);',
            '  color:var(--n-tinta,#0f172a);',
            '  transition:border-color .12s ease,background .12s ease}',
            '.narch-zona:hover,.narch-zona:focus-visible,.narch-zona.encima{outline:none;',
            '  border-color:var(--n-info-solido,#148ec2);border-style:solid;',
            '  background:var(--n-info-fondo,rgba(20,142,194,.12))}',
            '.narch-icono{flex:none;width:20px;height:20px;opacity:.8}',
            '.narch-txt{display:flex;flex-direction:column;min-width:0;line-height:1.25}',
            '.narch-txt b{font-size:.9rem;font-weight:700}',
            '.narch-txt small{font-size:.75rem;color:var(--n-apagado,#64748b)}',
            '.narch-fichas{display:flex;flex-wrap:wrap;gap:6px}',
            '.narch-fichas:not(:empty){margin-top:6px}',
            '.narch-ficha{display:inline-flex;align-items:center;gap:6px;max-width:100%;',
            '  padding:4px 9px;border-radius:999px;font-size:.78rem;',
            '  background:var(--n-info-fondo,rgba(20,142,194,.14));',
            '  border:1px solid var(--n-info-linea,rgba(20,142,194,.35))}',
            '.narch-ficha svg{flex:none;width:13px;height:13px;opacity:.8}',
            '.narch-nombre{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
        ].join('');
        document.head.appendChild(css);
    }

    // ------------------------------------------------------- una lista viva

    /** Lo que el `<select>` tiene AHORA: se relee en cada apertura. */
    function opciones(sel) {
        var fuera = [];
        [].forEach.call(sel.children, function (hijo) {
            if (hijo.tagName === 'OPTGROUP') {
                fuera.push({ grupo: hijo.label });
                [].forEach.call(hijo.children, function (o) { fuera.push(dato(o)); });
            } else if (hijo.tagName === 'OPTION') {
                fuera.push(dato(hijo));
            }
        });
        return fuera;
    }

    function dato(o) {
        return { valor: o.value, texto: o.textContent.trim(), apagada: o.disabled };
    }

    function etiqueta(sel) {
        var o = sel.options[sel.selectedIndex];
        return o ? o.textContent.trim() : '';
    }

    /** Un texto que no dice nada ("—", "(select customer)") se pinta apagado. */
    function esVacio(sel) {
        var o = sel.options[sel.selectedIndex];
        if (!o) return true;
        var v = (o.value || '').trim();
        return !v || /^[—\-–]+$/.test(o.textContent.trim());
    }

    function refrescar(caja) {
        var sel = caja.querySelector('select');
        var txt = caja.querySelector('.nsel-txt');
        if (!sel || !txt) return;
        var t = etiqueta(sel);
        txt.textContent = t || '—';
        txt.classList.toggle('vacio', esVacio(sel));
        caja.querySelector('.nsel-btn').disabled = sel.disabled;
        var titulo = sel.title || t;
        if (titulo) caja.querySelector('.nsel-btn').title = titulo;
    }

    // ------------------------------------------------------------- abrir

    function cerrar() {
        if (!abierto) return;
        var a = abierto;
        abierto = null;
        a.pop.remove();
        a.btn.setAttribute('aria-expanded', 'false');
        document.removeEventListener('mousedown', fuera, true);
        document.removeEventListener('keydown', teclas, true);
        window.removeEventListener('resize', cerrar);
        window.removeEventListener('scroll', cerrar, true);
    }

    function fuera(ev) {
        if (!abierto) return;
        if (abierto.pop.contains(ev.target) || abierto.caja.contains(ev.target)) return;
        cerrar();
    }

    function teclas(ev) {
        if (!abierto) return;
        var items = [].slice.call(abierto.pop.querySelectorAll('.nsel-op:not([disabled])'));
        var i = items.indexOf(abierto.pop.querySelector('.nsel-op.marcada'));
        if (ev.key === 'Escape') { ev.preventDefault(); var b = abierto.btn; cerrar(); b.focus(); return; }
        if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
            ev.preventDefault();
            var j = ev.key === 'ArrowDown' ? i + 1 : i - 1;
            if (j < 0) j = items.length - 1;
            if (j >= items.length) j = 0;
            marcar(items[j]);
            return;
        }
        if (ev.key === 'Enter') {
            ev.preventDefault();
            var m = abierto.pop.querySelector('.nsel-op.marcada');
            if (m) m.click();
            return;
        }
        if (ev.key === 'Home' || ev.key === 'End') {
            ev.preventDefault();
            marcar(ev.key === 'Home' ? items[0] : items[items.length - 1]);
        }
    }

    function marcar(el) {
        if (!el || !abierto) return;
        var previa = abierto.pop.querySelector('.nsel-op.marcada');
        if (previa) previa.classList.remove('marcada');
        el.classList.add('marcada');
        el.scrollIntoView({ block: 'nearest' });
    }

    function colocar(pop, btn) {
        var r = btn.getBoundingClientRect();
        var margen = 6;
        pop.style.width = Math.min(Math.max(r.width, 240), 440) + 'px';
        pop.style.left = Math.max(8, Math.min(r.left, window.innerWidth - pop.offsetWidth - 8)) + 'px';
        var alto = pop.offsetHeight;
        var abajo = window.innerHeight - r.bottom;
        if (abajo >= alto + margen || abajo >= 180) pop.style.top = (r.bottom + margen) + 'px';
        else pop.style.top = Math.max(8, r.top - alto - margen) + 'px';
    }

    function abrir(caja) {
        var sel = caja.querySelector('select');
        var btn = caja.querySelector('.nsel-btn');
        if (!sel || sel.disabled) return;
        if (abierto && abierto.caja === caja) { cerrar(); return; }
        cerrar();

        var lista = opciones(sel);
        var pop = document.createElement('div');
        pop.className = 'nsel-pop';
        var buscador = lista.filter(function (o) { return !o.grupo; }).length > CON_BUSCADOR;
        pop.innerHTML =
            (buscador ? '<div class="nsel-buscar"><input type="text" autocomplete="off" spellcheck="false" ' +
                'placeholder="' + esc(textoBuscar()) + '"></div>' : '') +
            '<div class="nsel-lista" role="listbox"></div>';
        document.body.appendChild(pop);

        var cajaLista = pop.querySelector('.nsel-lista');
        function pintar(filtro) {
            var f = (filtro || '').trim().toLowerCase();
            var html = '', hay = 0;
            lista.forEach(function (o, idx) {
                if (o.grupo) { html += '<div class="nsel-grupo">' + esc(o.grupo) + '</div>'; return; }
                if (f && o.texto.toLowerCase().indexOf(f) === -1 &&
                         String(o.valor).toLowerCase().indexOf(f) === -1) return;
                hay++;
                var elegida = o.valor === sel.value;
                html += '<button type="button" class="nsel-op' + (elegida ? ' elegida' : '') + '"' +
                        ' role="option" data-i="' + idx + '"' + (o.apagada ? ' disabled' : '') +
                        (elegida ? ' aria-selected="true"' : '') + '>' + esc(o.texto || '—') + '</button>';
            });
            cajaLista.innerHTML = hay ? html : '<div class="nsel-nada">Sin coincidencias</div>';
            var elegida = cajaLista.querySelector('.nsel-op.elegida') ||
                          cajaLista.querySelector('.nsel-op:not([disabled])');
            if (elegida) elegida.classList.add('marcada');
        }
        pintar('');

        btn.setAttribute('aria-expanded', 'true');
        abierto = { caja: caja, btn: btn, pop: pop, sel: sel };
        colocar(pop, btn);
        var elegida = cajaLista.querySelector('.nsel-op.marcada');
        if (elegida) elegida.scrollIntoView({ block: 'nearest' });

        cajaLista.addEventListener('click', function (ev) {
            var op = ev.target.closest('.nsel-op');
            if (!op || op.disabled) return;
            elegir(sel, lista[Number(op.dataset.i)]);
            cerrar();
            btn.focus();
        });
        var buscar = pop.querySelector('.nsel-buscar input');
        if (buscar) {
            buscar.addEventListener('input', function () { pintar(buscar.value); });
            setTimeout(function () { buscar.focus(); }, 0);
        }

        document.addEventListener('mousedown', fuera, true);
        document.addEventListener('keydown', teclas, true);
        window.addEventListener('resize', cerrar);
        window.addEventListener('scroll', cerrar, true);
    }

    /**
     * Elegir de verdad: se le pone el valor al `<select>` y se le dispara
     * `change`. Ahí es donde la calculadora hace su trabajo —recalcular,
     * repintar, guardar—, y por eso esto no tiene que saber nada de ella.
     */
    function elegir(sel, opcion) {
        if (!opcion || sel.value === opcion.valor) return;
        sel.value = opcion.valor;
        sel.dispatchEvent(new Event('input', { bubbles: true }));
        sel.dispatchEvent(new Event('change', { bubbles: true }));
    }

    // --------------------------------------------------------- enganchar

    function enganchar(sel) {
        if (!sel || sel.dataset.nsel || sel.multiple || sel.size > 1) return;
        if (sel.closest('.nsel')) return;
        sel.dataset.nsel = '1';

        var caja = document.createElement('div');
        caja.className = 'nsel';
        sel.parentNode.insertBefore(caja, sel);
        caja.appendChild(sel);

        var btn = document.createElement('button');
        btn.type = 'button';                     // dentro de un <form> no envía
        btn.className = 'nsel-btn';
        btn.setAttribute('aria-haspopup', 'listbox');
        btn.setAttribute('aria-expanded', 'false');
        btn.innerHTML = '<span class="nsel-txt"></span>' +
            '<svg class="nsel-flecha" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
            'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
            '<polyline points="6 9 12 15 18 9"/></svg>';
        caja.appendChild(btn);

        btn.addEventListener('click', function (ev) { ev.preventDefault(); abrir(caja); });
        btn.addEventListener('keydown', function (ev) {
            // Con la lista ya abierta manda el teclado de la lista: si esto
            // volviera a atender la flecha, la cerraría en el primer
            // movimiento —el botón conserva el foco— y no se podría elegir
            // nada sin ratón.
            if (abierto && abierto.caja === caja) return;
            if (ev.key === 'ArrowDown' || ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault(); abrir(caja);
            }
        });

        // Que la etiqueta siga al valor, venga de donde venga.
        sel.addEventListener('change', function () { refrescar(caja); });
        new MutationObserver(function () { refrescar(caja); })
            .observe(sel, { childList: true, attributes: true,
                            attributeFilter: ['disabled', 'title'] });
        seguirValor(sel, caja);

        refrescar(caja);
    }

    /**
     * `select.value = "X"` desde el código no avisa a nadie.
     *
     * La calculadora lo hace constantemente al cargar una cotización guardada
     * o al leer un plano. Sin esto el botón seguiría enseñando lo anterior
     * —el valor de verdad sí cambiaba, pero la pantalla mentía—. Se le pone al
     * elemento una propiedad propia que hace lo de siempre y además refresca.
     */
    function seguirValor(sel, caja) {
        ['value', 'selectedIndex'].forEach(function (nombre) {
            var d = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, nombre) ||
                    Object.getOwnPropertyDescriptor(HTMLElement.prototype, nombre);
            if (!d || !d.set) return;
            try {
                Object.defineProperty(sel, nombre, {
                    configurable: true,
                    get: function () { return d.get.call(this); },
                    set: function (v) { d.set.call(this, v); refrescar(caja); }
                });
            } catch (e) { /* si el navegador no deja, queda el `change` */ }
        });
    }


    // ------------------------------------------------- el campo de archivos

    /**
     * "Elegir archivos / Sin archivos seleccionados".
     *
     * Ese control lo pinta el navegador y no se puede maquetar: un botón gris
     * del sistema y una frase al lado, sin decir qué se espera ni qué se ha
     * puesto. Aquí es por donde entran los PLANOS del cliente, que es el
     * trabajo de verdad de esta pantalla.
     *
     * Se le pone delante una zona propia: se pulsa o se arrastran los ficheros
     * encima, y lo elegido se enseña como fichas con su nombre. El `<input
     * type="file">` sigue debajo y sigue siendo el que manda: al soltar se le
     * ponen los ficheros y se le dispara `change`, así que "AI Read Drawing"
     * recibe exactamente lo que recibía antes.
     */
    function textoArchivos(clave) {
        var i = 'en';
        try { i = (window.parent && window.parent.I18N && window.parent.I18N.idioma) || i; } catch (e) {}
        var t = {
            en: { pulsa: 'Choose drawings', arrastra: 'or drop them here', uno: 'file', varios: 'files', quitar: 'Remove' },
            es: { pulsa: 'Elegir planos', arrastra: 'o arrástralos aquí', uno: 'archivo', varios: 'archivos', quitar: 'Quitar' },
            fr: { pulsa: 'Choisir des plans', arrastra: 'ou déposez-les ici', uno: 'fichier', varios: 'fichiers', quitar: 'Retirer' }
        };
        return (t[i] || t.en)[clave];
    }

    function engancharArchivos(inp) {
        if (!inp || inp.dataset.narch) return;
        inp.dataset.narch = '1';

        var caja = document.createElement('div');
        caja.className = 'narch';
        inp.parentNode.insertBefore(caja, inp);
        caja.appendChild(inp);

        var zona = document.createElement('div');
        zona.className = 'narch-zona';
        zona.setAttribute('role', 'button');
        zona.tabIndex = 0;
        zona.innerHTML =
            '<svg class="narch-icono" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
            '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>' +
            '<polyline points="7 9 12 4 17 9"/><line x1="12" y1="4" x2="12" y2="16"/></svg>' +
            '<span class="narch-txt"><b>' + esc(textoArchivos('pulsa')) + '</b>' +
            '<small>' + esc(textoArchivos('arrastra')) + '</small></span>';
        caja.appendChild(zona);

        var fichas = document.createElement('div');
        fichas.className = 'narch-fichas';
        caja.appendChild(fichas);

        function pintar() {
            var lista = inp.files ? [].slice.call(inp.files) : [];
            fichas.innerHTML = lista.map(function (f) {
                return '<span class="narch-ficha" title="' + esc(f.name) + '">' +
                    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" ' +
                    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
                    '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>' +
                    '<polyline points="14 2 14 8 20 8"/></svg>' +
                    '<span class="narch-nombre">' + esc(f.name) + '</span></span>';
            }).join('');
            caja.classList.toggle('con-archivos', lista.length > 0);
        }

        zona.addEventListener('click', function () { inp.click(); });
        zona.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); inp.click(); }
        });
        inp.addEventListener('change', pintar);

        ['dragenter', 'dragover'].forEach(function (e) {
            zona.addEventListener(e, function (ev) {
                ev.preventDefault(); ev.stopPropagation();
                zona.classList.add('encima');
            });
        });
        ['dragleave', 'drop'].forEach(function (e) {
            zona.addEventListener(e, function (ev) {
                ev.preventDefault(); ev.stopPropagation();
                zona.classList.remove('encima');
            });
        });
        zona.addEventListener('drop', function (ev) {
            var fs = ev.dataTransfer && ev.dataTransfer.files;
            if (!fs || !fs.length) return;
            try {
                inp.files = fs;                       // el input sigue mandando
                inp.dispatchEvent(new Event('change', { bubbles: true }));
            } catch (e) { /* navegador que no deja asignar: queda el botón */ }
        });

        pintar();
    }

    function repasar(raiz) {
        if (!raiz || typeof raiz.querySelectorAll !== 'function') return;
        if (raiz.tagName === 'SELECT') { enganchar(raiz); return; }
        if (raiz.tagName === 'INPUT' && raiz.type === 'file') { engancharArchivos(raiz); return; }
        [].forEach.call(raiz.querySelectorAll('select'), enganchar);
        [].forEach.call(raiz.querySelectorAll('input[type="file"]'), engancharArchivos);
    }

    function vigilar() {
        estilos();
        repasar(document);
        if (typeof MutationObserver === 'undefined') return;
        new MutationObserver(function (cambios) {
            for (var i = 0; i < cambios.length; i++) {
                var nodos = cambios[i].addedNodes;
                for (var j = 0; j < nodos.length; j++) {
                    if (nodos[j].nodeType === 1) repasar(nodos[j]);
                }
            }
        }).observe(document.documentElement, { childList: true, subtree: true });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', vigilar, { once: true });
    } else {
        vigilar();
    }

    window.ISCSelects = { repasar: repasar, cerrar: cerrar };
})();
