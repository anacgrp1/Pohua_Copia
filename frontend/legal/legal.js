/**
 * La página de información legal: aviso de privacidad, cookies y términos.
 *
 * Pinta el documento pedido (?doc=privacidad|cookies|terminos) en el idioma
 * pedido (?lang=, o el que la persona tenga puesto en Pohua), rellenando los
 * datos del responsable desde `responsable.js`. Lo que falte se enseña
 * marcado como pendiente: un aviso de privacidad sin la identidad del
 * responsable no cumple, y es mejor que se vea que taparlo.
 *
 * Los textos son del equipo (contenido.*.js), no de los usuarios, así que
 * pueden llevar <b> y enlaces. Los DATOS del responsable sí se escapan.
 */
(function () {
    'use strict';

    var DOCS = ['privacidad', 'cookies', 'terminos'];
    var CONF = window.POHUA_LEGAL || {};
    var TEXTOS = window.POHUA_LEGAL_TEXTOS || {};

    // Lo que Pohua guarda en el navegador por preferencia del usuario. La
    // sesión y la copia de la calculadora NO van aquí: borrarlas saca a la
    // persona o le hace perder trabajo, y eso lo decide ella en su navegador.
    var PREFERENCIAS = ['cgr_correo', 'cgr-tema', 'cgr-idioma', 'cgr-sonido',
                        'cgr-reloj', 'cgr-instalar-oculto', 'cgr-legal'];

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function parametro(nombre) {
        try { return new URLSearchParams(location.search).get(nombre); } catch (e) { return null; }
    }

    function idiomaInicial() {
        var pedido = parametro('lang');
        if (pedido && TEXTOS[pedido]) return pedido;
        try {
            var guardado = localStorage.getItem('cgr-idioma');
            if (guardado && TEXTOS[guardado]) return guardado;
        } catch (e) {}
        var nav = String(navigator.language || 'es').slice(0, 2);
        return TEXTOS[nav] ? nav : 'es';
    }

    var estado = {
        idioma: idiomaInicial(),
        doc: DOCS.indexOf(parametro('doc')) >= 0 ? parametro('doc') : 'privacidad',
        huecos: 0,
    };

    function pendiente(que) {
        estado.huecos++;
        var T = TEXTOS[estado.idioma].ui;
        return '<mark class="lg-pendiente">[' + esc(T.pendiente) + (que ? ': ' + esc(que) : '') + ']</mark>';
    }

    function dato(valor, que) {
        return valor ? esc(valor) : pendiente(que);
    }

    function responsables() {
        var lista = CONF.responsables || [];
        if (!lista.length) return pendiente('responsables');
        return '<ul class="lg-responsables">' + lista.map(function (r) {
            return '<li><b>' + dato(r.razonSocial, 'razón social') + '</b> — ' +
                   esc(r.sede || '') + '<br>' + dato(r.domicilio, 'domicilio') +
                   (r.rfcOIdentificador ? '<br>' + esc(r.rfcOIdentificador) : '') + '</li>';
        }).join('') + '</ul>';
    }

    function correo() {
        if (!CONF.correoPrivacidad) return pendiente('correo de privacidad');
        var c = esc(CONF.correoPrivacidad);
        return '<a href="mailto:' + c + '">' + c + '</a>';
    }

    function tabla(filas) {
        var T = TEXTOS[estado.idioma].ui;
        return '<div class="lg-tabla-caja"><table class="lg-tabla"><thead><tr>' +
            '<th>' + esc(T.tablaNombre) + '</th><th>' + esc(T.tablaTipo) + '</th>' +
            '<th>' + esc(T.tablaPara) + '</th><th>' + esc(T.tablaDura) + '</th>' +
            '</tr></thead><tbody>' + (filas || []).map(function (f) {
                return '<tr><td><code>' + esc(f[0]) + '</code></td><td>' + esc(f[1]) +
                       '</td><td>' + esc(f[2]) + '</td><td>' + esc(f[3]) + '</td></tr>';
            }).join('') + '</tbody></table></div>';
    }

    function rellenar(texto, docTextos) {
        var T = TEXTOS[estado.idioma].ui;
        return String(texto)
            .replace(/\{\{responsables\}\}/g, responsables)
            .replace(/\{\{correo\}\}/g, correo)
            .replace(/\{\{departamento\}\}/g, function () {
                return dato(CONF.departamentoDatos, 'departamento de datos personales');
            })
            .replace(/\{\{dpo\}\}/g, function () {
                // Sin delegado designado no es un hueco: el RGPD no siempre lo exige.
                return CONF.delegadoProteccionDatos ? esc(CONF.delegadoProteccionDatos) : '—';
            })
            .replace(/\{\{jurisdiccion\}\}/g, function () {
                return dato(CONF.jurisdiccion, 'jurisdicción');
            })
            .replace(/\{\{version\}\}/g, esc(CONF.VERSION || ''))
            .replace(/\{\{tabla\}\}/g, function () { return tabla(docTextos.tabla); })
            .replace(/\{\{botonBorrar\}\}/g, function () {
                return '<button type="button" class="lg-boton" id="lgBorrar">' +
                       esc(T.borrarPreferencias) + '</button> <span id="lgBorrado" role="status"></span>';
            });
    }

    function bloque(b, docTextos) {
        if (Array.isArray(b)) {
            return '<ul>' + b.map(function (li) {
                return '<li>' + rellenar(li, docTextos) + '</li>';
            }).join('') + '</ul>';
        }
        var html = rellenar(b, docTextos);
        return /^<(ul|div|button)/.test(html) ? html : '<p>' + html + '</p>';
    }

    function pintar() {
        var todo = TEXTOS[estado.idioma] || TEXTOS.es;
        var T = todo.ui;
        var d = todo[estado.doc];
        estado.huecos = 0;

        document.documentElement.lang = estado.idioma;
        document.title = 'Pohua · ' + d.titulo;
        document.getElementById('lgIdioma').value = estado.idioma;
        document.getElementById('lgImprimir').textContent = T.imprimir;
        document.getElementById('lgVolver').title = T.volver;

        document.getElementById('lgPestanas').innerHTML = DOCS.map(function (k) {
            var activa = k === estado.doc;
            return '<a role="tab" href="?doc=' + k + '&lang=' + estado.idioma + '" data-doc="' + k +
                   '" aria-selected="' + activa + '" class="' + (activa ? 'activa' : '') + '">' +
                   esc(T[k]) + '</a>';
        }).join('');

        var cuerpo = d.secciones.map(function (s) {
            return '<section><h2>' + esc(s.t) + '</h2>' +
                   s.b.map(function (b) { return bloque(b, d); }).join('') + '</section>';
        }).join('');

        var html = '<h1>' + esc(d.titulo) + '</h1>' +
                   '<p class="lg-version">' + esc(T.version) + ' ' + esc(CONF.VERSION || '') + '</p>' +
                   '<p class="lg-intro">' + rellenar(d.intro, d) + '</p>' + cuerpo;
        var doc = document.getElementById('lgDoc');
        doc.innerHTML = html;
        if (estado.huecos) {
            doc.insertAdjacentHTML('afterbegin',
                '<div class="lg-alerta" role="alert">' + esc(T.avisoPendiente) + '</div>');
        }

        // Los enlaces entre documentos no recargan la página.
        doc.querySelectorAll('a[href^="?doc="]').forEach(function (a) {
            a.href = a.getAttribute('href') + '&lang=' + estado.idioma;
        });

        var borrar = document.getElementById('lgBorrar');
        if (borrar) borrar.addEventListener('click', function () {
            PREFERENCIAS.forEach(function (k) { try { localStorage.removeItem(k); } catch (e) {} });
            document.getElementById('lgBorrado').textContent = T.borradas;
        });
    }

    function ir(doc, idioma) {
        if (doc) estado.doc = doc;
        if (idioma) estado.idioma = idioma;
        try {
            history.replaceState(null, '', '?doc=' + estado.doc + '&lang=' + estado.idioma);
        } catch (e) {}
        pintar();
        window.scrollTo(0, 0);
    }

    document.getElementById('lgPestanas').addEventListener('click', function (ev) {
        var a = ev.target.closest('[data-doc]');
        if (!a) return;
        ev.preventDefault();
        ir(a.getAttribute('data-doc'));
    });
    document.getElementById('lgDoc').addEventListener('click', function (ev) {
        var a = ev.target.closest('a[href^="?doc="]');
        if (!a) return;
        ev.preventDefault();
        var doc = new URLSearchParams(a.getAttribute('href').slice(1)).get('doc');
        ir(doc);
    });
    document.getElementById('lgIdioma').addEventListener('change', function (ev) {
        ir(null, ev.target.value);
    });
    document.getElementById('lgImprimir').addEventListener('click', function () { window.print(); });

    pintar();
})();
