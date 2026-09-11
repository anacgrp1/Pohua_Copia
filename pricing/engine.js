// pricing/engine.js
// Extracted from ISC Price Calculator V5

const SEED = {"machines":[{"family":"COILER","name":"AIM 3000","m1":"AIM30","setupH":6.0,"pph":327.0,"purchase":700000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":52.0833,"ccvTargetH":156.2499,"wireMinMm":0.8,"wireMaxMm":6.0,"odMaxMm":80.0,"capC":true,"capE":true,"capT":true,"setupClass":"High","uses":"High-capability CNC former. Complex geometries, all three spring types, medium-to-large wire.","risk":"Highest setup time and tooling cost; reserve for complex or higher-value parts."},{"family":"COILER","name":"AIM AFM-3D2-T","m1":"3D2T","setupH":2.0,"pph":450.0,"purchase":250000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":18.6012,"ccvTargetH":55.8036,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"COILER","name":"NUCOIL CSF-200","m1":"NUCO2","setupH":6.0,"pph":327.0,"purchase":200000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":14.881,"ccvTargetH":44.643,"wireMinMm":0.15,"wireMaxMm":2.0,"odMaxMm":25.0,"capC":true,"capE":true,"capT":false,"setupClass":"Medium","uses":"Fine-wire compression / extension coiler. Efficient for small high-volume parts.","risk":"No torsion capability; restricted OD and wire range."},{"family":"COILER","name":"NUCOIL CSF-400","m1":"NUCOI","setupH":6.0,"pph":327.0,"purchase":300000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":22.3214,"ccvTargetH":66.9642,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"COILER","name":"NUCOIL HX-60","m1":"HX-60","setupH":10.0,"pph":327.0,"purchase":400000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":29.7619,"ccvTargetH":89.2857,"wireMinMm":1.0,"wireMaxMm":6.0,"odMaxMm":90.0,"capC":true,"capE":true,"capT":false,"setupClass":"Medium","uses":"Heavy-duty coiler for larger compression and extension springs.","risk":"No torsion capability; limited for complex end forming."},{"family":"COILER","name":"SIMPLEX MC 50","m1":"MC50","setupH":5.0,"pph":600.0,"purchase":650000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":48.3631,"ccvTargetH":145.0893,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"COILER","name":"KMH-516","m1":"K516","setupH":5.0,"pph":600.0,"purchase":100000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":7.4405,"ccvTargetH":22.3215,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"COILER","name":"KMH-508","m1":"K508","setupH":5.0,"pph":600.0,"purchase":100000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":7.4405,"ccvTargetH":22.3215,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"COILER","name":"SLEEPER 1/2","m1":"","setupH":2.0,"pph":360.0,"purchase":100000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":7.4405,"ccvTargetH":22.3215,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"COILER","name":"SHINKO TF-45","m1":"TF-45","setupH":10.0,"pph":327.0,"purchase":700000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":52.0833,"ccvTargetH":156.2499,"wireMinMm":0.5,"wireMaxMm":4.5,"odMaxMm":55.0,"capC":true,"capE":true,"capT":true,"setupClass":"High","uses":"Mid-range precision CNC former. Versatile for all types in the medium wire band.","risk":"Setup-intensive; over-capable (uneconomic) for simple high-volume parts."},{"family":"COILER","name":"SHINKO TF-23","m1":"TF-23","setupH":10.0,"pph":327.0,"purchase":400000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":29.7619,"ccvTargetH":89.2857,"wireMinMm":0.2,"wireMaxMm":2.3,"odMaxMm":30.0,"capC":true,"capE":true,"capT":true,"setupClass":"High","uses":"Fine-wire precision CNC former. Small intricate springs, tight tolerances, all types.","risk":"Not suitable for larger wire; setup-intensive for simple parts."},{"family":"COILER","name":"ZX250","m1":"ZX250","setupH":6.0,"pph":450.0,"purchase":250000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":18.6012,"ccvTargetH":55.8036,"wireMinMm":0.3,"wireMaxMm":2.5,"odMaxMm":32.0,"capC":true,"capE":true,"capT":true,"setupClass":"Medium","uses":"Compact CNC former. Good all-round machine for small / medium parts of all types.","risk":"Limited to small wire and OD; verify torsion tooling availability."},{"family":"COILER","name":"AUTOLINK","m1":"AUTOL","setupH":6.0,"pph":600.0,"purchase":250000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":18.6012,"ccvTargetH":55.8036,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"COILER","name":"TORIN (FENN) FZ-11","m1":"FZ-11","setupH":3.0,"pph":600.0,"purchase":200000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":14.881,"ccvTargetH":44.643,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"COILER","name":"TORIN (FENN) W10A","m1":"W10A","setupH":3.0,"pph":600.0,"purchase":150000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":11.1607,"ccvTargetH":33.4821,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"COILER","name":"TORIN (FENN) W115A","m1":"W115","setupH":3.0,"pph":600.0,"purchase":150000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":11.1607,"ccvTargetH":33.4821,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"COILER","name":"TORIN (FENN) W11A","m1":"W11A","setupH":3.0,"pph":600.0,"purchase":150000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":11.1607,"ccvTargetH":33.4821,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"COILER","name":"TORIN (FENN) W11T","m1":"W11T","setupH":3.0,"pph":600.0,"purchase":150000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":11.1607,"ccvTargetH":33.4821,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"COILER","name":"TORIN (FENN) W125","m1":"W125","setupH":3.0,"pph":600.0,"purchase":150000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":11.1607,"ccvTargetH":33.4821,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"COILER","name":"TORIN (FENN) W12T","m1":"W12T","setupH":3.0,"pph":600.0,"purchase":150000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":11.1607,"ccvTargetH":33.4821,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"COILER","name":"TORIN (FENN) Z-11","m1":"Z-11","setupH":3.0,"pph":600.0,"purchase":150000.0,"laborH":40.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.8,"costRateH":11.1607,"ccvTargetH":33.4821,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"SECONDARY","name":"Grinder A","m1":"SEC","setupH":1.0,"pph":null,"purchase":150000.0,"laborH":27.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.6,"costRateH":11.1607,"ccvTargetH":55.8035,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"SECONDARY","name":"Grinder B","m1":"SEC","setupH":1.0,"pph":null,"purchase":140000.0,"laborH":27.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.6,"costRateH":10.4167,"ccvTargetH":52.0835,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"SECONDARY","name":"Grinder C","m1":"SEC","setupH":1.0,"pph":null,"purchase":130000.0,"laborH":27.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.6,"costRateH":9.6726,"ccvTargetH":48.363,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"SECONDARY","name":"Grinder D","m1":"SEC","setupH":1.0,"pph":null,"purchase":120000.0,"laborH":27.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.6,"costRateH":8.9286,"ccvTargetH":44.643,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"SECONDARY","name":"Grinder PED","m1":"SEC","setupH":1.0,"pph":null,"purchase":80000.0,"laborH":27.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.6,"costRateH":5.9524,"ccvTargetH":29.762,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"SECONDARY","name":"Stationary Oven","m1":"SEC","setupH":3.0,"pph":null,"purchase":120000.0,"laborH":27.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.6,"costRateH":8.9286,"ccvTargetH":44.643,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"SECONDARY","name":"Looping / Hooks","m1":"SEC","setupH":1.0,"pph":null,"purchase":null,"laborH":27.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.6,"costRateH":null,"ccvTargetH":null,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"SECONDARY","name":"Bending / Kick","m1":"SEC","setupH":1.0,"pph":null,"purchase":null,"laborH":27.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.6,"costRateH":null,"ccvTargetH":null,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"SECONDARY","name":"Assembly","m1":"SEC","setupH":1.0,"pph":null,"purchase":null,"laborH":27.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.6,"costRateH":null,"ccvTargetH":null,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""},{"family":"SECONDARY","name":"Inspection / Sorting","m1":"SEC","setupH":1.0,"pph":null,"purchase":null,"laborH":27.0,"amortYrs":7.0,"loadPct":1.0,"hPerYr":1920.0,"oee":0.6,"costRateH":null,"ccvTargetH":null,"wireMinMm":null,"wireMaxMm":null,"odMaxMm":null,"capC":null,"capE":null,"capT":null,"setupClass":"","uses":"","risk":""}],"materialLegend":{"BB":"Round Bar Stock","BRASS":"Brass Wire","CSI":"Chrome Silicon (ASTM A401)","GHD":"Galvanized Hard Drawn","GMW":"Galvanized Music Wire","HAST":"Hastelloy C-276","HD":"Hard Drawn (ASTM A227)","MW":"Music Wire (ASTM A228)","OT":"Oil Tempered (ASTM A229)","PHOSB":"Phosphor Bronze","SG":"Soft Galvanized","SS":"Stainless Steel 302/304 (ASTM A313)","SS177":"Stainless Steel 17-7 PH","316":"Stainless Steel 316 (ASTM A313 Type 316)"},"materialPrices":[],"surcharges":[],"surchargeAppliesTo":["SS","SS177","316"],"subcontractors":[],"platingHistory":[],"packing":[{"id":"COR100803","desc":"10 X 8 X 3 BOX","supplier":"SIP","price":0.63,"uom":"EACH","defaultPerBox":null},{"id":"GAYLORD","desc":"GAYLORD — special packaging","supplier":"ISC","price":30.0,"uom":"EACH","defaultPerBox":null}],"customers":[]};

