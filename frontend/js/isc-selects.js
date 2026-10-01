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

            /* El tope va en PÍXELES, no en `vh`. Esto vive dentro de un marco
               tan alto como su contenido —seis mil píxeles en una cotización
               llena—, así que ahí `60vh` no son dos tercios de pantalla: son
               tres mil seiscientos píxeles, y la lista salía tan larga como la
               calculadora. */
            '.nsel-pop{position:fixed;z-index:9600;display:flex;flex-direction:column;',
            '  max-height:380px;overflow:hidden;',
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

            /* En el teléfono la lista ocupa el ancho y con opciones más altas,
               para tocarlas con el pulgar. Lo que NO hace es subir desde abajo
               de la pantalla: esto vive dentro de un iframe tan alto como su
               contenido —seis mil píxeles— y ahí `position:fixed` se mide
               contra el documento, no contra la ventana. Anclada a "abajo" la
               lista aparecía al final de la calculadora, a cinco pantallas de
               distancia del campo que se acababa de tocar. Pegada al campo se
               ve siempre, que es lo único que importa. */
            '@media (max-width:820px){',
            ' .nsel-pop{left:8px!important;right:8px!important;width:auto!important;',
            '   max-height:320px}',
            ' .nsel-op{padding:11px 12px;font-size:.95rem}',
            '}',

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

            /* --- el campo de fecha --- */
            '.nfec{position:relative;display:block;width:100%}',
            '.nfec>input{position:absolute;inset:0;width:100%;height:100%;opacity:0;',
            '  pointer-events:none;margin:0}',
            '.nfec-btn{display:flex;align-items:center;gap:8px;width:100%;',
            '  font:inherit;font-size:.95rem;text-align:left;cursor:pointer;',
            '  padding:6px 8px;border-radius:7px;',
            '  border:1px solid var(--n-linea,#cbd5e1);background:var(--n-papel,#fff);',
            '  color:var(--n-tinta,#0f172a);',
            '  transition:border-color .12s ease,box-shadow .12s ease}',
            '.nfec-btn:hover:not([disabled]){border-color:var(--n-info-solido,#148ec2)}',
            '.nfec-btn[aria-expanded="true"],.nfec-btn:focus-visible{outline:none;',
            '  border-color:var(--n-info-solido,#148ec2);',
            '  box-shadow:0 0 0 3px var(--n-info-fondo,rgba(20,142,194,.18))}',
            '.nfec-btn[disabled]{opacity:.55;cursor:not-allowed}',
            '.nfec-icono{flex:none;width:15px;height:15px;opacity:.7}',
            '.nfec-txt{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
            '.nfec-txt.vacio{color:var(--n-apagado,#64748b)}',
            'td .nfec-btn{padding:4px 6px;font-size:.86rem}',

            '.nfec-pop{position:fixed;z-index:9600;width:296px;padding:10px;',
            '  background:var(--n-papel,#fff);color:var(--n-tinta,#0f172a);',
            '  border:1px solid var(--n-linea,#cbd5e1);border-radius:12px;',
            '  box-shadow:0 12px 32px rgba(0,0,0,.28);',
            '  animation:nselEntra .12s ease-out}',
            '.nfec-cab{display:flex;align-items:center;gap:2px;margin-bottom:6px}',
            /* "septiembre de 2026" -> "Septiembre de 2026". Con `capitalize` a
               secas salía "Septiembre De 2026": en español el mes va en
               minúscula y el "de" también. */
            '.nfec-titulo{flex:1;text-align:center;font-size:.92rem;font-weight:700}',
            '.nfec-titulo::first-letter{text-transform:uppercase}',
            '.nfec-paso{flex:none;display:grid;place-items:center;width:28px;height:28px;',
            '  padding:0;border:0;border-radius:7px;background:transparent;color:inherit;',
            '  cursor:pointer}',
            '.nfec-paso:hover{background:var(--n-sutil,#f1f5f9)}',
            '.nfec-paso:focus-visible{outline:2px solid var(--n-info-solido,#148ec2);outline-offset:1px}',
            '.nfec-paso svg{width:15px;height:15px}',
            '.nfec-sem,.nfec-rejilla{display:grid;grid-template-columns:repeat(7,1fr);gap:2px}',
            '.nfec-sem{margin-bottom:2px}',
            '.nfec-sem span{text-align:center;font-size:10px;font-weight:700;letter-spacing:.04em;',
            '  color:var(--n-apagado,#64748b)}',
            '.nfec-dia{height:34px;padding:0;font:inherit;font-size:.86rem;',
            '  border:0;border-radius:8px;background:transparent;color:inherit;cursor:pointer}',
            '.nfec-dia:hover:not([disabled]){background:var(--n-sutil,#f1f5f9)}',
            '.nfec-dia:focus-visible{outline:2px solid var(--n-info-solido,#148ec2);outline-offset:-2px}',
            '.nfec-dia.fuera{color:var(--n-apagado,#64748b);opacity:.6}',
            '.nfec-dia.hoy{box-shadow:inset 0 0 0 1.5px var(--n-info-solido,#148ec2);font-weight:700}',
            '.nfec-dia.elegido{background:var(--n-info-solido,#148ec2);color:#fff;font-weight:700}',
            '.nfec-dia.elegido:hover{background:var(--n-info-solido,#148ec2)}',
            '.nfec-dia[disabled]{opacity:.3;cursor:not-allowed}',
            '.nfec-pie{display:flex;justify-content:space-between;gap:8px;margin-top:8px;',
            '  padding-top:8px;border-top:1px solid var(--n-linea,#cbd5e1)}',
            '.nfec-pie button{font:inherit;font-size:.84rem;font-weight:700;padding:5px 9px;',
            '  border:0;border-radius:7px;background:transparent;cursor:pointer;',
            '  color:var(--n-info-solido,#148ec2)}',
            '.nfec-pie button:hover{background:var(--n-info-fondo,rgba(20,142,194,.14))}',

            /* En el teléfono, como las listas: a lo ancho y pegado al campo. */
            '@media (max-width:820px){',
            ' .nfec-pop{left:8px!important;right:8px!important;width:auto!important;padding:12px}',
            ' .nfec-dia{height:42px;font-size:.95rem}',
            '}',
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

    /**
     * La ventana DE VERDAD, que es la de fuera.
     *
     * Esto corre dentro de un marco tan alto como su contenido: aquí
     * `window.innerHeight` no es la pantalla, son los seis mil píxeles de la
     * calculadora, y con ese número "¿cabe debajo?" siempre sale que sí. Lo
     * que hace falta es el alto de la ventana de Pohua y dónde empieza el
     * marco dentro de ella; con eso, la cuenta vuelve a ser la de una página
     * normal.
     */
    function ventanaReal() {
        try {
            var m = window.frameElement;
            if (m && window.parent !== window) {
                return { alto: window.parent.innerHeight, desfase: m.getBoundingClientRect().top };
            }
        } catch (e) { /* otro origen: se sigue con lo de aquí */ }
        return { alto: window.innerHeight, desfase: 0 };
    }

    /**
     * Debajo del campo, o encima si abajo no cabe.
     *
     * Y con el alto recortado a lo que quede libre: más vale una lista de
     * ciento y pico píxeles con su propia barra que una lista perfecta que se
     * sale de la pantalla por abajo.
     */
    function colocarCaja(pop, btn, anchoPropio) {
        var r = btn.getBoundingClientRect();
        var margen = 6;
        var v = ventanaReal();
        var arribaEnPantalla = r.top + v.desfase;
        var abajoEnPantalla = r.bottom + v.desfase;

        if (anchoPropio && window.innerWidth > 820) {
            pop.style.width = Math.min(Math.max(r.width, 240), 440) + 'px';
            pop.style.left = Math.max(8, Math.min(r.left, window.innerWidth - pop.offsetWidth - 8)) + 'px';
        } else if (window.innerWidth > 820) {
            pop.style.left = Math.max(8, Math.min(r.left, window.innerWidth - pop.offsetWidth - 8)) + 'px';
        }

        var hueco = { abajo: v.alto - abajoEnPantalla - margen - 8,
                      arriba: arribaEnPantalla - margen - 8 };
        var alto = pop.offsetHeight;
        var cabeAbajo = hueco.abajo >= alto;
        var arriba = !cabeAbajo && hueco.arriba > hueco.abajo;

        var sitio = arriba ? hueco.arriba : hueco.abajo;
        if (alto > sitio && sitio > 120) pop.style.maxHeight = Math.floor(sitio) + 'px';

        pop.style.top = arriba
            ? Math.max(0, r.top - pop.offsetHeight - margen) + 'px'
            : (r.bottom + margen) + 'px';
    }

    function colocar(pop, btn) { colocarCaja(pop, btn, true); }

    /**
     * Que se vea. La página que se desplaza es la de FUERA.
     *
     * El marco no tiene barra propia —mide lo que su contenido—, así que si la
     * lista se abre por debajo del borde de la pantalla, aquí dentro no hay
     * nada que desplazar. `scrollIntoView` sí sube por los marcos y mueve la
     * página de Pohua, que es la que manda. Con `nearest` no hace nada cuando
     * ya se ve entera, que es casi siempre.
     */
    function traerALaVista(el) {
        try { el.scrollIntoView({ block: 'nearest', inline: 'nearest' }); } catch (e) {}
    }

    /**
     * Y si aun así se sale por abajo, se mueve la página de fuera.
     *
     * `scrollIntoView` no sirve para la lista: está en `position:fixed`, y a
     * un elemento fijo el navegador lo da siempre por visible —dentro de este
     * marco no hay nada que desplazar—. Lo que hay que desplazar es la página
     * de Pohua, y como la lista viaja con el marco, moverla a ella la sube
     * exactamente lo mismo.
     */
    function asegurarVisible(pop) {
        var v = ventanaReal();
        if (!v.desfase && v.alto === window.innerHeight) return;   // no estamos en un marco
        var r = pop.getBoundingClientRect();
        var arriba = r.top + v.desfase;
        var abajo = r.bottom + v.desfase;
        var mueve = 0;
        if (abajo > v.alto - 8) mueve = abajo - (v.alto - 8);
        if (arriba - mueve < 8) mueve = arriba - 8;                 // que no se salga por arriba
        if (!mueve) return;
        try { window.parent.scrollBy(0, mueve); } catch (e) { traerALaVista(pop); }
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
        // Primero el CAMPO a la vista y luego se coloca la lista: al revés se
        // decidía "arriba o abajo" con una geometría que el desplazamiento
        // cambiaba un instante después.
        traerALaVista(caja);
        colocar(pop, btn);
        asegurarVisible(pop);
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
            /* En la compu el cursor va al buscador: se abre y se escribe. En el
               teléfono NO, porque enfocarlo abre el teclado, y el teclado se
               come media pantalla justo encima de la lista que se acaba de
               abrir. Quien quiera buscar toca el campo; quien sólo quiera
               elegir —que es lo normal— ve la lista entera. */
            if (window.innerWidth > 820) setTimeout(function () { buscar.focus(); }, 0);
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
            en: { pulsa: 'Choose drawings', arrastra: 'or drop them here', uno: 'file', varios: 'files', quitar: 'Remove',
                  ver: 'View', verTitulo: 'See the drawing as the customer sent it' },
            es: { pulsa: 'Elegir planos', arrastra: 'o arrástralos aquí', uno: 'archivo', varios: 'archivos', quitar: 'Quitar',
                  ver: 'Ver', verTitulo: 'Ver el dibujo tal cual lo mandó el cliente' },
            fr: { pulsa: 'Choisir des plans', arrastra: 'ou déposez-les ici', uno: 'fichier', varios: 'fichiers', quitar: 'Retirer',
                  ver: 'Voir', verTitulo: 'Voir le plan tel que le client l’a envoyé' }
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
            // Sin «Ver» en la ficha: el plano se mira con el botón «Plano del
            // cliente» de Pohua (components/plano-cliente.js).
            var conVer = false;
            fichas.innerHTML = lista.map(function (f, i) {
                return '<span class="narch-ficha" title="' + esc(f.name) + '">' +
                    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" ' +
                    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
                    '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>' +
                    '<polyline points="14 2 14 8 20 8"/></svg>' +
                    '<span class="narch-nombre">' + esc(f.name) + '</span>' +
                    (conVer ? '<button type="button" class="narch-ver" data-narch-ver="' + i + '" title="' +
                              esc(textoArchivos('verTitulo')) + '">' + esc(textoArchivos('ver')) + '</button>' : '') +
                    '</span>';
            }).join('');
            caja.classList.toggle('con-archivos', lista.length > 0);
        }

        zona.addEventListener('click', function () { inp.click(); });
        fichas.addEventListener('click', function (ev) {
            var b = ev.target.closest('[data-narch-ver]');
            if (!b) return;
            ev.preventDefault();
            ev.stopPropagation();
            var i = Number(b.dataset.narchVer) || 0;
            if (window.ISCPlano) { window.ISCPlano.ver(i); return; }
            // Sin el visor (una capa que no cargó): el fichero en otra
            // pestaña, que el navegador sabe enseñar. Nunca un clic muerto.
            var f = inp.files && inp.files[i];
            if (f) window.open(URL.createObjectURL(f), '_blank', 'noopener');
        });
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

    // --------------------------------------------------- el campo de fecha

    /**
     * "RFQ Date": el último control que seguía siendo del sistema operativo.
     *
     * El `<input type="date">` nativo tiene el mismo problema que el `<select>`
     * y uno peor: su calendario lo pinta Windows en blanco sobre la pantalla
     * oscura, con su propio tipo de letra, y encima el campo enseña la fecha en
     * el formato del SISTEMA, no en el del idioma que tenga puesto la
     * aplicación. En una operación con tres países eso es justo lo que no
     * conviene: 09/08/2026 quiere decir dos días distintos según quién lo lea.
     *
     * Aquí se hace lo mismo que con los desplegables: el input sigue debajo,
     * invisible pero vivo —la calculadora lee `q-rfq.value` y escucha su
     * `oninput`, y eso no cambia—, y encima va un botón que enseña la fecha con
     * el mes escrito ("18 sept 2026"), que no se puede leer al revés, más un
     * calendario propio con los colores del tema.
     *
     * El valor sigue siendo ISO (`2026-09-18`), que es lo que guarda y compara
     * la calculadora: lo que cambia es cómo se lee y cómo se elige.
     */

    var LOCALES = { en: 'en-US', es: 'es-MX', fr: 'fr-FR' };
    var abiertaF = null;       // { caja, btn, pop, inp, mes, foco }

    function idiomaActual() {
        try {
            return (window.parent && window.parent.I18N && window.parent.I18N.idioma) || 'en';
        } catch (e) { return 'en'; }
    }

    function local() { return LOCALES[idiomaActual()] || 'en-US'; }

    function textoFecha(clave) {
        var t = {
            en: { vacia: 'Pick a date', hoy: 'Today', borrar: 'Clear', calendario: 'Open calendar',
                  mesAtras: 'Previous month', mesAdelante: 'Next month',
                  anoAtras: 'Previous year', anoAdelante: 'Next year' },
            es: { vacia: 'Elegir fecha', hoy: 'Hoy', borrar: 'Borrar', calendario: 'Abrir el calendario',
                  mesAtras: 'Mes anterior', mesAdelante: 'Mes siguiente',
                  anoAtras: 'Año anterior', anoAdelante: 'Año siguiente' },
            fr: { vacia: 'Choisir une date', hoy: "Aujourd'hui", borrar: 'Effacer', calendario: 'Ouvrir le calendrier',
                  mesAtras: 'Mois précédent', mesAdelante: 'Mois suivant',
                  anoAtras: 'Année précédente', anoAdelante: 'Année suivante' }
        };
        return (t[idiomaActual()] || t.en)[clave];
    }

    /* Las fechas se manejan como día de calendario, nunca como instante: un
       `new Date('2026-09-18')` se lee como medianoche UTC y en México sale el
       día 17. Por eso se parte la cadena a mano. */
    function dos(n) { return (n < 10 ? '0' : '') + n; }

    function deIso(cadena) {
        var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(cadena || '').trim());
        if (!m) return null;
        var f = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
        return isNaN(f.getTime()) ? null : f;
    }

    function aIso(f) {
        return f.getFullYear() + '-' + dos(f.getMonth() + 1) + '-' + dos(f.getDate());
    }

    function hoyMismo() {
        var h = new Date();
        return new Date(h.getFullYear(), h.getMonth(), h.getDate());
    }

    function conFormato(f) {
        try {
            return new Intl.DateTimeFormat(local(), {
                day: 'numeric', month: 'short', year: 'numeric'
            }).format(f);
        } catch (e) { return aIso(f); }
    }

    /** Lunes primero en todas partes menos en inglés, donde la semana abre en domingo. */
    function primerDia() { return idiomaActual() === 'en' ? 0 : 1; }

    function nombresSemana() {
        var fuera = [];
        for (var i = 0; i < 7; i++) {
            // 2026-02-01 fue domingo: sumando i salen los siete en orden.
            var f = new Date(2026, 1, 1 + ((primerDia() + i) % 7));
            var n;
            try {
                n = new Intl.DateTimeFormat(local(), { weekday: 'short' }).format(f);
            } catch (e) { n = ['Su','Mo','Tu','We','Th','Fr','Sa'][f.getDay()]; }
            fuera.push(n.replace('.', '').slice(0, 2).toUpperCase());
        }
        return fuera;
    }

    function tituloMes(mes) {
        try {
            return new Intl.DateTimeFormat(local(), { month: 'long', year: 'numeric' }).format(mes);
        } catch (e) { return mes.getFullYear() + '-' + dos(mes.getMonth() + 1); }
    }

    /** Fuera de `min`/`max` no se puede elegir, igual que en el nativo. */
    function permitida(inp, f) {
        var iso = aIso(f);
        if (inp.min && iso < inp.min) return false;
        if (inp.max && iso > inp.max) return false;
        return true;
    }

    function refrescarFecha(caja) {
        var inp = caja.querySelector('input');
        var txt = caja.querySelector('.nfec-txt');
        if (!inp || !txt) return;
        var f = deIso(inp.value);
        txt.textContent = f ? conFormato(f) : textoFecha('vacia');
        txt.classList.toggle('vacio', !f);
        var btn = caja.querySelector('.nfec-btn');
        btn.disabled = inp.disabled;
        btn.title = f ? inp.value : textoFecha('calendario');   // el ISO, para quien lo necesite
    }

    function cerrarFecha(devolverFoco) {
        if (!abiertaF) return;
        var a = abiertaF;
        abiertaF = null;
        a.pop.remove();
        a.btn.setAttribute('aria-expanded', 'false');
        document.removeEventListener('mousedown', fueraFecha, true);
        window.removeEventListener('resize', cerrarFecha);
        window.removeEventListener('scroll', cerrarFecha, true);
        if (devolverFoco) a.btn.focus();
    }

    function fueraFecha(ev) {
        if (!abiertaF) return;
        if (abiertaF.pop.contains(ev.target) || abiertaF.caja.contains(ev.target)) return;
        cerrarFecha();
    }

    function elegirFecha(inp, iso) {
        if (inp.value === iso) return;
        inp.value = iso;                 // la propiedad propia refresca la etiqueta
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        inp.dispatchEvent(new Event('change', { bubbles: true }));
    }

    var FLECHA = {
        mesAtras:    '<polyline points="15 18 9 12 15 6"/>',
        mesAdelante: '<polyline points="9 18 15 12 9 6"/>',
        anoAtras:    '<polyline points="11 17 6 12 11 7"/><polyline points="18 17 13 12 18 7"/>',
        anoAdelante: '<polyline points="13 17 18 12 13 7"/><polyline points="6 17 11 12 6 7"/>'
    };

    function paso(clave, salto) {
        return '<button type="button" class="nfec-paso" data-salto="' + salto + '"' +
               ' title="' + esc(textoFecha(clave)) + '" aria-label="' + esc(textoFecha(clave)) + '">' +
               '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" ' +
               'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
               FLECHA[clave] + '</svg></button>';
    }

    function pintarMes() {
        if (!abiertaF) return;
        var a = abiertaF;
        var inp = a.inp;
        var elegida = deIso(inp.value);
        var hoy = hoyMismo();

        a.pop.querySelector('.nfec-titulo').textContent = tituloMes(a.mes);

        // El primer día de la rejilla: el arranque de la semana del día 1.
        var primero = new Date(a.mes.getFullYear(), a.mes.getMonth(), 1);
        var desfase = (primero.getDay() - primerDia() + 7) % 7;
        var inicio = new Date(primero.getFullYear(), primero.getMonth(), 1 - desfase);

        var html = '';
        for (var i = 0; i < 42; i++) {
            var d = new Date(inicio.getFullYear(), inicio.getMonth(), inicio.getDate() + i);
            var iso = aIso(d);
            var clases = 'nfec-dia';
            if (d.getMonth() !== a.mes.getMonth()) clases += ' fuera';
            if (elegida && iso === aIso(elegida)) clases += ' elegido';
            else if (iso === aIso(hoy)) clases += ' hoy';
            var puede = permitida(inp, d);
            var enfocado = iso === aIso(a.foco);
            html += '<button type="button" class="' + clases + '" data-iso="' + iso + '"' +
                    (puede ? '' : ' disabled') +
                    ' tabindex="' + (enfocado ? '0' : '-1') + '"' +
                    ' aria-label="' + esc(conFormato(d)) + '"' +
                    (elegida && iso === aIso(elegida) ? ' aria-selected="true"' : '') +
                    '>' + d.getDate() + '</button>';
        }
        a.pop.querySelector('.nfec-rejilla').innerHTML = html;
    }

    function enfocarDia() {
        if (!abiertaF) return;
        var dia = abiertaF.pop.querySelector('.nfec-dia[tabindex="0"]');
        if (dia) dia.focus({ preventScroll: true });
    }

    /** Mueve el foco n días; si se sale del mes pintado, se cambia de mes. */
    function moverFoco(dias) {
        if (!abiertaF) return;
        var f = abiertaF.foco;
        abiertaF.foco = new Date(f.getFullYear(), f.getMonth(), f.getDate() + dias);
        abiertaF.mes = new Date(abiertaF.foco.getFullYear(), abiertaF.foco.getMonth(), 1);
        pintarMes();
        enfocarDia();
    }

    function moverMes(saltoMeses) {
        if (!abiertaF) return;
        var f = abiertaF.foco;
        // El 31 de enero + 1 mes no es el 3 de marzo: se recorta al último día.
        var destino = new Date(f.getFullYear(), f.getMonth() + saltoMeses, 1);
        var ultimo = new Date(destino.getFullYear(), destino.getMonth() + 1, 0).getDate();
        abiertaF.foco = new Date(destino.getFullYear(), destino.getMonth(),
                                 Math.min(f.getDate(), ultimo));
        abiertaF.mes = destino;
        pintarMes();
        enfocarDia();
    }

    /* El calendario se coloca igual que las listas; lo único suyo es que no
       elige su ancho (296 px en la compu, de borde a borde en el teléfono). */
    function colocarFecha(pop, btn) { colocarCaja(pop, btn, false); }

    function abrirFecha(caja) {
        var inp = caja.querySelector('input');
        var btn = caja.querySelector('.nfec-btn');
        if (!inp || inp.disabled) return;
        if (abiertaF && abiertaF.caja === caja) { cerrarFecha(); return; }
        cerrar();            // si había una lista desplegada, fuera
        cerrarFecha();

        var elegida = deIso(inp.value) || hoyMismo();
        var pop = document.createElement('div');
        pop.className = 'nfec-pop';
        pop.setAttribute('role', 'dialog');
        pop.innerHTML =
            '<div class="nfec-cab">' +
                paso('anoAtras', -12) + paso('mesAtras', -1) +
                '<div class="nfec-titulo"></div>' +
                paso('mesAdelante', 1) + paso('anoAdelante', 12) +
            '</div>' +
            '<div class="nfec-sem">' + nombresSemana().map(function (n) {
                return '<span>' + esc(n) + '</span>';
            }).join('') + '</div>' +
            '<div class="nfec-rejilla" role="grid"></div>' +
            '<div class="nfec-pie">' +
                '<button type="button" data-fec="borrar">' + esc(textoFecha('borrar')) + '</button>' +
                '<button type="button" data-fec="hoy">' + esc(textoFecha('hoy')) + '</button>' +
            '</div>';
        document.body.appendChild(pop);

        btn.setAttribute('aria-expanded', 'true');
        abiertaF = {
            caja: caja, btn: btn, pop: pop, inp: inp,
            mes: new Date(elegida.getFullYear(), elegida.getMonth(), 1),
            foco: elegida
        };
        pintarMes();
        traerALaVista(caja);
        colocarFecha(pop, btn);
        asegurarVisible(pop);
        enfocarDia();

        pop.addEventListener('click', function (ev) {
            var salto = ev.target.closest('.nfec-paso');
            if (salto) { moverMes(Number(salto.dataset.salto)); return; }

            var dia = ev.target.closest('.nfec-dia');
            if (dia && !dia.disabled) {
                elegirFecha(inp, dia.dataset.iso);
                cerrarFecha(true);
                return;
            }

            var pie = ev.target.closest('[data-fec]');
            if (!pie) return;
            if (pie.dataset.fec === 'hoy') {
                var h = hoyMismo();
                if (permitida(inp, h)) { elegirFecha(inp, aIso(h)); cerrarFecha(true); }
                return;
            }
            elegirFecha(inp, '');
            cerrarFecha(true);
        });

        pop.addEventListener('keydown', function (ev) {
            var saltos = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
            if (saltos[ev.key] !== undefined && ev.target.closest('.nfec-dia')) {
                ev.preventDefault(); moverFoco(saltos[ev.key]); return;
            }
            if (ev.key === 'PageUp' || ev.key === 'PageDown') {
                ev.preventDefault(); moverMes(ev.key === 'PageUp' ? -1 : 1); return;
            }
            if (ev.key === 'Home' || ev.key === 'End') {
                if (!ev.target.closest('.nfec-dia')) return;
                ev.preventDefault();
                var d = abiertaF.foco.getDay();
                var haciaInicio = (d - primerDia() + 7) % 7;
                moverFoco(ev.key === 'Home' ? -haciaInicio : 6 - haciaInicio);
                return;
            }
            if (ev.key === 'Escape') { ev.preventDefault(); cerrarFecha(true); }
        });

        document.addEventListener('mousedown', fueraFecha, true);
        window.addEventListener('resize', cerrarFecha);
        window.addEventListener('scroll', cerrarFecha, true);
    }

    function engancharFecha(inp) {
        if (!inp || inp.dataset.nfec) return;
        if (inp.closest('.nfec')) return;
        inp.dataset.nfec = '1';

        var caja = document.createElement('div');
        caja.className = 'nfec';
        inp.parentNode.insertBefore(caja, inp);
        caja.appendChild(inp);

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'nfec-btn';
        btn.setAttribute('aria-haspopup', 'dialog');
        btn.setAttribute('aria-expanded', 'false');
        btn.innerHTML =
            '<svg class="nfec-icono" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
            '<rect x="3" y="4.5" width="18" height="16" rx="2"/><line x1="3" y1="9.5" x2="21" y2="9.5"/>' +
            '<line x1="8" y1="2.5" x2="8" y2="6.5"/><line x1="16" y1="2.5" x2="16" y2="6.5"/></svg>' +
            '<span class="nfec-txt"></span>';
        caja.appendChild(btn);

        btn.addEventListener('click', function (ev) { ev.preventDefault(); abrirFecha(caja); });
        btn.addEventListener('keydown', function (ev) {
            if (abiertaF && abiertaF.caja === caja) return;
            if (ev.key === 'ArrowDown' || ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault(); abrirFecha(caja);
            }
        });

        inp.addEventListener('change', function () { refrescarFecha(caja); });
        new MutationObserver(function () { refrescarFecha(caja); })
            .observe(inp, { attributes: true, attributeFilter: ['disabled', 'min', 'max', 'value'] });
        seguirFecha(inp, caja);

        refrescarFecha(caja);
    }

    /**
     * Lo mismo que con los desplegables: `input.value = "2026-09-18"` desde el
     * código no avisa a nadie, y aquí pasa constantemente —la fecha de hoy que
     * pone la capa de la nube al abrir un RFQ nuevo, y la que trae una
     * cotización guardada—. Sin esto el botón enseñaría la anterior.
     */
    function seguirFecha(inp, caja) {
        var d = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
        if (!d || !d.set) return;
        try {
            Object.defineProperty(inp, 'value', {
                configurable: true,
                get: function () { return d.get.call(this); },
                set: function (v) { d.set.call(this, v); refrescarFecha(caja); }
            });
        } catch (e) { /* si el navegador no deja, queda el `change` */ }
    }

    /**
     * Al cambiar el idioma de Pohua, las fechas y los textos propios se
     * reescriben: "18 sept 2026" pasa a "Sep 18, 2026" y el calendario abre en
     * domingo o en lunes según toque. Lo demás de la calculadora ya lo traduce
     * la capa de idioma, pero esto lo pinta este fichero y hay que repasarlo.
     */
    function seguirIdioma() {
        var repintar = function () {
            cerrarFecha();
            [].forEach.call(document.querySelectorAll('.nfec'), refrescarFecha);
            [].forEach.call(document.querySelectorAll('.narch-zona'), function (z) {
                var b = z.querySelector('b'), s = z.querySelector('small');
                if (b) b.textContent = textoArchivos('pulsa');
                if (s) s.textContent = textoArchivos('arrastra');
            });
        };
        try {
            if (window.parent && window.parent.I18N && window.parent.I18N.alCambiar) {
                window.parent.I18N.alCambiar(repintar);
                return;
            }
        } catch (e) { /* otro origen */ }
        window.addEventListener('storage', function (ev) {
            if (ev.key === 'cgr-idioma') repintar();
        });
    }

    function repasar(raiz) {
        if (!raiz || typeof raiz.querySelectorAll !== 'function') return;
        if (raiz.tagName === 'SELECT') { enganchar(raiz); return; }
        if (raiz.tagName === 'INPUT' && raiz.type === 'file') { engancharArchivos(raiz); return; }
        // Por ATRIBUTO, no por `raiz.type`: un navegador que no soporte fechas
        // devuelve 'text' ahí, y es justo donde más falta hace el calendario.
        if (raiz.tagName === 'INPUT' && raiz.getAttribute('type') === 'date') {
            engancharFecha(raiz); return;
        }
        [].forEach.call(raiz.querySelectorAll('select'), enganchar);
        [].forEach.call(raiz.querySelectorAll('input[type="file"]'), engancharArchivos);
        [].forEach.call(raiz.querySelectorAll('input[type="date"]'), engancharFecha);
    }

    function vigilar() {
        estilos();
        repasar(document);
        seguirIdioma();
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

    window.ISCSelects = {
        repasar: repasar,
        cerrar: function () { cerrar(); cerrarFecha(); }
    };
})();
