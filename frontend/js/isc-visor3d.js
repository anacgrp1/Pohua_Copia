/**
 * El resorte de compresión en 3D, encima del Spring Calculator.
 *
 * Se añade a la página igual que isc-tema.js e isc-nube.js: `api/lector.py` lo
 * mete detrás de `<head>`, con `defer`. Llega a las dos calculadoras, pero sólo
 * hace algo en la de resortes, que es la única que trae `window.ISC_SC`.
 *
 * USA SÓLO EL CONTRATO. `ISC_SC` (versión 1) es lo que el núcleo promete no
 * cambiar sin avisar (mientras el núcleo no lo traiga, lo publica
 * isc-contrato.js, que se inyecta justo antes que este archivo): los datos del resorte ya calculados, en mm y N, y un aviso
 * tras cada repintado. Nada de `STATE`, `calcCompression` ni clases internas:
 * el día que el núcleo renombre algo por dentro, esto sigue funcionando.
 *
 * NO RECALCULA. La constante, el esfuerzo y la altura sólida salen de la
 * calculadora. Al mover la barra, la fuerza es k·x y el esfuerzo se escala en
 * proporción a la deflexión desde el de sólido que da ella — que es lo mismo
 * que hace su fórmula, porque el esfuerzo es proporcional a la fuerza.
 *
 * SI ALGO FALLA, NO ESTORBA. Sin `ISC_SC`, sin three.js o sin WebGL no hace
 * nada y se sigue viendo el dibujo SVG de siempre.
 *
 * UN SOLO VISOR. La calculadora repinta la casilla del dibujo entera con cada
 * dato que cambia. Crear un visor por repintado agotaría los contextos WebGL
 * del navegador (hay un tope de unos 16), así que se crea uno y su lienzo se
 * cambia de sitio: a la casilla nueva, o a la vista ampliada.
 *
 * Es una representación, no un modelo CAD: las espiras inactivas van con paso
 * igual al alambre, el esmerilado es un corte plano y no hay tolerancias.
 *
 * Los textos van en inglés, como el resto de la calculadora: isc-idioma.js los
 * traduce al idioma de Pohua junto con todo lo demás.
 */
