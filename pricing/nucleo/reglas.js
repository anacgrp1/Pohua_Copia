/* Las reglas del taller de ISC.

   Qué máquina hace esta pieza, qué operaciones secundarias lleva, en qué caja
   va, a qué servicio de recubrimiento corresponde su acabado, y a qué cliente
   se parece un nombre escrito de otra forma.

   LA FRONTERA, QUE NO ES ARBITRARIA
     Aquí vive lo que las reglas DICEN. No vive si se escribe o no: eso depende
     de si una persona ya puso ese valor a mano, que es estado de una
     cotización abierta y no una regla del taller. Por eso `sugerirRuta`
     devuelve la ruta y es la aplicación quien decide si la aplica.

   NADA DE ESTO LEE UNA BASE DE DATOS NI UNA PANTALLA
     Las tablas entran por argumento -- `maquinas`, `embalajes`,
     `subcontratistas`, `clientes` --. Lo hace así para que el Cotizador pueda
     llamarlas con las filas que saca de Postgres y la calculadora con las que
     tiene en el navegador, sin que ninguno de los dos tenga su propia copia de
     la regla.

   Fuente única: este fichero. El HTML lo lleva incrustado (`construir.py`).
*/

/* ------------------------------------------------------------------ tipos */

/* Antes había una tabla de CARRILES por diámetro que elegía bobinadora sin
   mirar el tipo de resorte: mandaba compresión de 0,16" a la NUCOIL HX-60 --
   que no hace compresión -- y llegaba a 0,590" con la AIM 3000, que para en
   0,375". Ahora se filtra por tipo y por alambre, y gana la preferida. */
const SG_TIPO = { 'Compression Spring': 'compression', 'Tension Spring': 'extension',
                  'Torsion Spring': 'torsion', 'Wire Form': 'wireform' };
const SG_CAP = { compression: 'capC', extension: 'capE', torsion: 'capT', wireform: 'capW' };

/* El orden de preferencia lo dio Miguel Rodea (2026-09-03): entre las máquinas
   capaces, gana la que él pondría primero. */
const SG_ORDEN = {
  compression: ["SIMPLEX MC 50", "TORIN W11A", "AIM 3000", "TORIN W10A", "ZX250",
    "TORIN W125", "TORIN W115A", "TORIN FZ-11", "SHINKO TF-45", "TORIN W11T",
    "TORIN W12T", "KMH-508", "SHINKO TF-23", "KMH-516"],
  extension: ["TORIN W11A", "AIM 3000", "TORIN W125", "TORIN W115A", "TORIN FZ-11",
    "SHINKO TF-45", "NUCOIL HX-60", "NUCOIL CSF-200", "NUCOIL CSF-400", "SHINKO TF-23"],
  torsion: ["AIM 3000", "ZX250", "TORIN W125", "TORIN FZ-11", "SHINKO TF-45",
    "NUCOIL HX-60", "TORIN W11T", "NUCOIL CSF-200", "NUCOIL CSF-400", "TORIN W12T",
    "SHINKO TF-23"],
  wireform: ["AIM 3000", "ZX250", "NUCOIL HX-60", "NUCOIL CSF-200", "NUCOIL CSF-400",
    "AIM AFM-3D2-T"]
};

const _num = s => (typeof s === 'number' ? s
  : (!s ? null : (isNaN(parseFloat(String(s).replace(/[$,\s]/g, ''))) ? null
                  : parseFloat(String(s).replace(/[$,\s]/g, '')))));
const _norm = t => String(t).toUpperCase().replace(/\(FENN\)/, '').replace(/[^A-Z0-9]/g, '');

/* --------------------------------------------------------------- máquinas */

