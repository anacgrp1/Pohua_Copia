/**
 * El tema de Pohua, puesto ANTES del primer pintado.
 *
 * Esto vive aparte de `isc-nube.js` y se carga **sin `defer`** a propósito. El
 * adaptador de almacenamiento puede llegar tarde sin que se note —guardar en
 * Neon no es algo que se vea—, pero el color no: cargado con `defer`, el
 * navegador ya había pintado la calculadora entera en blanco, y un instante
 * después se volvía oscura. Ese salto es lo que se veía al recargar.
 *
 * Un script externo síncrono en el `<head>` frena el parseo hasta que termina,
 * así que cuando el navegador pinta por primera vez el color ya está decidido.
 * Es el mismo truco que usa el `index.html` de Pohua para su propio tema, y
 * por el mismo motivo.
 *
 * LA OTRA MITAD DEL PROBLEMA ERA LA ESPECIFICIDAD. Este bloque entra justo
 * detrás de `<head>`, o sea ANTES del `<style>` de la calculadora. Con la
 * misma especificidad gana el que va último, que sería el suyo: adelantar el
 * momento no habría bastado. Por eso se marca el `<html>` con `data-nube` y
 * todas las reglas van prefijadas con `html[data-nube]`: pesan más que las
 * suyas y ganan estén donde estén, sin usar `!important` ni una sola vez.
 *
 * Sin padre al que preguntar —la calculadora abierta con doble clic en la
 * planta— no hace nada y se queda con sus colores de siempre.
 */