(function () {
    'use strict';

    if (!window.ISC_SC || window.ISC_SC.version !== 1) return;
    var SC = window.ISC_SC;

    /* three.js servido por el propio Cotizador, no por una CDN: así funciona sin
       conexión (el service worker lo guarda) y no depende de que un sitio de
       fuera esté disponible. `window.ISC_VISOR3D_LIBS` permite apuntar a otro
       sitio sin tocar este archivo; se usa en las pruebas. */
    var LIBS = window.ISC_VISOR3D_LIBS || [
        '/js/vendor/three.min.js',
        '/js/vendor/OrbitControls.js'
    ];

    var st = {
        cargando: null,     // la promesa de three.js
        fallo: false,       // sin three.js o sin WebGL: sólo 2D
        v: null,            // el visor, uno solo
        r: null,            // el resorte que hay en pantalla (de ISC_SC)
        clave: null,        // para saber si es OTRO resorte y reencuadrar
        nuevo: false,
        L: null,            // longitud a la que se dibuja, en mm
        pantalla: 'in',
        ampliado: false,
        relleno: true,
        placas: true,
        anim: false,        // comprimir y soltar en bucle, en la vista ampliada
        t0: 0
    };

    // ------------------------------------------------------------ estilos

    /* Los colores van con las variables del tema de Pohua (--n-*) y un valor de
       reserva: así se ve bien en su modo oscuro y también en la calculadora
       suelta, donde esas variables no existen. */
    var css = document.createElement('style');
    css.textContent = [
        '.v3d-caja{position:relative;width:100%;height:220px;overflow:hidden}',
        /* El mismo cielo que el fondo de Pohua: su base, el resplandor azul y
           rosa de la marca, y las estrellas (canvas .v3d-cielo, debajo del 3D). */
        '.v3d-caja,.v3d-lienzo{background:radial-gradient(circle at 50% 40%,rgba(47,89,163,.30) 0%,',
        '  rgba(27,61,121,.18) 38%,rgba(179,22,113,.07) 68%,transparent 100%),var(--n-sutil,#0f172a)}',
        '.v3d-caja canvas.v3d-cielo,.v3d-lienzo canvas.v3d-cielo{position:absolute;inset:0;z-index:0;pointer-events:none;cursor:default}',
        '.v3d-caja>canvas:not(.v3d-cielo),.v3d-lienzo>canvas:not(.v3d-cielo){position:relative;z-index:1}',
        '.v3d-caja[hidden],.v3d-btns[hidden],.v3d-ov[hidden]{display:none!important}',
        '.v3d-caja canvas,.v3d-lienzo canvas{display:block;width:100%;height:100%;touch-action:none;cursor:grab}',
        '.v3d-btns{position:absolute;top:4px;right:4px;display:flex;gap:4px;z-index:3}',
        '.v3d-btn{font-family:inherit;font-size:11px;font-weight:600;line-height:1.2;padding:4px 8px;border-radius:6px;cursor:pointer;',
        '  border:1px solid var(--n-linea,#cdd4de);background:var(--n-papel,#fff);color:var(--n-tinta,#1F2937)}',
        '.v3d-btn:hover{border-color:#148EC2}',
        '.v3d-btn[aria-pressed="true"]{background:#148EC2;border-color:#148EC2;color:#fff}',
        '.v3d-btn:focus-visible{outline:2px solid #148EC2;outline-offset:1px}',
        '.v3d-ov{position:fixed;inset:0;z-index:500;background:rgba(15,25,50,.6);display:flex;align-items:center;justify-content:center;padding:12px}',
        '.v3d-panel{background:var(--n-papel,#fff);color:var(--n-tinta,#1F2937);border:1px solid var(--n-linea,#E2E8F0);border-radius:12px;',
        '  width:min(1000px,100%);height:min(660px,100%);display:grid;grid-template-columns:minmax(0,1fr) 260px;overflow:hidden}',
        '@media (max-width:720px){.v3d-panel{grid-template-columns:minmax(0,1fr);grid-template-rows:minmax(240px,1fr) auto}}',
        '.v3d-lienzo{position:relative;min-height:0}',
        '.v3d-lado{border-left:1px solid var(--n-linea,#E2E8F0);padding:12px 14px;display:flex;flex-direction:column;gap:10px;overflow:auto;font-size:12.5px}',
        '@media (max-width:720px){.v3d-lado{border-left:0;border-top:1px solid var(--n-linea,#E2E8F0)}}',
        '.v3d-cab{display:flex;justify-content:space-between;align-items:center;gap:8px}',
        '.v3d-cab b{font-size:14px;color:var(--n-marca-tinta,#1B3D79)}',
        '.v3d-lbl{font-size:10px;text-transform:uppercase;letter-spacing:.07em;font-weight:700;color:var(--n-apagado,#6B7280)}',
        '.v3d-big{font-size:22px;font-weight:700;color:var(--n-marca-tinta,#1B3D79);font-variant-numeric:tabular-nums}',
        '.v3d-fila{display:flex;flex-wrap:wrap;gap:5px}',
        '.v3d-kv{display:flex;justify-content:space-between;gap:8px;font-variant-numeric:tabular-nums}',
        '.v3d-kv span{color:var(--n-apagado,#6B7280)}',
        '.v3d-nota{margin:0;font-size:11px;color:var(--n-apagado,#6B7280)}',
        '.v3d-sello{position:absolute;z-index:2;left:8px;top:8px;font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;',
        '  background:var(--n-papel,#fff);border:1px solid var(--n-linea,#E2E8F0);color:var(--n-apagado,#6B7280)}'
    ].join('\n');
    document.head.appendChild(css);

    // ------------------------------------------------------------ three.js

    function cargarLibs() {
        if (st.cargando) return st.cargando;
        st.cargando = LIBS.reduce(function (p, src) {
            return p.then(function () {
                if (/three(\.min)?\.js$/.test(src) && window.THREE) return;
                if (/OrbitControls/.test(src) && window.THREE && window.THREE.OrbitControls) return;
                return new Promise(function (ok, mal) {
                    var s = document.createElement('script');
                    s.src = src;
                    s.onload = ok;
                    s.onerror = function () { mal(new Error('No se pudo cargar ' + src)); };
                    document.head.appendChild(s);
                });
            });
        }, Promise.resolve());
        return st.cargando;
    }

    // ------------------------------------------------------------ geometría

    /* El paso de las espiras activas a la longitud L, con la misma fórmula que
       usa la calculadora para cada tipo de extremo. */
    function pasoActivo(r, L) {
        var d = r.d, Na = r.Na;
        switch (r.extremos.tipo) {
            case 'plain':        return (L - d) / Na;
            case 'plain_ground': return L / (Na + 1);
            case 'closed':       return (L - 3 * d) / Na;
            default:             return (L - 2 * d) / Na;           // closed_ground
        }
    }

    function suave(t) { t = Math.max(0, Math.min(1, t)); return t * t * (3 - 2 * t); }

    /* La altura de la línea central a lo largo de las Nt vueltas.
       Extremos cerrados: una vuelta en cada punta con paso igual al alambre
       (van tocándose) y un cambio suave de 0.3 vueltas hacia el paso activo.
       Extremos planos: el mismo paso en todo el resorte.
       Esmerilados: la línea central va de 0 a L y los planos de corte se llevan
       media espira en cada punta. Sin esmerilar: va de d/2 a L - d/2, apoyada. */
    function alturas(r, L) {
        var d = r.d, Nt = r.Nt, p = pasoActivo(r, L);
        var cerrado = r.extremos.tipo === 'closed' || r.extremos.tipo === 'closed_ground';
        var N = 2400, z = new Float64Array(N + 1), dn = Nt / N, bl = 0.3, i;
        function paso(n) {
            if (!cerrado) return p;
            return d + (p - d) * (suave((n - (1 - bl)) / (2 * bl)) - suave((n - (Nt - 1 - bl)) / (2 * bl)));
        }
        for (i = 1; i <= N; i++) z[i] = z[i - 1] + 0.5 * (paso((i - 1) * dn) + paso(i * dn)) * dn;
        var esm = !!r.extremos.esmerilado, base = esm ? 0 : d / 2, tramo = esm ? L : L - d;
        var s = tramo / (z[N] || 1);
        for (i = 0; i <= N; i++) z[i] = base + z[i] * s;
        return z;
    }

    // ------------------------------------------------------------ el visor

    function crearVisor() {
        var T = window.THREE;
        var renderer = new T.WebGLRenderer({ antialias: true, alpha: true, stencil: true });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.localClippingEnabled = true;
        var canvas = renderer.domElement;

        var escena = new T.Scene();
        var camara = new T.PerspectiveCamera(32, 1, 0.01, 5000);
        var ctl = T.OrbitControls ? new T.OrbitControls(camara, canvas) : null;
        if (ctl) ctl.enableDamping = true;

        escena.add(new T.HemisphereLight(0xffffff, 0x8a95a3, 0.9));
        var luz1 = new T.DirectionalLight(0xffffff, 0.9); luz1.position.set(4, 6, 3); escena.add(luz1);
        var luz2 = new T.DirectionalLight(0xdfefff, 0.5); luz2.position.set(-5, 2, -4); escena.add(luz2);

        var bajo = new T.Plane(new T.Vector3(0, 1, 0), 0);
        var alto = new T.Plane(new T.Vector3(0, -1, 0), 1);
        var PLANOS = [bajo, alto];

        var acero = new T.MeshStandardMaterial({ color: 0xb9c3cd, metalness: 0.55, roughness: 0.32 });
        var matPlaca = new T.MeshStandardMaterial({ color: 0x148EC2, transparent: true, opacity: 0.22, depthWrite: false, roughness: 0.6 });
        var placaA = new T.Mesh(new T.CylinderGeometry(1, 1, 1, 64), matPlaca), placaB = placaA.clone();
        escena.add(placaA); escena.add(placaB);

        /* ALAMBRE RELLENO. Cortar el tubo con los planos del esmerilado lo deja
           abierto. Se tapa con el stencil: por cada plano se cuentan las caras
           traseras menos las delanteras del alambre cortado; donde no da cero,
           el rayo pasa por el corte, y ahí se pinta la tapa, del color del acero
           recién esmerilado. Necesita un volumen cerrado: por eso las puntas
           del alambre llevan un disco. */
        function matStencil(pl, atras) {
            var op = atras ? T.IncrementWrapStencilOp : T.DecrementWrapStencilOp;
            return new T.MeshBasicMaterial({
                depthWrite: false, depthTest: false, colorWrite: false,
                stencilWrite: true, stencilFunc: T.AlwaysStencilFunc,
                stencilFail: op, stencilZFail: op, stencilZPass: op,
                side: atras ? T.BackSide : T.FrontSide, clippingPlanes: [pl]
            });
        }
        var STENCIL = PLANOS.map(function (pl) { return [matStencil(pl, true), matStencil(pl, false)]; });
        var tapas = PLANOS.map(function (pl, i) {
            var m = new T.MeshStandardMaterial({
                color: 0xd6dde3, metalness: 0.6, roughness: 0.22,
                clippingPlanes: PLANOS.filter(function (p) { return p !== pl; }),
                stencilWrite: true, stencilRef: 0, stencilFunc: T.NotEqualStencilFunc,
                stencilFail: T.ReplaceStencilOp, stencilZFail: T.ReplaceStencilOp, stencilZPass: T.ReplaceStencilOp
            });
            var c = new T.Mesh(new T.PlaneGeometry(1, 1), m);
            c.renderOrder = i + 1.1;
            c.onAfterRender = function (rr) { rr.clearStencil(); };
            escena.add(c);
            return c;
        });

        /* A derechas con el eje hacia arriba, (z, x, y) es un triedro directo:
           el coseno va en z y el seno en x. Al revés sale a izquierdas. */
        class Helice extends T.Curve {
            constructor(r, L) {
                super();
                this.z = alturas(r, L); this.R = (r.OD - r.d) / 2; this.Nt = r.Nt;
                this.sg = r.sentido === 'left' ? -1 : 1;
            }
            getPoint(t, destino) {
                var N = this.z.length - 1, f = t * N, i = Math.min(Math.floor(f), N - 1);
                var y = this.z[i] + (this.z[i + 1] - this.z[i]) * (f - i), a = 2 * Math.PI * t * this.Nt;
                return (destino || new T.Vector3()).set(this.sg * this.R * Math.sin(a), y, this.R * Math.cos(a));
            }
        }

        var alambre = null, geos = [], tam = 1, casa = new T.Vector3(), objetivo = new T.Vector3();

        function colocarTapas() {
            tapas.forEach(function (c, i) {
                var pl = PLANOS[i];
                c.scale.set(tam * 3, tam * 3, 1);
                pl.coplanarPoint(c.position);
                c.lookAt(c.position.x - pl.normal.x, c.position.y - pl.normal.y, c.position.z - pl.normal.z);
            });
        }

        function encuadrar(r) {
            tam = Math.max(r.OD, r.L0);
            placaA.scale.set(r.OD * 0.68, tam * 0.02, r.OD * 0.68);
            placaB.scale.copy(placaA.scale);
            placaA.position.y = -placaA.scale.y / 2;
            objetivo.set(0, r.L0 / 2, 0);
            casa.set(tam * 1.85, tam * 0.5 + r.L0 * 0.7, tam * 1.85);
            if (ctl) { ctl.minDistance = tam * 0.8; ctl.maxDistance = tam * 6; }
            vistaInicial();
        }

        function vistaInicial() {
            camara.position.copy(casa);
            if (ctl) { ctl.target.copy(objetivo); ctl.update(); } else camara.lookAt(objetivo);
        }

        function poner(r, L, op) {
            if (alambre) { escena.remove(alambre); geos.forEach(function (g) { g.dispose(); }); }
            var esm = !!r.extremos.esmerilado, rell = esm && op.relleno;
            var curva = new Helice(r, L);
            var tubo = new T.TubeGeometry(curva, Math.max(240, Math.round(r.Nt * 150)), r.d / 2, 24, false);
            var disco = new T.CircleGeometry(r.d / 2, 24);
            geos = [tubo, disco];
            var P0 = curva.getPoint(0), P1 = curva.getPoint(1), T0 = curva.getTangent(0), T1 = curva.getTangent(1);
            alambre = new T.Group();
            function poblar(mat, orden) {
                var t = new T.Mesh(tubo, mat);
                var a = new T.Mesh(disco, mat); a.position.copy(P0); a.lookAt(P0.clone().sub(T0));
                var b = new T.Mesh(disco, mat); b.position.copy(P1); b.lookAt(P1.clone().add(T1));
                [t, a, b].forEach(function (m) { m.renderOrder = orden; alambre.add(m); });
            }
            acero.clippingPlanes = esm ? PLANOS : [];
            acero.side = (esm && !op.relleno) ? T.DoubleSide : T.FrontSide;
            acero.needsUpdate = true;
            poblar(acero, 6);
            if (rell) STENCIL.forEach(function (par, i) { poblar(par[0], i + 1); poblar(par[1], i + 1); });
            escena.add(alambre);
            alto.constant = L;
            placaB.position.y = L + placaB.scale.y / 2;
            placaA.visible = placaB.visible = !!op.placas;
            colocarTapas();
            tapas.forEach(function (c) { c.visible = rell; });
        }

        function ajustar() {
            var w = canvas.clientWidth, h = canvas.clientHeight;
            if (!w || !h) return;
            renderer.setSize(w, h, false);
            camara.aspect = w / h;
            camara.updateProjectionMatrix();
        }
        if (window.ResizeObserver) new ResizeObserver(ajustar).observe(canvas);
        else window.addEventListener('resize', ajustar);

        /* Sólo se dibuja mientras el lienzo está en la página: en 2D, o con la
           calculadora en otra pestaña, no gasta nada. */
        (function bucle() {
            requestAnimationFrame(bucle);
            if (!canvas.isConnected) return;
            if (ctl) ctl.update();
            renderer.render(escena, camara);
        })();

        return { canvas: canvas, poner: poner, encuadrar: encuadrar, vistaInicial: vistaInicial, ajustar: ajustar };
    }

    function conVisor(fn) {
        cargarLibs().then(function () {
            if (!st.v) st.v = crearVisor();       // sin WebGL lanza, y cae abajo
            fn(st.v);
        }).catch(function (e) {
            st.fallo = true;
            if (window.console) console.warn('isc-visor3d: sin 3D, se queda el dibujo 2D.', e);
            var d = SC.datosDelResorte();
            if (d.contenedor && d.contenedor.__v3d) pintarModo(d.contenedor.__v3d);
            if (st.ampliado) cerrar();
        });
    }

    function dibujar() {
        if (!st.v || !st.r) return;
        if (st.nuevo) { st.v.encuadrar(st.r); st.nuevo = false; }
        st.v.poner(st.r, st.L, { relleno: st.relleno, placas: st.placas });
        st.v.ajustar();
        if (st.ampliado) refrescarPanel();
    }

    // ------------------------------------------------------------ el cielo

    /* Las estrellas de Pohua (js/starfield.js), detrás del resorte: blancas,
       subiendo despacio y parpadeando, sobre el resplandor de la marca. Se
       redibujan aquí y no se toma el lienzo de Pohua porque éste vive en su
       documento, no en el marco de la calculadora. Un lienzo por casilla; el
       bucle se para solo cuando la casilla deja de estar en la página (la
       calculadora la rehace en cada repintado) o si se pide menos movimiento. */
    var QUIETO = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function crearCielo(cont) {
        var c = document.createElement('canvas');
        c.className = 'v3d-cielo';
        cont.insertBefore(c, cont.firstChild);
        var ctx = c.getContext('2d'), estrellas = [], w = 0, h = 0, raf = null;

        function medir() {
            var r = cont.getBoundingClientRect();
            var dpr = Math.min(window.devicePixelRatio || 1, 2);
            w = Math.max(1, Math.round(r.width)); h = Math.max(1, Math.round(r.height));
            c.width = Math.floor(w * dpr); c.height = Math.floor(h * dpr);
            c.style.width = w + 'px'; c.style.height = h + 'px';
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            var n = Math.min(320, Math.max(40, Math.round(w * h / 7000)));
            estrellas = [];
            for (var i = 0; i < n; i++) {
                estrellas.push({ x: Math.random() * w, y: Math.random() * h, r: Math.random() * 1.5,
                                 v: 0.1 + Math.random() * 0.5, o: Math.random(), s: Math.random() > 0.5 ? 1 : -1 });
            }
            pintar(false);
        }
        function pintar(mover) {
            ctx.clearRect(0, 0, w, h);
            for (var i = 0; i < estrellas.length; i++) {
                var e = estrellas[i];
                if (mover) {
                    e.y -= e.v;
                    if (e.y < 0) { e.y = h; e.x = Math.random() * w; }
                    e.o += 0.01 * e.s;
                    if (e.o <= 0.2) { e.o = 0.2; e.s = 1; } else if (e.o >= 1) { e.o = 1; e.s = -1; }
                }
                ctx.beginPath();
                ctx.arc(e.x, e.y, e.r, 0, Math.PI * 2);
                ctx.fillStyle = 'rgba(255,255,255,' + e.o + ')';
                ctx.fill();
            }
        }
        function bucle() {
            if (!cont.isConnected || cont.offsetParent === null) { raf = null; return; }
            pintar(true);
            raf = requestAnimationFrame(bucle);
        }
        var cielo = {
            arrancar: function () { medir(); if (QUIETO) return; if (!raf) raf = requestAnimationFrame(bucle); },
            parar: function () { if (raf) cancelAnimationFrame(raf); raf = null; },
            medir: medir
        };
        window.addEventListener('resize', function () { if (cont.isConnected) medir(); });
        return cielo;
    }

    // ------------------------------------------------------------ la casilla

    /* En Pohua se ve SOLO el 3D: se queda la casilla del dibujo y también la de
       la curva de carga, que se oculta, y ocupa la fila entera. Si el 3D no
       puede (sin three.js o sin WebGL) vuelven las dos: mejor el dibujo de
       siempre que una casilla vacía. Se aplica en cada repintado, porque las
       casillas son nuevas cada vez. */
    function montarCasilla(cont, grafica) {
        if (cont.__v3d) { pintarModo(cont.__v3d); return; }
        var ui = { cont: cont, svg: cont.querySelector('svg'), grafica: grafica || null,
                   caja: document.createElement('div'), btns: document.createElement('div') };
        ui.caja.className = 'v3d-caja';
        ui.caja.hidden = true;
        ui.cielo = crearCielo(ui.caja);
        ui.btns.className = 'v3d-btns';
        ui.btns.hidden = true;
        ui.btns.innerHTML =
            '<button type="button" class="v3d-btn" title="Enlarge" aria-label="Enlarge the spring in 3D">&#x2922; Enlarge</button>';
        ui.btns.addEventListener('click', function (e) { if (e.target.closest('button')) abrir(); });
        if (getComputedStyle(cont).position === 'static') cont.style.position = 'relative';
        cont.appendChild(ui.caja);
        cont.appendChild(ui.btns);
        cont.__v3d = ui;
        pintarModo(ui);
    }

    function pintarModo(ui) {
        if (st.fallo) { soloEl3D(ui, false); return; }
        conVisor(function (v) {
            if (!ui.cont.isConnected) return;          // ya hubo otro repintado
            soloEl3D(ui, true);
            if (!st.ampliado) ui.caja.appendChild(v.canvas);
            if (ui.cielo) ui.cielo.arrancar();
            dibujar();
        });
    }

    function soloEl3D(ui, si) {
        if (ui.svg) ui.svg.style.display = si ? 'none' : '';
        if (ui.grafica) ui.grafica.style.display = si ? 'none' : '';
        ui.cont.style.gridColumn = si ? '1 / -1' : '';
        ui.cont.style.borderRight = si ? '0' : '';
        ui.caja.hidden = !si;
        ui.btns.hidden = !si;
    }

    // ------------------------------------------------------------ la vista ampliada

    var ov = null, $ = function (id) { return document.getElementById(id); };

    function crearAmpliado() {
        ov = document.createElement('div');
        ov.className = 'v3d-ov';
        ov.hidden = true;
        ov.innerHTML =
            '<div class="v3d-panel" role="dialog" aria-modal="true" aria-labelledby="v3dTit">' +
              '<div class="v3d-lienzo" id="v3dLienzo"><span class="v3d-sello" id="v3dSello"></span></div>' +
              '<div class="v3d-lado">' +
                '<div class="v3d-cab"><b id="v3dTit">Spring in 3D</b>' +
                  '<button type="button" class="v3d-btn" id="v3dCerrar" aria-label="Close">&times;</button></div>' +
                '<div><div class="v3d-lbl">Length</div><div class="v3d-big" id="v3dL"></div>' +
                  '<input type="range" id="v3dSl" style="width:100%;accent-color:#148EC2" aria-label="Spring length"></div>' +
                '<div class="v3d-fila" id="v3dPos"></div>' +
                '<div class="v3d-fila">' +
                  '<button type="button" class="v3d-btn" id="v3dAnim" aria-pressed="false">Animate</button>' +
                  '<button type="button" class="v3d-btn" id="v3dRell" aria-pressed="true">Solid wire</button>' +
                  '<button type="button" class="v3d-btn" id="v3dPl" aria-pressed="true">Plates</button>' +
                  '<button type="button" class="v3d-btn" id="v3dVista">Reset view</button></div>' +
                '<div class="v3d-kv"><span>Deflection</span><b id="v3dX"></b></div>' +
                '<div class="v3d-kv"><span>Force</span><b id="v3dF"></b></div>' +
                '<div class="v3d-kv"><span>Stress</span><b id="v3dT"></b></div>' +
                '<div class="v3d-kv"><span>Gap between coils</span><b id="v3dG"></b></div>' +
                '<p class="v3d-nota">Force and stress come from the calculator’s rate and solid stress, in proportion to the deflection. This is a representation, not a CAD model.</p>' +
              '</div>' +
            '</div>';
        document.body.appendChild(ov);
        st.cieloAmpliado = crearCielo($('v3dLienzo'));

        ov.addEventListener('click', function (e) { if (e.target === ov) cerrar(); });
        document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && st.ampliado) cerrar(); });
        $('v3dCerrar').addEventListener('click', cerrar);
        $('v3dAnim').addEventListener('click', function () { animar(!st.anim); });
        $('v3dSl').addEventListener('input', function () { animar(false); st.L = +this.value; dibujar(); });
        $('v3dRell').addEventListener('click', function () {
            st.relleno = !st.relleno; this.setAttribute('aria-pressed', String(st.relleno)); dibujar();
        });
        $('v3dPl').addEventListener('click', function () {
            st.placas = !st.placas; this.setAttribute('aria-pressed', String(st.placas)); dibujar();
        });
        $('v3dVista').addEventListener('click', function () { if (st.v) st.v.vistaInicial(); });
        $('v3dPos').addEventListener('click', function (e) {
            var b = e.target.closest('button');
            if (!b || !st.r) return;
            animar(false); st.L = +b.dataset.l; dibujar();
        });
    }

    /* Comprime de la longitud libre a sólido y vuelve, con un coseno para que
       frene en los extremos. Lo pide el usuario, así que no se apaga con
       prefers-reduced-motion; pero nunca arranca solo. Rehacer el tubo en cada
       fotograma es barato: unos 20.000 vértices. */
    function animar(on) {
        st.anim = !!on && !!st.r && st.ampliado;
        var b = $('v3dAnim');
        if (b) b.setAttribute('aria-pressed', String(st.anim));
        if (st.anim) { st.t0 = performance.now(); requestAnimationFrame(pasoAnim); }
    }
    function pasoAnim(ahora) {
        if (!st.anim) return;
        if (!st.ampliado || !st.r) { animar(false); return; }
        var s = 0.5 - 0.5 * Math.cos((ahora - st.t0) / 1400 * Math.PI);
        st.L = st.r.L0 - (st.r.L0 - st.r.Ls) * s;
        dibujar();
        requestAnimationFrame(pasoAnim);
    }

    function abrir() {
        if (!st.r) return;
        conVisor(function (v) {
            if (!ov) crearAmpliado();
            ov.hidden = false;
            st.ampliado = true;
            $('v3dLienzo').appendChild(v.canvas);
            if (st.cieloAmpliado) st.cieloAmpliado.arrancar();
            prepararPanel();
            dibujar();
            $('v3dCerrar').focus();
        });
    }

    function cerrar() {
        if (!ov) return;
        animar(false);
        ov.hidden = true;
        st.ampliado = false;
        if (st.cieloAmpliado) st.cieloAmpliado.parar();
        var d = SC.datosDelResorte();
        if (d.listo && d.contenedor) montarCasilla(d.contenedor, d.contenedorGrafica);
    }

    function prepararPanel() {
        var r = st.r, sl = $('v3dSl');
        sl.min = r.Ls; sl.max = r.L0; sl.step = (r.L0 - r.Ls) / 1000; sl.value = st.L;
        var pos = [['Free', r.L0]];
        if (r.L1 && r.L1 > r.Ls && r.L1 < r.L0) pos.push(['L1', r.L1]);
        pos.push(['Solid', r.Ls]);
        $('v3dPos').innerHTML = pos.map(function (p) {
            return '<button type="button" class="v3d-btn" data-l="' + p[1] + '">' + p[0] + '</button>';
        }).join('');
    }

    function fmt(x, n) { return x.toLocaleString('en-US', { minimumFractionDigits: n, maximumFractionDigits: n }); }
    function uLen(mm) { return st.pantalla === 'mm' ? fmt(mm, 2) + ' mm' : fmt(mm / 25.4, 3) + ' in'; }
    function uF(N) { return st.pantalla === 'mm' ? fmt(N, 2) + ' N' : fmt(N / 4.4482216, 2) + ' lbf'; }
    function uT(MPa) { return st.pantalla === 'mm' ? fmt(MPa, 0) + ' MPa' : fmt(MPa * 0.14503774, 1) + ' ksi'; }

    function refrescarPanel() {
        var r = st.r, L = st.L, x = r.L0 - L, eps = (r.L0 - r.Ls) * 0.002;
        var hueco = pasoActivo(r, L) - r.d;
        $('v3dSl').value = L;
        $('v3dL').textContent = uLen(L);
        $('v3dX').textContent = uLen(x);
        $('v3dF').textContent = uF(r.k * x);
        $('v3dT').textContent = uT(r.tauSolido * x / (r.L0 - r.Ls));
        $('v3dG').textContent = hueco > r.d * 0.002 ? uLen(hueco) : '0 — coils in contact';
        var sello = L >= r.L0 - eps ? 'Free length' : L <= r.Ls + eps ? 'Solid'
            : (r.L1 && Math.abs(L - r.L1) < eps) ? 'Working height L1' : 'Compressed ' + uLen(x);
        $('v3dSello').textContent = sello;
    }

    // ------------------------------------------------------------ el enganche

    function claveDe(r) { return [r.d, r.OD, r.L0, r.Nt, r.Na, r.extremos.tipo].join('|'); }

    SC.alPintar(function (datos) {
        st.pantalla = datos.unidadPantalla || 'in';
        if (!datos.listo || !datos.contenedor || !datos.resorte) {
            st.r = null;
            if (st.ampliado) cerrar();
            return;
        }
        var r = datos.resorte, k = claveDe(r);
        if (k !== st.clave) { st.clave = k; st.L = r.L0; st.nuevo = true; st.anim = false; }
        st.r = r;
        st.L = Math.max(r.Ls, Math.min(r.L0, st.L));
        montarCasilla(datos.contenedor, datos.contenedorGrafica);
        if (st.ampliado) { prepararPanel(); dibujar(); }
    });
})();
