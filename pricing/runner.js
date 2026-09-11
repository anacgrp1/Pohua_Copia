// pricing/runner.js
// Lee un payload JSON por stdin, corre ENGINE.computePN y escribe el resultado
// en stdout.  Los errores salen por stderr con código 1, para que el envoltorio
// de Python (pricing/engine.py) los distinga de un resultado válido.

const { ENGINE, SEED, DEFAULT_PARAMS } = require('./engine.js');

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
            dbs: Object.assign({}, SEED, overrides.dbs || {}),
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