/* El tope por material: hay materiales que una máquina sólo dobla hasta un
   diámetro menor que el suyo. Devuelve por qué NO puede, o null.

   Rodea lo contestó en su columna «Material caps (if max dia drops)», y sólo
   para una: la SIMPLEX MC 50 con temple en aceite, que le baja de .198" a
   .165". Vive aquí, y no dentro de quien elige, porque lo aplican los dos
   lados -- el dictamen del Spring Calculator y la ruta automática de la
   cotización -- y es la misma regla: tiene que ser el mismo código.

   `material` es la fila del catálogo, no un identificador: se compara
   `capMaterial` con su nombre, así que un tope nuevo se añade como dato y esto
   no se toca. */
function topeDeMaterial(maquina, material, dmm) {
  if (!maquina || !material || !maquina.capWireMaxMm) return null;
  const suyo = String(maquina.capMaterial || '').trim().toLowerCase();
  if (!suyo || suyo !== String(material.name || '').trim().toLowerCase()) return null;
  if (!(dmm > maquina.capWireMaxMm)) return null;
  return suyo + ' above ' + maquina.capWireMaxMm + ' mm on this machine';
}

/* La bobinadora: entre las capaces para ese tipo y ese alambre, la que el
   taller prefiere. Sin tipo no se elige nada -- una descripción que no es un
   resorte no se convierte en el resorte más parecido.

   `material` es la fila del catálogo y es opcional. Sin él no se aplica el
   tope: con temple en aceite de .177" esto devolvía la SIMPLEX MC 50, que no
   puede correrlo, y la pieza se cotizaba a un cuarto de lo que cuesta en la
   máquina que sí. Quien llame debería pasarlo siempre que lo tenga. */
function bobinadora(descripcion, diaIn, maquinas, material) {
  const tipo = SG_TIPO[descripcion];
  if (!tipo) return null;
  const cap = SG_CAP[tipo], orden = SG_ORDEN[tipo] || [];
  const dmm = diaIn * 25.4;
  const capaces = (maquinas || []).filter(m =>
    m.family === 'COILER' && !m.excluded && m[cap] &&
    m.wireMinMm && m.wireMaxMm && dmm >= m.wireMinMm && dmm <= m.wireMaxMm &&
    !topeDeMaterial(m, material, dmm));
  if (!capaces.length) return null;
  const puesto = m => {
    const i = orden.findIndex(n => _norm(n) === _norm(m.name));
    return i < 0 ? 99 : i;
  };
  return capaces.sort((a, b) => puesto(a) - puesto(b))[0];
}

function porNombre(nombre, maquinas) {
  return (maquinas || []).find(m => m.name === nombre) || null;
}

/* Las secundarias salen del plano, no de una lista por defecto.

   El horno va por material o porque el plano pida tratamiento térmico. NO por
   el acabado: un "Zinc Clear & Bake" lleva un horneado que hace el recubridor
   -- es literalmente uno de los servicios subcontratados -- no el horno de
   ISC. Buscar "bake" en el acabado metía el horno en casi todas las piezas de
   zinc, que son casi todas.

   Queda fuera el otro caso de Rodea, "resortes muy grandes": no dio umbral,
   así que no hay forma de decidirlo sin inventárselo. Lo añade una persona. */
function secundarias(descripcion, plano, materialCode) {
  const dw = plano || {}, ops = [];
  const campo = k => {
    const f = (dw.fields || []).find(x => x.key === k);
    return f ? String(f.value || '').toLowerCase() : '';
  };
  if (descripcion === 'Compression Spring') {
    if (/ground/.test(campo('endType')))
      ops.push({ m: 'Grinder A', why: 'the drawing calls for ground ends' });
  } else if (descripcion === 'Tension Spring') {
    ops.push({ m: 'Looping / Hooks', why: 'extension spring: hook forming' });
  } else {
    ops.push({ m: 'Bending / Kick', why: 'leg bending' });
  }
  const revision = (dw.feasibility || []).map(x => String(x.label || '').toLowerCase()).join(' | ');
  if (materialCode === 'SS177')
    ops.push({ m: 'Stationary Oven', why: '17-7 PH needs ageing' });
  else if (/heat treatment|stress relie|anneal/.test(revision))
    ops.push({ m: 'Stationary Oven', why: 'the drawing calls for heat treatment' });
  return ops;
}

