// pricing/resortes_runner.js
// El dictamen del Spring Engineering Calculator para un resorte, sin abrir la
// calculadora.
//
// Lee un payload JSON por stdin y escribe el resultado en stdout. Mismo
// contrato que runner.js y reglas_runner.js: los errores salen por stderr con
// código 1, para que el envoltorio de Python (pricing/spring_calc.py) los
// distinga de un resultado válido.
//
// POR QUÉ ASÍ
//   El cálculo es `resortes.js` del núcleo, el MISMO fichero que la calculadora
//   lleva incrustado. Las tablas —materiales y bobinadoras— se leen del propio
//   HTML de la calculadora vendorizada (MAT_DEFAULTS y MCH_DEFAULTS), que es de
//   donde las toma la calculadora dentro de Pohua: ese HTML no recibe el
//   catálogo de Neon (ver scripts/vendorizar_nucleo.py). Así la ficha del RFQ y
//   la pestaña Spring Calc no pueden opinar distinto sobre si una pieza sale.
//
//   El límite duro de 15 mm («NOT FEASIBLE at ISC. Do not price.») es el
//   `wireMaxIn` del motor de coste (engine.js), leído de allí.
//
// Payload:
//   { tipo: 'compression'|'extension'|'torsion'|'wireform',
//     material: 'SS' | 'ss302' | texto | null,
//     d, od, L0, Nt, Na, endType }       -- todo en mm
//
// Salida:
//   { evaluado, factible, score, banda, material, maquina:{factible,mejor,por_que},
//     bloqueos:[{codigo, ...datos}], banderas:[{nivel, titulo}] }

const fs = require('fs');
const path = require('path');

const NUCLEO = path.join(__dirname, 'nucleo');
const HTML_SPRING = process.env.ISC_SPRING_CALC_HTML || path.join(
    __dirname, '..', 'vendor', 'calculadora', 'Spring Engineering Calculator V2.html');

function requerir(variable, nombre) {
    const ruta = process.env[variable] || path.join(NUCLEO, nombre);
    return require(ruta);
}

/** Un `var NOMBRE = [ ... ];` del HTML, evaluado como el literal que es. */
function tablaDelHtml(html, nombre) {
    const ini = html.indexOf('var ' + nombre + ' = [');
    if (ini < 0) throw new Error('La calculadora no trae ' + nombre + ' (' + HTML_SPRING + ').');
    const desde = html.indexOf('[', ini);
    const hasta = html.indexOf('\n];', desde);
    if (hasta < 0) throw new Error(nombre + ' no termina donde se esperaba.');
    // Es el fichero de la calculadora vendorizada, generado por el núcleo: un
    // literal de JavaScript con claves sin comillas, no JSON.
    return (new Function('return ' + html.slice(desde, hasta + 2)))();
}

const MUERTAS = { plain: 0, plain_ground: 1, closed: 2, closed_ground: 2 };

function num(v) {
    const n = typeof v === 'number' ? v : parseFloat(v);
    return isFinite(n) && n > 0 ? n : null;
}

