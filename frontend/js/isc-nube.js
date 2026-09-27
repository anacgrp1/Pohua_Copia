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

    // ------------------------------------------ mirar un caso ya dictaminado

    /*
     * Un RFQ aprobado o declinado se abre para MIRARLO, no para seguir
     * trabajándolo: ya se decidió. Pero la hoja es una sola, y cargarlo encima
     * pisa el borrador de quien estuviera calculando otra cosa — que es
     * exactamente la confusión entre cálculos que hay que evitar.
     *
     * Así que en consulta el borrador de trabajo se guarda aparte ANTES de
     * cargar nada, y se devuelve al salir. La hoja queda como estaba, sin que
     * nadie tenga que acordarse de guardar.
     *
     * Vive en memoria de la página, no en el almacenamiento: si alguien
     * recarga en mitad de una consulta, lo que se conserva es el borrador
     * guardado en disco, que es el de trabajo. Perder la consulta no cuesta
     * nada; perder el borrador, sí.
     */
    var borradorGuardado = null;     // null = no hay ninguna consulta abierta

    function enConsulta() { return borradorGuardado !== null; }

    function guardarBorrador() {
        if (borradorGuardado !== null) return;   // ya había una consulta
        try {
            borradorGuardado = JSON.stringify(local.draft || null);
        } catch (e) {
            // Si no se puede copiar, NO se entra en consulta: mejor no
            // enseñar el caso viejo que enseñarlo a cambio de perder trabajo.
            borradorGuardado = null;
            console.warn('[nube] No se pudo apartar el borrador: ' + e.message);
        }
    }

    function devolverBorrador() {
        if (borradorGuardado === null) return false;
        try {
            local.draft = JSON.parse(borradorGuardado);
            borradorGuardado = null;
            if (typeof saveLocal === 'function') saveLocal();
            intentar(function () {
                if (typeof renderQuote === 'function') renderQuote();
            }, 'repintar al volver de la consulta');
            return true;
        } catch (e) {
            console.warn('[nube] No se pudo devolver el borrador: ' + e.message);
            borradorGuardado = null;
            return false;
        }
    }

    // ------------------------------------------ la hoja es del RFQ que se abre

    /*
     * La calculadora SIEMPRE abre limpia. Sólo se llena al abrir un RFQ, y se
     * vuelve a limpiar al salir de él.
     *
     * Antes el borrador vivía en este navegador y se quedaba puesto: entrabas
     * a Quoting a cotizar otra cosa y te encontrabas el último RFQ que alguien
     * abrió, con su cliente, sus notas y su número. Así es como se mezclan dos
     * cotizaciones.
     *
     * Lo escrito en un RFQ no se pierde al limpiar: se guarda en el documento
     * de Neon (`shared.drafts`, el mismo sitio donde la calculadora ya sube
     * sus borradores) y vuelve al abrir ESE RFQ otra vez, desde cualquier
     * computadora. Se olvida cuando el RFQ se dictamina —aprobado o
     * declinado—: ya no hay nada que seguir escribiendo.
     *
     * Una cotización tecleada a mano, sin RFQ y sin guardar en el Quote Log,
     * no se tira nunca sin preguntar: es trabajo de una persona que no está
     * en ningún otro sitio.
     */
    var docListo = null;     // se resuelve cuando el documento de Neon ya manda

    /** Lo que necesita `shared.drafts` espera a que llegue el documento de
        Neon: escrito antes, `adoptar()` lo pisaría al reemplazar `shared`. */
    function cuandoDoc(fn) {
        (docListo || Promise.resolve()).then(fn, fn);
    }

    function aPohuaDirecto(mensaje) {
        try { window.parent.postMessage(mensaje, '*'); } catch (e) {}
    }

    function compartir() {
        if (typeof queueShared === 'function') queueShared();
        else if (typeof SFS !== 'undefined' && SFS.write) SFS.write();
    }

    function esDeRfq(q) { return !!(q && q.pohuaRfq && !q.pohuaConsulta); }

    function trabajoSuelto(q) {
        return !!q && !q.pohuaRfq && !q.number &&
               typeof quoteVirgen === 'function' && !quoteVirgen(q);
    }

    /** Lo escrito en un RFQ, al documento compartido. */
    function archivar(q) {
        if (!esDeRfq(q) || typeof shared === 'undefined' || !shared) return;
        try {
            shared.drafts = shared.drafts || {};
            shared.drafts[q.id] = {
                guardadoEn: (typeof nowStr === 'function') ? nowStr() : new Date().toISOString(),
                guardadoPor: (typeof CUR !== 'undefined' && CUR) ? CUR.email : '\u2014',
                pns: (q.pns || []).map(function (p) { return p.pn; }).filter(Boolean).join(', '),
                pohuaRfq: q.pohuaRfq,
                data: JSON.parse(JSON.stringify(q))
            };
            compartir();
        } catch (e) {
            console.warn('[nube] No se pudo guardar lo escrito en ' + q.pohuaRfq + ': ' + e.message);
        }
    }

    /** El borrador más reciente de un RFQ, o null. */
    function guardadoDe(rfqId) {
        var d = (typeof shared !== 'undefined' && shared && shared.drafts) || {};
        var mejor = null;
        Object.keys(d).forEach(function (k) {
            var e = d[k];
            if (!e || !e.data || e.data.pohuaRfq !== rfqId) return;
            if (hojaVacia(e.data)) return;      // un guardado vacío no es trabajo
            if (!mejor || String(e.guardadoEn || '') > String(mejor.guardadoEn || '')) mejor = e;
        });
        return mejor ? mejor.data : null;
    }

    function rfqsGuardados() {
        var d = (typeof shared !== 'undefined' && shared && shared.drafts) || {};
        var ids = [];
        Object.keys(d).forEach(function (k) {
            var r = d[k] && d[k].data && d[k].data.pohuaRfq;
            if (r && ids.indexOf(r) < 0) ids.push(r);
        });
        return ids;
    }

    // ------------------------------------- lo cotizado, de vuelta al RFQ

    /*
     * El camino de vuelta de «Open full quote».
     *
     * El PM corrige aquí lo que el sistema costeó al entrar el correo —el
     * material, el precio del alambre, la máquina, las cantidades, el
     * margen— y al volver a la ventana de revisión tiene que ver ESOS
     * números, y son esos los que salen en la oferta cuando aprueba. Hasta
     * ahora lo escrito aquí se quedaba en la hoja: la ventana volvía a
     * costear con lo que el sistema tenía.
     *
     * Se manda el PN entero tal como quedó (la forma de `blankPn()`) y el
     * resultado del motor tal como lo calculó ESTA calculadora, con sus
     * parámetros y sus bases: así la ventana enseña exactamente lo que el
     * PM vio, no un cálculo parecido hecho en otro sitio. Sale cada vez que
     * la hoja guarda el borrador de un RFQ (con un respiro, para no mandar
     * una copia por cada tecla) y cuando Pohua lo pide al pulsar «Volver a
     * revisión».
     */
    var publicarTimer = null;

    function cotizacionParaPohua(q) {
        if (!esDeRfq(q) || !q.pns || !q.pns.length) return null;
        var pn = q.pns[q.activePn || 0] || q.pns[0];
        if (!pn) return null;
        var r = null;
        try {
            r = (typeof computeFor === 'function') ? computeFor(pn, q) : null;
        } catch (e) {
            console.warn('[nube] No se pudo costear el PN para Pohua: ' + e.message);
            return null;
        }
        if (!r || !r.tiers || !r.tiers.some(function (x) { return !!x; })) return null;
        var contribution = (q.contribution === null || q.contribution === undefined)
            ? ((typeof shared !== 'undefined' && shared && shared.params)
               ? shared.params.contribution : null)
            : q.contribution;
        var cab = q.header || {};
        var mat = null;
        try {
            var leyenda = (shared && shared.dbs && shared.dbs.materialLegend) || {};
            var code = pn.material && pn.material.code;
            mat = (code && leyenda[code]) ? String(leyenda[code]) : null;
        } catch (e) { mat = null; }
        return {
            rfq_id: q.pohuaRfq,
            pn: JSON.parse(JSON.stringify(pn)),
            resultado: { tiers: r.tiers, flags: r.flags || [] },
            contribution: (contribution === null || contribution === undefined) ? null : Number(contribution),
            cabecera: {
                numero: q.number || null,
                representante: cab.rep || null,
                plazo_dias: (cab.leadDays !== undefined) ? cab.leadDays : null,
                condiciones_pago: cab.terms || null,
                cliente: cab.customerCode || null,
                fecha: cab.rfqDate || null
            },
            material_nombre: mat,
            // La versión escogida en la ventana con la que se cargó esta hoja:
            // si allí se escogió otra después, el servidor no guarda esto.
            restauracion: q.pohuaRestauracion || null
        };
    }

    /*
     * Abrir no es corregir. La hoja guarda sola al cargarse, y sin esto sólo
     * con abrir la calculadora el RFQ pasaba a «Cotizado por el PM» con los
     * mismos números del sistema. Al cargar desde Pohua se apunta cómo quedó
     * la hoja (`pohuaBase`) y sólo se manda cuando el PM cambia algo.
     */
    function firmaDeLaHoja(q) {
        try {
            var pn = q.pns[q.activePn || 0] || q.pns[0];
            return JSON.stringify({ pn: pn, c: q.contribution });
        } catch (e) { return ''; }
    }

    function marcarBase(q) {
        if (!q) return;
        q.pohuaBase = 'pendiente';
        q.pohuaPublicado = null;
        setTimeout(function () {
            var actual = (typeof Q === 'function') ? Q() : null;
            if (actual && actual === q && q.pohuaBase === 'pendiente') {
                q.pohuaBase = firmaDeLaHoja(q);
            }
        }, 600);
    }

    function sinCambios(q) {
        if (!q || q.pohuaBase === undefined || q.pohuaBase === null) return false;
        if (q.pohuaBase === 'pendiente') { q.pohuaBase = firmaDeLaHoja(q); return true; }
        if (q.pohuaBase === firmaDeLaHoja(q)) return true;
        q.pohuaBase = null;                 // ya cambió: desde aquí todo cuenta
        return false;
    }

    function publicarCotizacion(motivo) {
        var q = (typeof Q === 'function') ? Q() : null;
        if (sinCambios(q)) return false;
        // Un guardado automático igual al último que se mandó no se repite:
        // la hoja guarda sola por muchos motivos (subir el borrador, repintar)
        // y cada copia repetida era una escritura más. «Volver» sí sale
        // siempre: es el que fija la versión.
        var firma = firmaDeLaHoja(q);
        if (motivo !== 'volver' && q.pohuaPublicado === firma) return false;
        var carga = cotizacionParaPohua(q);
        if (!carga) return false;
        q.pohuaPublicado = firma;
        carga.source = 'isc-nube';
        carga.tipo = 'rfq-cotizado';
        carga.motivo = motivo || 'guardado';
        aPohuaDirecto(carga);
        return true;
    }

    function publicarPronto() {
        if (publicarTimer) clearTimeout(publicarTimer);
        publicarTimer = setTimeout(function () {
            publicarTimer = null;
            publicarCotizacion('guardado');
        }, 700);
    }

    /** Cada guardado del borrador de un RFQ avisa a Pohua de lo cotizado. */
    function vigilarGuardado() {
        if (typeof window.saveLocal !== 'function' || window.saveLocal.nubeVigilado) return;
        var original = window.saveLocal;
        var envuelto = function () {
            var r = original.apply(this, arguments);
            try { publicarPronto(); } catch (e) {}
            return r;
        };
        envuelto.nubeVigilado = true;
        window.saveLocal = envuelto;
    }

    function repintar() {
        intentar(function () { if (typeof renderQuote === 'function') renderQuote(); }, 'pintar la hoja');
        intentar(function () { if (typeof updateSummaryTab === 'function') updateSummaryTab(); }, 'refrescar el resumen');
    }

    function dejarEnBlanco() {
        var viejo = Q();
        if (viejo && typeof shared !== 'undefined' && shared && shared.locks && shared.locks[viejo.id]) {
            delete shared.locks[viejo.id];
            compartir();
        }
        local.draft = blankQuote();
        if (typeof saveLocal === 'function') saveLocal();
        repintar();
    }

    /** Guarda lo del RFQ abierto y deja la hoja en blanco. */
    function limpiar() {
        if (enConsulta()) {
            // Se estaba mirando un caso cerrado encima de otro trabajo.
            var aparte = null;
            try { aparte = JSON.parse(borradorGuardado); } catch (e) {}
            borradorGuardado = null;
            if (trabajoSuelto(aparte)) {
                local.draft = aparte;
                if (typeof saveLocal === 'function') saveLocal();
                repintar();
                return;
            }
            archivar(aparte);
            dejarEnBlanco();
            return;
        }
        var q = Q();
        if (trabajoSuelto(q)) return;
        archivar(q);
        dejarEnBlanco();
    }

    /** Los RFQ dictaminados: su borrador ya no sirve. */
    function olvidar(ids) {
        if (!ids || !ids.length) return;
        var d = (typeof shared !== 'undefined' && shared && shared.drafts) || {};
        var quitados = 0;
        Object.keys(d).forEach(function (k) {
            var r = d[k] && d[k].data && d[k].data.pohuaRfq;
            if (r && ids.indexOf(r) >= 0) { delete d[k]; quitados++; }
        });
        if (quitados) compartir();
        var q = Q();
        if (esDeRfq(q) && ids.indexOf(q.pohuaRfq) >= 0) dejarEnBlanco();
    }

    /** Vuelve a poner lo que se llevaba escrito en ese RFQ. */
    function reabrir(data, d) {
        var q = JSON.parse(JSON.stringify(data));
        delete q.pohuaConsulta;
        local.draft = (typeof migrateQuote === 'function') ? migrateQuote(q) : q;
        if (typeof saveLocal === 'function') saveLocal();
        repintar();
        var pn = local.draft.pns && local.draft.pns[local.draft.activePn || 0];
        if (pn && pn.drawing) {
            intentar(function () {
                if (typeof openSpringCalc === 'function') openSpringCalc(false);
            }, 'pasar la geometría a la hoja de resortes');
        }
        aviso(t('rfqRecuperado', { rfq: d.rfq_id }));
    }

    // ------------------------------------------------- lo que se le dice a quien mira

    /*
     * El puente hablaba siempre en español.
     *
     * Pohua entero está traducido —`frontend/js/i18n.js`— y el plant manager
     * que lo abre en inglés ve inglés en todas partes… hasta que la
     * calculadora dice algo. Entonces le salta un «La hoja tiene una
     * cotización a medias» en mitad de una pantalla en inglés. Y no es un
     * aviso cualquiera: es justo el que le pregunta si puede pisar su
     * trabajo. Un mensaje que pide permiso tiene que leerse.
     *
     * No se mete en `i18n.js` porque esto corre DENTRO del iframe de la
     * calculadora, que es de otro repositorio y no carga ese archivo. Se le
     * pregunta el idioma a Pohua a través de `window.parent` —el mismo camino
     * que ya usa el visor de recortes más abajo— y si no contesta, inglés,
     * que es el idioma por defecto de la aplicación.
     */
    var T = {
        en: {
            fundidas: '{n} item(s) that existed only in this browser were uploaded to Pohua.',
            noGuardo: 'COULD NOT SAVE TO POHUA — {error}. Your work is still in this browser; it will upload on the next save.',
            actualizado: 'Quotes updated by {quien}.',
            otroUsuario: 'another user',
            abrirTitulo: 'Open {rfq}',
            abrirTexto: 'The sheet has a quote typed by hand that is not saved in the Quote Log. Opening {rfq} discards it.',
            rfqRecuperado: 'RFQ {rfq} reopened with what you had written.',
            restaurada: 'Version {v} chosen in the review is loaded.',
            restauradaSistema: 'The system costing chosen in the review is loaded.',
            noAbrio: 'Could not open {rfq} in the sheet: {error}',
            clienteNuevo: 'Customer "{cliente}" was not in the catalog: it was created as {codigo} with Net 30. Review terms and rep.',
            variosFicheros: 'There are {n} files from the email in the box; the first one is read ({nombre}). The rest, by hand.',
            planoPuesto: 'The drawing from the email ({nombre}) is loaded: press "AI Read Drawing".',
            planosPuestos: '{n} drawings from the email are loaded: press "AI Read Drawing".',
            lectorApagado: 'The drawing from the email ({nombre}) is loaded. The reader is off: turn it on and press "AI Read Drawing".',
            leyendo: 'Reading the drawing from the email ({nombre})…',
            planoLeido: 'Drawing read: check the highlighted fields.',
            planoNoLeido: 'Could not read the drawing: {error}. It is loaded; you can press "AI Read Drawing".',
            rfqAbierto: 'RFQ {rfq} open in the sheet',
            sinCatalogo: 'customer "{cliente}" is not in the catalog: pick one or create it',
            conCliente: 'customer {cliente}',
            sinResolver: '{n} field(s) the catalog did not resolve',
            sinRegenerar: 'The calculator was not rebuilt: scripts/vendorizar_nucleo.py has not been run. It stays on the light theme.',
            sembrado: 'First time: what was in this browser was uploaded to Pohua.',
            noLeyoEstado: 'Could not read the state from Pohua — {error}'
        },
        es: {
            fundidas: '{n} elemento(s) que estaban sólo en este navegador se subieron a Pohua.',
            noGuardo: 'NO SE PUDO GUARDAR EN POHUA — {error}. Tu trabajo sigue en este navegador; se subirá al volver a guardar.',
            actualizado: 'Cotizaciones actualizadas por {quien}.',
            otroUsuario: 'otro usuario',
            abrirTitulo: 'Abrir {rfq}',
            abrirTexto: 'La hoja tiene una cotización tecleada a mano que no está guardada en el Quote Log. Al abrir {rfq} se descarta.',
            rfqRecuperado: 'RFQ {rfq} abierto con lo que llevabas escrito.',
            restaurada: 'Cargada la versión {v} escogida en la revisión.',
            restauradaSistema: 'Cargado el cálculo del sistema escogido en la revisión.',
            noAbrio: 'No se pudo abrir {rfq} en la hoja: {error}',
            clienteNuevo: 'El cliente "{cliente}" no estaba en el catálogo: se dio de alta como {codigo} con Net 30. Revisa términos y representante.',
            variosFicheros: 'Hay {n} ficheros del correo en la casilla; se lee el primero ({nombre}). Los demás, a mano.',
            planoPuesto: 'El plano del correo ({nombre}) ya está puesto: pulsa "AI Read Drawing".',
            planosPuestos: '{n} planos del correo ya están puestos: pulsa "AI Read Drawing".',
            lectorApagado: 'El plano del correo ({nombre}) ya está puesto. El lector está apagado: enciéndelo y pulsa "AI Read Drawing".',
            leyendo: 'Leyendo el plano del correo ({nombre})…',
            planoLeido: 'Plano leído: revisa los campos marcados.',
            planoNoLeido: 'No se pudo leer el plano: {error}. Está cargado; puedes pulsar "AI Read Drawing".',
            rfqAbierto: 'RFQ {rfq} abierto en la hoja',
            sinCatalogo: 'el cliente "{cliente}" no está en el catálogo: hay que elegirlo o darlo de alta',
            conCliente: 'cliente {cliente}',
            sinResolver: '{n} dato(s) que el catálogo no resolvió',
            sinRegenerar: 'La calculadora no se regeneró: falta pasar scripts/vendorizar_nucleo.py. Se queda en tema claro.',
            sembrado: 'Primera vez: se subió a Pohua lo que había en este navegador.',
            noLeyoEstado: 'No se pudo leer el estado desde Pohua — {error}'
        },
        fr: {
            fundidas: "{n} élément(s) qui n'existaient que dans ce navigateur ont été envoyés à Pohua.",
            noGuardo: "IMPOSSIBLE D'ENREGISTRER DANS POHUA — {error}. Votre travail reste dans ce navigateur ; il partira au prochain enregistrement.",
            actualizado: 'Devis mis à jour par {quien}.',
            otroUsuario: 'un autre utilisateur',
            abrirTitulo: 'Ouvrir {rfq}',
            abrirTexto: "La feuille contient un devis saisi à la main qui n'est pas enregistré dans le Quote Log. Ouvrir {rfq} le supprime.",
            rfqRecuperado: 'RFQ {rfq} rouvert avec ce que vous aviez saisi.',
            restaurada: 'Version {v} choisie dans la revue chargée.',
            restauradaSistema: 'Chiffrage du système choisi dans la revue chargé.',
            noAbrio: "Impossible d'ouvrir {rfq} dans la feuille : {error}",
            clienteNuevo: 'Le client « {cliente} » ne figurait pas au catalogue : il a été créé comme {codigo} avec Net 30. Vérifiez les conditions et le représentant.',
            variosFicheros: "Il y a {n} fichiers du courrier dans la case ; le premier est lu ({nombre}). Les autres, à la main.",
            planoPuesto: 'Le plan du courrier ({nombre}) est chargé : appuyez sur « AI Read Drawing ».',
            planosPuestos: '{n} plans du courrier sont chargés : appuyez sur « AI Read Drawing ».',
            lectorApagado: "Le plan du courrier ({nombre}) est chargé. Le lecteur est éteint : allumez-le et appuyez sur « AI Read Drawing ».",
            leyendo: 'Lecture du plan du courrier ({nombre})…',
            planoLeido: 'Plan lu : vérifiez les champs signalés.',
            planoNoLeido: "Impossible de lire le plan : {error}. Il est chargé ; vous pouvez appuyer sur « AI Read Drawing ».",
            rfqAbierto: 'RFQ {rfq} ouvert dans la feuille',
            sinCatalogo: "le client « {cliente} » n'est pas au catalogue : choisissez-en un ou créez-le",
            conCliente: 'client {cliente}',
            sinResolver: "{n} donnée(s) que le catalogue n'a pas résolue(s)",
            sinRegenerar: "La calculatrice n'a pas été régénérée : scripts/vendorizar_nucleo.py n'est pas passé. Elle reste en thème clair.",
            sembrado: "Première fois : ce qu'il y avait dans ce navigateur a été envoyé à Pohua.",
            noLeyoEstado: "Impossible de lire l'état depuis Pohua — {error}"
        }
    };

    /* Pohua manda. Esto vive en el iframe, así que el idioma está un piso
       arriba; si no se alcanza —abierto suelto, o el padre de otro origen—,
       inglés, que es con lo que arranca la aplicación. */
    function idiomaDePohua() {
        try {
            var p = (window.parent && window.parent !== window) ? window.parent : window;
            return (p.I18N && p.I18N.idioma) || (window.I18N && window.I18N.idioma) || 'en';
        } catch (e) { return 'en'; }
    }

    function t(clave, datos) {
        var textos = T[idiomaDePohua()] || T.en;
        var s = textos[clave] || T.en[clave] || '';
        if (datos) {
            for (var k in datos) {
                if (Object.prototype.hasOwnProperty.call(datos, k)) {
                    s = s.split('{' + k + '}').join(String(datos[k]));
                }
            }
        }
        return s;
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
            //
            // Y después se vuelve a leer UNA vez. La hoja de Pohua lleva el
            // SEED vacío —el catálogo no se versiona—, así que lo que acaba de
            // sembrar no trae máquinas, ni precios, ni cajas. El servidor sí
            // los pone al servir el documento (`pricing/proyeccion_hoja.py`),
            // pero sólo al LEERLO: sin esta segunda lectura, la primera sesión
            // cotizaría con las bases vacías. Una sola vez y sin volver a
            // `adoptar()`, para que un guardado que falle no se convierta en
            // un bucle.
            return SFS.write().then(function () {
                return pedir(ESTADO).then(function (r2) {
                    if (r2.estado === 'datos' && r2.texto) {
                        var doc2 = JSON.parse(r2.texto);
                        if (doc2 && doc2.dbs) {
                            shared = doc2;
                            revConocida = r2.rev;
                            try { ensureV7Dbs(shared); } catch (e) {}
                            try { refreshSeedDriven(); } catch (e) {}
                        }
                    }
                    return 'sembrado';
                }, function () { return 'sembrado'; });
            });
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
        aviso(t('fundidas', { n: fundidas }));
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
                aviso(t('noGuardo', { error: err.message }));
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
                    aviso(t('actualizado', {
                        quien: String(e.guardado_por || '').split('@')[0] ||
                               t('otroUsuario')
                    }));
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

        // A la izquierda, delante del letrero (que ya sólo sale si algo falló).
        barra.insertBefore(herramientas, barra.firstChild);
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
            '#sharebar-msg{flex:0 1 auto;min-width:0}',
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
            '#btn-spring{font-weight:700}',
            /* Dentro de Pohua las dos pestañas —Quote y Spring Calc— son suyas
               y están encima del marco (js/pages/quoting.js). Repetirlas aquí
               dejaba dos filas de botones diciendo lo mismo, una con el
               aspecto de la calculadora y otra con el de Pohua. Se esconden,
               no se quitan: la calculadora sigue cambiando de vista sola. */
            'html.nube-en-pohua .nube-herramientas{display:none}'
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
            barra.classList.add('nube-aviso');
            msg.textContent = '⚠ El último guardado no llegó a Pohua. Tu trabajo ' +
                              'está en este navegador; vuelve a guardar.';
            return;
        }
        // Guardado bien: el letrero verde ya no se enseña (se pidió quitarlo y
        // dejar sólo Quote y Spring Calc). El dato se conserva en el título
        // de la barra, por si alguien quiere saber cuándo y quién.
        barra.classList.add('ok');
        barra.classList.remove('nube-aviso');
        var quien = String((shared && shared.savedBy) || '').split('@')[0] || '—';
        var cuando = (shared && shared.savedAt) || '—';
        msg.textContent = '';
        barra.title = 'Guardado en Pohua (Neon). Último guardado: ' + cuando + ' por ' + quien;
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
        // La vista ampliada del visor 3D (isc-visor3d.js) es otra capa
        // `position:fixed; inset:0`, sin id: se reconoce por su clase.
        var visor = document.querySelector('.v3d-ov');
        if (visor && getComputedStyle(visor).display !== 'none') return true;
        // La ventana de aprobación (isc-aprobacion.js), igual.
        if (document.querySelector('.nube-aprobacion')) return true;
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
    var ultimoAlto = 0;      // el alto de la barra que ya está publicado

    function estiloAnclaje() {
        if (document.getElementById('nube-anclaje')) return;
        var css = document.createElement('style');
        css.id = 'nube-anclaje';
        css.textContent = [
            /* EN EL TELÉFONO LA BARRA NO SE ENSEÑA.
               Reset, Save, Ver PDF y Aprobar son los mismos cuatro botones
               que la ventana de revisión de Pohua ya tiene —y ésa es la que
               sigue el flujo de aprobación, avisa al cliente y deja rastro—.
               Duplicados dentro del marco, en una pantalla de 390 px, eran
               media pantalla de botones que hacían otra cosa parecida pero no
               igual, y encima tapaban el final de la hoja. El borrador se
               guarda solo (`queueDraft`), así que quitarla no pierde trabajo. */
            '@media (max-width:820px){',
            ' html:not(.nube-ventana) #botbar{display:none!important}',
            '}',
            /* Sólo de tableta para arriba. En el teléfono esta barra NO se
               persigue con JavaScript: ver `anclarFijos`. */
            '@media (min-width:821px){',
            ' html:not(.nube-ventana) #botbar{position:absolute;top:0;bottom:auto;',
            '   left:0;right:0;will-change:transform}',
            ' html:not(.nube-ventana) #toast{position:absolute;top:0;bottom:auto;',
            '   left:50%;will-change:transform}',
            '}'
        ].join('');
        document.head.appendChild(css);
    }

    /* De este ancho para abajo, la barra no se persigue: ver `anclarFijos`. */
    var ANCHO_TELEFONO = 820;

    function anclarFijos() {
        if (!marco || modoVentana) return;

        var bot = document.getElementById('botbar');
        var toast = document.getElementById('toast');
        if (!bot && !toast) return;

        /* EN EL TELÉFONO NO SE PERSIGUE NADA.
         *
         * Aquí la barra se colocaba a mano en cada scroll de la página de
         * fuera, y eso en un teléfono se ve: el dedo desplaza la pantalla por
         * el compositor y el `transform` llega un fotograma tarde, así que la
         * barra nada por encima del contenido y parpadea. Con el impulso del
         * scroll táctil —que sigue corriendo solo— es peor todavía.
         *
         * Se le quita el trabajo: sin la regla de anclaje (que ahora es sólo
         * de 821 px para arriba) la barra vuelve a su `position:fixed` de
         * siempre, y dentro de un marco tan alto como su contenido eso la deja
         * quieta AL FINAL de la calculadora. Se llega a ella desplazando, como
         * al último campo del formulario, y no se mueve ni tapa nada por el
         * camino. El hueco que se reserva al final se sigue publicando.
         */
        if (bot) {
            // Escondida en el teléfono: el hueco del final sobra.
            var estrecho = window.innerWidth <= ANCHO_TELEFONO;
            var alto = estrecho ? 0 : (bot.offsetHeight || 0);
            if (alto !== ultimoAlto) {
                ultimoAlto = alto;
                document.documentElement.style.setProperty('--nube-barra', alto + 'px');
            }
        }
        if (window.innerWidth <= ANCHO_TELEFONO) {
            if (bot && bot.style.transform) bot.style.transform = '';
            if (toast && toast.style.transform) toast.style.transform = '';
            return;
        }

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

    /**
     * Los avisos de la calculadora, dichos por Pohua (sólo en el teléfono).
     *
     * `#toast` también era `position:fixed`, así que en el teléfono —donde ya
     * no se persigue nada— se quedaría al final del documento: un "Guardado"
     * que aparece y se va a cinco pantallas de distancia no lo lee nadie. Se
     * esconde ahí (js/isc-tema.js) y su texto se le pasa a Pohua, que tiene su
     * propio aviso y sí está fijo de verdad sobre la pantalla.
     */
    function relevarAvisos() {
        var caja = document.getElementById('toast');
        if (!caja || typeof MutationObserver === 'undefined') return;
        var ultimo = '';
        new MutationObserver(function () {
            var encendido = (caja.className || '').indexOf('on') !== -1;
            if (!encendido) { ultimo = ''; return; }
            if (window.innerWidth > ANCHO_TELEFONO) return;
            var texto = (caja.textContent || '').trim();
            if (!texto || texto === ultimo) return;
            ultimo = texto;
            try {
                window.parent.postMessage({ source: 'isc-nube', tipo: 'aviso',
                                            texto: texto.slice(0, 300) }, '*');
            } catch (e) { /* sin padre: se queda como estaba */ }
        }).observe(caja, { attributes: true, attributeFilter: ['class'],
                           childList: true, characterData: true, subtree: true });
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


    // ------------------------------------------------- el resorte, por fuera

    /**
     * El Spring Calculator deja de abrirse DENTRO de la calculadora.
     *
     * La calculadora de precios lo abría en un marco propio (`#scframe`)
     * dentro de una capa flotante (`#scwrap`): una ventana pequeña, con su
     * barra de título dentro de otra barra, y a dos marcos de profundidad de
     * Pohua —lo bastante lejos como para que el tema no siempre llegara y se
     * viera blanca dentro de Pohua oscuro—.
     *
     * Dentro de Pohua el resorte es un apartado hermano, con su propio botón
     * arriba (js/pages/quoting.js). Aquí no se reescribe nada de la
     * calculadora: se le cambian dos cosas al marco anidado y su función de
     * apertura sigue haciendo exactamente lo que hacía.
     *
     *   `src`           ya no carga nada; avisa a Pohua de qué dirección
     *                   quería (lleva el `?j=` del plano) y finge el `load`,
     *                   que es lo que la calculadora espera para mandar.
     *   `contentWindow` un buzón: lo que ella le postea a "su" marco, se lo
     *                   reenvía a Pohua, que lo mete en el marco de verdad.
     *
     * Así el traspaso del plano y la vuelta del peso siguen siendo los de la
     * calculadora, sin copiar aquí ni una línea de cómo se arma esa carga.
     */
    function desanidarResorte() {
        document.documentElement.classList.add('nube-en-pohua');
        var marco = document.getElementById('scframe');
        var capa = document.getElementById('scwrap');
        if (!marco || marco.dataset.desanidado) return;
        marco.dataset.desanidado = '1';

        var urlPedida = '';

        function aPohua(mensaje) {
            try { window.parent.postMessage(mensaje, '*'); } catch (e) {}
        }

        Object.defineProperty(marco, 'src', {
            configurable: true,
            get: function () { return urlPedida; },
            set: function (v) {
                urlPedida = String(v || '');
                aPohua({ source: 'isc-nube', tipo: 'abrir-resortes', url: urlPedida });
                // El `load` que la calculadora espera para poder mandar.
                var fn = marco.onload;
                if (typeof fn === 'function') setTimeout(function () { fn.call(marco); }, 0);
            }
        });

        Object.defineProperty(marco, 'contentWindow', {
            configurable: true,
            get: function () {
                return {
                    postMessage: function (carga) {
                        aPohua({ source: 'isc-nube', tipo: 'a-resortes',
                                 url: urlPedida, carga: carga });
                    }
                };
            }
        });

        // La capa flotante ya no se abre: si algo la enciende, se apaga.
        if (capa) {
            capa.classList.remove('on');
            new MutationObserver(function () {
                if (capa.classList.contains('on')) {
                    capa.classList.remove('on');
                    aPohua({ source: 'isc-nube', tipo: 'abrir-resortes', url: urlPedida });
                }
            }).observe(capa, { attributes: true, attributeFilter: ['class'] });
        }

        // Y Pohua puede pedirle la entrega cuando es ELLA quien abre el
        // apartado: la misma función, sin enseñar ninguna capa.
        window.addEventListener('message', function (ev) {
            var d = ev.data || {};
            if (d.source !== 'pohua') return;
            if (d.tipo === 'pedir-resorte') {
                try { if (typeof openSpringCalc === 'function') openSpringCalc(false); } catch (e) {}
            } else if (d.tipo === 'cargar-rfq') {
                cargarRfq(d.datos, d.consulta);
            } else if (d.tipo === 'salir-consulta') {
                /* Salir de mirar un caso cerrado es salir de un RFQ: la hoja
                   queda limpia, y lo que hubiera debajo se guarda o se
                   devuelve según sea de un RFQ o hecho a mano. */
                cuandoDoc(function () {
                    limpiar();
                    aPohua({ source: 'isc-nube', tipo: 'consulta-cerrada', volvio: true });
                });
            } else if (d.tipo === 'limpiar') {
                cuandoDoc(limpiar);
            } else if (d.tipo === 'olvidar-rfqs') {
                cuandoDoc(function () { olvidar(d.ids || []); });
            } else if (d.tipo === 'pedir-cotizacion') {
                // «Volver a revisión»: lo cotizado, ahora mismo. Si no hay
                // nada que mandar se dice igual, para que Pohua no espere.
                if (publicarTimer) { clearTimeout(publicarTimer); publicarTimer = null; }
                if (!publicarCotizacion('volver')) {
                    aPohuaDirecto({ source: 'isc-nube', tipo: 'rfq-cotizado',
                                    rfq_id: d.rfq_id || null, vacio: true, motivo: 'volver' });
                }
            }
        });
    }


    // ----------------------------------------- abrir un RFQ en la calculadora

    /**
     * El RFQ del correo, puesto en la hoja.
     *
     * "Abrir cotización completa" traía a la calculadora en blanco: el PM
     * acababa de ver el material, el diámetro, el peso y tres cantidades en la
     * ventana de revisión, y aquí se encontraba un "Needs the customer, at
     * least one quantity before it can be approved" y a teclearlo otra vez.
     *
     * Lo que llega de Pohua NO es una lista de campos que haya que ir
     * colocando uno por uno: es el PN entero, con la forma exacta que la
     * calculadora guarda en su borrador (`blankPn()`), porque lo arma el mismo
     * código del servidor que se lo pasa al motor para costear. Aquí se
     * adopta tal cual y se repinta. Si se copiara campo por campo desde el
     * navegador, el día que el motor cambiara un nombre la hoja se abriría con
     * un número distinto del que el PM acaba de aprobar.
     *
     * Lo que NO se hace: pisar trabajo de nadie. Si el borrador está en blanco
     * se llena; si ya trae otra cotización a medias, se pregunta; y si ya es
     * este mismo RFQ, no se toca nada —volver a entrar no puede deshacer lo
     * que se lleve escrito—.
     */
    function cargarRfq(d, consulta) {
        if (!d || !d.pn) return;
        if (typeof Q !== 'function' || typeof blankQuote !== 'function') return;
        // Necesita el documento de Neon: ahí está lo que se llevaba escrito.
        cuandoDoc(function () { cargarRfqYa(d, consulta); });
    }

    /*
     * La versión que el PM escogió en la ventana de revisión.
     *
     * Si escogió una versión anterior (o volvió al cálculo del sistema), la
     * hoja tiene que abrir ESA y no su último borrador: si no, la ventana
     * diría un precio y la calculadora otro. Se aplica una sola vez por
     * elección (`pohuaRestauracion` guarda cuál), así que lo que el PM
     * escriba después ya no se pisa.
     */
    function aplicarRestauracion(d) {
        var r = d && d.restauracion;
        var q = (typeof Q === 'function') ? Q() : null;
        if (!r || !r.en || !q || q.pohuaRfq !== d.rfq_id) return false;
        if (q.pohuaRestauracion === r.en) return false;
        var fuente = r.pn || d.pn;
        if (!fuente) return false;
        try {
            var pn = JSON.parse(JSON.stringify(fuente));
            if (typeof completarPn === 'function') pn = completarPn(pn);
            q.pns = [pn];
            q.activePn = 0;
            q.pohuaRestauracion = r.en;
            marcarBase(q);
            if (typeof saveLocal === 'function') saveLocal();
            repintar();
            aviso(r.version === null || r.version === undefined
                  ? t('restauradaSistema')
                  : t('restaurada', { v: r.version }));
            return true;
        } catch (e) {
            console.warn('[nube] No se pudo cargar la versión escogida: ' + e.message);
            return false;
        }
    }

    /** ¿La hoja de este RFQ se quedó sin nada (ni número de parte ni cantidades)? */
    function hojaVacia(q) {
        var pns = (q && q.pns) || [];
        return !pns.some(function (p) {
            return p && (p.pn || (p.tiers || []).some(function (x) { return x && x.qty; }));
        });
    }

    function cargarRfqYa(d, consulta) {
        var q = Q();
        if (q && q.pohuaRfq === d.rfq_id && !consulta) {
            // Ya está abierto. Si la hoja se quedó vacía, se vuelve a llenar
            // —con lo que llevaba escrito si lo hay, o con lo del RFQ—; si
            // tiene trabajo, no se toca, salvo que el PM haya escogido otra
            // versión desde la revisión.
            if (hojaVacia(q)) {
                delete q.pohuaRfq;              // para que `abrirRfq` no lo archive vacío
                abrirRfq(d);
                return;
            }
            if (!aplicarRestauracion(d)) avisarCargado(d.rfq_id, false);
            return;
        }

        // En consulta NO se pregunta nada: el borrador se aparta entero y se
        // devuelve al salir, así que no hay nada que el usuario pueda perder
        // y no tiene sentido hacerle decidir.
        if (consulta) {
            guardarBorrador();
            if (!enConsulta()) return;            // no se pudo apartar: no se entra
            ponerRfq(d, true);
            return;
        }

        // Se estaba mirando un caso cerrado: primero se devuelve lo de debajo.
        if (enConsulta()) { devolverBorrador(); q = Q(); }

        if (!trabajoSuelto(q)) { abrirRfq(d); return; }

        // Sólo pregunta cuando hay trabajo hecho a mano que no está en ningún
        // otro sitio: lo de otro RFQ se guarda solo y vuelve al reabrirlo.
        var texto = t('abrirTexto', { rfq: d.rfq_id });
        if (typeof confirmBox === 'function') {
            confirmBox(t('abrirTitulo', { rfq: d.rfq_id }), texto,
                       function () { abrirRfq(d); });
        } else if (window.confirm(texto)) {
            abrirRfq(d);
        }
    }

    /** Guarda lo del RFQ que hubiera y abre este: lo que ya llevaba, o nuevo. */
    function abrirRfq(d) {
        archivar(Q());
        var guardado = guardadoDe(d.rfq_id);
        if (guardado) reabrir(guardado, d);
        else ponerRfq(d);
        aplicarRestauracion(d);
    }

    /** Un paso que puede fallar sin llevarse los demás. */
    function intentar(fn, que) {
        try { fn(); return true; }
        catch (e) {
            console.warn('[nube] No se pudo ' + que + ': ' + e.message);
            return false;
        }
    }

    function ponerRfq(d, consulta) {
        try {
            var q = blankQuote();
            q.pohuaRfq = d.rfq_id;              // para no volver a cargarlo encima
            // Lo que llega de Pohua no es una corrección del PM (ver `sinCambios`).
            q.pohuaBase = 'pendiente';
            // Una elección hecha antes de abrir la hoja por primera vez ya
            // viene en `d.pn`/`restauracion`; no hay borrador que pisar.
            if (d.restauracion && d.restauracion.en && !d.restauracion.pn) {
                q.pohuaRestauracion = d.restauracion.en;
            }
            // Marca lo que se está mirando. La pantalla la usa para enseñar la
            // cinta de "estás viendo un caso cerrado" y el botón de volver.
            if (consulta) q.pohuaConsulta = d.rfq_id;
            d.pn = completarPn(d.pn);
            q.pns = [d.pn];
            q.activePn = 0;

            var cab = d.header || {};
            q.header.customerCode = codigoDeCliente(cab.customer) ||
                                    codigoDeCliente(cab.cliente_id) ||
                                    altaDeCliente(cab.cliente) ||
                                    altaDelCorreo(cab.customer);
            // Lo que el comprador pidió y no tiene casilla propia, en las
            // notas internas del PN: de dónde salió esta cotización, para
            // cuándo la quiere, en qué moneda y con qué incoterm, y lo que
            // escribiera de más. No se imprime en la oferta; se lee antes de
            // cotizar, que es justo cuando hace falta.
            d.pn.notes = notasDelCorreo(d, cab) || d.pn.notes || '';

            // La geometría se cuelga del PN ANTES de guardarlo: `migrateQuote`
            // devuelve una copia, así que lo que se le añada al objeto después
            // ya no es el que queda en el borrador —y el plano del correo se
            // perdía sin ruido—.
            prepararResorte(d);

            local.draft = (typeof migrateQuote === 'function')
                ? migrateQuote(q) : q;
            if (typeof saveLocal === 'function') saveLocal();

            /* Cada paso en su propio intento, y no los tres en uno.
               `renderQuote()` termina llamando a `recalc()`, y un RFQ al que
               le falta el diámetro o la tarifa de la máquina —que es
               exactamente el que se viene a completar aquí— puede hacerla
               tropezar. Encadenados, ese tropiezo se llevaba por delante lo
               que venía después: la hoja de resortes no recibía la geometría
               y el aviso final tampoco salía. El borrador ya está guardado,
               así que un fallo al pintar no pierde nada. */
            intentar(function () {
                if (typeof renderQuote === 'function') renderQuote();
            }, 'pintar la hoja');
            intentar(function () {
                if (typeof updateSummaryTab === 'function') updateSummaryTab();
            }, 'refrescar el resumen');

            /* El número de cotización y las condiciones de pago los pone la
               calculadora al ELEGIR cliente, no al tener uno: poniendo el
               código en el modelo, la casilla quedaba con el cliente puesto y
               el número en "(select customer)". Se dispara el mismo camino que
               el desplegable, que además apunta la cotización en el registro
               y deja las condiciones del cliente. */
            intentar(function () {
                var sel = document.getElementById('q-customer');
                if (!sel || !q.header.customerCode) return;
                sel.value = q.header.customerCode;
                if (typeof sel.onchange === 'function') {
                    sel.onchange({ target: { value: q.header.customerCode } });
                }
            }, 'numerar la cotización');

            // El plano del correo, puesto en la casilla de "AI Read Drawing"
            // —y leído solo si quien mira es el PM—.
            intentar(function () {
                ponerPlanos(d.ficheros, q, !!((d.resorte || {}).plano_calculadora));
            }, 'poner el plano');

            // Y ya con el borrador puesto, se le entrega a la hoja de resortes.
            if (d.pn.drawing) {
                intentar(function () {
                    if (typeof openSpringCalc === 'function') openSpringCalc(false);
                }, 'pasar la geometría a la hoja de resortes');
            }
            avisarCargado(d.rfq_id, true, cab.customer,
                          !q.header.customerCode ? cab.customer : null,
                          d.faltantes || []);
        } catch (e) {
            aviso(t('noAbrio', { rfq: d.rfq_id, error: e.message }));
        }
    }

    /**
     * Copiar al catálogo de la calculadora un cliente que Pohua YA tiene.
     *
     * YA CASI NUNCA HACE FALTA, y conviene saber por qué sigue aquí.
     *
     * Eran dos catálogos distintos —el de Pohua, donde un cliente entra
     * cuando se registra su dominio, y el de la calculadora, que vivía dentro
     * del documento compartido— y divergían solos: un cliente que Pohua
     * conocía perfectamente dejaba la casilla "Customer" vacía, y sin cliente
     * la cotización no se puede ni numerar ni aprobar.
     *
     * Ya no son dos. El servidor arma `dbs.customers` desde la tabla
     * `clientes` cada vez que sirve el documento
     * (`app/clients/catalogo_hoja.py`), así que al abrir un RFQ el cliente ya
     * está en la lista.
     *
     * Esto se queda de red: si ese día la base no contestara, el servidor
     * deja el catálogo que hubiera y esta función sigue sabiendo rellenar el
     * hueco. Comprueba antes si ya está, así que cuando todo va bien no hace
     * nada.
     *
     * Se copia SÓLO lo que Pohua ya dio de alta. Un remitente desconocido no
     * crea nada: el nombre que el modelo leyó de un correo no es un alta, y
     * un catálogo con "Re: quote request" dentro no se limpia solo.
     */
    function altaDeCliente(cliente) {
        if (!cliente || !cliente.codigo || !cliente.razon_social) return '';
        if (typeof shared === 'undefined' || !shared.dbs || !shared.dbs.customers) return '';

        var codigo = String(cliente.codigo).trim().toUpperCase()
                        .replace(/[^A-Z0-9-]/g, '').slice(0, 20);
        if (!codigo) return '';
        for (var i = 0; i < shared.dbs.customers.length; i++) {
            if (String(shared.dbs.customers[i].code || '').toUpperCase() === codigo) {
                return shared.dbs.customers[i].code;
            }
        }

        shared.dbs.customers.push({
            code: codigo,
            name: String(cliente.razon_social).slice(0, 80),
            terms: cliente.payment_terms || 'Net 30',
        });
        shared.dbs.customers.sort(function (a, b) {
            return String(a.code).localeCompare(String(b.code));
        });
        intentar(function () {
            if (typeof journal === 'function') {
                journal('DB:customers', 'Cliente copiado desde Pohua: ' +
                        codigo + ' — ' + cliente.razon_social);
            }
            if (typeof fillCustomers === 'function') fillCustomers();
            if (typeof queueShared === 'function') queueShared();
        }, 'apuntar el alta del cliente');
        return codigo;
    }

    /**
     * El PN del servidor, completado con la forma que espera la hoja.
     *
     * El servidor manda lo que sabe: el material, las cantidades y la ruta que
     * salió del catálogo —una o dos operaciones—. La hoja, en cambio, cuenta
     * con que TODO esté: cinco tramos, ocho renglones de ruta en cada uno, y
     * dentro de cada tramo su utillaje, su subcontrato y su empaque.
     *
     * Con un hueco, `renderQuote()` revienta a mitad de pintar —`t.tooling` no
     * existe y se cae leyendo `.desc`— y lo que falta detrás no se dibuja: las
     * casillas de arriba salían llenas y de la ruta para abajo no había nada,
     * sin un solo error a la vista. Y con dos renglones de ruta en vez de
     * ocho, no hay dónde añadir la tercera operación.
     *
     * Así que lo que llega se funde SOBRE un PN en blanco de la propia hoja:
     * manda el valor del servidor donde lo haya, y donde no, queda el hueco
     * que la hoja espera. Vale para hoy y para el día que cualquiera de los
     * dos lados añada un campo.
     */
    function completarPn(pn) {
        if (!pn || typeof blankPn !== 'function') return pn;
        var base = blankPn();

        var fundir = function (destino, origen) {
            if (!origen || typeof origen !== 'object') return destino;
            Object.keys(origen).forEach(function (k) {
                var v = origen[k];
                if (v === undefined) return;
                if (v && typeof v === 'object' && !Array.isArray(v) &&
                    destino[k] && typeof destino[k] === 'object' && !Array.isArray(destino[k])) {
                    fundir(destino[k], v);
                } else {
                    destino[k] = v;
                }
            });
            return destino;
        };

        var tramos = Array.isArray(pn.tiers) ? pn.tiers : [];
        var copia = fundir(base, pn);

        copia.tiers = base.tiers.map(function (vacio, i) {
            var suyo = tramos[i];
            if (!suyo) return vacio;
            var ruta = Array.isArray(suyo.routing) ? suyo.routing : [];
            var tramo = fundir(vacio, suyo);
            // La ruta, renglón a renglón sobre los ocho que la hoja dibuja.
            tramo.routing = blankTier().routing.map(function (fila, j) {
                return ruta[j] ? fundir(fila, ruta[j]) : fila;
            });
            return tramo;
        });
        return copia;
    }

    /**
     * El cliente del correo, cuando no está en ningún catálogo.
     *
     * Sin cliente la cotización no se numera ni se aprueba, así que dejarlo
     * vacío corta el flujo justo donde se abrió la hoja para no cortarlo. Se
     * da de alta con el nombre que venía en el correo y un código sacado de
     * ese mismo nombre, y se dice en voz alta —aviso y registro— que salió de
     * ahí y hay que revisarlo: los términos de pago son una decisión, y aquí
     * se pone el que la casa usa por defecto.
     */
    function altaDelCorreo(nombre) {
        var limpio = String(nombre || '').trim();
        if (!limpio) return '';
        if (typeof shared === 'undefined' || !shared.dbs || !shared.dbs.customers) return '';

        // El código: las primeras letras y números del nombre, sin acentos.
        var codigo = limpio.normalize ? limpio.normalize('NFD').replace(/[\u0300-\u036f]/g, '') : limpio;
        codigo = codigo.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 10);
        if (!codigo) return '';
        for (var i = 0; i < shared.dbs.customers.length; i++) {
            if (String(shared.dbs.customers[i].code || '').toUpperCase() === codigo) {
                return shared.dbs.customers[i].code;
            }
        }

        shared.dbs.customers.push({ code: codigo, name: limpio.slice(0, 80), terms: 'Net 30' });
        shared.dbs.customers.sort(function (a, b) {
            return String(a.code).localeCompare(String(b.code));
        });
        intentar(function () {
            if (typeof journal === 'function') {
                journal('DB:customers', 'Cliente creado desde el correo (revisar): ' +
                        codigo + ' — ' + limpio);
            }
            if (typeof fillCustomers === 'function') fillCustomers();
            if (typeof queueShared === 'function') queueShared();
        }, 'apuntar el cliente nuevo');
        aviso(t('clienteNuevo', { cliente: limpio, codigo: codigo }));
        return codigo;
    }

    /**
     * El plano del correo, dentro de la casilla del lector.
     *
     * El dibujo ya está guardado en Pohua desde que se dio de alta el RFQ;
     * hasta ahora había que ir a buscarlo al buzón y subirlo a mano para
     * poder pulsar "AI Read Drawing". Se le mete en el `<input type=file>`
     * con un DataTransfer, que es la única forma de rellenar esa casilla, y
     * se lanza el evento `change` para que la calculadora se entere igual que
     * si lo hubiera elegido una persona.
     *
     * NO se lee solo: cada lectura es una llamada de pago y el lector puede
     * estar apagado. Queda cargado y a un toque.
     */
    function ponerPlanos(ficheros, q, yaLeido) {
        if (!ficheros || !ficheros.length) return;
        var campo = document.getElementById('q-drawing');
        if (!campo || typeof DataTransfer === 'undefined') return;

        var dt = new DataTransfer();
        for (var i = 0; i < ficheros.length; i++) dt.items.add(ficheros[i]);
        campo.files = dt.files;
        campo.dispatchEvent(new Event('change', { bubbles: true }));

        /* Se lee SIEMPRE uno solo, el primero, aunque el correo trajera
           varios.

           El botón "AI Read Drawing" de la calculadora, con más de un
           fichero en la casilla, entra en su modo por lotes: UN NÚMERO DE
           PARTE POR FICHERO. Con el plano y una segunda imagen dentro, eso
           abría un "PN 2" con la segunda imagen y dejaba la hoja mirando a
           esa pieza inventada —sin descripción, sin cotas y sin resorte—,
           que es exactamente lo que no se quería ver al abrir la cotización.

           Los demás se quedan cargados para quien quiera leerlos a mano. */
        // Ya leído en el servidor con el mismo lector: leerlo otra vez aquí
        // sería pagar dos veces la misma lectura. Se queda en la casilla por
        // si alguien quiere los recortes («AI Read Drawing»).
        if (esPlantManager() && !yaLeido) {
            leerPlanoSolo(ficheros[0], q);
            if (ficheros.length > 1) {
                aviso(t('variosFicheros', { n: ficheros.length,
                                            nombre: ficheros[0].name }));
            }
            return;
        }
        aviso(ficheros.length === 1
            ? t('planoPuesto', { nombre: ficheros[0].name })
            : t('planosPuestos', { n: ficheros.length }));
    }

    /** Quien dictamina. El lector traduce ese permiso a ADMIN al servir la hoja. */
    function esPlantManager() {
        try {
            return String((window.ISC_USER || {}).role || '').toUpperCase() === 'ADMIN';
        } catch (e) { return false; }
    }

    /**
     * Leer el plano sin que nadie pulse nada.
     *
     * Para el PM, "Abrir cotización completa" tiene que enseñar TODO lo que el
     * sistema sabe de la pieza, y el plano es la mitad de eso: sin leerlo, el
     * diámetro de alambre, el exterior y la longitud libre salen vacíos y la
     * hoja de resortes no puede dimensionar nada. Dejarlo cargado y esperar un
     * clic era pedirle que hiciera a mano el paso que vino a ver hecho.
     *
     * Se lee UNA vez por RFQ (`pohuaPlanoLeido`): cada lectura es una llamada
     * de pago, y volver a entrar a mirar no puede volver a cobrarla. Si el
     * lector está apagado y no hay clave, no se intenta: se dice que está
     * cargado y a un toque, que es lo de antes.
     *
     * Y NO se llama al botón: su manejador termina preguntando si abrir la
     * hoja de resortes. Aquí se hace lo mismo que hace él —leer, repintar, y
     * pasar las cotas— sin preguntar nada, porque esto no lo pidió nadie en
     * ese momento.
     */
    function leerPlanoSolo(fichero, q) {
        if (q && q.pohuaPlanoLeido) return;
        if (typeof parseOneFile !== 'function') return;

        var puede = (typeof parserStatus === 'function')
            ? parserStatus() : Promise.resolve(false);
        Promise.resolve(puede).then(function (vivo) {
            if (!vivo && !(typeof local !== 'undefined' && local.apiKey)) {
                aviso(t('lectorApagado', { nombre: fichero.name }));
                return;
            }
            aviso(t('leyendo', { nombre: fichero.name }));
            if (typeof setParseUI === 'function') setParseUI(true);
            return parseOneFile(fichero).then(function () {
                var actual = (typeof Q === 'function') ? Q() : null;
                if (actual) actual.pohuaPlanoLeido = true;
                intentar(function () {
                    if (typeof renderQuote === 'function') renderQuote();
                    if (typeof queueDraft === 'function') queueDraft();
                }, 'repintar tras leer el plano');
                // Las cotas, a la hoja de resortes, sin abrirla ni preguntar.
                intentar(function () {
                    if (typeof openSpringCalc === 'function') openSpringCalc(false);
                }, 'pasar las cotas del plano a la hoja de resortes');
                aviso(t('planoLeido'));
            }).catch(function (err) {
                aviso(t('planoNoLeido', {
                    error: (err && err.message) ? err.message : err
                }));
            }).then(function () {
                if (typeof setParseUI === 'function') setParseUI(false);
            });
        });
    }

    /** Las notas internas del PN, armadas con lo que trajo el correo. */
    function notasDelCorreo(d, cab) {
        var partes = [];
        partes.push('RFQ ' + d.rfq_id + (cab.asunto ? ' — ' + cab.asunto : ''));
        if (cab.contacto || cab.remitente) {
            partes.push('Pide: ' + (cab.contacto || '') +
                        (cab.remitente ? ' <' + cab.remitente + '>' : ''));
        }
        if (cab.entrega) partes.push('Entrega pedida: ' + cab.entrega);
        if (cab.incoterm) partes.push('Incoterm: ' + cab.incoterm);
        if (cab.moneda) partes.push('Moneda: ' + cab.moneda);
        if (cab.notas) partes.push(cab.notas);
        // Lo que el catálogo no pudo resolver se dice aquí y no sólo en un
        // aviso que se va solo: es lo que hay que capturar a mano.
        (d.faltantes || []).forEach(function (f) { partes.push('Falta: ' + f); });
        return partes.join(' · ');
    }

    /**
     * El cliente del correo, contra el catálogo de la calculadora.
     *
     * Se busca por código exacto y por nombre, sin distinguir mayúsculas ni
     * espacios de más. Si no está, se devuelve vacío A PROPÓSITO: dar de alta
     * un cliente es una decisión con términos de pago y representante detrás,
     * y no la toma sola una pantalla porque llegó un correo.
     */
    function codigoDeCliente(nombre) {
        var buscado = String(nombre || '').trim().toLowerCase();
        if (!buscado) return '';
        var lista = (typeof shared !== 'undefined' && shared.dbs &&
                     shared.dbs.customers) || [];
        for (var i = 0; i < lista.length; i++) {
            var c = lista[i] || {};
            if (String(c.code || '').trim().toLowerCase() === buscado) return c.code;
        }
        for (var j = 0; j < lista.length; j++) {
            var c2 = lista[j] || {};
            if (String(c2.name || '').trim().toLowerCase() === buscado) return c2.code;
        }
        return '';
    }

    /**
     * La geometría, a la hoja de resortes.
     *
     * Se arma la MISMA carga que manda el lector de planos (`drawingData`),
     * porque la hoja de resortes ya sabe recibirla: reparte diámetros, largo y
     * espiras según el tipo, resuelve el material y deja el resorte listo para
     * dimensionar. Lo que venga vacío no se manda, y lo que no se manda no se
     * pisa allí.
     */
    function prepararResorte(d) {
        var r = d.resorte || {};

        /* Si el servidor leyó el plano con el lector del núcleo —el mismo de
           «AI Read Drawing»—, se usa TAL CUAL: cotas, lista de factibilidad y
           veredicto. Así la Spring Calc abre este RFQ igual que abriría el
           plano en la calculadora suelta, con su checklist y su FEASIBLE, en
           lugar de «No customer drawing parsed yet». */
        var pc = r.plano_calculadora;
        if (pc && pc.fields && pc.fields.length) {
            var titulo = {};
            Object.keys(pc.title || {}).forEach(function (k) { titulo[k] = pc.title[k]; });
            titulo.pn = titulo.pn || d.pn.pn || '';
            titulo.customer = titulo.customer || (d.header || {}).customer || '';
            d.pn.drawing = {
                springType: pc.springType || TIPOS_RESORTE[String(r.tipo || '').toLowerCase()] || undefined,
                fields: pc.fields,
                feasibility: pc.feasibility || [],
                verdict: pc.verdict || null,
                title: titulo,
                remarks: pc.remarks || undefined,
                origen: 'correo',
            };
            return;
        }
        var tipo = TIPOS_RESORTE[String(r.tipo || '').toLowerCase()] || null;
        var campos = [];
        var mm = function (clave, valor) {
            if (valor || valor === 0) campos.push({ key: clave, value: valor, unit: 'mm' });
        };
        mm('wireDia', r.diametro_alambre_mm);
        mm('od', r.diametro_exterior_mm);
        mm('id', r.diametro_interior_mm);
        mm('freeLength', r.longitud_libre_mm);
        mm('bodyLength', r.longitud_cuerpo_mm);
        if (r.espiras_totales) campos.push({ key: 'coils', value: r.espiras_totales, unit: '' });
        if (r.acabado) campos.push({ key: 'finish', value: r.acabado, unit: '' });
        if (r.material_texto || (d.pn.material && d.pn.material.code)) {
            campos.push({ key: 'material', value: r.material_texto || '',
                          code: (d.pn.material && d.pn.material.code) || '', unit: '' });
        }
        if (!tipo && !campos.length) return;

        // Se guarda en el PN como si lo hubiera leído el plano: así la propia
        // calculadora lo reenvía sola cada vez que se abre la hoja de
        // resortes, sin que haya que repetir este camino.
        d.pn.drawing = {
            springType: tipo || undefined,
            fields: campos,
            title: { pn: d.pn.pn || '', customer: (d.header || {}).customer || '' },
            origen: 'correo',
            feasibility: [],
            verdict: null,
        };
    }

    var TIPOS_RESORTE = {
        compresion: 'compression', compression: 'compression',
        extension: 'extension', tension: 'extension', tracción: 'extension',
        traccion: 'extension', torsion: 'torsion', torsión: 'torsion',
    };

    /** Lo que se le dice a quien acaba de pulsar "Abrir cotización completa". */
    function avisarCargado(rfqId, lleno, cliente, sinCatalogo, faltantes) {
        if (!lleno) return;
        var partes = [t('rfqAbierto', { rfq: rfqId })];
        if (sinCatalogo) {
            partes.push(t('sinCatalogo', { cliente: sinCatalogo }));
        } else if (cliente) {
            partes.push(t('conCliente', { cliente: cliente }));
        }
        if (faltantes && faltantes.length) {
            partes.push(t('sinResolver', { n: faltantes.length }));
        }
        aviso(partes.join(' · '));
    }

    // ------------------------------------------------- la fecha del RFQ

    /**
     * La fecha de una cotización que empieza hoy, es la de hoy.
     *
     * La calculadora pone `today()` al crear el borrador, y hasta ahí bien.
     * Lo que pasa es que el borrador VIVE: se queda guardado en el navegador
     * de un día para otro, así que quien abre Pohua el jueves se encuentra la
     * cotización en blanco que dejó el viernes anterior, con la fecha de aquel
     * viernes. Como por aquí van a entrar los RFQ que llegan por correo, esa
     * fecha vieja acabaría en la oferta.
     *
     * Se corrige SÓLO si el borrador está en blanco —sin número y sin
     * cliente—: en cuanto alguien ha empezado a trabajar, la fecha es suya y
     * no se toca. Y se usa el día del reloj de Pohua (Querétaro), que es el
     * que tiene delante quien mira la pantalla.
     */
    function fechaDeHoy() {
        try {
            var hoy = new Date().toLocaleDateString('sv-SE', { timeZone: 'America/Mexico_City' });
            var q = (typeof Q === 'function') ? Q() : null;
            if (!q || !q.header) return;
            if (q.number || q.header.customerCode) return;      // ya hay trabajo hecho
            if (q.header.rfqDate === hoy) return;

            q.header.rfqDate = hoy;
            var campo = document.getElementById('q-rfq') || document.getElementById('q-date');
            if (campo) campo.value = hoy;
            if (typeof queueDraft === 'function') queueDraft();
        } catch (e) { /* la fecha nunca puede impedir que arranque */ }
    }


    // ------------------------------------------------- recortes que ya no están

    /**
     * Un recorte de plano que no carga, explicado.
     *
     * "Ver en el plano" abre el recuadro que el lector recortó al leer el PDF.
     * Ese PNG lo guarda el lector en su disco, y el disco de Render se vacía
     * en cada despliegue: una cotización de la semana pasada se abría con el
     * icono de imagen partida y ni una palabra de por qué. Desde ahora el
     * servidor los conserva en la base (api/lector.py), pero los recortes
     * ANTERIORES a ese cambio no están en ninguna parte, y los de un plano
     * que nunca se volvió a leer tampoco.
     *
     * Así que cuando uno falla se dice, en su sitio y en una línea: no está
     * guardado, se recupera volviendo a leer el plano. Es lo que alguien
     * necesita saber para desatascarse.
     */
    function explicarRecortes() {
        var T = {
            en: { base: 'This drawing crop did not load.',
                  vacio: 'The reader saved no crop for this item.',
                  falta: 'It is no longer stored on the server: read the drawing again.',
                  sesion: 'The reader session expired: reload Pohua and try again.',
                  lejos: 'It points at another machine ({host}), which is not reachable from here.',
                  http: 'The server answered {n}.' },
            es: { base: 'Este recorte del plano no cargó.',
                  vacio: 'El lector no guardó ningún recorte para este punto.',
                  falta: 'Ya no está guardado en el servidor: vuelve a leer el plano.',
                  sesion: 'La sesión del lector caducó: recarga Pohua y vuelve a intentarlo.',
                  lejos: 'Apunta a otra máquina ({host}), que desde aquí no se alcanza.',
                  http: 'El servidor contestó {n}.' },
            fr: { base: "Ce détail du plan n'a pas pu s'afficher.",
                  vacio: "Le lecteur n'a enregistré aucun détail pour ce point.",
                  falta: "Il n'est plus enregistré sur le serveur : relisez le plan.",
                  sesion: 'La session du lecteur a expiré : rechargez Pohua et réessayez.',
                  lejos: "Il pointe vers une autre machine ({host}), injoignable d'ici.",
                  http: 'Le serveur a répondu {n}.' }
        };
        function idioma() {
            try { return (window.parent && window.parent.I18N && window.parent.I18N.idioma) || 'en'; }
            catch (e) { return 'en'; }
        }
        function t(clave, datos) {
            var textos = T[idioma()] || T.en;
            var s = textos[clave] || T.en[clave] || '';
            if (datos) for (var k in datos) s = s.replace('{' + k + '}', datos[k]);
            return s;
        }

        /**
         * Por qué no cargó, preguntándoselo al servidor.
         *
         * "No se ve la imagen" puede ser cuatro cosas muy distintas —no hay
         * recorte, el disco de Render se vació, la sesión del lector caducó, o
         * la cotización guarda la dirección del lector de OTRA máquina— y cada
         * una se arregla de una forma. El icono de imagen partida no dice
         * ninguna; esto lo pregunta y lo escribe en la nota.
         */
        function diagnosticar(url, alSaber) {
            if (!url) return alSaber(t('vacio'));
            var destino;
            try { destino = new URL(url, location.href); } catch (e) { destino = null; }
            if (destino && destino.origin !== location.origin) {
                return alSaber(t('lejos', { host: destino.host }));
            }
            fetch(url, { credentials: 'same-origin', cache: 'no-store' }).then(function (r) {
                if (r.status === 404) return alSaber(t('falta'));
                if (r.status === 401 || r.status === 403) return alSaber(t('sesion'));
                alSaber(t('http', { n: r.status }));
            }).catch(function () { alSaber(t('falta')); });
        }

        /**
         * El mismo recorte, pero pedido a ESTE servidor.
         *
         * Una cotización guarda la dirección del lector con la que se leyó el
         * plano. Si se leyó con el lector corriendo en la máquina de quien
         * cotiza —"Parser: LIVE (local server)"—, esa dirección es un
         * `127.0.0.1` que desde la nube no existe, y al abrir la cotización en
         * otro sitio los recuadros salen rotos aunque el servidor los tenga
         * guardados. El identificador del recorte es el mismo en los dos
         * lados, así que se vuelve a pedir aquí antes de rendirse.
         */
        function prefijoLector() {
            try {
                var p = window.ISC_PARSER_URL;
                if (typeof p === 'string' && p && p.charAt(0) === '/') return p.replace(/\/$/, '');
            } catch (e) { /* no está puesto */ }
            var m = /^(.*\/lector)\//.exec(location.pathname || '');
            return m ? m[1] : '';
        }

        function mismoRecorteAqui(url) {
            if (!url || url.indexOf('/api/crop/') === -1) return '';
            var destino;
            try { destino = new URL(url, location.href); } catch (e) { return ''; }
            if (destino.origin === location.origin) return '';
            var id = destino.pathname.split('/api/crop/').pop();
            if (!id) return '';
            return prefijoLector() + '/api/crop/' + id;
        }

        /* La imagen NO se saca del documento: se esconde y la nota se pone a su
           lado. Sacarla costó caro la primera vez: la hoja de resortes reusa
           SIEMPRE el mismo `<img id="cropImg">` —le cambia el `src` en cada
           punto que se abre—, así que en cuanto uno fallaba y la nota ocupaba
           su sitio, el siguiente reventaba con "cannot set src of null" y la
           ventana del plano no volvía a abrirse en toda la sesión. */
        function limpiarNota(img) {
            if (img.notaRecorte && img.notaRecorte.parentNode) {
                img.notaRecorte.parentNode.removeChild(img.notaRecorte);
            }
            img.notaRecorte = null;
            img.dataset.recorteAvisado = '';
            /* También el reintento: la hoja de resortes usa siempre la MISMA
               imagen, y sin esto el segundo recorte de otra máquina ya no se
               volvía a pedir aquí —se comía el intento del primero—. No hay
               bucle posible: el reintento apunta a este mismo servidor, y de
               una dirección de aquí ya no se reintenta nada. */
            img.dataset.recorteReintentado = '';
            img.style.display = '';
        }

        /* Cada vez que le cambian el `src`, borrón y cuenta nueva: el punto
           siguiente puede tener su recuadro perfectamente. */
        function vigilarSrc(img) {
            if (img.vigiladoRecorte || typeof MutationObserver === 'undefined') return;
            img.vigiladoRecorte = new MutationObserver(function () { limpiarNota(img); });
            img.vigiladoRecorte.observe(img, { attributes: true, attributeFilter: ['src'] });
        }

        document.addEventListener('error', function (ev) {
            var img = ev.target;
            if (!img || img.tagName !== 'IMG' || img.dataset.recorteAvisado) return;
            var url = img.getAttribute('src') || '';
            /* Los recortes del lector, y también el visor de la hoja de
               resortes (`#cropImg`), que se queda con `src=""` cuando el punto
               no trae recuadro: esa imagen partida es la de la captura que
               llegó, y sin esto no decía nada. */
            var esRecorte = url.indexOf('/api/crop/') !== -1 || img.id === 'cropImg' ||
                            !!(img.closest && img.closest('.crop-b'));
            if (!esRecorte) return;

            /* Antes de dar nada por perdido: si la dirección es de otra
               máquina, se pide el mismo recorte a este servidor. Una sola vez. */
            var aqui = mismoRecorteAqui(url);
            if (aqui && !img.dataset.recorteReintentado) {
                img.dataset.recorteReintentado = '1';
                vigilarSrc(img);
                img.src = aqui;
                return;
            }

            img.dataset.recorteAvisado = '1';
            vigilarSrc(img);

            var nota = document.createElement('p');
            nota.className = 'small';
            nota.style.cssText = 'margin:6px 0;padding:8px 10px;border-radius:8px;' +
                'background:var(--n-avi-fondo,rgba(245,158,11,.14));' +
                'border:1px solid var(--n-avi-linea,rgba(245,158,11,.5))';
            nota.textContent = t('base');
            img.notaRecorte = nota;
            img.style.display = 'none';
            if (img.parentNode) img.parentNode.insertBefore(nota, img.nextSibling);

            diagnosticar(url, function (motivo) {
                nota.textContent = t('base') + ' ' + motivo;
            });
        }, true);   // en captura: el error de una imagen no burbujea

        /* Y si luego carga, la nota sobra. */
        document.addEventListener('load', function (ev) {
            var img = ev.target;
            if (img && img.tagName === 'IMG' && img.notaRecorte) limpiarNota(img);
        }, true);
    }

    // ------------------------------------------------------------- arranque

    /* Medir el marco NO depende de la calculadora de precios.
     *
     * `esperarCalculadora` espera a que existan `SFS` y `shared`, que son
     * globales SUYAS. La hoja de resortes es otro documento —otra pestaña de
     * Pohua, otro marco— y ahí esos dos nunca aparecen: por eso su marco se
     * quedaba en el mínimo del CSS, 320 px, con la ficha cortada dentro y
     * media pantalla vacía debajo. Era el mismo fallo en la compu y en el
     * teléfono, y la causa no era el teléfono.
     *
     * Así que lo que vale para cualquier documento dentro de un marco —medirlo
     * y anclar lo que esté fijo— arranca ya. Lo que es de la calculadora de
     * precios sigue esperándola. */
    function arrancarMarco() {
        estilos();
        vigilarAlto();
        vigilarAnclaje();
        relevarAvisos();
        /* Y explicar los recortes que no carguen. Esto también es de cualquier
           documento: el recuadro del plano se abre desde la lista de
           factibilidad, que vive en la HOJA DE RESORTES. Estaba colgado de la
           espera de la calculadora de precios, así que justo donde ella lo
           estaba viendo roto no salía la explicación. */
        explicarRecortes();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', arrancarMarco, { once: true });
    } else {
        arrancarMarco();
    }

    esperarCalculadora(function () {
        /* La hoja arranca limpia. Lo que dejó puesto este navegador se aparta
           ya —para no enseñarlo ni un instante— y, si era de un RFQ, se guarda
           en Neon en cuanto llegue el documento. */
        var alArrancar = null;
        try {
            alArrancar = Q();
            if (alArrancar && !trabajoSuelto(alArrancar)) {
                local.draft = blankQuote();
                if (typeof saveLocal === 'function') saveLocal();
                repintar();
            } else {
                alArrancar = null;
            }
        } catch (e) { alArrancar = null; }

        /* Pohua espera esta señal para mandar el RFQ que hay que abrir. Sin
           ella tendría que adivinar cuándo terminó de arrancar la calculadora
           —el `load` del marco llega mucho antes— y el mensaje se perdería. */
        try {
            window.parent.postMessage({ source: 'isc-nube', tipo: 'hoja-lista' }, '*');
        } catch (e) {}
        fusionarBarras();
        desanidarResorte();
        fechaDeHoy();
        vigilarTablas();
        /* Si la calculadora no se regeneró, el tema no puede pintarla y se
           queda en claro dentro de Pohua oscuro. Se dice en voz alta: la vez
           que pasó, lo que se vio fue una tabla ilegible y no había forma de
           adivinar por qué. */
        if (!document.documentElement.hasAttribute('data-nube-tema')) {
            aviso(t('sinRegenerar'));
        }
        enchufar();
        vigilarGuardado();
        if (typeof renderShareBar === 'function') {
            try { renderShareBar = pintarBarra; } catch (e) {}
        }
        docListo = adoptar().then(function (como) {
            pintarBarra();
            if (como === 'sembrado') {
                aviso(t('sembrado'));
            }
        }).catch(function (err) {
            SFS.healthy = false;
            pintarBarra();
            aviso(t('noLeyoEstado', { error: err.message }));
        }).then(function () {
            archivar(alArrancar);
            // Pohua comprueba cuáles de estos RFQ ya se dictaminaron.
            aPohuaDirecto({ source: 'isc-nube', tipo: 'rfqs-guardados',
                            ids: rfqsGuardados() });
        });
    });
})();