/* --------------------------------------------------------------- embalaje */

/* La caja se elige por el peso TOTAL del tramo, así que otra cantidad puede
   significar otra caja -- o barriles. */
function embalaje(pesoLb, descripcion, cantidad, embalajes) {
  const wt = _num(pesoLb), qty = _num(cantidad);
  if (!wt || wt <= 0 || !qty || qty <= 0) return null;
  const tierWt = wt * qty;
  let id, objetivo;
  if (tierWt >= 400) { id = 'barrels no lids'; objetivo = 130; }
  else if (descripcion === 'Wire Form' && tierWt >= 30) { id = 'CHP12012'; objetivo = 15; }
  else if (tierWt >= 200) { id = 'COR121212U'; objetivo = 17; }
  else if (tierWt >= 60) { id = 'COR100803'; objetivo = 13; }
  else { id = 'COR11050'; objetivo = 11; }
  const lista = embalajes || [];
  if (!lista.some(x => x.id === id)) id = (lista[0] || {}).id || '';
  let ppb = Math.max(1, Math.round(objetivo / wt));
  const redondas = [1, 2, 5, 10, 25, 50, 100, 200, 250, 500, 1000, 2000, 2500,
                    5000, 10000, 25000, 50000];
  let mejor = redondas[0];
  redondas.forEach(n => { if (Math.abs(n - ppb) < Math.abs(mejor - ppb)) mejor = n; });
  ppb = Math.min(mejor, qty);
  return { id: id, ppb: ppb, boxWt: ppb * wt, tierWt: tierWt };
}

/* --------------------------------------------------------------- acabados */

function normAcabado(t) {
  return String(t || '').toLowerCase().replace(/&/g, 'and').replace(/[^a-z0-9]/g, '');
}

/* El acabado del plano, traducido a servicio de recubrimiento.

   `tabla` son las grafías del historial de cotizaciones que tradujo Rodea. Un
   acabado que no esté NO se convierte en el más parecido: adivinar aquí es
   elegir a qué proveedor va la pieza y a qué precio.

   Segunda pasada: que el plano nombre EL SERVICIO tal cual. La tabla traduce
   lo que ISC tecleó en el pasado, y el plano habla otro idioma -- dice
   "PASSIVATED" donde el servicio se llama "Passivate". Eso no es adivinar: es
   la misma palabra. Lo que sí sería adivinar es un "ZINC" a secas. */
function servicioDelTexto(texto, tabla, subcontratistas) {
  const txt = String(texto || '');
  if (!txt) return null;
  const k = normAcabado(txt);
  const m = (tabla || {})[k];
  if (m) return Object.assign({ texto: txt }, m);
  const sinD = k.replace(/d$/, '');
  const serv = (subcontratistas || []).reduce((a, s) => a.concat(s.services || []), [])
    .find(x => { const n = normAcabado(x.service); return n === k || n === sinD; });
  if (serv) return { texto: txt, canonical: serv.service, service: serv.service, delPlano: true };
  return { texto: txt, desconocido: true };
}

/* --------------------------------------------------------------- clientes */

/* Primero exacto por nombre o por código; después por contención, que es lo
   que salva los "Inc." y los "& Co." de más o de menos. Devuelve null cuando
   no encuentra: quien llama decide si lo dice o lo calla. */
function buscarCliente(nombre, clientes) {
  const txt = String(nombre || '').trim();
  if (!txt) return null;
  const n = s => String(s).toUpperCase().replace(/[^A-Z0-9]/g, '');
  const cn = n(txt), lista = clientes || [];
  return lista.find(c => n(c.name) === cn || n(c.code) === cn) ||
         lista.find(c => cn && (n(c.name).includes(cn) || cn.includes(n(c.name)))) ||
         null;
}

/* ------------------------------------------------------------------ ruta */

/* La firma de una ruta: qué máquinas, a qué cadencia y con qué puesta a punto.
   Sirve para saber si lo que hay lo escribió la máquina o una persona. */
