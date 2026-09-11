/**
 * La calculadora, guardando en Neon en vez de en una carpeta de OneDrive.
 *
 * La calculadora de precios se escribió para la planta: su trabajo vive en un
 * único fichero, `ISC_V4_DATA.json`, dentro de una carpeta compartida que cada
 * persona conecta a mano desde su navegador. Quien no la conecta trabaja en
 * LOCAL MODE y sus cotizaciones se quedan en su equipo.
 *
 * Dentro de Pohua eso no vale: el flujo principal es este, y la base es Neon.
 *
 * Lo bueno es que no hace falta reescribir la calculadora. Toda su persistencia
 * pasa por un solo objeto —`SFS`— con cinco métodos, y el "fichero compartido"
 * es literalmente un documento JSON. Así que este adaptador cambia esos cinco
 * métodos por llamadas al Cotizador y deja el resto de la aplicación intacta:
 * ella sigue creyendo que hay una carpeta conectada.
 *
 *     SFS.readData   ->  GET  /quoting/estado
 *     SFS.write      ->  PUT  /quoting/estado
 *     SFS.poll       ->  GET  /quoting/estado/rev
 *     SFS.saveInto   ->  POST /quoting/oferta
 *     SFS.connect    ->  ya está conectada; vuelve a leer
 *
 * POR QUÉ VA POR FUERA Y NO DENTRO DE LA CALCULADORA. Porque la calculadora es
 * de otro repositorio —el núcleo— y ahí se genera desde `construir.py`. Un
 * cambio suyo aquí se perdería en la siguiente construcción, y peor: haría que
 * la que se abre con doble clic en la planta y la que se ve en Pohua dejaran de
 * ser el mismo programa. La adaptación es cosa de quien empotra.
 *
 * CUÁNDO CORRE. Se carga con `defer`, así que entra después de que la
 * calculadora haya arrancado. No es un descuido: arrancar es justo lo que hace
 * que existan `SFS` y `shared`, y lo que hace este adaptador —adoptar el
 * documento de la nube y repintar— es exactamente lo que la calculadora ya
 * hacía al pulsar "Connect shared folder". Se usa su propio camino, no uno
 * nuevo.
 */