window.ISCTema = (function () {
    'use strict';

    var MARCA = 'data-nube';

    /**
     * El documento de Pohua, o null si no nos ha empotrado nadie.
     *
     * Se sube por la cadena de marcos hasta dar con el que lleva los tokens
     * de Pohua (--cgr-primary), no sólo un nivel: el Spring Calculator se abre
     * DENTRO de la calculadora de precios, en un segundo marco, y su padre
     * inmediato es ella —que no tiene tokens—. Mirando sólo un nivel se
     * quedaba en claro dentro de Pohua oscuro, con su inglés y sus cremas.
     */
    var saltosAPohua = 0;   // 1 = Pohua es el padre directo; 2 = hay otro marco en medio

    function padre() {
        var w = window, salto = 0;
        try {
            while (w.parent && w.parent !== w && salto < 5) {
                w = w.parent; salto++;
                // Tocar una propiedad es lo que lanza cuando el origen no es
                // el mismo; comprobar que el objeto existe no comprueba nada.
                var d = w.document;
                if (!d || d === document || !d.documentElement) continue;
                var raiz = d.documentElement;
                if (getComputedStyle(raiz).getPropertyValue('--cgr-primary').trim()) {
                    saltosAPohua = salto;
                    return d;
                }
            }
        } catch (e) {
            return null;
        }
        return null;
    }

    function variable(raiz, nombre, respaldo) {
        var v = getComputedStyle(raiz).getPropertyValue(nombre);
        return (v && v.trim()) || respaldo;
    }

    /**
     * ¿Está la calculadora regenerada con las variables del tema?
     *
     * Las dos mitades tienen que ir a la par: este script escribe --n-papel y
     * compañía, y el CSS de la calculadora tiene que usarlas. Eso lo deja
     * hecho `scripts/vendorizar_nucleo.py` al vendorizar, y de paso marca el
     * <html> con data-nube-tema.
     *
     * Si alguien actualiza este archivo pero no vuelve a pasar el script, la
     * calculadora se queda con sus blancos y sus cremas escritos a mano y aquí
     * se le pondría la tinta clara del tema oscuro encima: letra casi blanca
     * sobre papel casi blanco. La tabla del CBD se volvía ilegible.
     *
     * Se mira el ATRIBUTO y no el CSS: esto corre dentro del <head>, antes de
     * que exista el <style> de la calculadora, así que `document.styleSheets`
     * está vacío y mirar ahí diría siempre que no. La etiqueta <html>, en
     * cambio, ya está analizada.
     *
     * Sin marca se aplica sólo lo que no puede hacer daño —el marco, la barra,
     * el esquema del navegador— y la calculadora se queda con su aspecto claro
     * de siempre: feo dentro de Pohua oscuro, pero legible.
     */
    var avisado = false;

    function estaRegenerada() {
        var si = document.documentElement.hasAttribute('data-nube-tema');
        if (!si && !avisado) {
            avisado = true;
            console.error('[tema] La calculadora no se regeneró: le falta ' +
                          'data-nube-tema. Ejecuta  python ' +
                          'scripts/vendorizar_nucleo.py  y vuelve a desplegar. ' +
                          'Mientras tanto se deja en claro para poder leerla.');
        }
        return si;
    }

    function aplicar() {
        var doc = padre();
        if (!doc) return false;

        var raiz = doc.documentElement;

        /* Tres niveles, y en este orden. La calculadora es una pantalla de
           meter números durante horas: si el campo y el papel son del mismo
           tono no se ve dónde se escribe, y eso cansa mucho antes que un color
           feo. Pohua ya tiene los tres separados, así que se toman de ahí en
           vez de inventarlos.

           Los colores de MARCA no se tocan: --navy, --cyan, --orange y --green
           de la calculadora ya son exactamente los de Pohua. Lo único que la
           delataba como invitada era el chasis. */
        var t = {
            fondo:   variable(raiz, '--bg-base', '#fff'),
            panel:   variable(raiz, '--bg-card', '#F5F7FA'),
            panelVeil: variable(raiz, '--bg-card-veil', 'rgba(255,255,255,0.06)'),
            campo:   variable(raiz, '--bg-input', '#fff'),
            realce:  variable(raiz, '--bg-card-hover', '#EEF2F7'),
            linea:   variable(raiz, '--border-default', '#E2E8F0'),
            tinta:   variable(raiz, '--text-primary', '#1F2937'),
            apagado: variable(raiz, '--text-muted', '#6B7280'),
            /* Un escalón más clara que `apagado`. Las etiquetas y los rótulos
               de fila de la calculadora son mucho texto pequeño sobre panel
               oscuro, y con --text-muted se leían apagados. --text-secondary
               es el mismo gris un punto más arriba. */
            secundaria: variable(raiz, '--text-secondary', '#4B5563'),
            letra:   variable(raiz, '--font-sans', 'Inter, system-ui, sans-serif'),
            hilo:    variable(raiz, '--border-strong', 'rgba(0,0,0,.2)'),
            /* La carpintería: radio, sombra y borde de las tarjetas de Pohua.
               Es lo que hace que una tarjeta de la calculadora y una del
               Overview se lean como la misma pieza y no como dos programas
               pegados. */
            borde:   variable(raiz, '--border-subtle', 'rgba(15,23,42,.08)'),
            radio:   variable(raiz, '--radius-lg', '16px'),
            sombra:  variable(raiz, '--shadow-sm', '0 1px 2px rgba(15,23,42,.06)')
        };

        /* Los cuatro avisos, y cada uno con DOS colores, porque Pohua los tiene
           así y por un motivo:

             · el tono de marca (--cgr-*), que no cambia nunca. Es el que tiñe
               fondos y líneas: un 14 % de verde vivo sobre el papel del tema
               da un verde suave en claro y en oscuro, y es exactamente lo que
               hace Pohua con --color-success-bg.

             · el semántico (--color-*), que Pohua oscurece en claro para que
               un texto de 12 px se lea sobre papel. Ese es el de la TINTA.

           Teñir con el semántico era el error: en claro es un oliva oscuro
           (#525a12), y mezclado con el panel no daba un verde pálido sino un
           gris sucio. El fondo se tiñe con el vivo; la letra se escribe con el
           que el tema ya dejó legible. */
        var tono = {
            ok:   variable(raiz, '--cgr-verde',     '#a4ae2d'),
            avi:  variable(raiz, '--cgr-naranja',   '#d67c2f'),
            mal:  variable(raiz, '--cgr-accent',    '#b31671'),
            info: variable(raiz, '--cgr-azul-frio', '#148ec2')
        };
        var letra = {
            ok:   variable(raiz, '--color-success', '#a4ae2d'),
            avi:  variable(raiz, '--color-warning', '#d67c2f'),
            mal:  variable(raiz, '--color-error',   '#b31671'),
            info: variable(raiz, '--color-info',    '#148ec2')
        };

        /* Un aviso dentro de la calculadora son tres cosas: un fondo apenas
           teñido, una línea que lo cierra y la tinta del texto. Fondo y línea
           se mezclan con el PAPEL del tema, así que en oscuro salen oscuros y
           en claro claros sin escribir dos paletas. */
        function fondo(color, pct) {
            return 'color-mix(in srgb,' + color + ' ' + pct + '%,' + t.panel + ')';
        }

        /* El esquema del navegador, no sólo los colores nuestros.
           De él dependen las piezas que pinta el sistema y que ninguna hoja de
           estilos alcanza: la barra de desplazamiento, el calendario del campo
           de fecha, la lista desplegada de un <select>. Sin esto, la barra del
           marco salía BLANCA sobre el fondo oscuro y se veía como una franja
           encendida al borde de la pantalla. */
        var regen = estaRegenerada();

        var tema = raiz.getAttribute('data-tema');
        if (tema !== 'light' && tema !== 'dark') {
            tema = (doc.defaultView && doc.defaultView.matchMedia &&
                    doc.defaultView.matchMedia('(prefers-color-scheme: light)').matches)
                   ? 'light' : 'dark';
        }

        document.documentElement.setAttribute(MARCA, '');

        var h = 'html[' + MARCA + '] ';
        var css = document.getElementById('nube-tema');
        if (!css) {
            css = document.createElement('style');
            css.id = 'nube-tema';
            document.head.appendChild(css);
        }

        /* Las cinco variables del chasis, y luego las pocas reglas que llevaban
           un blanco escrito a mano y no pasaban por variable.

           No se tocan los blancos que son TEXTO sobre un color de marca —los
           botones de guardar y aprobar, las cabeceras azules—: ahí el blanco es
           lo correcto y cambiarlo los dejaría ilegibles. */
        css.textContent = [
            'html[', MARCA, ']{',
            /* El chasis: los nombres que `vendorizar_nucleo.py` dejó escritos
               en el CSS de las calculadoras en lugar de los blancos y grises
               originales. */
            '  --n-papel:', t.panel, ';--n-sutil:', t.fondo, ';',
            '  --n-linea:', t.linea, ';--n-tinta:', t.tinta, ';',
            '  --n-apagado:', t.apagado, ';',
            /* Los avisos, los tres tonos de cada uno. */
            '  --n-ok-fondo:', fondo(tono.ok, 14), ';',
            '  --n-ok-linea:', fondo(tono.ok, 38), ';',
            '  --n-ok-tinta:', letra.ok, ';',
            '  --n-avi-fondo:', fondo(tono.avi, 14), ';',
            '  --n-avi-linea:', fondo(tono.avi, 38), ';',
            '  --n-avi-tinta:', letra.avi, ';',
            '  --n-mal-fondo:', fondo(tono.mal, 14), ';',
            '  --n-mal-linea:', fondo(tono.mal, 38), ';',
            '  --n-mal-tinta:', letra.mal, ';',
            '  --n-info-fondo:', fondo(tono.info, 14), ';',
            '  --n-info-linea:', fondo(tono.info, 38), ';',
            '  --n-info-tinta:', letra.info, ';',
            /* Y el tono pleno, para los rellenos: la barra llena de una
               gráfica no es un aviso teñido, es una superficie de color. */
            /* El azul de marca cuando es LETRA, no fondo.
               El navy puesto sobre el panel oscuro da 1.4:1 y desaparece; el
               cian, 3.96, por debajo del 4.5 que pide un texto de 13 px. Se
               mezcla con la tinta del tema —que aclara en oscuro y oscurece en
               claro— y queda en 6.7 y 5.4, con el azul todavía reconocible.
               Como fondo, la marca no se toca: eso lo separa
               `vendorizar_nucleo.py`, que sí ve la propiedad. */
            '  --n-marca-tinta:color-mix(in srgb,', tono.info, ' 60%,', t.tinta, ');',
            '  --n-ok-solido:', tono.ok, ';--n-avi-solido:', tono.avi, ';',
            '  --n-mal-solido:', tono.mal, ';--n-info-solido:', tono.info, ';',
            /* Y las variables que la calculadora declara en su propio :root.
               Se redefinen aquí, no en el HTML generado: así el `:root` de la
               calculadora sigue siendo el que trae el núcleo y esta hoja es el
               único sitio donde vive la adaptación.

               --navy, --cyan, --orange, --green y --accent* se quedan: son los
               colores de marca, y son los mismos que los de Pohua. */
            /* El chasis propio de la calculadora —papel, líneas y tinta— sólo
               se toca si está regenerada. Sin regenerar sus fondos siguen
               siendo blancos escritos a mano, y darle esta tinta clara la deja
               ilegible: letra casi blanca sobre papel casi blanco. */
            !regen ? '' : [
            '  --bg:transparent;',
            '  --panel:', t.panel, ';--line:', t.linea, ';',
            '  --line-strong:', t.hilo, ';',
            '  --ink:', t.tinta, ';--muted:', t.secundaria, ';--ink-soft:', t.secundaria, ';'
            ].join(''),
            '  --ok:', letra.ok, ';--ok-bg:', fondo(tono.ok, 14), ';',
            '  --crit:', letra.mal, ';--crit-bg:', fondo(tono.mal, 14), ';',
            '  --info:', letra.info, ';--info-bg:', fondo(tono.info, 14), ';',
            '  --accent-soft:', fondo(tono.info, 14), ';',
            '  --gold:', fondo(tono.avi, 22), ';',
            '  --goldline:', fondo(tono.avi, 45), ';',
            !regen ? '}' : ['  background:transparent !important;color:', t.tinta, ';}'].join(''),
            'html, html[', MARCA, ']{background:transparent !important}',
            'body, html body{font-family:', t.letra, ';background:transparent !important;color:', t.tinta, '}',
            'main, html main{background:transparent !important;max-width:none;margin:0;padding:0}',
            !regen ? '' : [
            h, '.card,', h, '#banner{background:', t.panelVeil, ' !important;border-color:', t.linea, ';',
            '  backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}',
            h, 'input,', h, 'select,', h, 'textarea{background:', t.campo, ';',
            '  color:', t.tinta, ';border-color:', t.linea, '}',
            h, 'input::placeholder,', h, 'textarea::placeholder{color:', t.apagado, '}',
            h, '.card{border-radius:', t.radio, ';border:1px solid ', t.borde, ';',
            '  box-shadow:', t.sombra, '}',
            h, '.card>header{border-radius:calc(', t.radio, ' - 1px) calc(',
            t.radio, ' - 1px) 0 0}',
            'html[', MARCA, ']{--r:', t.radio, ';--sh:', t.sombra, '}'
            ].join(''),
            /* th NO se toca: `th{background:var(--navy);color:#fff}` es una
               cabecera de marca, la misma que lleva Pohua en sus tablas. */
            !regen ? '' : [h, 'td{border-color:', t.linea, '}'].join(''),
            /* .hbtn y .dbbtn NO se tocan: van sobre la cabecera navy, con
               rgba(255,255,255,.25) de fondo. Ahí el blanco translúcido es lo
               correcto en los dos temas; ponerles el papel del tema los
               arrancaba de la cabecera y los dejaba flotando. */
            !regen ? '' : [h, '#rolechip,', h, '#pntabs .add{',
            '  background:', t.panel, ';color:', t.tinta, ';border-color:', t.linea, '}'].join(''),
            /* La barra de estado, con los colores de las tarjetas del Overview.
               ------------------------------------------------------------
               El mismo oliva de "Last 7 days" cuando el guardado llegó a Neon,
               y el mismo naranja de "Waiting for you" cuando no. Son los tonos
               de marca sin retocar, los mismos que llevan los chips de icono.

               La letra va OSCURA, no blanca. Sobre estos tonos el blanco no da
               la talla: 2,4:1 sobre el oliva y 3,1:1 sobre el naranja, cuando
               una frase de 13 px necesita 4,5:1. La tinta de Pohua sube a 7,4
               y a 5,8. Los chips de los KPI sí llevan un icono blanco, pero un
               icono aguanta un contraste que una frase no.

               Y el color no cambia con el tema: es un bloque de marca, como la
               cabecera navy. En claro y en oscuro es el mismo verde. */
            /* La barra de arriba: transparente, sin letrero verde, dejando sólo Quote y Spring Calc */
            h, '#sharebar, #sharebar{background:transparent !important;border:none !important;padding:0 !important;box-shadow:none !important;',
            '  justify-content:flex-start;margin-bottom:12px;display:flex;align-items:center;gap:10px}',
            h, '#sharebar.ok, #sharebar.ok{background:transparent !important;border:none !important;box-shadow:none !important}',
            h, '#sharebar-msg, #sharebar-msg{display:none !important}',
            h, '#sharebar.nube-aviso #sharebar-msg{display:inline-block;flex:0 1 auto;',
            '  min-width:0;background:', tono.avi, ';color:#0f172a;font-weight:600;',
            '  font-size:.78rem;padding:5px 11px;border-radius:7px;',
            '  border:1px solid color-mix(in srgb,', tono.avi, ' 72%,#0f172a)}',
            h, '.nube-herramientas{display:flex;align-items:center;gap:6px;flex:0 0 auto}',
            h, '.nube-herramientas #viewtabs button,',
            h, '.nube-herramientas .topbtn{background:', t.panel, ';',
            '  color:', t.tinta, ';border:1px solid ', t.linea, ';',
            '  padding:6px 14px;border-radius:7px;font-weight:700;font-size:.82rem;',
            '  cursor:pointer;line-height:1.4}',
            h, '.nube-herramientas #viewtabs button:hover,',
            h, '.nube-herramientas .topbtn:hover{border-color:var(--cyan);color:', t.tinta, '}',
            h, '.nube-herramientas #viewtabs button.on{background:var(--navy);color:#fff;',
            '  border-color:var(--navy)}',
            h, '.nube-herramientas #viewtabs button:not([data-v="quote"]){display:none !important}',
            h, '#topbar #viewtabs button:not([data-v="quote"]){display:none !important}',
            h, '#topbar #clock, #topbar #btn-settings, #topbar #btn-help-global, #topbar #userchip{display:none !important}',
            '#botbar,', h, '#botbar{display:none !important}',
            'body,', h, 'body{padding-bottom:0 !important}',

            /* --- El teléfono y pantallas móviles (≤ 820px) ----------------
               Despejar todo el quoter para que no se vea amontonado:
               - En Spring Calc: layout vertical de 1 columna (diagrama 3D
                 completo y tabla legible con desplazamiento).
               - En la calculadora principal: cards, alertas y botones
                 con respiro y touch-friendly. */
            '@media (max-width:820px){',
            h, '.grid,', h, '.grid.g2,', h, '.grid.g3,', h, '.grid.g4,',
            h, '.grid.g5,', h, '.grid.g6{',
            '  grid-template-columns:repeat(auto-fit,minmax(140px,1fr)) !important;gap:8px !important}',

            h, '.grid label{display:block;overflow:hidden;',
            '  text-overflow:ellipsis;font-size:.72rem;line-height:1.25}',
            h, 'input,', h, 'select,', h, 'textarea{width:100%;min-width:0;',
            '  font-size:15px;min-height:36px;padding:6px 8px}',

            h, '.card>header{flex-wrap:wrap;row-gap:6px;font-size:.85rem;padding:8px 12px}',
            h, '.card>header .sp{flex:1 0 100%;height:0}',
            h, '.card>.bd{padding:10px 12px}',

            /* Spring Engineering Calculator V2 en teléfono */
            'html,body{height:auto !important;min-height:100% !important;overflow-y:auto !important;overflow-x:hidden !important}',
            '#appwrap{height:auto !important;overflow:visible !important;padding:6px !important}',
            '.sheet{display:flex !important;flex-direction:column !important;height:auto !important;',
            '  min-height:100% !important;overflow:visible !important;box-shadow:none !important}',
            '.ds-info{display:grid !important;grid-template-columns:repeat(2,1fr) !important;gap:4px !important;padding:6px !important}',
            '.fcell{min-width:0 !important;padding:6px 8px !important;border-right:1px solid var(--line) !important}',
            '.fcell .k{font-size:9px !important}',
            '.fcell .v{font-size:13px !important}',
            '.ds-left{width:100% !important;border-right:none !important;border-bottom:2px solid var(--line-strong) !important;',
            '  overflow:visible !important;min-height:auto !important}',
            '.ds-tblwrap{overflow-x:auto !important;-webkit-overflow-scrolling:touch !important;width:100% !important}',
            'table.dst{width:100% !important;min-width:320px !important}',
            'table.dst td,table.dst th{padding:6px 8px !important;font-size:11.5px !important}',
            '.ds-right{width:100% !important;overflow:visible !important;min-height:auto !important}',
            '.diagram{width:100% !important;padding:10px 0 !important;min-height:200px !important}',
            '.diagram svg,.diagram canvas{max-width:100% !important;height:auto !important}',
            '.vdt{padding:12px 14px !important;margin:8px 0 !important;font-size:12.5px !important;border-radius:8px !important}',
            '.score-card{flex-direction:column !important;align-items:flex-start !important;gap:8px !important}',

            /* Modal Spring Calc */
            '#scwrap{padding:0 !important;inset:0 !important}',
            '#scbox{width:100vw !important;height:100dvh !important;max-height:100dvh !important;border-radius:0 !important}',
            '#scbox>header{height:48px !important;padding:0 14px !important;font-size:14px !important}',
            '#sc-x{width:40px !important;height:40px !important;font-size:24px !important;display:flex !important;align-items:center !important;justify-content:center !important}',

            /* Alertas y avisos de cotización */
            '.verdictbox{flex-direction:column !important;align-items:flex-start !important;gap:8px !important;padding:12px 14px !important;border-radius:8px !important}',
            '.verdictbox .vtag{font-size:.8rem !important;padding:4px 10px !important}',
            '.verdictbox .vbody{font-size:.85rem !important;line-height:1.5 !important}',
            '.dwwarn{padding:12px 14px !important;margin-bottom:12px !important;border-radius:8px !important}',
            '.dwwarn .wline{margin:5px 0 !important;line-height:1.45 !important;font-size:.82rem !important}',
            '.dwfeas .row{padding:6px 0 !important}',

            /* Anchuras y scroll */
            h, '.hrow>*,', h, '.grid>*,', h, '.card,', h, '.card>*{min-width:0}',
            h, '.tbl-wrap,', h, '.nube-ancha{max-width:100%;min-width:0}',
            h, 'html,', h, 'body{overflow-x:hidden;max-width:100%}',
            h, 'main{padding:8px 8px}',
            '}',

            /* La caja que `isc-nube.js` pone alrededor de cada tabla. Va fuera
               del media query: una tabla de seis columnas tampoco cabe en una
               ventana de escritorio a medio ancho, y ahí el problema es el
               mismo. */
            h, '.nube-ancha{overflow-x:auto;max-width:100%;',
            '  -webkit-overflow-scrolling:touch}',
            h, '.nube-ancha table{min-width:max-content}',

            /* El esquema del sistema y la barra, iguales a las de Pohua: finas
               y discretas, no la barra gorda por defecto del navegador. */
            'html[', MARCA, ']{color-scheme:', tema, '}',
            h, '::-webkit-scrollbar{width:6px;height:6px}',
            h, '::-webkit-scrollbar-track{background:transparent}',
            h, '::-webkit-scrollbar-thumb{background:', t.hilo, ';border-radius:3px}',
            h, '::-webkit-scrollbar-thumb:hover{background:', t.apagado, '}'
        ].join('');
        return true;
    }

    /**
     * Y que siga al interruptor de Pohua.
     *
     * Se observa `data-tema` en su <html> y se vuelve a leer todo. No hace
     * falta saber a qué tema cambió, y por eso un tercer tema algún día
     * funcionaría sin tocar nada de aquí.
     *
     * El observador se pone cuando haya <body>: en el <head> el documento aún
     * no está listo para escuchar nada.
     */
    function seguir() {
        var doc = padre();
        if (!doc) return;
        var poner = function () {
            new MutationObserver(aplicar).observe(doc.documentElement,
                { attributes: true, attributeFilter: ['data-tema'] });
        };
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', poner);
        } else {
            poner();
        }
    }

    // Ahora mismo, sin esperar a nada: es lo único que tiene que pasar antes
    // de que el navegador pinte.
    aplicar();
    seguir();

    return { aplicar: aplicar, seguir: seguir };
})();