function firmaRuta(tramo) {
  return ((tramo && tramo.routing) || []).filter(o => o.machine)
    .map(o => o.machine + '@' + (o.pph || '') + '/' + (o.setupH || '')).join(' > ');
}

/* La ruta completa: bobinadora más secundarias.

   `maquinaElegida` es la del Spring Calculator cuando ya corrió: allí está
   además la geometría, así que aplica también el aviso de OD.

   `material` es la fila del catálogo, y con ella el tope por material se
   aplica aquí igual que allí. Antes no llegaba, y no era teórico: con temple en
   aceite de .177" esto ponía la SIMPLEX MC 50 -- el tope de Rodea son 4,2 mm --
   en vez de la AIM 3000. La MC 50 no puede correr ese alambre, y cuesta la
   cuarta parte por pieza: la oferta salía un 75 % por debajo de lo que cuesta
   hacerla. El aviso de "abre el Spring Calculator" protegía sólo a quien lo
   leyera. */
function sugerirRuta(pieza, maquinas, maquinaElegida, material) {
  const dia = _num(pieza.material && pieza.material.diaIn);
  if (!dia || dia <= 0)
    return { err: 'Enter the wire ø first (Material card) — the coiler choice depends on it.' };
  const fam = pieza.desc || 'Compression Spring';
  if (!SG_TIPO[fam])
    return { err: '“' + fam + '” is not a spring type, so there is no automatic ' +
                  'routing for it — add the operations by hand.' };
  const elegida = maquinaElegida ? porNombre(maquinaElegida, maquinas) : null;
  const cm = elegida || bobinadora(fam, dia, maquinas, material);
  if (!cm) return { err: 'No machine in the shop can coil ' + dia + '" wire for a ' + fam +
                         (material ? ' in ' + material.name : '') +
                         '. Above 0.375" there is no coiler at all: flag it for manual ' +
                         'routing instead of pricing it.' };
  /* El motivo no es adorno: dice con qué se decidió, y por tanto qué NO se
     comprobó. Sin material sigue avisando, porque entonces sigue siendo verdad. */
  const ops = [{ m: cm, pph: cm.pph,
    why: elegida ? 'chosen by the Spring Calculator (type, wire, OD and material)'
      : material ? 'preferred coiler that fits the wire and the material'
                 : 'preferred coiler that fits the wire — open the Spring ' +
                   'Calculator so the material cap is applied too' }];
  secundarias(fam, pieza.drawing, pieza.material && pieza.material.code).forEach(s => {
    const m = porNombre(s.m, maquinas);
    if (m) ops.push({ m: m, pph: m.pph, why: s.why });
  });
  return { fam: fam, ops: ops };
}

/* ------------------------------------------------------------ el veredicto */

/* Lo que impide aprobar, en una lista. Se calcula para poder enseñarlo ANTES
   del clic, no descubrirlo pulsando. */
function faltaParaAprobar(cotizacion) {
  const falta = [];
  if (!cotizacion) return ['no quote open'];
  if (!cotizacion.header || !cotizacion.header.customerCode) falta.push('the customer');
  const pns = cotizacion.pns || [];
  if (!pns.some(p => String(p.pn || '').trim())) falta.push('the part number');
  if (!pns.some(p => (p.tiers || []).some(t => _num(t.qty) > 0))) falta.push('at least one quantity');
  if (!pns.some(p => _num(p.material.weightLb) > 0)) falta.push('the weight per piece');
  if (!pns.some(p => (p.tiers || []).some(t => (t.routing || []).some(o => o.machine))))
    falta.push('a routing');
  return falta;
}

const REGLAS = { SG_TIPO, SG_CAP, SG_ORDEN, topeDeMaterial, bobinadora,
                 porNombre, secundarias,
                 embalaje, normAcabado, servicioDelTexto, buscarCliente,
                 firmaRuta, sugerirRuta, faltaParaAprobar };

/* Para Node. En el navegador `module` no existe y esto no hace nada. */
if (typeof module !== 'undefined' && module.exports) { module.exports = REGLAS; }