function evaluar(p) {
    const RES = requerir('ISC_NUCLEO_RESORTES', 'resortes.js');
    const REGLAS = requerir('ISC_NUCLEO_REGLAS', 'reglas.js');
    const { DEFAULT_PARAMS } = requerir('ISC_NUCLEO_MOTOR', 'engine.js');

    const html = fs.readFileSync(HTML_SPRING, 'utf8');
    const materiales = tablaDelHtml(html, 'MAT_DEFAULTS');
    const maquinas = tablaDelHtml(html, 'MCH_DEFAULTS');

    const tipo = p.tipo || 'compression';
    const endType = MUERTAS.hasOwnProperty(p.endType) ? p.endType : 'closed';
    RES.configurar({
        materiales, maquinas, orden: REGLAS.SG_ORDEN,
        estado: { unit: 'mm', tab: tipo, comp: { endType }, ext: {}, tors: {} },
    });

    // El material: primero por código de compra (SS, MW…), luego por id de
    // ingeniería (ss302…), luego por los alias del texto. Sin material no se
    // puntúa: `getMat` caería en el primero de la lista y el score sería el de
    // otro alambre.
    let mat = null;
    const m = String(p.material || '').trim();
    if (m) {
        mat = materiales.find(x => String(x.codigo || '').toUpperCase() === m.toUpperCase())
           || materiales.find(x => x.id === m)
           || (RES.materialDelTexto(m) ? materiales.find(x => x.id === RES.materialDelTexto(m)) : null);
    }

    const d = num(p.d), od = num(p.od), L0 = num(p.L0);
    let Nt = num(p.Nt), Na = num(p.Na);
    const salida = {
        evaluado: false, factible: null, score: null, banda: null,
        material: mat ? { id: mat.id, nombre: mat.name, codigo: mat.codigo } : null,
        tipo, endType, maquina: null, bloqueos: [], banderas: [],
    };
    if (!d) return salida;          // sin calibre no hay nada que dictaminar
    salida.evaluado = true;

    // 1. El límite duro del motor de coste: 15 mm (0.59").
    const maxMm = (DEFAULT_PARAMS.wireMaxIn || 0.59) * 25.4;
    if (d >= maxMm - 1e-9) {
        salida.bloqueos.push({ codigo: 'alambre_maximo', valor: d,
                               limite_mm: +maxMm.toFixed(2),
                               limite_pulg: DEFAULT_PARAMS.wireMaxIn || 0.59 });
    }

    // 2. La bobinadora: los seis pasos de la hoja de Rodea (selectMachine).
    const sel = RES.selectMachine(tipo, d, od || 0, mat ? mat.id : null);
    salida.maquina = {
        factible: !!sel.feasible,
        mejor: sel.best && sel.best.m ? sel.best.m.name : null,
        alternativa: sel.alt && sel.alt.m ? sel.alt.m.name : null,
        notas: sel.best ? (sel.best.notes || []) : [],
        por_que: (!sel.feasible && sel.near && sel.near[0])
            ? sel.near[0].m.name + ': ' + sel.near[0].why.join(', ') : '',
    };
    if (!sel.feasible) {
        // Lo más grueso que enrolla el taller para este tipo: dice cuánto
        // falta, que es lo que se le contesta al cliente.
        const capaces = maquinas.filter(x => x[tipo]);
        const tope = capaces.length ? Math.max.apply(null, capaces.map(x => x.wireMax || 0)) : null;
        salida.bloqueos.push({ codigo: 'sin_maquina', alambre: d, od: od, alambre_max_taller: tope,
                               cercana: sel.near && sel.near[0] ? sel.near[0].m.name : null,
                               por_que: salida.maquina.por_que });
    }

    // 3. La puntuación de fabricabilidad. Sólo compresión: extensión y
    //    torsión necesitan carga, recorrido o ángulo, que el plano rara vez da
    //    y que la calculadora no inventa.
    if (tipo === 'compression' && mat && od && L0 && (Nt || Na)) {
        const muertas = MUERTAS[endType];
        if (!Nt) Nt = Na + muertas;
        if (!Na) Na = Math.max(Nt - muertas, 0.5);
        const R = RES.calcCompression({ matId: mat.id, d, odMode: 'OD', dia: od,
                                        Na, Nt, endType, L0, h: 0 });
        const S = RES.scoreCompression(R);
        salida.score = S.score;
        salida.banda = S.score >= 90 ? 'Easy to manufacture'
            : S.score >= 70 ? 'Manufacturable'
            : S.score >= 50 ? 'Engineering review'
            : S.score >= 30 ? 'High manufacturing risk' : 'Not recommended';
        // Sin altura de trabajo el score es de geometría y enrollado, no de
        // servicio: la calculadora lo matiza igual (postFeasibility).
        salida.solo_geometria = S.flags.some(x => /not evaluated/.test(x.title || ''));
        salida.banderas = S.flags
            .filter(x => x.level !== 'ok')
            .map(x => ({ nivel: x.level, titulo: x.title }));
    }

    salida.factible = salida.bloqueos.length === 0;
    return salida;
}

let entrada = '';
process.stdin.on('data', c => { entrada += c.toString(); });
process.stdin.on('end', () => {
    try {
        process.stdout.write(JSON.stringify(evaluar(JSON.parse(entrada || '{}'))));
    } catch (err) {
        process.stderr.write(String((err && err.stack) || err));
        process.exit(1);
    }
});