const DEFAULT_PARAMS = { matMk:6, compMk:6, consMk:6, subMk:50, contribution:20, hq:5, commissionNic:5, ohLadder:[12,16,20,24], ohSub:28, ohMin:10, ohMax:35, floorBase:800, floorPerOp:200, scrapDefault:5, wireMaxIn:0.59 };

function parseNum(s){ if(typeof s==='number') return s; if(!s) return null; const n=parseFloat(String(s).replace(/[$,\s]/g,'')); return isNaN(n)?null:n; }

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
 function tierFloor(t,P){ return P.floorBase+P.floorPerOp*(Math.max(tierOpsCount(t),1)-1); }
 function yields(ops){
  const n=ops.length, yf=new Array(n+1).fill(1);
  for(let k=n-1;k>=0;k--){ const s=Math.min(Math.max((ops[k].scrapPct||0)/100,0),0.9); yf[k]=yf[k+1]*(1-s); }
  return yf;
 }
 function computePN(pn,ctx){
  const P=ctx.params;
  const wt=parseNum(pn.material.weightLb)||0;
  const matMk=(pn.material.mkPct===null||pn.material.mkPct===undefined)?P.matMk:Number(pn.material.mkPct);
  const perLb=(parseNum(pn.material.basePerLb)||0)+(parseNum(pn.material.surchPerLb)||0)+(parseNum(pn.material.transpPerLb)||0);
  const contrib=(ctx.contribution===undefined?P.contribution:ctx.contribution)/100;
  const comm=(ctx.rep==='Nic Scherer'?P.commissionNic:0)/100;
  const hq=P.hq/100;
  const flags=[];
  if((parseNum(pn.material.diaIn)||0)>=P.wireMaxIn) flags.push({t:'err',m:'Wire Ø '+pn.material.diaIn+'" ≥ 0.59" (15 mm) — NOT FEASIBLE at ISC. Do not price.'});

  const tiers=pn.tiers.map((tier,ti)=>{
   const Q=parseNum(tier.qty);
   if(!Q||Q<=0) return null;
   const ops=opsUsed(tier.routing);
   const yf=yields(ops); const Y=yf[0]||1;
   const sub=subEnabled(tier.sub);
   const tCon=parseNum(tier.contribPct), tOhP=parseNum(tier.ohPct);
   const contribT=(tCon===null?contrib:tCon/100);
   const oh=(tOhP===null?tierOh(pn,tier,P):tOhP)/100;
   const divisor=1-contribT-comm-hq-oh;
   const fJob=tierFloor(tier,P);
   const nOps=tierOpsCount(tier);
   const batch=parseNum(tier.prodBatch);
   const setups=(batch&&batch>0)?Math.max(1,Math.ceil(Q/batch)):1;
   const startQty=Q/Y;
   const lbNeeded=wt*startQty;
   const moq=parseNum(pn.material.moqLb);
   let lbBuy=lbNeeded, moqBind=false;
   if(moq&&moq>lbNeeded){ lbBuy=moq; moqBind=true; }
   const matRaw=Q>0?(lbBuy*perLb)/Q:0;
   const mat=matRaw*(1+matMk/100);
   const surchPart=wt&&perLb?((parseNum(pn.material.surchPerLb)||0)/perLb)*mat:0;
   const matNoSurch=mat-surchPart;
   const compRaw=(parseNum(pn.components[0].usd)||0)+(parseNum(pn.components[1].usd)||0);
   const comp=compRaw*(1+P.compMk/100);
   const cons=(parseNum(pn.consumable.usd)||0)*(1+P.consMk/100);
   let run=0,setup=0,machDirect=0,msVar=0,msFix=0,runHours=0,setupHours=0,tgtHrWeighted=0;
   let scrapWarn=false;
   ops.forEach((o,k)=>{
    if((o.scrapPct||0)>5) scrapWarn=true;
    const m=parseNum(o.machH)||0,l=parseNum(o.laborH)||0;
    const R=Math.max(parseNum(o.ratio)||1,0.1),pph=parseNum(o.pph)||0,sH=parseNum(o.setupH)||0;
    const pieces=Q/yf[k];
    const hrs=pph>0?pieces/pph:0;
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
   const tgtRate=hours>0?tgtHrWeighted/hours:null;
   let subRaw=0,subMk=0,subTransp=0;
   if(sub){
    const ppb=Math.max(parseNum(tier.sub.partsPerBatch)||Q,1);
    const bw=ppb*wt;
    const cb=Math.max(parseNum(tier.sub.minUsd)||0,(parseNum(tier.sub.perLb)||0)*bw,(parseNum(tier.sub.perPc)||0)*ppb);
    subRaw=cb/ppb; subMk=subRaw*(1+P.subMk/100);
    const supDb=(ctx.dbs.subcontractors||[]).find(s=>s.name===tier.sub.supplier);
    const trip=supDb?supDb.loopTrip:150, skidMax=supDb?supDb.skidMaxLb:2400;
    const skids=Math.max(Math.ceil(bw/skidMax),1);
    let tb=trip*skids;
    const shareN=(ctx.shareCountFn?ctx.shareCountFn(ti,tier.sub.supplier):1);
    if(tier.sub.shareSkid==='YES'&&shareN>1) tb=tb/shareN;
    subTransp=tb/ppb;
   }
   const packDb=(ctx.dbs.packing||[]).find(p=>p.id===tier.packing.id);
   const pack=(packDb&&parseNum(tier.packing.qtyPerBox))?packDb.price/parseNum(tier.packing.qtyPerBox):0;
   const tool=(parseNum(tier.tooling.cost)&&parseNum(tier.tooling.amortQty))?parseNum(tier.tooling.cost)/parseNum(tier.tooling.amortQty):0;
   const vc=mat+comp+cons+subMk+subTransp+pack+tool+run+setup;
   const sellCalc=divisor>0.05?vc/divisor:null;
   const floorPc=fJob/Q;
   let sell=sellCalc!==null?Math.max(sellCalc,floorPc):floorPc;
   let overridden=false,belowFloor=false;
   const ov=parseNum(tier.override);
   if(ov!==null){ sell=ov; overridden=true; belowFloor=ov<floorPc-1e-9; }
   const floorBinds=!overridden&&sellCalc!==null&&floorPc>sellCalc;
   const revenue=sell*Q;
   const purchases=mat+comp+cons+subMk+subTransp+pack+tool;
   const av=sell-purchases;
   const ccv=av-msVar;
   const ccd=ccv-machDirect-msFix;
   const ohV=oh*sell,hqV=hq*sell,commV=comm*sell;
   const result=ccd-ohV-hqV-commV;
   const ccvTier=ccv*Q;
   const ccvHr=hours>0?ccvTier/hours:null;
   const ratio=(ccvHr!==null&&tgtRate)?ccvHr/tgtRate:null;
   const setupShare=vc>0?setup/vc:0;
   const belowContrib=overridden&&sellCalc!==null&&ov<sellCalc-1e-9;
   return { qty:Q,startQty,lbNeeded,lbBuy,moqBind,scrapWarn,setups,
    mat,matNoSurch,surchPart,comp,cons,subRaw,subMk,subTransp,pack,tool,run,setup,vc,
    nOps,oh:oh*100,contribPct:contribT*100,divisor,sellCalc,floorPc,floorJob:fJob,sell,overridden,belowFloor,belowContrib,floorBinds,
    revenue,hours,runHours,setupHours,sub,
    pnl:{purchases,av,msVar,machDirect,msFix,ccv,ccd,ohV,hqV,commV,result,
     avPct:sell?av/sell*100:null,msVarPct:sell?msVar/sell*100:null,
     ccvPct:sell?ccv/sell*100:null,ccdPct:sell?ccd/sell*100:null,
     ccvHr,tgtRate,ratio},
    setupShare };
  });

  tiers.forEach((t,i)=>{ if(!t) return;
   const tn='Tier '+(i+1);
   if(t.scrapWarn) flags.push({t:'warn',m:tn+': an operation carries scrap > 5% — customers do not pay for lack of productivity.'});
   if(t.divisor<=0.05) flags.push({t:'err',m:tn+': gross-up divisor ≤ 5% — no cost coverage left.'});
   if(t.oh<ctx.params.ohMin||t.oh>ctx.params.ohMax) flags.push({t:'warn',m:tn+': overheads '+parseFloat(t.oh).toFixed(1)+'% outside CGR range '+ctx.params.ohMin+'–'+ctx.params.ohMax+'%.'});
   if(t.moqBind){ const altQty=Math.floor(t.lbBuy/Math.max(wt,1e-9));
    flags.push({t:'info',m:tn+': MOQ '+parseFloat(t.lbBuy).toFixed(0)+' lb > needed '+parseFloat(t.lbNeeded).toFixed(1)+' lb — quoted at MOQ cost. Option: offer ~'+parseFloat(altQty).toFixed(0)+' pcs.'}); }
   if(t.belowFloor) flags.push({t:'err',m:tn+': override '+parseFloat(t.sell).toFixed(4)+' is BELOW the ISC floor '+parseFloat(t.floorPc).toFixed(4)+' /pc ('+parseFloat(t.floorJob).toFixed(0)+' per job).'});
   else if(t.belowContrib) flags.push({t:'warn',m:tn+': override '+parseFloat(t.sell).toFixed(4)+' is below the '+parseFloat((ctx.contribution===undefined?ctx.params.contribution:ctx.contribution)).toFixed(0)+'% contribution price '+parseFloat(t.sellCalc).toFixed(4)+'.'});
   if(t.floorBinds) flags.push({t:'info',m:tn+': ISC floor binds ('+parseFloat(t.floorJob).toFixed(0)+' job ÷ '+parseFloat(t.qty).toFixed(0)+' pcs).'});
   if(t.setupShare>0.30) flags.push({t:'warn',m:tn+': setup is '+parseFloat(t.setupShare*100).toFixed(0)+'% of variable cost — low-volume inefficiency; consider a larger batch.'});
  });
  if(!tiers.some(x=>x)) flags.push({t:'warn',m:'No volume tiers entered.'});
  return { tiers, flags };
 }

 function suggestMaterial(code,diaIn,dbs){
  // Extracted stub
  return {price: 2.50, basis: 'STUB'};
 }
 function suggestSurcharge(code,dbs){ return 0; }
 function mapMaterialText(raw,dbs){ return ''; }
 const WIRE_DENS={MW:.284,CSI:.284,HD:.284,OT:.284,GMW:.284,GHD:.284,SG:.284,BB:.284,SS:.286,PHOSB:.320,BRASS:.308,HAST:.321};
 function wireDensity(code){ return WIRE_DENS[String(code||'').toUpperCase()]||0.284; }
 function wireFormWeight(devLenIn,diaIn,code){
  const L=parseNum(devLenIn),d=parseNum(diaIn);
  if(!L||!d||L<=0||d<=0) return null;
  return Math.PI/4*d*d*L*wireDensity(code); }
 return { computePN, suggestMaterial, suggestSurcharge, mapMaterialText, opsUsed, subEnabled, tierOpsCount, tierOh, tierFloor, wireDensity, wireFormWeight };
})();

module.exports = { ENGINE, SEED, DEFAULT_PARAMS };
