/* El motor de coste de la calculadora ISC.

   Fuente unica: este fichero. El HTML de la calculadora lo lleva incrustado
   (lo hace `apps/calculadora/construir.py`) y el Cotizador lo ejecuta en un
   subproceso de Node. Editar la copia incrustada en vez de esta es como
   acaban divergiendo dos precios de la misma pieza.

   No depende del navegador: no toca el DOM, ni `window`, ni ninguna base de
   datos. Todo lo que necesita entra por argumentos -- `computePN(pn, ctx)`.
*/

/* ---------- formatters ---------- */
function fmt(n,dec){ if(n===null||n===undefined||isNaN(n)) return '—';
 return Number(n).toLocaleString('en-US',{minimumFractionDigits:dec,maximumFractionDigits:dec}); }
const f0=n=>fmt(n,0), f1=n=>fmt(n,1), f2=n=>fmt(n,2), f3=n=>fmt(n,3), f4=n=>fmt(n,4);
function money(n,dec){ if(n===null||n===undefined||isNaN(n)) return '—';
 const sg=n<0?'-':''; return sg+'$'+fmt(Math.abs(n),dec===undefined?2:dec); }
function unitMoney(n){ if(n===null||n===undefined||isNaN(n)) return '—';
 const sg=n<0?'-':''; return sg+'$'+fmt(Math.abs(n), Math.abs(n)>=1?3:4); }
function pct(n){ return (n===null||n===undefined||isNaN(n))?'—':fmt(n,1)+'%'; }
function ratioFmt(v,r){ if(v===null||v===undefined||isNaN(v)) return '—';
 const rr=(r===null||r===undefined||isNaN(r)||!isFinite(r))?'—':String(Math.round(r)).padStart(2,'0');
 return fmt(v,2)+' ('+rr+')'; }
function parseNum(s){ if(typeof s==='number') return s;
 if(!s) return null; const n=parseFloat(String(s).replace(/[$,\s]/g,'')); return isNaN(n)?null:n; }

const DEFAULT_PARAMS={ matMk:6, compMk:6, consMk:6, subMk:50,
 contribution:20, hq:5, commissionNic:5,
 ohLadder:[30,30,30,30], ohSub:35, ohMin:10, ohMax:35,
 floorBase:800, floorPerOp:200, scrapDefault:5, wireMaxIn:0.59 };

