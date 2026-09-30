/**
 * La ventana de revisión del Plant Manager.
 *
 * Una sola vista con todo lo que hace falta para dictaminar un RFQ sin abrir
 * la cotización completa: qué pide el cliente, lo que el sistema extrajo del
 * correo y del plano, los avisos de factibilidad, y los TRAMOS ya costeados
 * —precio por pieza, margen, cascada de costes, material, ruta y totales—,
 * uno por cada cantidad que venía en el correo.
 *
 * Dos caras, un mismo DOM:
 *
 *   - Compu (> 768 px): una caja compacta en el centro, con pestañas por
 *     tramo, cinco fichas de cascada y tres columnas.
 *   - Teléfono (≤ 768 px): pantalla completa, una sola columna, los tramos
 *     como tarjetas, la cascada como lista y los botones de 44 px al pie.
 *
 * Quién la abre:
 *
 *   - El botón «Revisar» del detalle del RFQ llama a `Revision.abrir(id)`.
 *     Un RFQ se abre siempre por su ficha (la campana, la cola del Resumen,
 *     «Requiere atención» y los enlaces `#/rfq/<id>` llevan ahí).
 *
 * Qué hace cada botón:
 *
 *   - Approve      → POST /approve    (el flujo de aprobación sigue después)
 *   (Sin «Send back»: el PM también cotiza —con la calculadora completa—,
 *   así que corrige él mismo en vez de devolver. El endpoint sigue existiendo.)
 *   - Decline      → POST /decline    (con motivo; avisa al cliente)
 *   - Open full quote → la pantalla de cotización completa.
 *
 * Los números NO se calculan aquí: vienen costeados del servidor, con el
 * catálogo de Neon. Si al catálogo le faltó algo (precio del alambre, tarifa
 * de máquina), `costeo.completo` viene en falso y la ventana lo dice en la
 * franja ámbar en vez de enseñar una cifra como si fuera fiable.
 */
