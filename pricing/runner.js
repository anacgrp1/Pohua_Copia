// pricing/runner.js
// Lee un payload JSON por stdin, corre ENGINE.computePN y escribe el resultado
// en stdout.  Los errores salen por stderr con código 1, para que el envoltorio
// de Python (pricing/engine.py) los distinga de un resultado válido.

//
// El motor es el del núcleo: el MISMO fichero que lleva incrustado la
// calculadora de la planta. Lo localiza pricing/nucleo.py y llega aquí en
// ISC_NUCLEO_MOTOR; sin la variable, la copia vendorizada de al lado.
//
// Hasta 2026-09 esto cargaba `./engine.js`, una copia vieja (V5) con su propio
// SEED escrito a mano. Con las mismas entradas daba otro precio: el 004-222
// salía a $0.5098 en la ventana del RFQ y a $0.3946 en la calculadora.
//
// Las bases (cajas con su precio, subcontratistas) las manda Python en
// ctx_overrides.dbs, leídas de Neon. Aquí no hay datos de catálogo.
const path = require('path');
const MOTOR = process.env.ISC_NUCLEO_MOTOR || path.join(__dirname, 'nucleo', 'engine.js');
const { ENGINE, DEFAULT_PARAMS } = require(MOTOR);

let input = '';

process.stdin.on('data', chunk => {
    input += chunk.toString();
});

process.stdin.on('end', () => {
    try {
        const payload = JSON.parse(input);
        const pn = payload.pn;
        // ctx_overrides puede venir ausente, null o vacío: antes se hacía
        // `ctx_overrides.params` a secas y un null tumbaba el proceso con un
        // TypeError en vez de calcular con los valores por defecto.
        const overrides = payload.ctx_overrides || {};

        if (!pn || typeof pn !== 'object') {
            throw new Error('El payload no trae un PN válido.');
        }

        const ctx = {
            params: Object.assign({}, DEFAULT_PARAMS, overrides.params || {}),
            dbs: overrides.dbs || {},
            rep: overrides.rep || '',
            contribution: overrides.contribution !== undefined
                ? overrides.contribution
                : DEFAULT_PARAMS.contribution,
            shareCountFn: () => 1,
        };

        const result = ENGINE.computePN(pn, ctx);

        process.stdout.write(JSON.stringify(result));
    } catch (err) {
        process.stderr.write('Error ejecutando computePN: ' + (err && err.message ? err.message : String(err)) + '\n');
        process.exit(1);
    }
});