const ENGINE=(function(){
 function opsUsed(routing){ return (routing||[]).filter(o=>o.machine&&(o.pph||o.setupH)); }
 function subEnabled(sub){ return !!(sub&&sub.supplier&&(sub.perLb!==null||sub.minUsd!==null)); }
 function tierOpsCount(t){ return opsUsed(t.routing).length+(subEnabled(t.sub)?1:0); }
 function tierOh(pn,t,P){
  if(pn.ohOverride!==null&&pn.ohOverride!==undefined&&pn.ohOverride!=='') return Number(pn.ohOverride);
  if(subEnabled(t.sub)) return P.ohSub;
  const n=tierOpsCount(t);
  if(n<=0) return P.ohLadder[0];
  return P.ohLadder[Math.min(n,4)-1];
 }
 /* Cuantas maquinas atiende un operario, segun lo que dure la tirada.
    Regla del taller (Miguel Rodea, 2026-09-03): la puesta a punto y las
    primeras 4 h van a maquina dedicada; a partir de ahi el operario cubre mas.
    Antes esto era un 1 fijo, o sea que toda tirada larga se cobraba como si
    hiciera falta una persona dedicada de principio a fin. */
 function maquinasPorOperario(horas){
  if(!(horas>4)) return 1;
  if(horas<=20) return 2;
  if(horas<=50) return 3;
  return 4;
 }
 function tierFloor(t,P){ return P.floorBase+P.floorPerOp*(Math.max(tierOpsCount(t),1)-1); }
 function yields(ops){
  const n=ops.length, yf=new Array(n+1).fill(1);
  /* El mismo defecto que ensena la casilla. Antes la pantalla pintaba
     `scrapPct||5` y aqui se calculaba con `||0`: una operacion sin merma
     declarada se veia al 5 % y se costeaba al 0 %. */
  for(let k=n-1;k>=0;k--){ const sp=(ops[k].scrapPct==null?5:ops[k].scrapPct);
   const s=Math.min(Math.max(sp/100,0),0.9); yf[k]=yf[k+1]*(1-s); }
  return yf;
 }
 /* ------------------------------------------------------------- el precio

    `computePN` era una funcion de 125 lineas: para saber por que una pieza
    salio a lo que salio habia que leerlas todas. Es la misma secuencia, con
    cada paso separado y con nombre. Ni una formula cambia.

    El orden es el del dinero: lo que vale para toda la pieza, luego lo que
    cuesta cada tramo -- material, proceso, subcontratacion, caja y utillaje --
    luego a que hay que venderlo, y al final que margen deja. */

 /* Lo que no depende del tramo, calculado una vez.

    `perLb` suma base, sobretasa y transporte porque el alambre se compra a ese
    precio total; la sobretasa se separa despues, para poder ensenarla aparte
    sin cobrarla dos veces. */
 function _basePieza(pn,ctx,P){
  const mk=pn.material.mkPct;
  return {
   wt:parseNum(pn.material.weightLb)||0,
   matMk:(mk===null||mk===undefined)?P.matMk:Number(mk),
   perLb:(parseNum(pn.material.basePerLb)||0)+(parseNum(pn.material.surchPerLb)||0)+(parseNum(pn.material.transpPerLb)||0),
   contrib:(ctx.contribution===undefined?P.contribution:ctx.contribution)/100,
   comm:(ctx.rep==='Nic Scherer'?P.commissionNic:0)/100,
   hq:P.hq/100 };
 }

 /* El material que hay que COMPRAR para entregar Q piezas buenas, mas los
    componentes y el consumible.

    Se compra por encima de Q por dos razones distintas: la merma de cada
    operacion -- de ahi `startQty` -- y el minimo del proveedor cuando pide mas
    alambre del que hace falta. Las dos suben el coste por pieza y las dos se
    dicen, porque las dos tienen salida: la primera bajando la merma, la
    segunda ofreciendo mas piezas por el mismo alambre. */
 function _materiaPrima(pn,B,Q,Y,P){
  const startQty=Q/Y;
  const lbNeeded=B.wt*startQty;
  const moq=parseNum(pn.material.moqLb);
  let lbBuy=lbNeeded, moqBind=false;
  if(moq&&moq>lbNeeded){ lbBuy=moq; moqBind=true; }
  const matRaw=Q>0?(lbBuy*B.perLb)/Q:0;
  const mat=matRaw*(1+B.matMk/100);
  const surchPart=B.wt&&B.perLb?((parseNum(pn.material.surchPerLb)||0)/B.perLb)*mat:0;
  const compRaw=(parseNum(pn.components[0].usd)||0)+(parseNum(pn.components[1].usd)||0);
  return { startQty,lbNeeded,lbBuy,moqBind,mat,surchPart,
   matNoSurch:mat-surchPart,
   comp:compRaw*(1+P.compMk/100),
   cons:(parseNum(pn.consumable.usd)||0)*(1+P.consMk/100) };
 }

 /* La ruta: horas de maquina y de operario, repartidas por pieza.

    Dos cosas que no son obvias y valen dinero. La primera, que la mano de obra
    se divide entre las maquinas que lleva un operario a la vez, y eso depende
    de lo que dure la tirada -- o sea del tramo, no de la maquina. La segunda,
    que la puesta a punto se paga entera tantas veces como lotes haya, asi que
    partir un tramo en cuatro lotes multiplica por cuatro ese coste.

    Se separa la mano de obra de las secundarias (`msVar`) de la del resto
    (`msFix`) porque en la cuenta de resultados van a lineas distintas. */
 function _proceso(ops,yf,Q,setups){
  let run=0,setup=0,machDirect=0,msVar=0,msFix=0,runHours=0,setupHours=0,tgtHrWeighted=0;
  const ratios=[];
  let scrapWarn=false;
  ops.forEach((o,k)=>{
   if((o.scrapPct||0)>5) scrapWarn=true;
   const m=parseNum(o.machH)||0,l=parseNum(o.laborH)||0;
   const pph=parseNum(o.pph)||0,sH=parseNum(o.setupH)||0;
   const pieces=Q/yf[k];
   const hrs=pph>0?pieces/pph:0;
   /* Sin valor propio se aplica la regla del taller, que depende de las horas
      de tirada y por tanto del tramo. Un numero escrito a mano manda. */
   const Rauto=maquinasPorOperario(hrs);
   const R=Math.max(parseNum(o.ratio)||Rauto,0.1);
   ratios.push(Rauto);   /* para que la pantalla pueda decir que aplica */
   const runMach=pph>0?m/pph/yf[k]:0;
   const runLab=pph>0?(l/R)/pph/yf[k]:0;
   const setMach=sH*m*setups/Q,setLab=sH*l*setups/Q;
   run+=runMach+runLab; setup+=setMach+setLab;
   machDirect+=runMach+setMach;
   const labPc=runLab+setLab;
   if(o.family==='SECONDARY') msVar+=labPc; else msFix+=labPc;
   runHours+=hrs; setupHours+=sH*setups;
   tgtHrWeighted+=(hrs+sH*setups)*(parseNum(o.tgtH)||m);
  });
  const hours=runHours+setupHours;
  return { run,setup,machDirect,msVar,msFix,runHours,setupHours,hours,ratios,scrapWarn,
   tgtRate:hours>0?tgtHrWeighted/hours:null };
 }

 /* Lo que cobra el recubridor, y lo que cuesta llevarle las piezas.

    El precio va por LOTE, no por pieza: manda el mayor de los tres -- minimo,
    por libra o por pieza -- y se reparte entre las piezas del lote. Por eso un
    lote pequeno sale caro por pieza aunque la tarifa sea la misma.

    El transporte son viajes de ida y vuelta, uno por tarima. Si dos piezas
    comparten tarima, el viaje se reparte: `shareCountFn` dice entre cuantas. */
 function _subcontratacion(tier,B,Q,ctx,ti,P){
  if(!subEnabled(tier.sub)) return { subRaw:0, subMk:0, subTransp:0 };
  const ppb=Math.max(parseNum(tier.sub.partsPerBatch)||Q,1);
  const bw=ppb*B.wt;
  const cb=Math.max(parseNum(tier.sub.minUsd)||0,(parseNum(tier.sub.perLb)||0)*bw,(parseNum(tier.sub.perPc)||0)*ppb);
  const subRaw=cb/ppb;
  const supDb=(ctx.dbs.subcontractors||[]).find(s=>s.name===tier.sub.supplier);
  const trip=supDb?supDb.loopTrip:150, skidMax=supDb?supDb.skidMaxLb:2400;
  const skids=Math.max(Math.ceil(bw/skidMax),1);
  let tb=trip*skids;
  const shareN=(ctx.shareCountFn?ctx.shareCountFn(ti,tier.sub.supplier):1);
  if(tier.sub.shareSkid==='YES'&&shareN>1) tb=tb/shareN;
  return { subRaw, subMk:subRaw*(1+P.subMk/100), subTransp:tb/ppb };
 }

 /* A cuanto hay que venderlo.

    El coste variable se divide entre lo que queda despues de contribucion,
    comision, HQ y overheads -- no se le suma un margen encima: es lo que hace
    que el porcentaje de contribucion se cumpla de verdad.

    Y hay un suelo por trabajo: ISC no abre una orden por menos de eso, se
    reparta entre las piezas que se reparta. Un precio escrito a mano manda
    sobre los dos, pero se dice cuando queda por debajo. */
 function _precioDeVenta(tier,Q,vc,divisor,fJob){
  const sellCalc=divisor>0.05?vc/divisor:null;
  const floorPc=fJob/Q;
  let sell=sellCalc!==null?Math.max(sellCalc,floorPc):floorPc;
  let overridden=false,belowFloor=false;
  const ov=parseNum(tier.override);
  if(ov!==null){ sell=ov; overridden=true; belowFloor=ov<floorPc-1e-9; }
  return { sellCalc, floorPc, sell, overridden, belowFloor,
   floorBinds:!overridden&&sellCalc!==null&&floorPc>sellCalc,
   belowContrib:overridden&&sellCalc!==null&&ov<sellCalc-1e-9 };
 }

 /* Lo que queda, escalon por escalon, como lo mira CGR: del precio se van
    restando compras, mano de obra variable, maquina y estructura. `ccvHr`
    contra el objetivo de la maquina es lo que dice si la pieza merece la pena
    ocupar esa maquina, que no es lo mismo que si deja margen. */
 function _margen(sell,Q,purchases,pr,oh,B){
  const av=sell-purchases;
  const ccv=av-pr.msVar;
  const ccd=ccv-pr.machDirect-pr.msFix;
  const ohV=oh*sell,hqV=B.hq*sell,commV=B.comm*sell;
  const ccvHr=pr.hours>0?(ccv*Q)/pr.hours:null;
  return { purchases,av,msVar:pr.msVar,machDirect:pr.machDirect,msFix:pr.msFix,
   ccv,ccd,ohV,hqV,commV,
   result:ccd-ohV-hqV-commV,
   avPct:sell?av/sell*100:null, msVarPct:sell?pr.msVar/sell*100:null,
   ccvPct:sell?ccv/sell*100:null, ccdPct:sell?ccd/sell*100:null,
   ccvHr, tgtRate:pr.tgtRate,
   ratio:(ccvHr!==null&&pr.tgtRate)?ccvHr/pr.tgtRate:null };
 }

 /* Un tramo entero. Se lee de arriba abajo como se calcula. */
 function _tramo(pn,tier,ti,B,ctx,P){
  const Q=parseNum(tier.qty);
  if(!Q||Q<=0) return null;

  const ops=opsUsed(tier.routing);
  const yf=yields(ops); const Y=yf[0]||1;

  /* La contribucion y los overheads pueden venir forzados en el tramo. */
  const tCon=parseNum(tier.contribPct), tOhP=parseNum(tier.ohPct);
  const contribT=(tCon===null?B.contrib:tCon/100);
  const oh=(tOhP===null?tierOh(pn,tier,P):tOhP)/100;
  const divisor=1-contribT-B.comm-B.hq-oh;

  const batch=parseNum(tier.prodBatch);
  const setups=(batch&&batch>0)?Math.max(1,Math.ceil(Q/batch)):1;

  const mp=_materiaPrima(pn,B,Q,Y,P);
  const pr=_proceso(ops,yf,Q,setups);
  const sc=_subcontratacion(tier,B,Q,ctx,ti,P);

  const packDb=(ctx.dbs.packing||[]).find(p=>p.id===tier.packing.id);
  const pack=(packDb&&parseNum(tier.packing.qtyPerBox))?packDb.price/parseNum(tier.packing.qtyPerBox):0;
  const tool=(parseNum(tier.tooling.cost)&&parseNum(tier.tooling.amortQty))?parseNum(tier.tooling.cost)/parseNum(tier.tooling.amortQty):0;

  const purchases=mp.mat+mp.comp+mp.cons+sc.subMk+sc.subTransp+pack+tool;
  const vc=purchases+pr.run+pr.setup;
  const fJob=tierFloor(tier,P);
  const v=_precioDeVenta(tier,Q,vc,divisor,fJob);

  return { qty:Q,startQty:mp.startQty,lbNeeded:mp.lbNeeded,lbBuy:mp.lbBuy,
   moqBind:mp.moqBind,scrapWarn:pr.scrapWarn,setups,
   mat:mp.mat,matNoSurch:mp.matNoSurch,surchPart:mp.surchPart,comp:mp.comp,cons:mp.cons,
   subRaw:sc.subRaw,subMk:sc.subMk,subTransp:sc.subTransp,pack,tool,
   run:pr.run,setup:pr.setup,vc,
   ratios:pr.ratios,nOps:tierOpsCount(tier),oh:oh*100,contribPct:contribT*100,divisor,
   sellCalc:v.sellCalc,floorPc:v.floorPc,floorJob:fJob,sell:v.sell,
   overridden:v.overridden,belowFloor:v.belowFloor,belowContrib:v.belowContrib,
   floorBinds:v.floorBinds,
   revenue:v.sell*Q,
   hours:pr.hours,runHours:pr.runHours,setupHours:pr.setupHours,
   sub:subEnabled(tier.sub),
   pnl:_margen(v.sell,Q,purchases,pr,oh,B),
   setupShare:vc>0?pr.setup/vc:0 };
 }

 /* Lo que hay que decirle a quien cotiza, mirando los tramos ya calculados.
    Van juntos y al final a proposito: son avisos sobre el resultado, no parte
    del calculo, y mezclarlos con las formulas era lo que hacia ilegible esto. */
 function _avisos(pn,tiers,ctx,B,flags){
  tiers.forEach((t,i)=>{ if(!t) return;
   const tn='Tier '+(i+1);
   if(t.scrapWarn) flags.push({t:'warn',m:tn+': an operation carries scrap > 5% — customers do not pay for lack of productivity.'});
   if(t.divisor<=0.05) flags.push({t:'err',m:tn+': gross-up divisor ≤ 5% — no cost coverage left.'});
   if(t.oh<ctx.params.ohMin||t.oh>ctx.params.ohMax) flags.push({t:'warn',m:tn+': overheads '+f1(t.oh)+'% outside CGR range '+ctx.params.ohMin+'–'+ctx.params.ohMax+'%.'});
   if(t.moqBind){ const altQty=Math.floor(t.lbBuy/Math.max(B.wt,1e-9));
    flags.push({t:'info',m:tn+': MOQ '+f0(t.lbBuy)+' lb > needed '+f1(t.lbNeeded)+' lb — quoted at MOQ cost. Option: offer ~'+f0(altQty)+' pcs.'}); }
   if(t.belowFloor) flags.push({t:'err',m:tn+': override '+money(t.sell,4)+' is BELOW the ISC floor '+money(t.floorPc,4)+' /pc ('+money(t.floorJob,0)+' per job).'});
   else if(t.belowContrib) flags.push({t:'warn',m:tn+': override '+money(t.sell,4)+' is below the '+f0((ctx.contribution===undefined?ctx.params.contribution:ctx.contribution))+'% contribution price '+money(t.sellCalc,4)+'.'});
   if(t.floorBinds) flags.push({t:'info',m:tn+': ISC floor binds ('+money(t.floorJob,0)+' job ÷ '+f0(t.qty)+' pcs).'});
   if(t.setupShare>0.30) flags.push({t:'warn',m:tn+': setup is '+f0(t.setupShare*100)+'% of variable cost — low-volume inefficiency; consider a larger batch.'});
   const tRaw=pn.tiers[i];
   if(tRaw&&tRaw.moqMode!=='STORE'&&t.sub){ const ppb=parseNum(tRaw.sub&&tRaw.sub.partsPerBatch);
    if(ppb&&ppb<t.qty) flags.push({t:'warn',m:tn+': MOQ TO PRODUCE & SHIP but the subcontracting lot ('+f0(ppb)+' pcs) is smaller than the MOQ ('+f0(t.qty)+' pcs) — the price carries lot minimums / freight loops that single-shipment terms do not require. Set the lot to the MOQ or switch the tier to PRODUCE & STORE.'}); }
  });
  if(!tiers.some(x=>x)) flags.push({t:'warn',m:'No volume tiers entered.'});
 }

 function computePN(pn,ctx){
  const P=ctx.params;
  const B=_basePieza(pn,ctx,P);
  const flags=[];
  if((parseNum(pn.material.diaIn)||0)>=P.wireMaxIn) flags.push({t:'err',m:'Wire Ø '+pn.material.diaIn+'" ≥ 0.59" (15 mm) — NOT FEASIBLE at ISC. Do not price.'});
  const tiers=pn.tiers.map((tier,ti)=>_tramo(pn,tier,ti,B,ctx,P));
  _avisos(pn,tiers,ctx,B,flags);
  return { tiers, flags };
 }

 function suggestMaterial(code,diaIn,dbs){
  const rows=(dbs.materialPrices||[]).filter(r=>r.code===code&&r.dia&&r.latest);
  if(!rows.length) return {price:null,basis:'no history for '+code};
  rows.sort((a,b)=>a.dia-b.dia);
  const d=Number(diaIn);
  if(!d) return {price:null,basis:'enter wire Ø first'};
  const exact=rows.find(r=>Math.abs(r.dia-d)<1e-9);
  if(exact) return {price:exact.latest,basis:'exact match '+exact.dia+'" ('+exact.date+', '+exact.sup+')'};
  let below=null,above=null;
  rows.forEach(r=>{ if(r.dia<d) below=r; if(r.dia>d&&!above) above=r; });
  if(below&&above){
   const t=(Math.log(d)-Math.log(below.dia))/(Math.log(above.dia)-Math.log(below.dia));
   const p=Math.exp(Math.log(below.latest)+t*(Math.log(above.latest)-Math.log(below.latest)));
   return {price:Math.round(p*100)/100,basis:'interpolated between '+below.dia+'" ($'+below.latest+') and '+above.dia+'" ($'+above.latest+')'};
  }
  const near=below||above;
  return {price:near.latest,basis:'EXTRAPOLATED from nearest '+near.dia+'" — manual review',extrapolated:true};
 }
 function suggestSurcharge(code,dbs){
  /* De `dbs`, no del `SEED` global. Todo lo demas de este fichero recibe las
     tablas por argumento -- es lo que permite que el Cotizador lo ejecute con
     las filas que saca de Postgres --, y esta linea era la unica que se saltaba
     la regla. En el navegador da igual (`shared.dbs` es una copia de `SEED`),
     pero desde Node reventaba con "SEED is not defined" en cuanto una pieza
     llevaba sobretasa. */
  if(!((dbs||{}).surchargeAppliesTo||[]).includes(code)) return 0;
  const s=(dbs.surcharges||[]).find(x=>x.code===code);
  return s?s.perLb:0;
 }
 function mapMaterialText(raw,dbs){
  if(!raw) return '';
  const t=String(raw).toUpperCase();
  const codes=Object.keys(dbs.materialLegend||{});
  for(const c of codes) if(t===c||t.startsWith(c+' ')) return c;
  if(/17-?7|SS177|631/.test(t)) return 'SS177';
  if(/316/.test(t)) return '316';
  if(/STAINLESS|302|304|\bSS\b/.test(t)) return 'SS';
  if(/GALV.*MUSIC|GMW/.test(t)) return 'GMW';
  if(/GALV/.test(t)) return 'GHD';
  if(/MUSIC|\bMW\b|A228/.test(t)) return 'MW';
  if(/CHROME|CSI|A401/.test(t)) return 'CSI';
  if(/OIL|\bOT\b|A229/.test(t)) return 'OT';
  if(/HARD.?DRAWN|\bHD\b|A227/.test(t)) return 'HD';
  if(/PHOS/.test(t)) return 'PHOSB';
  if(/BRASS/.test(t)) return 'BRASS';
  if(/HAST/.test(t)) return 'HAST';
  if(/BAR/.test(t)) return 'BB';
  return '';
 }
 const WIRE_DENS={MW:.284,CSI:.284,HD:.284,OT:.284,GMW:.284,GHD:.284,SG:.284,BB:.284,SS:.286,PHOSB:.320,BRASS:.308,HAST:.321};
 function wireDensity(code){ return WIRE_DENS[String(code||'').toUpperCase()]||0.284; }
 function wireFormWeight(devLenIn,diaIn,code){
  const L=parseNum(devLenIn),d=parseNum(diaIn);
  if(!L||!d||L<=0||d<=0) return null;
  return Math.PI/4*d*d*L*wireDensity(code); }
 return { computePN, suggestMaterial, suggestSurcharge, mapMaterialText, opsUsed, subEnabled, tierOpsCount, tierOh, tierFloor, wireDensity, wireFormWeight };
})();

/* Para Node. En el navegador `module` no existe y esto no hace nada. */
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ENGINE, DEFAULT_PARAMS, parseNum,
                     fmt, f0, f1, f2, f3, f4, money, unitMoney, pct, ratioFmt };
}
