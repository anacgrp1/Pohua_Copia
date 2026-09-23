// pricing/reglas_runner.js
// Lee un payload JSON por stdin, pregunta a las reglas del taller y escribe el
// resultado en stdout.  Mismo contrato que runner.js: los errores salen por
// stderr con código 1, para que el envoltorio de Python los distinga de un
// resultado válido.
//
// Las reglas viven en el núcleo (github.com/dasniela/ISCQuotingCore), en
// `nucleo/motor/reglas.js`.  Aquí NO se reimplementan: si el fichero no está,
// esto falla y el adaptador lo declara como dato faltante, en vez de inventarse
// una ruta que parezca buena.

const path = require('path');

function cargarReglas() {
    // 1) la ruta que diga el entorno -- es la que pone `pricing/reglas.py`,
    //    con lo que localizó `pricing/nucleo.py`, para que haya UNA sola
    //    forma de encontrar el núcleo y no dos que puedan discrepar;
    // 2) la copia vendorizada de este repositorio, que es la que hay en
    //    Render, donde no se puede clonar un repositorio privado;
    // 3) al lado, si alguien lo puso ahí; 4) un clon del núcleo al lado del
    //    proyecto, que es lo que hay trabajando en local.
    const candidatos = [
        process.env.ISC_NUCLEO_REGLAS,
        path.join(__dirname, 'nucleo', 'reglas.js'),
        path.join(__dirname, 'reglas.js'),
        path.join(__dirname, '..', 'ISCQuotingCore', 'nucleo', 'motor', 'reglas.js'),
        path.join(__dirname, '..', 'nucleo', 'motor', 'reglas.js'),
    ].filter(Boolean);
    for (const c of candidatos) {
        try { return require(c); } catch (e) { /* siguiente */ }
    }
    throw new Error(
        'No se encontraron las reglas del taller. Se buscaron: ' +
        candidatos.join(', ') + '. Define ISC_NUCLEO_REGLAS o instala el núcleo.');
}

function comprobar(REGLAS) {
    // Un fichero que carga pero no trae las funciones es el caso del
    // placeholder: `// reglas` es JavaScript válido y `require` lo acepta tan
    // contento. Sin esto, `REGLAS.secundarias` sería `undefined` y el error
    // saldría como "not a function", que no dice nada de lo que pasa.
    if (!REGLAS || typeof REGLAS.secundarias !== 'function') {
        throw new Error(
            'Las reglas del taller se cargaron pero no traen `secundarias`: ' +
            'lo que hay en el sitio del núcleo no son las reglas.');
    }
    return REGLAS;
}

let input = '';
process.stdin.on('data', c => { input += c.toString(); });
process.stdin.on('end', () => {
    try {
        const REGLAS = comprobar(cargarReglas());
        const p = JSON.parse(input);
        const salida = {};

        // Las operaciones secundarias que pide el plano: rectificado si los
        // extremos van rectificados, horno por 17-7 o por tratamiento térmico,
        // looping en extensión y doblado en torsión.
        if (p.op === 'secundarias' || p.op === 'todo') {
            salida.secundarias = REGLAS.secundarias(
                p.descripcion, p.plano || {}, p.material_codigo || null);
        }

        // La bobinadora según el orden de preferencia del taller, para poder
        // comparar con la que eligió el catálogo.
        if (p.op === 'bobinadora' || p.op === 'todo') {
            // `material` es la ficha del catálogo: sin ella no se aplica el
            // tope por material, y con temple en aceite de .177" saldría la
            // SIMPLEX MC 50, que no puede correrlo.
            const m = REGLAS.bobinadora(p.descripcion, p.diam_pulg,
                                        p.maquinas || [], p.material || null);
            salida.bobinadora = m ? m.name : null;
        }

        // ¿Puede esta máquina, en concreto, con este material a este diámetro?
        // Se pregunta aparte de elegir porque son dos cosas distintas: cuál
        // preferiría el taller, y si la que ya está puesta es siquiera capaz.
        // Devuelve el motivo por el que NO, o null.
        if (p.op === 'tope') {
            salida.tope = REGLAS.topeDeMaterial(
                p.maquina || null, p.material || null, p.diam_mm);
        }

        // La caja del tramo. La decide el peso TOTAL —piezas x peso de la
        // pieza—, así que un tramo de 50.000 puede acabar en tambores donde
        // el de 10.000 va en cajas.
        if (p.op === 'empaque') {
            salida.empaque = REGLAS.embalaje(
                p.peso_lb, p.descripcion, p.cantidad, p.cajas || []);
        }

        process.stdout.write(JSON.stringify(salida));
    } catch (err) {
        process.stderr.write(String((err && err.message) || err));
        process.exit(1);
    }
});