const Revision = (() => {
    'use strict';

    let capa = null;        // el velo con la ventana dentro, o null
    let datos = null;       // lo que devolvió /revision
    let tramoActivo = 0;    // índice del tramo elegido
    let ocupado = false;    // una acción en curso: los botones se bloquean
    let rfqAbierto = null;  // para no reabrir la misma dos veces

    // ------------------------------------------------------------ utilidades

    function esc(v) {
        return String(v == null ? '' : v)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function t(clave, sustituciones) {
        let texto = I18N.t(clave);
        if (sustituciones) {
            for (const [k, v] of Object.entries(sustituciones)) {
                texto = texto.replace(new RegExp('\\{' + k + '\\}', 'g'), v);
            }
        }
        return texto;
    }

    function esNum(v) { return typeof v === 'number' && isFinite(v); }

    /** $ con tantos decimales como pida la cifra: $0.8658/pc, $12.50, $1,234. */
    function dinero(v, dec) {
        if (!esNum(v)) return '—';
        if (dec == null) dec = Math.abs(v) < 10 ? 4 : (Math.abs(v) < 1000 ? 2 : 0);
        return '$' + v.toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec });
    }

    function pct(v, dec) {
        if (!esNum(v)) return '—';
        return v.toFixed(dec == null ? 1 : dec) + '%';
    }

    function num(v, dec) {
        if (!esNum(v)) return '—';
        return v.toLocaleString(undefined, { minimumFractionDigits: dec || 0, maximumFractionDigits: dec == null ? 3 : dec });
    }

    function entero(v) {
        return esNum(v) ? Math.round(v).toLocaleString() : '—';
    }

    function claseEstado(estado) {
        if (typeof RFQTable !== 'undefined' && RFQTable.badgeClass) return RFQTable.badgeClass(estado);
        return { New: 'badge-new', RequiresReview: 'badge-review', Incomplete: 'badge-review',
                 Approved: 'badge-approved', Declined: 'badge-declined' }[estado] || '';
    }

    function tipoResorte(codigo) {
        // 'Compresion', 'compression', 'torsión'…: I18N sabe normalizarlos.
        return I18N.tipoResorte ? I18N.tipoResorte(codigo) : (codigo || '');
    }

    /** Mayúsculas en el idioma puesto (para los rótulos en versalitas). */
    function MAY(clave, vars) { return t(clave, vars).toLocaleUpperCase(I18N.locale); }

    // ------------------------------------------------------------- avisos

    /** Todo lo que el PM tiene que saber antes de fiarse del número. */
    function avisos(d) {
        const lista = [];
        const f = d.factibilidad || {};
        const c = d.costeo || {};
        const tramo = (d.tramos || [])[tramoActivo];

        // Lo primero, lo del Spring Engineering Calculator: si la planta no
        // puede enrollar el resorte, nada de lo que viene debajo importa.
        if (typeof SpringCalc !== 'undefined') {
            for (const a of SpringCalc.items(d.spring_calc)) lista.push(a);
        }
        if (d.error_costeo) lista.push({ nivel: 'error', texto: t('rev.aviso.errorCosteo') + ' ' + d.error_costeo });
        if (!c.completo) {
            for (const m of motivosDelCosteo(c)) lista.push({ nivel: 'warn', texto: m });
            if (!(c.faltantes || []).length && (d.tramos || []).length) {
                lista.push({ nivel: 'warn', texto: t('rev.aviso.incompleto') });
            }
        }
        for (const m of (c.banderas_motor || [])) if (m) lista.push({ nivel: 'warn', texto: m });
        if (tramo && tramo.avisos) {
            if (tramo.avisos.bajo_piso) lista.push({ nivel: 'warn', texto: t('rev.aviso.bajoPiso') });
            if (tramo.avisos.bajo_contribucion) lista.push({ nivel: 'warn', texto: t('rev.aviso.bajoContribucion') });
            if (tramo.avisos.scrap) lista.push({ nivel: 'warn', texto: t('rev.aviso.scrap') });
        }
        if (tramo && tramo.material && tramo.material.moq_manda) {
            lista.push({ nivel: 'info', texto: t('rev.aviso.moq') });
        }
        for (const m of (f.motivos || [])) {
            // Los del motor de factibilidad vienen con su código; se dicen en
            // el idioma puesto igual que los del costeo.
            const texto = typeof m === 'string' ? m
                : (m && m.codigo) ? I18N.motivo('factib.', m)
                : ((m && (m.texto || m.motivo || m.mensaje)) || JSON.stringify(m));
            lista.push({ nivel: 'info', texto });
        }
        for (const campo of (d.campos_faltantes || [])) {
            lista.push({ nivel: 'warn', texto: t('rev.aviso.campoFalta', { campo }) });
        }
        return lista;
    }

    /**
     * Los motivos del costeo, en el idioma de Pohua.
     *
     * El servidor los manda de dos formas: la frase ya armada (siempre en
     * español, que es la que va al registro) y la misma con su CÓDIGO y sus
     * datos. Él no sabe en qué idioma está la pantalla —y el mismo RFQ lo
     * abren personas distintas—, así que la frase se arma aquí. Sin la lista
     * con códigos, o con un código que esta versión no conozca, se usa la
     * frase del servidor: mejor en español que un hueco.
     */
    function motivosDelCosteo(costeo) {
        const conCodigo = costeo.faltantes_i18n;
        if (!Array.isArray(conCodigo) || !conCodigo.length) {
            return costeo.faltantes || [];
        }
        return conCodigo.map((m) => traducirMotivo(m));
    }

    /** Un motivo suelto: por código si se conoce, y si no, tal como vino.
     *
     * Pasa por `I18N.motivo`, el mismo que traduce los del motor de
     * factibilidad: así `{campo}` se resuelve al nombre de la cota en el
     * idioma puesto —"número de espiras" y no "numero_espiras_totales"— sin
     * tener dos traductores que se van separando. */
    function traducirMotivo(m) {
        if (!m) return '';
        if (typeof m === 'string') return m;
        return I18N.motivo('costeo.', m) || m.texto || m.codigo || '';
    }

    function qtyCorta(v) {
        if (!esNum(v)) return '—';
        if (v >= 1000000) return (v / 1000000).toFixed(v % 1000000 ? 1 : 0) + 'M';
        if (v >= 1000) return Math.round(v / 1000) + 'k';
        return String(v);
    }

    // ------------------------------------------------------------- plantilla

    function cabecera(d) {
        const r = d.rfq || {};
        const pn = r.part_number || '—';
        const tipo = tipoResorte(r.tipo_resorte) || t('rev.tipo.compresion');
        const quoteNum = r.quote_number || r.rfq_id || '—';
        const cliente = r.customer || '—';
        return `
            <div class="revision-cab">
                <div class="revision-cab-izq">
                    <span class="revision-cab-pn">${esc(pn)}</span>
                    <span class="revision-cab-sep">·</span>
                    <span class="revision-cab-tipo">${esc(tipo)}</span>
                </div>
                <div class="revision-cab-meta">${esc(t('rev.cotizacion', { n: quoteNum }))} · ${esc(cliente)}</div>
                <button type="button" class="revision-cerrar" data-accion="cerrar" aria-label="${esc(t('rev.cerrar'))}">&times;</button>
            </div>`;
    }

    /** La máquina que enrolla el resorte: la primera de la ruta que es
        COILER (o la primera, si ninguna dice su familia). Es la pregunta que
        hace el PM antes que ninguna: «¿en qué la vamos a hacer?». */
    function bobinadora(d) {
        for (const tr of (d.tramos || [])) {
            const ruta = tr.ruta || [];
            const op = ruta.find(o => String(o.familia || '').toUpperCase() === 'COILER') || ruta[0];
            if (op && op.maquina) return op.maquina;
        }
        return null;
    }

    function familia(op) {
        const f = String((op && op.familia) || '').toUpperCase();
        if (f === 'COILER') return t('rev.fam.coiler');
        if (f === 'SECONDARY') return t('rev.fam.secundaria');
        return f ? f.charAt(0) + f.slice(1).toLowerCase() : '';
    }

    /** «Cotizado por el PM en la calculadora · hora»: de dónde salen los números. */
    function origenDelCosteo(d) {
        const c = d.costeo || {};
        if (c.origen !== 'calculadora' || !c.pm) return '';
        const pm = c.pm;
        let cuando = '';
        try {
            if (pm.en) {
                cuando = new Date(pm.en).toLocaleString((typeof I18N.idioma === 'string' ? I18N.idioma : undefined),
                    { dateStyle: 'short', timeStyle: 'short' });
            }
        } catch (_) { cuando = pm.en || ''; }
        const quien = pm.por ? esc(String(pm.por).split('@')[0]) : '';
        const numero = pm.numero ? ` · ${esc(pm.numero)}` : '';
        const ver = pm.version ? ` · v${esc(pm.version)}` : '';
        return `<span class="revision-pill revision-pill--pm" title="${esc(t('rev.pm.ayuda'))}">
                    ${esc(t('rev.pm.cotizado'))}${ver}${quien ? ` · ${quien}` : ''}${cuando ? ` · ${esc(cuando)}` : ''}${numero}
                </span>`;
    }

    // ------------------------------------------------------------ versiones

    /*
     * Las versiones que el PM trajo de la calculadora, para escoger.
     *
     * Cada vez que el PM vuelve de la calculadora queda una versión fijada
     * (app/rfq/versiones_pm.py). Aquí se ven todas —cuándo, quién, el precio
     * de cada tramo— y se escoge cuál vale: la ventana, la oferta y la
     * calculadora pasan a usar ésa. También se puede volver al cálculo del
     * sistema sin perder ninguna.
     */
    let versionesAbiertas = false;

    function botonVersiones(d) {
        const v = (d.versiones_pm && d.versiones_pm.versiones) || [];
        if (!v.length) return '';
        // El menú cuelga del botón y flota encima de la ventana: abrirlo no
        // empuja los tramos ni la cascada hacia abajo.
        return `<span class="revision-ver-ancla">
                <button type="button" class="revision-pill revision-pill--versiones"
                        data-accion="versiones" aria-haspopup="true" aria-expanded="${versionesAbiertas}">
                    ${esc(t('rev.ver.boton', { n: v.length }))} ${versionesAbiertas ? '▴' : '▾'}
                </button>
                ${menuVersiones(d)}
            </span>`;
    }

    function cuandoCorto(iso) {
        if (!iso) return '';
        try {
            return new Date(iso).toLocaleString((typeof I18N.idioma === 'string' ? I18N.idioma : undefined),
                { dateStyle: 'short', timeStyle: 'short' });
        } catch (_) { return iso; }
    }

    function menuVersiones(d) {
        const info = d.versiones_pm || {};
        const lista = info.versiones || [];
        if (!versionesAbiertas || !lista.length) return '';
        const puede = API.puede('rfq:dictaminar') && !(d.rfq && ['Approved', 'Declined'].includes(d.rfq.estado));
        // Toda la fila es el botón: un toque y queda escogida. La que está en
        // uso se marca y no se puede volver a tocar.
        const opcion = (valor, enUso, cabeza, detalle, precios) => {
            const marca = enUso
                ? `<span class="revision-ver-marca revision-ver-marca--uso">${esc(t('rev.ver.enUso'))}</span>`
                : (puede ? `<span class="revision-ver-usar">${esc(t('rev.ver.usar'))}</span>` : '');
            const dentro = `
                <span class="revision-ver-cab"><b>${cabeza}</b><span>${detalle}</span></span>
                <span class="revision-ver-accion">${marca}</span>
                ${precios ? `<span class="revision-ver-precios">${precios}</span>` : ''}`;
            return enUso || !puede
                ? `<li class="revision-ver-fila ${enUso ? 'en-uso' : ''}" role="menuitemradio" aria-checked="${enUso}">${dentro}</li>`
                : `<li><button type="button" class="revision-ver-fila" role="menuitemradio" aria-checked="false"
                        data-accion="usarVersion" data-version="${esc(valor)}">${dentro}</button></li>`;
        };
        const filas = lista.map((v) => {   // la más nueva arriba (así llegan)
            const precios = (v.precios || []).map((p, i) => {
                const q = (v.cantidades || [])[i];
                return `<span class="revision-ver-precio">${q ? esc(entero(q)) + ' · ' : ''}${esNum(p) ? dinero(p, 4) : '—'}</span>`;
            }).join('');
            const quien = v.por ? esc(String(v.por).split('@')[0]) : '';
            const detalle = `${esc(cuandoCorto(v.en))}${quien ? ' · ' + quien : ''}`
                + (v.fijada ? '' : ` · <i>${esc(t('rev.ver.enCurso'))}</i>`);
            return opcion(v.n, v.en_uso, 'v' + esc(v.n), detalle, precios);
        }).join('');
        const sistema = opcion('', info.sistema_en_uso, esc(t('rev.ver.sistema')), esc(t('rev.ver.sistemaAyuda')), '');
        return `<div class="revision-ver-menu" role="menu" aria-label="${esc(t('rev.ver.titulo'))}">
                <div class="revision-ver-titulo">${esc(t('rev.ver.titulo'))}</div>
                <ul class="revision-ver-lista">${filas}${sistema}</ul>
            </div>`;
    }

    // El menú nace pegado a la izquierda del botón; si el botón quedó a la
    // derecha, el menú se saldría de la ventana (que recorta): se corre a la
    // izquierda lo justo para caber.
    function encajarMenu() {
        const menu = capa && capa.querySelector('.revision-ver-menu');
        const cuerpo = capa && capa.querySelector('.revision-cuerpo');
        if (!menu || !cuerpo) return;
        const caja = cuerpo.getBoundingClientRect();
        const r = menu.getBoundingClientRect();
        const margen = 12;
        const sobra = r.right - (caja.right - margen);
        if (sobra > 0) {
            menu.style.left = -Math.min(sobra, r.left - caja.left - margen) + 'px';
        }
    }

    async function usarVersion(valor) {
        if (!API.puede('rfq:dictaminar')) { Toast.error(I18N.t('aviso.sinPermisoRfq')); return; }
        const version = valor === '' || valor === undefined || valor === null ? null : Number(valor);
        bloquear(true);
        try {
            const nuevo = await API.rfqUsarVersionPM(rfqAbierto, version);
            if (!capa) return;
            datos = nuevo;
            versionesAbiertas = false;
            ultimoCosteo = huellaDelCosteo(datos);
            if (tramoActivo >= (datos.tramos || []).length) tramoActivo = 0;
            pintar();
            Toast.success(version === null ? t('rev.ver.usandoSistema') : t('rev.ver.usando', { n: version }));
            // La calculadora que tenga este RFQ abierto (aquí o en otra
            // pestaña) carga la versión escogida ahora mismo.
            API.avisarRfq('version', rfqAbierto, { version });
        } catch (err) {
            if (!(err && err.sesionExpirada)) Toast.error(err.message);
        } finally {
            bloquear(false);
        }
    }

    function comunes(d) {
        const c = d.comunes || {};
        const mat = c.material ? (esc(c.material) + (c.material_nombre ? ` — ${esc(c.material_nombre)}` : '')) : '—';
        const maq = bobinadora(d);
        return `
            <section class="revision-comunes" aria-label="${esc(t('rev.todosTramos'))}">
                <div class="revision-rotulo">${esc(t('rev.todosTramos'))}</div>
                <div class="revision-pills">
                    ${origenDelCosteo(d)}
                    ${botonVersiones(d)}
                    <span class="revision-pill revision-pill--maquina ${maq ? '' : 'revision-pill--falta'}"
                          title="${esc(t('rev.maquinaAyuda'))}">
                        ${esc(t('rev.maquina'))}: <b>${maq ? esc(maq) : esc(t((d.costeo || {}).no_producible ? 'rev.sinMaquinaNoProducible' : 'rev.sinMaquina'))}</b>
                    </span>
                    <!-- Los datos del alambre: en la compu, en la misma fila; en
                         el teléfono, una tira que se desliza (ver style.css). -->
                    <span class="revision-pills-datos">
                    <span class="revision-pill">${mat}</span>
                    <span class="revision-pill">Ø ${esNum(c.dia_in) ? num(c.dia_in, 3) + ' in' : '—'}</span>
                    <span class="revision-pill">${esNum(c.peso_lb_pc) ? num(c.peso_lb_pc, 3) + ' lb/' + esc(t('rev.pza')) : '—'}</span>
                    <span class="revision-pill">${esc(t('rev.base'))} ${esNum(c.base_lb) ? dinero(c.base_lb, 2) + '/lb' : '—'}</span>
                    ${esNum(c.surcharge_lb) && c.surcharge_lb > 0 ? `<span class="revision-pill">${esc(t('rev.surcharge'))} ${dinero(c.surcharge_lb, 2)}/lb</span>` : `<span class="revision-pill">${esc(t('rev.surcharge'))} $0.00/lb</span>`}
                    </span>
                </div>
            </section>`;
    }

    function pestanas(d) {
        const tramos = d.tramos || [];
        if (!tramos.length && (d.costeo || {}).no_producible) {
            // Sin máquina que lo enrolle no se produce, y no se costea.
            return `<div class="revision-sin-tramos revision-sin-tramos--bloqueo">${esc(t('rev.sinTramosNoProducible'))}</div>`;
        }
        if (!tramos.length) {
            const cantidades = (d.cantidades || []).map(entero).join(' · ');
            return `<div class="revision-sin-tramos">${esc(t('rev.sinTramos'))}${cantidades ? ` <b>${cantidades}</b>` : ''}</div>`;
        }
        return `
            <div class="revision-tramos" role="tablist" aria-label="${esc(t('rev.tramos'))}">
                ${tramos.map((tr, i) => `
                    <button type="button" role="tab" class="revision-tramo-card ${i === tramoActivo ? 'activo' : ''}"
                            data-tramo="${i}" aria-selected="${i === tramoActivo}">
                        <div class="revision-tramo-cab">
                            <span class="revision-tramo-tit">${esc(t('rev.tramo', { n: i + 1 }))}${i === 0 ? ' ★' : ''} · </span>
                            <span class="qty-larga">${entero(tr.cantidad)} ${esc(t('rev.pzas'))}</span>
                            <span class="qty-corta">${qtyCorta(tr.cantidad)}</span>
                        </div>
                        <div class="revision-tramo-cuerpo">
                            <span class="revision-tramo-precio">
                                <span class="precio-largo">${dinero(tr.precio_pc)}/${esc(t('rev.pza'))}</span>
                                <span class="precio-corto">${dinero(tr.precio_pc)}</span>
                            </span>
                            <span class="revision-tramo-margen">${pct(tr.resultado_pct)}</span>
                        </div>
                    </button>`).join('')}
            </div>`;
    }

    function franja(lista) {
        if (!lista.length) return '';
        const nivel = lista.some(a => a.nivel === 'error') ? 'error'
                    : lista.some(a => a.nivel === 'warn') ? 'warn' : 'info';
        return `
            <div class="revision-franja revision-franja--${nivel}" role="status">
                <span class="revision-franja-icono">⚠</span>
                <ul class="revision-franja-texto">
                    ${lista.map(a => `<li>${esc(a.texto)}</li>`).join('')}
                </ul>
            </div>`;
    }

    function cascada(tr) {
        const c = (tr && tr.cascada) || {};
        const targetPct = tr && tr.objetivo_pct != null ? pct(tr.objetivo_pct, 0) : '20%';
        const llega = tr && tr.llega;
        const resClase = llega ? 'revision-cascada--ok' : 'revision-cascada--corto';
        return `
            <div class="revision-cascada-wrap">
                <div class="revision-cascada-tit-movil">
                    ${esc(MAY('rev.cascada'))} · ${esc(MAY('rev.porPieza'))} · ${entero(tr ? tr.cantidad : 0)} ${esc(MAY('rev.pzas'))}
                </div>
                <!-- Desktop 5 columns -->
                <div class="revision-cascada-grid">
                    <div class="revision-cascada-col">
                        <span class="revision-cascada-lbl">${esc(MAY('rev.sell'))}</span>
                        <span class="revision-cascada-val">${dinero(c.sell)}</span>
                        <span class="revision-cascada-sub">100%</span>
                    </div>
                    <div class="revision-cascada-col">
                        <span class="revision-cascada-lbl">AV</span>
                        <span class="revision-cascada-val">${dinero(c.av)}</span>
                        <span class="revision-cascada-sub">${pct(c.av_pct)}</span>
                    </div>
                    <div class="revision-cascada-col">
                        <span class="revision-cascada-lbl">C/CV</span>
                        <span class="revision-cascada-val">${dinero(c.ccv)}</span>
                        <span class="revision-cascada-sub">${pct(c.ccv_pct)}</span>
                    </div>
                    <div class="revision-cascada-col">
                        <span class="revision-cascada-lbl">C/CD</span>
                        <span class="revision-cascada-val">${dinero(c.ccd)}</span>
                        <span class="revision-cascada-sub">${pct(c.ccd_pct)}</span>
                    </div>
                    <div class="revision-cascada-col revision-cascada-col--resultado ${resClase}">
                        <span class="revision-cascada-lbl">${esc(MAY('rev.resultado'))} · ${esc(MAY('rev.objetivo'))} ${targetPct}</span>
                        <span class="revision-cascada-val">${dinero(c.resultado)}</span>
                        <span class="revision-cascada-sub">${pct(c.resultado_pct)}</span>
                    </div>
                </div>
                <!-- Mobile 5 rows -->
                <div class="revision-cascada-lista">
                    <div class="revision-cascada-fila">
                        <span class="revision-cascada-fila-lbl">${esc(t('rev.sell'))}</span>
                        <span class="revision-cascada-fila-val">${dinero(c.sell)}</span>
                        <span class="revision-cascada-fila-sub">100%</span>
                    </div>
                    <div class="revision-cascada-fila">
                        <span class="revision-cascada-fila-lbl">AV</span>
                        <span class="revision-cascada-fila-val">${dinero(c.av)}</span>
                        <span class="revision-cascada-fila-sub">${pct(c.av_pct)}</span>
                    </div>
                    <div class="revision-cascada-fila">
                        <span class="revision-cascada-fila-lbl">C/CV</span>
                        <span class="revision-cascada-fila-val">${dinero(c.ccv)}</span>
                        <span class="revision-cascada-fila-sub">${pct(c.ccv_pct)}</span>
                    </div>
                    <div class="revision-cascada-fila">
                        <span class="revision-cascada-fila-lbl">C/CD</span>
                        <span class="revision-cascada-fila-val">${dinero(c.ccd)}</span>
                        <span class="revision-cascada-fila-sub">${pct(c.ccd_pct)}</span>
                    </div>
                    <div class="revision-cascada-fila revision-cascada-fila--resultado ${resClase}">
                        <span class="revision-cascada-fila-lbl">${esc(t('rev.resultado'))} - ${esc(t('rev.objetivo'))} ${targetPct}</span>
                        <span class="revision-cascada-fila-val">${dinero(c.resultado)}</span>
                        <span class="revision-cascada-fila-sub">${pct(c.resultado_pct)}</span>
                    </div>
                </div>
            </div>`;
    }

    function columnas(tr) {
        const m = (tr && tr.material) || {};
        const ruta = (tr && tr.ruta) || [];
        const tot = (tr && tr.totales) || {};
        const horasTot = esNum(tot.horas) ? Math.round(tot.horas) : null;
        return `
            <div class="revision-columnas-grid">
                <section class="revision-bloque">
                    <h4 class="revision-bloque-tit">${esc(MAY('rev.materialTramo'))}</h4>
                    <div class="revision-fila-dato">
                        <span class="revision-fila-lbl">
                            <span class="lbl-desktop">$/${esc(t('rev.pza'))}</span>
                            <span class="lbl-movil">${esc(t('rev.materialPc'))}</span>
                        </span>
                        <span class="revision-fila-val">
                            ${esNum(m.pc) ? `<b>${dinero(m.pc)}</b> <small>· ${pct(m.pct)}</small>` : '—'}
                        </span>
                    </div>
                    <div class="revision-fila-dato">
                        <span class="revision-fila-lbl">${esc(t('rev.alambre'))}</span>
                        <span class="revision-fila-val">
                            <b>${esNum(m.lb_comprar) ? num(m.lb_comprar, 0) + ' lb' : '—'}</b>
                        </span>
                    </div>
                    ${m.moq_manda ? `<div class="revision-nota">${esc(t('rev.aviso.moq'))}</div>` : ''}
                </section>

                <section class="revision-bloque">
                    <h4 class="revision-bloque-tit">
                        <span class="lbl-desktop">${esc(MAY('rev.ruta'))}${horasTot ? ` · ${horasTot} ${esc(MAY('rev.maquinaH'))}` : ''}</span>
                        <span class="lbl-movil">${esc(MAY('rev.ruta'))}${horasTot ? ` · ${horasTot} ${esc(MAY('rev.horas'))}` : ''}</span>
                    </h4>
                    ${ruta.length ? ruta.map((op, i) => `
                        <div class="revision-op">
                            <div class="revision-op-cab">
                                <span class="revision-op-num">${i + 1}</span>
                                <span class="revision-op-maq">${esc(op.maquina || '—')}</span>
                                ${familia(op) ? `<span class="revision-op-fam revision-op-fam--${esc(String(op.familia || '').toLowerCase())}">${esc(familia(op))}</span>` : ''}
                            </div>
                            <div class="revision-op-datos">
                                <span>${esNum(op.pph) ? num(op.pph, 0) + ' ' + esc(t('rev.pza')) + '/h' : '—'}</span>
                                <span>${esc(t('rev.setup'))} ${esNum(op.setup_h) ? num(op.setup_h, 1) + ' h' : '—'}</span>
                                ${esNum(op.costo_h) ? `<span>${dinero(op.costo_h, 2)}/h</span>` : ''}
                            </div>
                        </div>`).join('') : `<div class="revision-nota">${esc(t('rev.sinRuta'))}</div>`}
                </section>

                <section class="revision-bloque">
                    <h4 class="revision-bloque-tit">${esc(MAY('rev.totalesTramo'))}</h4>
                    <div class="revision-fila-dato">
                        <span class="revision-fila-lbl">${esc(t('rev.ingreso'))}</span>
                        <span class="revision-fila-val">
                            <b>${dinero(tot.ingreso, 0)}</b>
                        </span>
                    </div>
                    <div class="revision-fila-dato">
                        <span class="revision-fila-lbl">
                            <span class="lbl-desktop">${esc(t('rev.ccvHora'))}</span>
                            <span class="lbl-movil">${esc(t('rev.ccvHoraLargo'))}</span>
                        </span>
                        <span class="revision-fila-val">
                            <b>${esNum(tot.ccv_hora) ? dinero(tot.ccv_hora, 2) : '—'}</b>
                        </span>
                    </div>
                </section>
            </div>`;
    }

    function pie(d) {
        const r = d.rfq || {};
        const puede = d.puede_dictaminar && API.puede('rfq:dictaminar');
        const abierto = r.estado === 'RequiresReview' || r.estado === 'New' || r.estado === 'Incomplete';
        const icono = `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`;

        // Dos grupos, y la raya entre ellos es lo que importa: a la izquierda
        // lo que sólo MIRA —el PDF y la cotización entera—, a la derecha lo
        // que DECIDE. En una sola fila, "ver el PDF" quedaba pegado a
        // "Aprobar", que es un clic entre enterarse y cerrar la cotización.
        const ver = [
            `<button type="button" class="btn revision-btn revision-btn--fantasma" data-accion="pdf">${icono}${esc(t('rev.previewPdf'))}</button>`,
            `<button type="button" class="btn revision-btn revision-btn--fantasma" data-accion="cotizar">${esc(t(r.estado === 'Approved' ? 'rev.abrirOferta' : 'rev.abrirCompleta'))}</button>`,
        ];
        // Sin «Devolver» (ISC, 2026-09-27): el PM también cotiza, así que no
        // hay a quién devolverle el RFQ. Si algo no cuadra, lo corrige él en
        // la cotización completa y vuelve a esta ventana.
        const decidir = [];
        if (puede && r.estado !== 'Declined') {
            decidir.push(`<button type="button" class="btn revision-btn revision-btn--suave" data-accion="declinar">${esc(t('rev.declinar'))}</button>`);
        }
        // Lo que el Spring Calc dice que no se puede fabricar no se aprueba:
        // el botón sigue a la vista —para que se entienda que existe y por qué
        // no se puede— pero deshabilitado. El servidor lo rechaza también.
        const hayCalc = !d.esCotizacion && typeof SpringCalc !== 'undefined';
        const noFactible = hayCalc && SpringCalc.bloquea(d.spring_calc);
        // Si ya lo cotizó a mano en la cotización completa, Aprobar vuelve:
        // la factibilidad es suya, y se le recuerda al pie.
        const notaPm = hayCalc && SpringCalc.intervencion(d.spring_calc) ? t('rev.aprobarConPm') : '';
        if (puede && abierto) {
            // La verde, la última: a la derecha en la compu y abajo en el
            // teléfono, donde llega el pulgar y donde termina la lectura.
            decidir.push(noFactible
                ? `<button type="button" class="btn btn-success revision-btn revision-btn--bloqueado" data-accion="aprobar" disabled aria-disabled="true" title="${esc(t('rev.noAprobable'))}">${esc(t('rev.aprobar'))}</button>`
                : `<button type="button" class="btn btn-success revision-btn" data-accion="aprobar">${esc(t('rev.aprobar'))}</button>`);
        }

        return `
            <div class="revision-pie">
                ${puede && abierto ? `<div class="revision-pie-nota${noFactible ? ' revision-pie-nota--bloqueo' : (notaPm ? ' revision-pie-nota--pm' : '')}">${noFactible ? esc(t('rev.noAprobable')) : esc(notaPm)}</div>`
                    : `<div class="revision-pie-nota">${esc(puede ? t('rev.pieCerrado') : t('rev.pieSoloLectura'))}</div>`}
                <div class="revision-acciones">
                    <div class="revision-grupo revision-grupo--ver">${ver.join('')}</div>
                    ${decidir.length ? `<div class="revision-grupo revision-grupo--decidir">${decidir.join('')}</div>` : ''}
                </div>
            </div>`;
    }

    /**
     * La geometría con la que se está dictaminando, y editable.
     *
     * Por qué editable y por qué AQUÍ: el veredicto se calculaba una sola vez,
     * al entrar el correo, y se quedaba grabado. El PM mira el dibujo, ve que
     * el modelo leyó 1.6 donde dice 1.8, y antes esa corrección no tenía
     * dónde ir: o dictaminaba sobre un dato que sabe malo, o lo corregía en la
     * calculadora y el RFQ se quedaba con el valor viejo.
     *
     * Los campos son los que mueven el dictamen y el costeo. Nada más: por
     * aquí entra lo que alguien escribe en un formulario, y la lista de lo que
     * puede tocar la cierra el servidor (app/rfq/recalculo.py).
     */
    // Ya no se pinta (2026-09-26, a petición de ventas): las cotas se corrigen
    // en la calculadora completa, que es de donde salen los números. Se deja
    // la función por si el apartado vuelve.
    function geometria(d) {
        const g = d.resorte || {};
        const puede = d.puede_dictaminar && API.puede('rfq:dictaminar');
        const lec = d.lectura_plano;

        const campo = (clave, etiqueta, valor, unidad) => `
            <label class="revision-campo">
                <span class="revision-campo-et">${esc(etiqueta)}${unidad ? ` <i>${esc(unidad)}</i>` : ''}</span>
                <input type="text" inputmode="decimal" data-campo="${esc(clave)}"
                       value="${valor === null || valor === undefined ? '' : esc(valor)}"
                       ${puede ? '' : 'disabled'}>
            </label>`;

        // Por qué la tarjeta está vacía, cuando lo está: es la diferencia
        // entre "el correo no traía plano" y "traía uno y ni se miró".
        let nota = '';
        if (lec && lec.estado && lec.estado !== 'leido') {
            const ficheros = (lec.ficheros || []).join(', ');
            if (lec.estado === 'sin_adjunto') nota = t('plano.sinAdjunto');
            else if (lec.estado === 'formato_no_leido') {
                nota = t('plano.sinFormato', { ficheros, soportados: (lec.soportados || []).join(', ') });
            } else if (lec.estado === 'fallo') {
                nota = t('plano.fallo', { ficheros, motivo: lec.motivo || '' });
            }
        }

        const ajustado = g.ajustado_por
            ? `<span class="revision-ajustado">${esc(t('rev.ajustadoPor', { quien: g.ajustado_por }))}</span>` : '';

        /* Lo que el lector anotó del plano. Se le piden en el prompt —"anota
           cualquier ambigüedad, texto ilegible o supuesto"— y hasta ahora se
           guardaban sin que las viera nadie. Van aquí, pegadas a las cotas
           que comentan, porque es donde el PM decide si corrige un número,
           manda releer o le pregunta al cliente. */
        /* Las totales deducidas de las activas. La casilla se deja VACÍA a
           propósito: lo que el PM escriba ahí se guarda como leído del plano,
           y este número no lo es. Se enseña debajo, con el método, para que
           se vea que el peso ya está resuelto y nadie lo teclee encima —si
           teclea las activas creyendo que son las totales, el peso sale corto
           y el precio con él—. */
        const deducidas = (g.espiras_calculadas && g.espiras_origen)
            ? `<p class="revision-geo-deducido">${esc(t('rev.espirasDeducidas', {
                   n: g.espiras_calculadas, metodo: g.espiras_origen }))}</p>`
            : '';

        const avisos = (g.advertencias || []).filter(Boolean);
        const avisosHtml = avisos.length ? `
            <ul class="revision-geo-avisos">
                ${avisos.map(a => `<li>${esc(a)}</li>`).join('')}
            </ul>` : '';

        return `
            <section class="revision-bloque revision-geo">
                <h4>${esc(t('rev.geometria'))}${ajustado}</h4>
                ${nota ? `<p class="revision-geo-nota">${esc(nota)}</p>` : ''}
                ${avisosHtml}
                <div class="revision-campos">
                    ${campo('diametro_alambre_mm', t('ficha.alambre'), g.diametro_alambre_mm, 'mm')}
                    ${campo('diametro_exterior_mm', t('ficha.exterior'), g.diametro_exterior_mm, 'mm')}
                    ${campo('longitud_libre_mm', t('ficha.libre'), g.longitud_libre_mm, 'mm')}
                    ${campo('numero_espiras_totales', t('ficha.espiras'), g.espiras_totales, '')}
                    ${campo('material', t('ficha.material'), g.material_texto || '', '')}
                </div>
                ${deducidas}
                ${puede ? `<div class="revision-geo-acciones">
                    <button type="button" class="btn btn-secondary revision-btn" data-accion="leerPlano">${esc(t('plano.releer'))}</button>
                    <button type="button" class="btn btn-primary revision-btn" data-accion="recalcular">${esc(t('rev.recalcular'))}</button>
                </div>
                <p class="revision-geo-pie">${esc(t('rev.recalcularNota'))}</p>` : ''}
            </section>`;
    }

    function plantilla(d) {
        const tr = (d.tramos || [])[tramoActivo];
        const r = d.rfq || {};
        return `
            <div class="revision" role="dialog" aria-modal="true" aria-labelledby="revisionTitulo">
                ${cabecera(d)}
                <div class="revision-cuerpo">
                    ${comunes(d)}
                    ${pestanas(d)}
                    ${franja(avisos(d))}
                    ${tr ? cascada(tr) + columnas(tr) : ''}
                    ${r.notas ? `<section class="revision-bloque revision-notas"><h4>${esc(t('rev.notas'))}</h4><pre>${esc(r.notas)}</pre></section>` : ''}
                </div>
                ${pie(d)}
            </div>`;
    }


    // ------------------------------------------------------------- acciones

    function bloquear(si) {
        ocupado = si;
        if (!capa) return;
        capa.querySelectorAll('.revision-btn').forEach(b => {
            // El Aprobar de un resorte no fabricable no se vuelve a habilitar
            // al terminar otra acción.
            b.disabled = si || b.classList.contains('revision-btn--bloqueado');
        });
        capa.classList.toggle('ocupado', si);
    }

    /**
     * Rehace el dictamen con lo que haya escrito el PM.
     *
     * `conPlano` es el botón «Leer el plano con IA»: relee el dibujo aunque el
     * resorte ya tenga cotas, porque el PM puede querer las del dibujo
     * justamente porque duda de las que hay.
     *
     * Lo que se manda son SÓLO los campos que cambiaron. Mandar el formulario
     * entero haría que cada recálculo marcara el resorte como "ajustado por
     * una persona" aunque nadie tocara nada, y se perdería la distinción entre
     * lo que leyó la IA y lo que corrigió el PM.
     */
    async function recalcular(conPlano) {
        if (!API.puede('rfq:dictaminar')) { Toast.error(I18N.t('aviso.sinPermisoRfq')); return; }
        if (!rfqAbierto || (datos && datos.esCotizacion)) return;

        const previo = (datos && datos.resorte) || {};
        const equivalencias = { numero_espiras_totales: 'espiras_totales',
                                material: 'material_texto' };
        const ajustes = {};
        capa.querySelectorAll('[data-campo]').forEach((entrada) => {
            const clave = entrada.dataset.campo;
            const escrito = entrada.value.trim();
            const antes = previo[equivalencias[clave] || clave];
            const antesTexto = (antes === null || antes === undefined) ? '' : String(antes);
            if (escrito === antesTexto) return;
            // Vaciar un campo a propósito se dice con "-": una cadena vacía es
            // "no lo mandé", y borraría sin querer lo que el modelo sí leyó.
            ajustes[clave] = escrito === '' ? '-' : escrito;
        });

        bloquear(true);
        const boton = capa.querySelector(conPlano ? '[data-accion="leerPlano"]' : '[data-accion="recalcular"]');
        const antesTexto = boton ? boton.textContent : '';
        if (boton) boton.textContent = I18N.t(conPlano ? 'plano.releyendo' : 'rev.recalculando');
        try {
            const nuevo = await API.recalcularRfq(rfqAbierto, {
                ajustes, leer_plano: !!conPlano });
            datos = nuevo;
            if (tramoActivo >= (datos.tramos || []).length) tramoActivo = 0;
            pintar();

            const rec = nuevo.recalculo || {};
            const lec = nuevo.lectura_plano;
            if (conPlano && lec && lec.estado !== 'leido') {
                Toast.error(I18N.t('plano.fallo', {
                    ficheros: (lec.ficheros || []).join(', '), motivo: lec.motivo || '' }));
            } else if (rec.error) {
                Toast.error(rec.error);
            } else if ((rec.tocados || []).length) {
                Toast.success(I18N.t('rev.recalculado', { n: rec.tocados.length }));
            } else {
                Toast.success(I18N.t('rev.recalculadoSinCambios'));
            }
        } catch (err) {
            Toast.error(err.message);
        } finally {
            if (boton) boton.textContent = antesTexto;
            bloquear(false);
        }
    }

    async function aprobar() {
        if (!API.puede('rfq:dictaminar')) { Toast.error(I18N.t('aviso.sinPermisoRfq')); return; }
        if (datos && !datos.esCotizacion && typeof SpringCalc !== 'undefined'
                && SpringCalc.bloquea(datos.spring_calc)) {
            Toast.error(I18N.t('rev.noAprobable'));
            return;
        }
        const si = await Confirmar.pedir({
            titulo: I18N.t('dlg.aprobar.titulo'),
            mensaje: I18N.t('dlg.aprobar.mensaje'),
            aceptar: I18N.t('dlg.aprobar.si'),
            firme: true,        // sólo con un clic de verdad (ver confirmar.js)
        });
        if (!si) return;
        bloquear(true);
        try {
            if (datos && datos.esCotizacion) {
                const marco = document.getElementById('quotingMarco');
                if (marco && marco.contentWindow) {
                    const cw = marco.contentWindow;
                    if (typeof cw.Q === 'function') {
                        const q = cw.Q();
                        q.status = 'APPROVED';
                        q.outcome = 'NO RECEPTION';
                        if (typeof cw.nowStr === 'function') q.approvedAt = cw.nowStr();
                        if (cw.CUR) q.approvedBy = cw.CUR.email;
                        if (typeof cw.logUpsert === 'function') cw.logUpsert();
                        if (typeof cw.renderQuote === 'function') cw.renderQuote();
                        if (typeof cw.saveLocal === 'function') cw.saveLocal();
                        if (cw.SFS && typeof cw.SFS.write === 'function') cw.SFS.write();
                        if (typeof cw.fileApprovedPdf === 'function') cw.fileApprovedPdf(q);
                    }
                }
                Toast.success(I18N.t('aviso.rfqAprobada'));
                cerrar();
                return;
            }
            await API.approveRFQ(rfqAbierto, {});
            Toast.success(I18N.t('aviso.rfqAprobada'));
            const id = rfqAbierto;
            cerrar();
            // Aprobar no manda nada al cliente: la oferta sale con «Enviar
            // oferta». Se abre ya el envío, con el destinatario puesto, para
            // que no se quede en «Listo para Sales» sin que nadie lo mande.
            APP.navigate('quote-review', { id, enviar: '1' });
        } catch (err) {
            if (!err.sesionExpirada) Toast.error(err.message);
        } finally { bloquear(false); }
    }

    /**
     * Declinar: el único botón de esta ventana que sale de la empresa.
     *
     * Existía desde el principio —con su diálogo ya escrito en los tres
     * idiomas— y nunca llegó a haber una función detrás. El clic moría con un
     * `ReferenceError` en la consola y la pantalla no se inmutaba: ni un
     * aviso, ni un error, nada. El mismo fallo que tuvo `cotizar` en su día.
     *
     * Eso, en un botón que DECLINA, es de lo peor que puede pasar: quien lo
     * pulsaba se quedaba convencido de haber rechazado el RFQ, y el RFQ
     * seguía vivo esperando dictamen. El cliente, sin respuesta.
     *
     * Tres cosas que este botón sí hace ahora:
     *
     *  - Pide el motivo, y no sigue sin él. Se guarda en las notas del RFQ,
     *    que es donde lo va a buscar dentro de seis meses quien se pregunte
     *    por qué se rechazó esta pieza. El cliente NO lo lee: el correo de
     *    declinación es el machote de la empresa y no incluye la nota.
     *  - Avisa de que el correo sale y de que no se puede deshacer, con el
     *    diálogo en rojo.
     *  - Dice si el correo SALIÓ DE VERDAD. El servidor lo devuelve en
     *    `correo_enviado`, y puede ser que no: con el envío automático
     *    apagado, o sin remitente en el correo original, el RFQ queda
     *    declinado y el comprador sin enterarse. Callarlo sería dejar al PM
     *    creyendo que avisó.
     */
    async function declinar() {
        if (!API.puede('rfq:dictaminar')) { Toast.error(I18N.t('aviso.sinPermisoRfq')); return; }
        // La ventana también sirve para mirar un borrador de la calculadora,
        // y ahí no hay nada que declinar: no hay RFQ ni cliente a quien
        // escribir.
        if (datos && datos.esCotizacion) { Toast.warning(I18N.t('rev.sinDictamen')); return; }

        // `pedirTexto`, no `pedir`: `pedir` es un sí/no que tira el cuadro de
        // texto y resuelve true/false. Con él, cancelar resolvía `false`, que
        // pasaba el filtro de null y se mandaba como motivo: el RFQ quedaba
        // rechazado (o devuelto) con la nota «false».
        const motivo = await Confirmar.pedirTexto({
            titulo: I18N.t('dlg.rechazar.titulo'),
            mensaje: I18N.t('dlg.rechazar.mensaje'),
            aceptar: I18N.t('dlg.rechazar.si'),
            peligro: true,
            etiqueta: I18N.t('dlg.rechazar.motivo'),
            marcador: I18N.t('dlg.rechazar.ejemplo'),
            obligatorio: true,
        });
        if (typeof motivo !== 'string') return;      // canceló
        if (!String(motivo).trim()) {
            // Declinar sin decir por qué deja el rastro vacío justo donde más
            // falta hace. Se pide otra vez en vez de dejarlo pasar.
            Toast.warning(I18N.t('aviso.motivoHace'));
            return;
        }

        bloquear(true);
        const id = rfqAbierto;
        try {
            const r = await API.declineRFQ(id, { nota: String(motivo).trim() });
            cerrar();
            if (r && r.correo_enviado) {
                Toast.success(I18N.t('aviso.rfqRechazadaAviso'));
            } else {
                // No es un error: el dictamen quedó. Pero hay que decirlo.
                Toast.warning(I18N.t('aviso.rfqRechazadaSinCorreo'));
            }
            // Repinta la pantalla de debajo para que el RFQ salga ya con
            // su nuevo estado, sin que haya que recargar a mano.
            if (typeof APP !== 'undefined' && APP.handleRoute) APP.handleRoute();
        } catch (err) {
            if (!err.sesionExpirada) Toast.error(err.message);
        } finally { bloquear(false); }
    }

    /** La cotización entera: la calculadora, abierta con este RFQ dentro.

        "Completa" es literal: las dos hojas —Quote y Spring Calc— con lo que
        el sistema sacó del correo y del plano ya puesto en cada casilla. Antes
        llevaba a la pantalla de la oferta, que es el resultado y no el
        trabajo; y antes de eso ni siquiera existía —el botón la llamaba, el
        clic moría con un ReferenceError y no pasaba nada—.

        La oferta sigue estando: se llega a ella desde la propia calculadora al
        aprobar, y desde la ficha del RFQ. */
    function cotizar() {
        const id = rfqAbierto;
        cerrar();
        APP.navigate('quoting', { rfq: id });
    }

    /**
     * El PDF de lo que se está mirando.
     *
     * Hay DOS PDF distintos y se estaban confundiendo:
     *
     *   - La OFERTA del RFQ: la hace el servidor con los tramos costeados que
     *     esta misma ventana acaba de enseñar. Lleva el número del RFQ, el
     *     cliente, el material del correo y las tres cantidades con su precio.
     *   - El borrador de la CALCULADORA: lo que haya ahora mismo en la hoja.
     *
     * Se miraba primero si existía el marco de la calculadora y, de existir,
     * se le pedía el suyo. Pero el marco existe siempre que alguien haya
     * pasado por Cotización en esta sesión —se queda montado a propósito, para
     * no perder el trabajo al navegar—, así que revisando un RFQ salía el PDF
     * del borrador ajeno: "2026-CUST-001 (DRAFT)", sin cliente, "Material: SS"
     * y "No priced quantities". Nada de eso era del RFQ que se estaba
     * dictaminando.
     *
     * Ahora manda de DÓNDE se abrió la ventana, no qué marcos hay en la
     * página: desde la calculadora, su PDF; desde un RFQ, la oferta. Es la
     * misma distinción que ya hacía "Aprobar".
     */
    async function verPdf() {
        if (datos && datos.esCotizacion) {
            const marco = document.getElementById('quotingMarco');
            if (marco && marco.contentWindow &&
                typeof marco.contentWindow.previewPdf === 'function') {
                try {
                    await marco.contentWindow.previewPdf();
                    return;
                } catch (_) { /* si su PDF falla, se intenta el del servidor */ }
            }
        }
        const id = rfqAbierto || (datos && datos.rfq && datos.rfq.rfq_id);
        if (!id || id === 'quote') {
            Toast.warning(I18N.t('rev.sinPdf'));
            return;
        }
        const w = window.open('', '_blank');
        try {
            const blob = await API.descargarOfertaPdf(id);
            const url = URL.createObjectURL(blob);
            if (w) w.location.href = url;
            else window.open(url, '_blank');
            setTimeout(() => URL.revokeObjectURL(url), 60000);
        } catch (err) {
            if (w) w.close();
            if (!err.sesionExpirada) Toast.error(err.message || t('rev.pdfError'));
        }
    }

    function convertirCotizacion(q, r) {
        if (!q) return null;
        const p = (q.pns && q.pns[q.activePn || 0]) || {};
        const pNum = p.pn || '1060-022';
        const tipo = p.desc || 'Compression spring';
        const quoteNum = q.number || 'Quote';
        const cliente = (q.header && q.header.customer) || 'Customer';

        const tramos = (r && r.tiers ? r.tiers : []).map(t => ({
            cantidad: t.qty || 0,
            precio_pc: t.sellingPrice || t.price || 0,
            resultado_pct: t.marginPct != null ? t.marginPct : (t.margin || 20),
            objetivo_pct: q.contribution || 20,
            llega: (t.marginPct != null ? t.marginPct : (t.margin || 20)) >= (q.contribution || 20),
            cascada: {
                sell: t.sellingPrice || 0,
                av: t.av || 0,
                av_pct: t.avPct || (t.av && t.sellingPrice ? (t.av / t.sellingPrice) * 100 : 0),
                ccv: t.ccv || 0,
                ccv_pct: t.ccvPct || (t.ccv && t.sellingPrice ? (t.ccv / t.sellingPrice) * 100 : 0),
                ccd: t.ccd || 0,
                ccd_pct: t.ccdPct || (t.ccd && t.sellingPrice ? (t.ccd / t.sellingPrice) * 100 : 0),
                resultado: t.result || (t.sellingPrice && t.ccd ? t.sellingPrice - t.ccd : 0),
                resultado_pct: t.marginPct != null ? t.marginPct : 20,
            },
            material: {
                pc: t.matCost || 0,
                pct: t.matPct || 0,
                lb_comprar: t.wireToBuy || t.matWeight || 0,
                moq_manda: false,
            },
            ruta: (t.ops || []).map(o => ({
                maquina: o.machine || o.name || '—',
                pph: o.pph || 0,
                setup_h: o.setupH || 0,
            })),
            totales: {
                ingreso: (t.sellingPrice || 0) * (t.qty || 0),
                horas: t.machineHours || t.totalHours || 0,
                ccv_hora: t.ccvPerH || 0,
            },
            avisos: {},
        }));

        return {
            rfq: {
                part_number: pNum,
                tipo_resorte: tipo,
                rfq_id: quoteNum,
                quote_number: quoteNum,
                customer: cliente,
                estado: q.status || 'DRAFT',
            },
            comunes: {
                material: p.wire || 'SS',
                material_nombre: p.matName || 'Stainless steel',
                dia_in: p.dia || p.wireDia || 0.205,
                peso_lb_pc: p.weight || 0.295,
                base_lb: p.basePrice || 1.85,
                surcharge_lb: p.surcharge || 1.30,
            },
            tramos: tramos,
            puede_dictaminar: true,
            costeo: { completo: true },
            esCotizacion: true,
        };
    }

    // ------------------------------------------------------------- ciclo

    function pintar() {
        if (!capa || !datos) return;
        // Repintar (cambiar de tramo, abrir el menú de versiones, el refresco
        // solo) no es abrir: la ventana no vuelve a entrar con su animación ni
        // salta arriba si se había bajado.
        const antes = capa.querySelector('.revision-cuerpo');
        const bajado = antes ? antes.scrollTop : 0;
        capa.innerHTML = plantilla(datos);
        if (antes) {
            const caja = capa.querySelector('.revision');
            if (caja) caja.classList.add('revision--quieta');
            const cuerpo = capa.querySelector('.revision-cuerpo');
            if (cuerpo) cuerpo.scrollTop = bajado;
        }
        encajarMenu();
        const activo = capa.querySelector('.revision-tramo-card.activo');
        if (activo && window.matchMedia('(max-width: 768px)').matches) {
            activo.scrollIntoView({ block: 'nearest', inline: 'center' });
        }
    }

    async function recargar() {
        if (!rfqAbierto || (datos && datos.esCotizacion)) return;
        datos = await API.rfqRevision(rfqAbierto);
        if (tramoActivo >= (datos.tramos || []).length) tramoActivo = 0;
        pintar();
        if (typeof Notificaciones !== 'undefined' && Notificaciones.refrescar) Notificaciones.refrescar();
    }

    // ------------------------------------------------ al momento

    /*
     * La ventana se refresca sola mientras está abierta.
     *
     * El PM corrige en la calculadora (otra pestaña, o «Open full quote» y
     * vuelta) y lo cotizado llega al RFQ por detrás (`quoting.js` →
     * `/cotizacion-pm`). Sin esto, la ventana enseñaba el costeo de cuando
     * se abrió hasta que alguien la cerraba y la abría. Señales: el aviso de
     * que se guardó una cotización o se escogió una versión de ESTE RFQ (en
     * esta pestaña o en otra del navegador, ver `API.avisarRfq`), volver a
     * la pestaña (visibilitychange) y un sondeo cada 3 s de `/pulso` —una
     * fila, sin costear— por si el cambio vino de otra computadora; sólo si
     * el pulso cambió se pide la ventana entera. Nunca mientras se está
     * guardando algo (ocupado).
     */
    const SONDEO_MS = 3000;
    let sondeo = null;
    let ultimoCosteo = '';
    let ultimoPulso = '';

    function huellaDelCosteo(d) {
        try {
            const c = (d && d.costeo && d.costeo.pm) || {};
            const v = (d && d.versiones_pm) || {};
            return JSON.stringify([c.en, c.por, c.version, v.en_uso,
                                   (v.versiones || []).map(x => [x.n, x.fijada, x.precios]),
                                   (d && d.tramos || []).map(x => x.precio_pc),
                                   d && d.rfq && d.rfq.estado]);
        } catch (_) { return ''; }
    }

    let mirando = false;

    async function refrescarSiCambio(forzar) {
        if (!capa || !rfqAbierto || ocupado || (datos && datos.esCotizacion)) return;
        if (document.hidden || mirando) return;
        const id = rfqAbierto;
        mirando = true;
        try {
            if (forzar !== true) {
                const pulso = await API.rfqPulso(id);
                const h = (pulso && pulso.huella) || '';
                if (h && h === ultimoPulso) return;
                ultimoPulso = h;
            }
            const nuevo = await API.rfqRevision(id);
            if (!capa || rfqAbierto !== id || ocupado) return;
            const huella = huellaDelCosteo(nuevo);
            if (huella === ultimoCosteo) return;
            ultimoCosteo = huella;
            datos = nuevo;
            if (tramoActivo >= (datos.tramos || []).length) tramoActivo = 0;
            pintar();
        } catch (err) {
            if (err && err.sesionExpirada) cerrar();
        } finally {
            mirando = false;
        }
    }

    function alVolverAVerse() { if (!document.hidden) refrescarSiCambio(); }
    function alCotizar(ev) {
        if (ev && ev.detail && ev.detail.rfq === rfqAbierto) refrescarSiCambio(true);
    }
    // Una versión escogida en ESTA ventana ya está pintada; sólo cuenta si
    // vino de otra pestaña.
    function alVersion(ev) {
        if (ev && ev.detail && ev.detail.deOtraPestana && ev.detail.rfq === rfqAbierto) refrescarSiCambio(true);
    }

    function vigilar() {
        if (sondeo) return;
        const id = rfqAbierto;
        // El pulso de partida: el primer sondeo no tiene que pedir la ventana
        // entera si nada cambió desde que se abrió.
        API.rfqPulso(id).then((r) => { if (rfqAbierto === id && !ultimoPulso) ultimoPulso = (r && r.huella) || ''; })
            .catch(() => {});
        sondeo = setInterval(refrescarSiCambio, SONDEO_MS);
        document.addEventListener('visibilitychange', alVolverAVerse);
        window.addEventListener('pohua:rfq-cotizado', alCotizar);
        window.addEventListener('pohua:rfq-dictaminado', alCotizar);
        window.addEventListener('pohua:rfq-version', alVersion);
    }

    function dejarDeVigilar() {
        if (sondeo) { clearInterval(sondeo); sondeo = null; }
        document.removeEventListener('visibilitychange', alVolverAVerse);
        window.removeEventListener('pohua:rfq-cotizado', alCotizar);
        window.removeEventListener('pohua:rfq-dictaminado', alCotizar);
        window.removeEventListener('pohua:rfq-version', alVersion);
        ultimoCosteo = '';
        ultimoPulso = '';
    }

    async function abrir(origen, calcData) {
        if (!origen) return;
        if (capa && rfqAbierto === origen) return;
        if (capa) cerrar(true);

        tramoActivo = 0;
        datos = null;
        capa = document.createElement('div');
        capa.className = 'revision-fondo';
        capa.innerHTML = `<div class="revision revision--cargando" role="dialog" aria-modal="true">
            <div class="loading-overlay"><div class="spinner"></div> ${esc(t('rev.cargando'))}</div></div>`;
        document.body.appendChild(capa);
        document.body.classList.add('revision-abierta');

        capa.addEventListener('click', alClic);
        document.addEventListener('keydown', alTeclear);

        if (typeof origen === 'object' && origen !== null) {
            if (origen.rfq && origen.tramos) {
                rfqAbierto = (origen.rfq && origen.rfq.rfq_id) || 'quote';
                datos = origen;
            } else {
                datos = convertirCotizacion(origen, calcData);
                rfqAbierto = (datos && datos.rfq && datos.rfq.rfq_id) || 'quote';
            }
            pintar();
            return;
        }

        if (!API.puede('rfq:leer')) { Toast.warning(I18N.t('aviso.sinPermiso')); cerrar(); return; }

        rfqAbierto = origen;
        try {
            datos = await API.rfqRevision(origen);
            if (!capa || rfqAbierto !== origen) return;
            // «Esperando al cliente»: le faltan datos y se le pidieron. No hay
            // nada completo que revisar; se lleva a su ficha, que dice qué falta.
            if (datos && datos.rfq && datos.rfq.estado === 'Incomplete') {
                cerrar(true);
                Toast.info(I18N.t('ficha.esperaTitulo'));
                if (typeof APP !== 'undefined') APP.navigate('rfq-detail', { id: origen });
                return;
            }
            ultimoCosteo = huellaDelCosteo(datos);
            pintar();
            vigilar();
        } catch (err) {
            if (err.sesionExpirada) { cerrar(); return; }
            if (!capa) return;
            capa.innerHTML = `<div class="revision" role="dialog" aria-modal="true">
                <div class="revision-cab"><div class="revision-cab-izq"><span class="revision-cab-pn">${esc(origen)}</span></div>
                    <button type="button" class="revision-cerrar" data-accion="cerrar" aria-label="${esc(t('rev.cerrar'))}">&times;</button></div>
                <div class="revision-cuerpo"><div class="revision-franja revision-franja--error"><span class="revision-franja-icono">⚠</span><div class="revision-franja-texto">${esc(err.message)}</div></div></div>
            </div>`;
        }
    }


    function cerrar(silencio) {
        dejarDeVigilar();
        versionesAbiertas = false;
        if (capa) capa.remove();
        capa = null; datos = null; rfqAbierto = null; ocupado = false;
        document.body.classList.remove('revision-abierta');
        document.removeEventListener('keydown', alTeclear);
        // La dirección deja de nombrar el RFQ para que "atrás" no lo reabra.
        if (!silencio && /^#\/rfq\//.test(location.hash)) {
            history.replaceState(history.state, '', location.pathname + location.search);
        }
    }

    function alClic(ev) {
        if (ocupado) return;
        // Menú de versiones abierto y el clic cae fuera de él: se cierra, y el
        // clic sigue su camino (una pestaña, un botón…).
        if (versionesAbiertas && !ev.target.closest('.revision-ver-ancla')) {
            versionesAbiertas = false;
            if (!ev.target.closest('[data-tramo], [data-accion]') && ev.target !== capa) { pintar(); return; }
            pintar();
        }
        const pestana = ev.target.closest('[data-tramo]');
        if (pestana) {
            tramoActivo = Number(pestana.dataset.tramo) || 0;
            pintar();
            return;
        }
        const boton = ev.target.closest('[data-accion]');
        if (boton) {
            const accion = boton.dataset.accion;
            if (accion === 'cerrar') cerrar();
            else if (accion === 'pdf') verPdf();
            else if (accion === 'aprobar') aprobar();
            else if (accion === 'declinar') declinar();
            else if (accion === 'cotizar') cotizar();
            else if (accion === 'versiones') { versionesAbiertas = !versionesAbiertas; pintar(); }
            else if (accion === 'usarVersion') usarVersion(boton.dataset.version);
            else if (accion === 'recalcular') recalcular(false);
            else if (accion === 'leerPlano') recalcular(true);
            return;
        }
        // Clic en el velo, fuera de la caja: se cierra. En el teléfono la caja
        // ocupa todo, así que esto sólo pasa en la compu.
        if (ev.target === capa) cerrar();
    }


    function alTeclear(ev) {
        if (ev.key !== 'Escape' || ocupado) return;
        // Si hay un diálogo de confirmación encima, la tecla es para él.
        if (document.querySelector('.dialogo-fondo')) return;
        // Con el menú de versiones abierto, Esc cierra el menú, no la ventana.
        if (versionesAbiertas) { versionesAbiertas = false; pintar(); return; }
        cerrar();
    }

    /*
     * `#/rfq/<id>` en la dirección (el enlace del correo de aviso, la
     * notificación del teléfono) lleva al DETALLE del RFQ, como cualquier
     * otra forma de abrir uno: un RFQ se abre siempre por su ficha, y desde
     * ahí «Revisar» abre esta ventana. Quitar el `#` la cierra.
     */
    function porDireccion(ev) {
        const m = /^#\/rfq\/(.+)$/.exec(location.hash || '');
        if (m) {
            let id = m[1];
            try { id = decodeURIComponent(id); } catch (_) { /* tal cual */ }
            if (capa) cerrar(true);
            if (!ev) {
                // Al arrancar: se deja la dirección en la ficha y la ruta
                // inicial de la aplicación la pinta.
                history.replaceState({ page: 'rfq-detail', params: { id } }, '',
                                     '/rfq-detail?' + new URLSearchParams({ id }).toString());
                return;
            }
            history.replaceState(history.state, '', location.pathname + location.search);
            APP.navigate('rfq-detail', { id });
        } else if (capa) {
            cerrar(true);
        }
    }

    function init() {
        window.addEventListener('hashchange', porDireccion);
        // Al cambiar de idioma se vuelve a pintar con los textos nuevos.
        if (I18N.alCambiar) I18N.alCambiar(() => { if (capa && datos) pintar(); });
        porDireccion(null);
    }

    return { init, abrir, cerrar, recargar };
})();