(function () {
    'use strict';

    var RAIZ = '/quoting';
    var ESTADO = RAIZ + '/estado';

    /* Cuánto se espera a que la calculadora termine de arrancar. Son 10 s en
       trozos de 50 ms: en una máquina lenta con el documento grande, arrancar
       tarda; rendirse antes dejaría la pantalla en LOCAL MODE sin decir por
       qué, que es el fallo silencioso que esto viene a quitar. */
    var ESPERA_MS = 10000;
    var PASO_MS = 50;

    /* Cada cuánto se pregunta si otro guardó. El mismo intervalo que usaba la
       carpeta compartida: cinco segundos es suficiente para que dos personas
       no se pisen y no tanto como para notar el tráfico. */
    var SONDEO_MS = 5000;

    var revConocida = 0;

    // ------------------------------------------------------------- utilidades

    function esperarCalculadora(alListo) {
        var esperado = 0;
        var t = setInterval(function () {
            if (typeof SFS !== 'undefined' && typeof shared !== 'undefined' && shared) {
                clearInterval(t);
                alListo();
                return;
            }
            esperado += PASO_MS;
            if (esperado >= ESPERA_MS) {
                clearInterval(t);
                console.error('[nube] La calculadora no arrancó en ' +
                              (ESPERA_MS / 1000) + ' s; se queda en modo local.');
            }
        }, PASO_MS);
    }

    function pedir(url, opciones) {
        opciones = opciones || {};
        /* `same-origin` explícito: la cookie de sesión va atada a /quoting y
           sin esto un fetch podría salir sin ella según el navegador. */
        opciones.credentials = 'same-origin';
        return fetch(url, opciones).then(function (r) {
            if (!r.ok) {
                return r.text().then(function (t) {
                    throw new Error('HTTP ' + r.status + (t ? ' — ' + t.slice(0, 200) : ''));
                });
            }
            return r.status === 204 ? null : r.json();
        });
    }

    function aviso(texto) {
        try { toast(texto); } catch (e) { console.warn('[nube] ' + texto); }
    }

    // ---------------------------------------------------- adoptar el documento

    /**
     * Trae el documento de Neon y lo pone a mandar.
     *
     * Si la base está vacía —el primer día— no se borra nada: se sube lo que
     * haya en este navegador, que es justo lo que hacía la carpeta al
     * conectarse por primera vez. Al revés también: lo que hubiera quedado en
     * local mode se funde con lo de la nube en vez de perderse.
     */
    function adoptar() {
        return pedir(ESTADO).then(function (r) {
            if (r.estado === 'datos' && r.texto) {
                var documento = JSON.parse(r.texto);
                if (documento && documento.dbs) {
                    fundirLocal(documento);
                    shared = documento;
                    revConocida = r.rev;
                    try { ensureV7Dbs(shared); } catch (e) {}
                    try { refreshSeedDriven(); } catch (e) {}
                    return 'adoptado';
                }
            }
            // Base vacía: se siembra con lo que haya aquí.
            return SFS.write().then(function () { return 'sembrado'; });
        });
    }

    /**
     * Lo que quedó guardado en este navegador y no está en la nube.
     *
     * Es la misma mezcla que hacía la calculadora al conectar la carpeta: las
     * cotizaciones del registro que no estén ya arriba y que no se hayan
     * borrado, y los clientes nuevos. Sin esto, la primera persona que abra
     * Pohua después de haber trabajado en local pierde ese trabajo sin aviso.
     */
    function fundirLocal(documento) {
        var crudo;
        try { crudo = LS.get('iscv4_sharedlocal'); } catch (e) { return; }
        if (!crudo) return;

        var local, fundidas = 0;
        try { local = JSON.parse(crudo); } catch (e) { return; }
        if (!local) return;

        var borradas = documento.deleted || [];
        (local.log || []).forEach(function (q) {
            var estaArriba = (documento.log || []).some(function (x) { return x.id === q.id; });
            if (!estaArriba && borradas.indexOf(q.id) < 0) {
                documento.log = documento.log || [];
                documento.log.push(q);
                fundidas++;
            }
        });
        if (local.dbs && local.dbs.customers) {
            local.dbs.customers.forEach(function (c) {
                var esta = (documento.dbs.customers || []).some(function (x) { return x.code === c.code; });
                if (!esta) { documento.dbs.customers.push(c); fundidas++; }
            });
        }
        if (!fundidas) return;

        documento.log.sort(function (x, y) {
            return String(y.createdAt || '').localeCompare(String(x.createdAt || ''));
        });
        try {
            documento.journal.unshift({
                when: nowStr(), who: (CUR ? String(CUR.email).split('@')[0] : '—'),
                area: 'MERGE',
                detail: fundidas + ' elemento(s) de modo local incorporados al abrir en Pohua.'
            });
        } catch (e) {}
        aviso(fundidas + ' elemento(s) que estaban sólo en este navegador se subieron a Pohua.');
    }

    // ------------------------------------------------------- los cinco métodos

    function enchufar() {
        SFS.mode = 'shared';     // el resto de la aplicación ya no ve "local"
        SFS.blocked = false;
        SFS.healthy = true;
        SFS.nube = true;

        SFS.connect = function () {
            return adoptar().then(function () { pintarBarra(); return true; })
                            .catch(function () { return false; });
        };

        SFS.attach = function () { return adoptar().then(pintarBarra); };

        SFS.readData = function () {
            return pedir(ESTADO).then(function (r) {
                return { state: r.estado === 'datos' ? 'data' : 'empty',
                         text: r.texto || '', mod: r.mod || 0 };
            });
        };

        SFS.writeOnce = function () {
            return pedir(ESTADO, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(shared)
            }).then(function (r) { revConocida = r.rev; });
        };

        /**
         * Guardar. Se conserva el espejo local a propósito.
         *
         * Si Neon no contesta —red caída, sesión caducada— el trabajo sigue en
         * este navegador y se sube en el siguiente guardado. Perder la conexión
         * no puede significar perder la cotización que se está escribiendo.
         */
        SFS.write = function () {
            try { LS.set('iscv4_sharedlocal', JSON.stringify(shared)); } catch (e) {}
            SFS.saving = true;
            try {
                shared.savedAt = nowStr();
                shared.savedBy = CUR ? CUR.email : '—';
                shared.rev = (shared.rev || 0) + 1;
            } catch (e) {}
            return SFS.writeOnce().then(function () {
                SFS.healthy = true;
            }).catch(function (err) {
                SFS.healthy = false;
                aviso('NO SE PUDO GUARDAR EN POHUA — ' + err.message +
                      '. Tu trabajo sigue en este navegador; se subirá al volver a guardar.');
            }).then(function () {
                SFS.saving = false;
                pintarBarra();
            });
        };

        /** ¿Guardó otro? Se pregunta por la revisión, no por el documento. */
        SFS.poll = function () {
            if (SFS.saving) return Promise.resolve();
            return pedir(ESTADO + '/rev').then(function (r) {
                if (!r.rev || r.rev <= revConocida) return;
                return pedir(ESTADO).then(function (e) {
                    if (e.estado !== 'datos' || !e.texto) return;
                    var documento = JSON.parse(e.texto);
                    if (!documento || !documento.dbs) return;
                    shared = documento;
                    revConocida = e.rev;
                    try { refreshSeedDriven(); } catch (err) {}
                    pintarBarra();
                    aviso('Cotizaciones actualizadas por ' +
                          (String(e.guardado_por || '').split('@')[0] || 'otro usuario') + '.');
                });
            }).catch(function () { /* un sondeo fallido no molesta a nadie */ });
        };

        /** El PDF de la oferta, al archivador de Pohua. */
        SFS.saveInto = function (cliente, nombre, blob, sub) {
            var datos = new FormData();
            datos.append('cliente', cliente || '');
            datos.append('nombre', nombre || 'oferta.pdf');
            datos.append('subcarpeta', sub || '');
            datos.append('archivo', blob, nombre || 'oferta.pdf');
            return pedir(RAIZ + '/oferta', { method: 'POST', body: datos })
                .then(function () { SFS.lastPdfError = null; return true; })
                .catch(function (err) { SFS.lastPdfError = err.message; return false; });
        };

        clearInterval(SFS.pollT);
        SFS.pollT = setInterval(SFS.poll, SONDEO_MS);
    }

    /* El tema lo pone js/isc-tema.js, que se carga SIN defer para llegar antes
       del primer pintado. Aquí sólo se le vuelve a pedir que repase después de
       mover los botones a la barra, porque esos botones no existían cuando él
       corrió. */
    function repasarTema() {
        try { window.ISCTema && window.ISCTema.aplicar(); } catch (e) {}
    }

    // -------------------------------------------------- una sola barra arriba

    /**
     * La calculadora traía su propia barra azul, y dentro había de todo.
     *
     * Empotrada en Pohua, la mitad de esa barra estaba repetida: el logo de
     * CGR y el nombre de la aplicación, el reloj y el nombre de quien entró ya
     * están en la cabecera de Pohua, dos centímetros más arriba. Dos barras
     * diciendo lo mismo se leen peor que una.
     *
     * Pero la otra mitad no sobra: `#viewtabs` es la navegación de la
     * calculadora —Quote, Summary, Quote Log, Databases, Sales Cockpit,
     * Brain— y sin ella no se llega a ningún sitio. Y el botón del Spring
     * Calculator es la puerta a la segunda cara del programa.
     *
     * Así que no se esconde la barra: se **vacía de lo repetido y lo útil baja
     * a la barra de estado**, que ya estaba ahí ocupando una línea entera para
     * decir dónde se guarda. Dos barras se vuelven una.
     *
     * Se mueven los NODOS, no copias: `appendChild` traslada el elemento con
     * los escuchadores que ya tenía puestos. Clonarlos habría dado botones
     * idénticos que no hacen nada, que es de los fallos más difíciles de ver.
     */
    function fusionarBarras() {
        var topbar = document.getElementById('topbar');
        var barra = document.getElementById('sharebar');
        if (!topbar || !barra || barra.dataset.fusionada) return;

        var herramientas = document.createElement('div');
        herramientas.className = 'nube-herramientas';

        // Sólo Quote y Spring Calc. Lo demás se queda dentro del topbar, que
        // pasa a `display:none`: sigue existiendo, con sus escuchadores, y la
        // calculadora puede cambiar de vista por su cuenta —enseñar Summary
        // después de aprobar, por ejemplo— sin que falte el botón que marca
        // dónde está.
        //
        // `#viewtabs` se mueve ENTERO y los que sobran se esconden con CSS. Su
        // lógica recorre `#viewtabs button` para poner y quitar la clase `.on`;
        // sacar un botón del grupo la dejaría sin encontrarlo.
        ['viewtabs', 'btn-spring'].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) herramientas.appendChild(el);
        });

        barra.appendChild(herramientas);
        barra.dataset.fusionada = '1';
        topbar.style.display = 'none';   // lo que queda dentro ya sólo repetía
        repasarTema();
    }

    /**
     * Los botones venían de un fondo azul marino y ahora están sobre uno
     * claro. Sin esto se quedarían en blanco sobre blanco.
     */
    function estilos() {
        if (document.getElementById('nube-estilos')) return;
        var css = document.createElement('style');
        css.id = 'nube-estilos';
        css.textContent = [
            '#sharebar{flex-wrap:wrap;gap:10px;align-items:center}',
            '#sharebar-msg{flex:1 1 auto;min-width:240px}',
            '.nube-herramientas{display:flex;align-items:center;gap:6px;flex:0 0 auto}',
            '.nube-herramientas #viewtabs{display:flex;gap:2px}',
            '.nube-herramientas #viewtabs button:not([data-v="quote"]){display:none}',
            '.nube-herramientas #viewtabs button,',
            '.nube-herramientas .topbtn{',
            '  background:#fff;color:#1B365D;border:1px solid #C7D3E4;',
            '  border-radius:7px;padding:5px 11px;font-size:.78rem;font-weight:600;',
            '  cursor:pointer;line-height:1.4}',
            '.nube-herramientas #viewtabs button:hover,',
            '.nube-herramientas .topbtn:hover{background:#EEF3FA;border-color:#8FA8C8}',
            '.nube-herramientas #viewtabs button.on{',
            '  background:#1B365D;color:#fff;border-color:#1B365D}',
            '#btn-spring{font-weight:700}'
        ].join('');
        document.head.appendChild(css);
    }

    // ------------------------------------------------------------- la barra

    /**
     * La barra de arriba deja de hablar de carpetas.
     *
     * Se sustituye entera en vez de dejar la de la calculadora: la suya ofrece
     * conectar una carpeta de OneDrive, y aquí esa acción no existe. Un botón
     * que no lleva a ninguna parte se pulsa igual.
     */
    function pintarBarra() {
        var barra = document.getElementById('sharebar');
        if (!barra) return;
        var msg = document.getElementById('sharebar-msg');
        var btn = document.getElementById('sharebar-btn');
        if (btn) btn.style.display = 'none';
        if (!msg) return;

        barra.style.display = 'flex';
        fusionarBarras();
        if (SFS.healthy === false) {
            barra.classList.remove('ok');
            msg.textContent = '⚠ El último guardado no llegó a Pohua. Tu trabajo ' +
                              'está en este navegador; vuelve a guardar.';
            return;
        }
        barra.classList.add('ok');
        var quien = String((shared && shared.savedBy) || '').split('@')[0] || '—';
        var cuando = (shared && shared.savedAt) || '—';
        msg.textContent = '☁ Guardado en Pohua (Neon) — lo mismo para todos. ' +
                          'Último guardado: ' + cuando + ' por ' + quien;
    }

    // ----------------------------------------- una sola barra de desplazamiento

    /**
     * Que baje la página de Pohua, no el marco.
     *
     * Antes el marco medía lo que la ventana y la calculadora se desplazaba por
     * dentro: dos zonas de scroll, y la barra salía a media pantalla, dentro de
     * la tarjeta, en vez de en el borde como en el resto de Pohua.
     *
     * Ahora el marco se estira hasta lo que mida su contenido y la única barra
     * es la de Pohua. Eso tiene dos consecuencias que hay que resolver aquí,
     * porque no se resuelven solas:
     *
     *   · `#botbar` —Reset, Save, Preview PDF, Approve— estaba en
     *     `position:fixed; bottom:0`. Dentro de un marco tan alto como su
     *     contenido, "abajo" es el final del documento: la barra se iría al
     *     fondo de todo y no se vería nunca. Por eso BAJA a Pohua, pegada al
     *     borde inferior de la ventana de verdad.
     *
     *   · Las capas —el modal, el Spring Calculator, la entrada— también son
     *     `position:fixed; inset:0`, y en un marco de 3.000 px se dibujarían
     *     de 3.000 px. Mientras haya una abierta, el marco vuelve a medir lo
     *     que la ventana y se desplaza por dentro: "modo ventana". Al cerrarla
     *     vuelve a estirarse.
     */
    var CAPAS = ['modalwrap', 'scwrap', 'loginwrap'];
    var marco = null;
    var modoVentana = null;

    try { marco = window.frameElement; } catch (e) { marco = null; }

    /* Se mira `display`, no `offsetParent`: las tres capas son
       `position:fixed`, y de un elemento fijo `offsetParent` vale null aunque
       esté delante de todo. Con esa comprobación el modo ventana no llegaba a
       activarse nunca. */
    function capaAbierta() {
        for (var i = 0; i < CAPAS.length; i++) {
            var el = document.getElementById(CAPAS[i]);
            if (el && getComputedStyle(el).display !== 'none') return true;
        }
        return false;
    }

    function altoDelPadre() {
        try { return window.parent.innerHeight; } catch (e) { return window.innerHeight; }
    }

    /**
     * Lo que mide el contenido. Y NO `documentElement.scrollHeight`.
     *
     * Ese fue un error con consecuencias: `scrollHeight` del documento nunca
     * devuelve menos que el alto de su ventana, y aquí la ventana ES el marco.
     * Así que en cuanto el marco crecía una vez —al cargar, o al abrirse una
     * capa, que lo pone al alto de la pantalla— la siguiente medida devolvía
     * ese mismo alto y el marco ya no podía volver a encoger. Quedaba clavado
     * en su máximo histórico, con media pantalla de vacío debajo de la
     * calculadora.
     *
     * La caja del `body` sí la dicta su contenido: no se estira hasta la
     * ventana salvo que alguien le ponga una altura, y aquí nadie lo hace.
     * Sus márgenes se suman aparte porque quedan fuera de la caja.
     */
    function altoDelContenido() {
        var cuerpo = document.body;
        if (!cuerpo) return 0;
        var estilo = getComputedStyle(cuerpo);
        var margen = (parseFloat(estilo.marginTop) || 0) +
                     (parseFloat(estilo.marginBottom) || 0);
        return Math.ceil(cuerpo.getBoundingClientRect().height + margen);
    }

    function ajustarAlto() {
        if (!marco) return;
        var capa = capaAbierta();

        if (capa !== modoVentana) {
            modoVentana = capa;
            document.documentElement.classList.toggle('nube-ventana', capa);
            /* La capa se dibuja centrada en el marco. Si la página estaba
               desplazada, el marco empieza por encima del borde de arriba y la
               capa saldría medio fuera, así que primero se sube a él. */
            if (capa) {
                try { marco.scrollIntoView({ block: 'start' }); } catch (e) {}
            }
        }

        if (capa) {
            marco.style.height = altoDelPadre() + 'px';
            return;
        }

        var alto = altoDelContenido();
        if (alto > 0) {
            marco.style.height = alto + 'px';
            /* El `min-height` del CSS es sólo para el rato en que la
               calculadora todavía no ha medido nada: sin él, un iframe vale
               150 px y se ve el salto al cargar. En cuanto hay una medida de
               verdad estorba —deja un hueco debajo cuando el contenido es más
               corto que el mínimo—, así que se retira. */
            if (marco.style.minHeight !== '0px') marco.style.minHeight = '0px';
        }
        anclarFijos();
    }

    /* La calculadora repinta tablas enteras al cambiar de etapa, así que no
       basta con medir una vez. Se mira el tamaño del cuerpo, los cambios del
       árbol y, por si algo se escapa, un latido lento. */
    function vigilarAlto() {
        if (!marco) return;
        var pendiente = false;
        function pedir() {
            if (pendiente) return;
            pendiente = true;
            requestAnimationFrame(function () { pendiente = false; ajustarAlto(); });
        }
        if (window.ResizeObserver) {
            new ResizeObserver(pedir).observe(document.documentElement);
            if (document.body) new ResizeObserver(pedir).observe(document.body);
        }
        new MutationObserver(pedir).observe(document.documentElement, {
            childList: true, subtree: true, attributes: true,
            attributeFilter: ['style', 'class', 'hidden']
        });
        window.addEventListener('resize', pedir);
        setInterval(ajustarAlto, 1000);
        ajustarAlto();
    }

    // ------------------------------------------------------- tablas anchas

    /**
     * Que la tabla se desplace sola, y no la página.
     *
     * El modelo de costes tiene seis columnas —la descripción y cinco tramos,
     * con tres cifras cada uno—: no hay forma de que eso quepa en un teléfono,
     * ni debería. Lo que no puede pasar es que empuje la página entera hacia
     * los lados, porque entonces se desplaza también la cabecera, el título se
     * va de la pantalla y se pierde el sitio al volver.
     *
     * Se envuelve cada tabla en su propia caja con desplazamiento horizontal.
     * Se hace aquí y no con CSS porque la alternativa —`table{display:block}`—
     * rompe el reparto de columnas: cada fila pasa a ser un bloque y las
     * columnas dejan de alinearse entre filas.
     *
     * La calculadora repinta tablas enteras al cambiar de etapa, así que esto
     * se vuelve a pasar cuando el árbol cambia, y la marca `data-envuelta`
     * evita envolver dos veces la misma.
     */
    function envolverTablas() {
        var tablas = document.querySelectorAll('table:not([data-envuelta])');
        for (var i = 0; i < tablas.length; i++) {
            var t = tablas[i];
            t.setAttribute('data-envuelta', '1');
            // Las que ya están dentro de una caja con scroll se dejan: puede
            // ser una del propio programa, y anidar dos no mejora nada.
            if (t.parentNode && t.parentNode.classList &&
                t.parentNode.classList.contains('nube-ancha')) continue;
            var caja = document.createElement('div');
            caja.className = 'nube-ancha';
            t.parentNode.insertBefore(caja, t);
            caja.appendChild(t);
        }
    }

    function vigilarTablas() {
        envolverTablas();
        var pendiente = false;
        new MutationObserver(function () {
            if (pendiente) return;
            pendiente = true;
            requestAnimationFrame(function () { pendiente = false; envolverTablas(); });
        }).observe(document.documentElement, { childList: true, subtree: true });
    }

    // ------------------------------------------------ la barra de acciones

    /**
     * La barra de acciones y el aviso, clavados al borde de la ventana.
     *
     * `#botbar` —Reset, Save, Preview PDF, Approve— y `#toast` estaban en
     * `position:fixed; bottom:0`. Dentro de un marco tan alto como su
     * contenido, "abajo" es el final del documento: se irían al fondo de todo
     * y no se verían nunca.
     *
     * El primer intento fue MOVERLOS al documento de Pohua. Funcionaba a la
     * vista y rompía la calculadora entera: al sacar el nodo con `adoptNode`,
     * `document.getElementById('bb-num')` pasa a devolver null dentro del
     * marco, y la primera línea que escribe el número de cotización revienta.
     * Con eso se cae el render y la pantalla se queda en blanco. Los nodos NO
     * se sacan de aquí.
     *
     * Así que se quedan donde están y se les cambia el anclaje: de `fixed` a
     * `absolute`, y un `transform` que los coloca a la altura del borde
     * inferior de la ventana de verdad, recalculado cuando la página se
     * desplaza. `transform` y no `top` porque lo compone la GPU y no obliga a
     * recalcular la maqueta en cada scroll.
     *
     * En modo ventana no hace falta nada: el marco vuelve a medir lo que la
     * ventana, y ahí `position:fixed` ya cae donde debe. Por eso la regla va
     * colgada de `html:not(.nube-ventana)`.
     */
    var HUECO_AVISO = 12;

    function estiloAnclaje() {
        if (document.getElementById('nube-anclaje')) return;
        var css = document.createElement('style');
        css.id = 'nube-anclaje';
        css.textContent = [
            'html:not(.nube-ventana) #botbar{position:absolute;top:0;bottom:auto;',
            '  left:0;right:0;will-change:transform}',
            'html:not(.nube-ventana) #toast{position:absolute;top:0;bottom:auto;',
            '  left:50%;will-change:transform}'
        ].join('');
        document.head.appendChild(css);
    }

    function anclarFijos() {
        if (!marco || modoVentana) return;

        var bot = document.getElementById('botbar');
        var toast = document.getElementById('toast');
        if (!bot && !toast) return;

        var r;
        try { r = marco.getBoundingClientRect(); } catch (e) { return; }
        var ventana = altoDelPadre();
        var largo = altoDelContenido();

        if (bot) {
            var h = bot.offsetHeight || 0;
            /* Pegada al borde de abajo de la ventana mientras el marco lo
               cruce, y quieta dentro del marco cuando no: ni se sale por
               arriba al llegar al final de la página ni por abajo al empezar. */
            var y = Math.min(Math.max(-r.top + ventana - h, 0), Math.max(largo - h, 0));
            bot.style.transform = 'translateY(' + Math.round(y) + 'px)';

            if (toast) {
                var ht = toast.offsetHeight || 0;
                toast.style.transform = 'translate(-50%,' +
                    Math.round(Math.max(y - ht - HUECO_AVISO, 0)) + 'px)';
            }
        }
    }

    /* El scroll que hay que escuchar es el del PADRE, no el nuestro: aquí
       dentro ya no se desplaza nada. */
    function vigilarAnclaje() {
        if (!marco) return;
        estiloAnclaje();
        var pendiente = false;
        function pedir() {
            if (pendiente) return;
            pendiente = true;
            requestAnimationFrame(function () { pendiente = false; anclarFijos(); });
        }
        try {
            window.parent.addEventListener('scroll', pedir, { passive: true });
            window.parent.addEventListener('resize', pedir, { passive: true });
        } catch (e) {}
        window.addEventListener('resize', pedir);
        anclarFijos();
    }

    // ------------------------------------------------------------- arranque

    esperarCalculadora(function () {
        estilos();
        fusionarBarras();
        vigilarAnclaje();
        vigilarTablas();
        vigilarAlto();
        /* Si la calculadora no se regeneró, el tema no puede pintarla y se
           queda en claro dentro de Pohua oscuro. Se dice en voz alta: la vez
           que pasó, lo que se vio fue una tabla ilegible y no había forma de
           adivinar por qué. */
        if (!document.documentElement.hasAttribute('data-nube-tema')) {
            aviso('La calculadora no se regeneró: falta pasar ' +
                  'scripts/vendorizar_nucleo.py. Se queda en tema claro.');
        }
        enchufar();
        if (typeof renderShareBar === 'function') {
            try { renderShareBar = pintarBarra; } catch (e) {}
        }
        adoptar().then(function (como) {
            pintarBarra();
            if (como === 'sembrado') {
                aviso('Primera vez: se subió a Pohua lo que había en este navegador.');
            }
        }).catch(function (err) {
            SFS.healthy = false;
            pintarBarra();
            aviso('No se pudo leer el estado desde Pohua — ' + err.message);
        });
    });
})();
