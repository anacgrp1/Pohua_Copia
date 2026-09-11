/* El calculo del resorte de ISC.

   Dado un resorte -- material, alambre, diametro, espiras, longitud libre --
   dice que fuerza da, si es fabricable, con que reservas, y en que bobinadora
   del taller sale. Es lo que decide el dictamen de factibilidad que la
   calculadora de precios necesita antes de dejar aprobar una oferta.

   POR QUE ESTA AQUI Y NO DENTRO DEL HTML
     Vivia dentro del Spring Engineering Calculator, y una copia hecha a mano
     vivia ademas en analisis/herramientas/motor.js, que llevaba tiempo rota
     sin que nadie lo notara. Dos copias del mismo calculo acaban dando dos
     dictamenes distintos para la misma pieza.

   LAS TABLAS NO ESTAN AQUI
     `MATERIALS`, `MACHINES` y `ORDEN_TALLER` salen del catalogo del nucleo, y
     `STATE` es de quien llame: en el navegador es el estado de la pantalla, y
     desde Node lo pone la herramienta. Se declaran vacios y se rellenan con
     `configurar()`; en el navegador los pisa directamente el HTML, que es lo
     que ya hacia cuando todo esto estaba dentro de el.

   Fuente unica: este fichero. El HTML lo lleva incrustado (`construir.py`).
   ========================================================================= */

/* Vacios a proposito: una llamada antes de tiempo falla donde se ve, y no con
   los datos de otra pieza. */
var MATERIALS = [];
var MACHINES = [];
var ORDEN_TALLER = {};
var STATE = { unit: 'in', comp: {}, ext: {}, tors: {} };

/* Las tablas del catalogo del nucleo, en la forma que usa este fichero.

   Vive aqui, en JavaScript, y no en el generador del HTML, porque hacen falta
   en los dos sitios: al construir la calculadora y al correr las herramientas
   desde Node. Escrito dos veces volveria a ser el problema que se acaba de
   quitar. */
function desdeCatalogo(cat) {
  const materiales = cat.matReference.map(r => ({
    id: r.id, name: r.name, astm: r.astm,
    G: r.G, E: r.E, density: r.densityKgM3, A: r.A, m: r.m,
    dMin: r.dMinMm, dMax: r.dMaxMm, tempMax: r.tempMaxC,
    shearFac: r.shearFac, bendFac: r.bendFac, costFac: r.costFac,
    fatigue: r.fatigue, note: r.note,
    codigo: r.codigo, alias: r.alias,
  }));

  /* Solo las de la hoja de Rodea: sin rango de alambre no hay forma de decidir
     si la pieza cabe. El resto del catalogo son centros de trabajo de
     operaciones secundarias, que esta aplicacion no elige. */
  const coil = cat.machines
    .filter(m => m.family === 'COILER' && m.wireMinMm)
    .sort((a, b) => a.rank - b.rank);

  const maquinas = coil.map(m => {
    /* "(FENN)" es como lo llama la contabilidad; en el taller es un TORIN.
       `_norm` de reglas.js hace que los dos nombres busquen la misma fila. */
    const name = m.name.replace('(FENN) ', '');
    /* La clase de setup es una lectura de las horas, no un dato aparte: se
       calcula para que no pueda contradecir a las horas con las que se cotiza. */
    const setup = m.setupH <= 2 ? 'Low' : (m.setupH <= 5 ? 'Medium' : 'High');
    /* Un tope por material bloquea la maquina, asi que manda sobre lo demas.
       Que no haya OD en la hoja no es un riesgo: es un dato que falta, y se
       dice tal cual para que nadie lo lea como "no tiene limite". */
    const risk = m.caps ? m.caps
      : (m.compSecondary ? 'compression needs a secondary operation'
        : (!m.odMaxMm ? 'no OD limit on record' : 'none on record'));
    return {
      id: name.toLowerCase().replace(/[^a-z0-9]/g, ''), name,
      wireMin: m.wireMinMm, wireMax: m.wireMaxMm,
      odMax: m.odMaxMm, odMin: m.odMinMm,
      compression: m.capC, extension: m.capE, torsion: m.capT, wireform: m.capW,
      compSecondary: m.compSecondary, rank: m.rank,
      pph: m.pph, setupH: m.setupH, rateH: m.costRateH, laborH: m.laborH,
      caps: m.caps, capMaterial: m.capMaterial, capWireMaxMm: m.capWireMaxMm,
      axes: m.uses, setup: setup,
      uses: m.uses + '. Usage rank ' + m.rank + ' of ' + coil.length + ' in 2026.',
      risk: risk,
    };
  });

  return { materiales, maquinas };
}

/* Las dos formas de nombrar un material.

   La cotizacion usa el codigo con el que se compra el alambre -- MW, OT,
   SS177 -- y el calculo del resorte usa el id de la constante de ingenieria --
   music, otemp, ss177. Un plano puede traer cualquiera de las dos, o el nombre
   escrito de otra forma.

   Estaba escrito dos veces, en direcciones opuestas: `SPRING_MAT` en la
   calculadora de precios y `_mm` en el Spring Calculator. Los alias salen
   ahora del catalogo, asi que anadir uno se hace en un sitio. */
function materialDelTexto(texto) {
  const t = String(texto || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  if (!t) return null;
  const m = MATERIALS.find(x => (x.alias || []).indexOf(t) >= 0);
  return m ? m.id : null;
}

/* El codigo de compra de un material, para pedir su $/lb. */
function codigoDeMaterial(id) {
  const m = MATERIALS.find(x => x.id === id);
  return m ? m.codigo : null;
}

/* Las reglas del taller, para cuando hagan falta aquí.

   Hoy sólo el tope por material, que decide si una máquina puede correr un
   alambre de ese material. Vive en `reglas.js` porque la aplica también la ruta
   automática de la cotización, y una regla en dos ficheros son dos reglas.

   Se busca al usarla, no al cargar: en el navegador los dos van incrustados en
   la misma página y el orden lo decide `construir.py`; desde Node se pide. */
function _reglas() {
  if (typeof REGLAS !== 'undefined') return REGLAS;
  if (typeof require !== 'undefined') return require('./reglas.js');
  return null;
}

function configurar(o) {
  if (o.materiales) MATERIALS = o.materiales;
  if (o.maquinas) MACHINES = o.maquinas;
  if (o.orden) ORDEN_TALLER = o.orden;
  if (o.estado) STATE = o.estado;
}

/* ---------- 1. UNIT CONVERSION ---------------------------------------------- */
var CONV = {
  len:   {in:1/25.4,        mm:1},          // mm -> display
  force: {in:1/4.4482216,   mm:1},          // N  -> display
  stress:{in:0.14503774/1,  mm:1},          // MPa-> display (ksi in inch mode)
  rate:  {in:5.7101471,     mm:1},          // N/mm -> display
  moment:{in:0.0088507458,  mm:1}           // N.mm -> display
};
var ULBL = {
  in:{len:'in',force:'lbf',stress:'ksi',rate:'lbf/in',moment:'lbf·in',freq:'Hz'},
  mm:{len:'mm',force:'N',  stress:'MPa', rate:'N/mm',  moment:'N·mm', freq:'Hz'}
};
function toDisp(siVal,kind,u){ return siVal*CONV[kind][u]; }
function toSI(dispVal,kind,u){ return dispVal/CONV[kind][u]; }
function ul(kind){ return ULBL[STATE.unit][kind]; }

/* ---------- 4. END-CONDITION TABLE (compression) ---------------------------- */
var END_TYPES = {
  plain:        {label:'Plain',             endCoils:0, ground:false},
  plain_ground: {label:'Plain & Ground',    endCoils:1, ground:true },
  closed:       {label:'Squared (Closed)',  endCoils:2, ground:false},
  closed_ground:{label:'Squared & Ground',  endCoils:2, ground:true }
};

/* ---------- 6. HELPERS ----------------------------------------------------- */
var PI = Math.PI;
function getMat(id){ for(var i=0;i<MATERIALS.length;i++) if(MATERIALS[i].id===id) return MATERIALS[i];
  return MATERIALS[0]; }
function num(v){ v=parseFloat(v); return isFinite(v)?v:0; }
function f(v,d){ if(d===undefined)d=2;
  if(v===null||v===undefined||!isFinite(v)) return '—';
  return v.toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:0}); }
function clamp(v,lo,hi){ return Math.max(lo,Math.min(hi,v)); }
function esc(s){ return String(s).replace(/[&<>"]/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }

/* tensile strength (MPa) from diameter (mm) using Sut = A / d^m */
function tensile(mat,d_mm){
  var dd=clamp(d_mm,0.05,30);
  return mat.A/Math.pow(dd,mat.m);
}
/* Wahl correction factor */
function wahl(C){ return (4*C-1)/(4*C-4) + 0.615/C; }
/* Bergstrasser correction factor */
function bergs(C){ return (4*C+2)/(4*C-3); }
/* curvature correction for bending (inner fibre) - torsion springs / hooks */
function kBendInner(C){ return (4*C*C-C-1)/(4*C*(C-1)); }

/* resolve mean diameter from a diameter value + mode + wire dia */
function resolveDia(mode,dia,d){
  if(mode==='OD')   return {D:dia-d,   OD:dia,     ID:dia-2*d};
  if(mode==='ID')   return {D:dia+d,   OD:dia+2*d, ID:dia};
  return {D:dia, OD:dia+d, ID:dia-d};               /* mean */
}

/* =====================================================================
   7. CALCULATION ENGINE
   ===================================================================== */

/* ---- 7a. COMPRESSION ------------------------------------------------- */
function calcCompression(I){
  var mat=getMat(I.matId), d=I.d, g=resolveDia(I.odMode,I.dia,d);
  var D=g.D, C=D/d, Na=I.Na, Nt=I.Nt, et=END_TYPES[I.endType];
  var Kw=wahl(C), Kb=bergs(C);
  var k = (mat.G*Math.pow(d,4))/(8*Math.pow(D,3)*Na);          /* N/mm */
  /* solid height */
  var Ls = et.ground ? d*Nt : d*(Nt+1);
  var L0=I.L0;
  /* pitch */
  var p;
  if(I.endType==='plain')        p=(L0-d)/Na;
  else if(I.endType==='plain_ground') p=L0/(Na+1);
  else if(I.endType==='closed')  p=(L0-3*d)/Na;
  else                           p=(L0-2*d)/Na;
  var helix = Math.atan(p/(PI*D))*180/PI;
  /* deflections & loads */
  var fSolid = L0-Ls;
  var Fsolid = k*fSolid;
  var defl   = L0-I.h;                       /* deflection at working height */
  var Fwork  = k*defl;
  var Sut=tensile(mat,d);
  var tauAllow = mat.shearFac*Sut;
  var tauWork  = Kw*8*Fwork*D /(PI*Math.pow(d,3));
  var tauSolid = Kw*8*Fsolid*D/(PI*Math.pow(d,3));
  var SFwork = tauAllow/tauWork;
  var SFsolid= tauAllow/tauSolid;
  var stressPctSolid = tauSolid/Sut*100;
  /* natural frequency (both ends fixed) fn = 0.5*sqrt(k/m) */
  var wireLen = PI*D*Na;                                  /* mm */
  var vol = (PI*d*d/4)*wireLen;                           /* mm^3 */
  var mass = vol*1e-9*mat.density;                        /* kg */
  var fn = 0.5*Math.sqrt((k*1000)/mass);                  /* Hz */
  /* buckling - critical deflection */
  var alpha = et.ground?0.5:0.707;
  var lamEff = alpha*L0/D;
  var C1 = mat.E/(2*(mat.E-mat.G));
  var C2 = 2*PI*PI*(mat.E-mat.G)/(2*mat.G+mat.E);
  var inside = 1 - C2/(lamEff*lamEff);
  var yCrit, absStable=false;
  if(inside<=0){ yCrit=Infinity; absStable=true; }          /* never buckles */
  else { yCrit = L0*C1*(1-Math.sqrt(inside)); }
  var bucklePct = absStable?0:(defl/yCrit*100);
  var slender = L0/D;
  var wireLenTot=PI*D*Nt/Math.cos(helix*PI/180);
  var partWeightKg=(PI*d*d/4)*wireLenTot*1e-9*mat.density;
  return {mat:mat,d:d,D:D,OD:g.OD,ID:g.ID,C:C,Na:Na,Nt:Nt,Kw:Kw,Kb:Kb,k:k,
    Ls:Ls,L0:L0,p:p,helix:helix,fSolid:fSolid,Fsolid:Fsolid,defl:defl,Fwork:Fwork,
    Sut:Sut,tauAllow:tauAllow,tauWork:tauWork,tauSolid:tauSolid,
    SFwork:SFwork,SFsolid:SFsolid,stressPctSolid:stressPctSolid,
    fn:fn,mass:mass,yCrit:yCrit,absStable:absStable,bucklePct:bucklePct,
    slender:slender,alpha:alpha,h:I.h,partWeightKg:partWeightKg,wireLenTot:wireLenTot};
}

/* ---- 7b. EXTENSION --------------------------------------------------- */
function calcExtension(I){
  var mat=getMat(I.matId), d=I.d, g=resolveDia(I.odMode,I.dia,d);
  var D=g.D, C=D/d, Na=I.Na, Kw=wahl(C);
  var k=(mat.G*Math.pow(d,4))/(8*Math.pow(D,3)*Na);          /* N/mm */
  var Fi=I.Fi, x=I.x;
  var F=Fi+k*x;
  var Sut=tensile(mat,d);
  var tauAllow=mat.shearFac*Sut;
  var sigAllow=mat.bendFac*Sut;
  /* body stress */
  var tauBody=Kw*8*F*D/(PI*Math.pow(d,3));
  /* uncorrected initial-tension stress */
  var tauI=8*Fi*D/(PI*Math.pow(d,3));
  /* preferred initial-tension torsional-stress band (SMI), psi -> MPa */
  var tauIprefPsi = 33500/Math.exp(0.105*C);
  var bandPsi = 1000*(4-(C-3)/6.5); if(bandPsi<0) bandPsi=0;
  var tauIpref   = tauIprefPsi*0.00689476;
  var tauIbandLo = (tauIprefPsi-bandPsi)*0.00689476;
  var tauIbandHi = (tauIprefPsi+bandPsi)*0.00689476;
  /* hook stresses */
  var r1=I.r1>0?I.r1:D/2, r2=I.r2>0?I.r2:D/2;
  var C1h=2*r1/d, C2h=2*r2/d;
  var K1 = C1h>1.05 ? (4*C1h*C1h-C1h-1)/(4*C1h*(C1h-1)) : 1.25;
  var K2 = C2h>1.05 ? (4*C2h-1)/(4*C2h-4) : 1.25;
  var sigHookA = F*( K1*16*D/(PI*Math.pow(d,3)) + 4/(PI*d*d) );  /* bending at body-to-hook */
  var tauHookB = K2*8*F*D/(PI*Math.pow(d,3));                    /* torsion at hook bend */
  /* safety factors */
  var SFbody = tauAllow/tauBody;
  var SFhookA= sigAllow/sigHookA;
  var SFhookB= tauAllow/tauHookB;
  /* max safe extension - governed by lowest-capacity location */
  var Fbody  = tauAllow*PI*Math.pow(d,3)/(Kw*8*D);
  var FhookB = tauAllow*PI*Math.pow(d,3)/(K2*8*D);
  var FhookA = sigAllow/( K1*16*D/(PI*Math.pow(d,3)) + 4/(PI*d*d) );
  var Fcap=Math.min(Fbody,FhookA,FhookB);
  var govName = Fcap===Fbody?'spring body':(Fcap===FhookA?'hook bend (point A)':'hook bend (point B)');
  var xMax=(Fcap-Fi)/k;
  /* hook developed length: loop of mean radius r1, turns set by hook style */
  var hookTurns=({machine_full:1.0,machine_half:0.55,crossover:1.15,side:1.05,extended:1.7,special:1.2})[I.hookType]||1.0;
  var hookDevLen=hookTurns*2*PI*r1;
  var wireLenTot=PI*D*Na+2*hookDevLen;
  var partWeightKg=(PI*d*d/4)*wireLenTot*1e-9*mat.density;
  return {mat:mat,d:d,D:D,OD:g.OD,ID:g.ID,C:C,Na:Na,Kw:Kw,k:k,Fi:Fi,x:x,F:F,
    Sut:Sut,tauAllow:tauAllow,sigAllow:sigAllow,tauBody:tauBody,tauI:tauI,
    tauIpref:tauIpref,tauIbandLo:tauIbandLo,tauIbandHi:tauIbandHi,
    r1:r1,r2:r2,K1:K1,K2:K2,sigHookA:sigHookA,tauHookB:tauHookB,
    SFbody:SFbody,SFhookA:SFhookA,SFhookB:SFhookB,
    xMax:xMax,Fcap:Fcap,govName:govName,bodyLen:I.bodyLen,hookType:I.hookType,partWeightKg:partWeightKg,wireLenTot:wireLenTot};
}

/* ---- 7c. TORSION ----------------------------------------------------- */
function calcTorsion(I){
  var mat=getMat(I.matId), d=I.d, g=resolveDia(I.odMode,I.dia,d);
  var D=g.D, C=D/d, Nb=I.Nb;
  /* active coils incl. leg contribution (two legs of equal length assumed) */
  var Ne=(2*I.legLen)/(3*PI*D);
  var Na=Nb+Ne;
  var Ki=kBendInner(C);
  /* angular rate: moment per revolution (10.8 empirical incl. friction) */
  var kRev=(mat.E*Math.pow(d,4))/(10.8*D*Na);     /* N.mm / rev */
  var kDeg=kRev/360;                              /* N.mm / deg */
  var ang=I.angle;
  var M=kDeg*ang;                                 /* N.mm at given angle */
  var Sut=tensile(mat,d);
  var sigAllow=mat.bendFac*Sut;
  var sigma=Ki*32*M/(PI*Math.pow(d,3));           /* bending stress, inner fibre */
  var SF=sigAllow/sigma;
  /* safe angular deflection */
  var sigPerDeg=Ki*32*kDeg/(PI*Math.pow(d,3));
  var angSafe=sigAllow/sigPerDeg;
  /* diameter change under load */
  var angRev=ang/360;
  var Dload, idLoad;
  if(I.loadDir==='closing'){ Dload=D*Nb/(Nb+angRev); }
  else                     { Dload=D*Nb/Math.max(Nb-angRev,0.01); }
  idLoad=Dload-d;
  var mandrelClear=idLoad-I.mandrel;
  var mandrelRec=0.90*idLoad;
  /* body length */
  var bodyLen=d*(Nb+1);
  var wireLenTot=PI*D*Nb+2*I.legLen;
  var partWeightKg=(PI*d*d/4)*wireLenTot*1e-9*mat.density;
  return {mat:mat,d:d,D:D,OD:g.OD,ID:g.ID,C:C,Nb:Nb,Ne:Ne,Na:Na,Ki:Ki,
    kRev:kRev,kDeg:kDeg,angle:ang,M:M,Sut:Sut,sigAllow:sigAllow,sigma:sigma,SF:SF,
    angSafe:angSafe,Dload:Dload,idLoad:idLoad,mandrel:I.mandrel,
    mandrelClear:mandrelClear,mandrelRec:mandrelRec,bodyLen:bodyLen,
    windDir:I.windDir,loadDir:I.loadDir,legLen:I.legLen,partWeightKg:partWeightKg,wireLenTot:wireLenTot};
}

/* =====================================================================
   8. MANUFACTURABILITY SCORING  -> {score, flags:[{level,title,rec}]}
   level: crit | warn | info | ok
   ===================================================================== */
function scoreCommon(flags,d,mat){
  var pen=0;
  if(d<mat.dMin||d>mat.dMax){
    pen+=15;
    flags.push({level:'warn',title:'Wire diameter outside material data range',
      rec:'Wire ø '+f(toDisp(d,'len',STATE.unit),3)+' '+ul('len')+
      ' is outside the validated range for '+mat.name+
      ' ('+f(toDisp(mat.dMin,'len',STATE.unit),3)+'–'+
      f(toDisp(mat.dMax,'len',STATE.unit),3)+' '+ul('len')+
      '). Tensile-strength estimate is extrapolated — confirm with the wire supplier.'});
  }
  return pen;
}
function bandFromScore(s){
  if(s>=90) return {band:'Easy to manufacture',  color:'#1f8a4c',
    desc:'Design sits well inside normal shop limits.'};
  if(s>=70) return {band:'Manufacturable',       color:'#3f9e57',
    desc:'Producible with normal process controls.'};
  if(s>=50) return {band:'Engineering review',   color:'#b9770e',
    desc:'Requires engineering review before quoting / release.'};
  if(s>=30) return {band:'High manufacturing risk',color:'#d35400',
    desc:'Significant risk — expect yield loss and added cost.'};
  return {band:'Not recommended',color:'#c0392b',
    desc:'Design is at or beyond practical limits — redesign advised.'};
}

function scoreCompression(R){
  var flags=[], pen=0, mat=R.mat;
  /* Un 100 sin punto de trabajo no es un resorte impecable: es un resorte
     que nadie ha podido evaluar. Se dice antes que nada. */
  if(!(R.h>0)) flags.push({level:'info',
    title:'Working stress, buckling and set not evaluated',
    rec:'The drawing gives no working point, so there is no deflection to evaluate. The score below covers geometry and coilability only \u2014 not how the spring behaves in service.'});
  /* spring index */
  if(R.C<4){ pen+=26; flags.push({level:'crit',title:'Spring index too low (C = '+f(R.C,2)+')',
    rec:'C below 4 is very hard to coil, causes high coiling stress and tool wear. Increase mean diameter or reduce wire diameter to bring C into 5–12.'}); }
  else if(R.C<5){ pen+=10; flags.push({level:'warn',title:'Spring index low (C = '+f(R.C,2)+')',
    rec:'C of 4–5 is coilable but stresses tooling. Aim for 5–12 where practical.'}); }
  else if(R.C>15){ pen+=20; flags.push({level:'crit',title:'Spring index too high (C = '+f(R.C,2)+')',
    rec:'C above 15 gives a slack, tangle-prone coil with inconsistent free length. Reduce mean diameter or increase wire diameter.'}); }
  else if(R.C>12){ pen+=8; flags.push({level:'warn',title:'Spring index high (C = '+f(R.C,2)+')',
    rec:'C of 12–15 risks tangling and free-length scatter. Tighten toward 5–12 if the envelope allows.'}); }
  else flags.push({level:'ok',title:'Spring index in ideal range (C = '+f(R.C,2)+')',rec:''});
  /* wire vs material range */
  pen+=scoreCommon(flags,R.d,mat);
  /* geometry consistency */
  if(R.ID<=0){ pen+=40; flags.push({level:'crit',title:'OD / ID conflict',
    rec:'Inside diameter computes to zero or negative. Check wire diameter and the entered diameter / mode.'}); }
  if(R.L0<=R.Ls){ pen+=40; flags.push({level:'crit',title:'Free length ≤ solid height',
    rec:'Free length must exceed solid height ('+f(toDisp(R.Ls,'len',STATE.unit),3)+' '+ul('len')+'). The spring has no working travel — revise free length or coil count.'}); }
  else if(R.h>0&&R.h<R.Ls){ pen+=22; flags.push({level:'crit',title:'Working height below solid height',
    rec:'Working height '+f(toDisp(R.h,'len',STATE.unit),3)+' '+ul('len')+' is below solid height. The spring is over-travelled — it will be forced past solid.'}); }
  /* stress / safety - working load is the primary check.
     Sin altura de trabajo no hay deflexion, y sin deflexion la tension no
     significa nada: se salta en vez de penalizar sobre un supuesto. */
  if(R.h>0&&R.SFwork<1){ pen+=36; flags.push({level:'crit',title:'Overstressed at working load (SF = '+f(R.SFwork,2)+')',
    rec:'Operating stress exceeds the allowable shear stress — the spring yields in normal use. Increase wire diameter, raise the spring index, or add active coils.'}); }
  else if(R.h>0&&R.SFwork<1.2){ pen+=18; flags.push({level:'warn',title:'Low safety factor at working load (SF = '+f(R.SFwork,2)+')',
    rec:'Operating stress is close to the allowable. Target SF ≥ 1.2 static, higher for cyclic / fatigue duty.'}); }
  else if(R.h>0&&R.SFwork<1.5){ pen+=6; flags.push({level:'info',title:'Moderate working safety factor (SF = '+f(R.SFwork,2)+')',
    rec:'Adequate for static duty. For cyclic or fatigue loading aim for SF ≥ 1.5.'}); }
  /* solid-stress check - secondary: many springs are not designed to go solid */
  if(R.SFsolid<1){ pen+=12; flags.push({level:'warn',title:'Spring takes a set if compressed solid (SF = '+f(R.SFsolid,2)+')',
    rec:'Solid stress exceeds the allowable. Acceptable only if the spring is never compressed fully solid in service; otherwise preset (cold-set) the spring or add capacity.'}); }
  /* buckling: tambien va con la deflexion de trabajo */
  if(R.h>0&&!R.absStable){
    if(R.bucklePct>=100){ pen+=24; flags.push({level:'crit',title:'Buckling expected at working deflection',
      rec:'Working deflection exceeds the critical buckling deflection. Use a guide rod or bore, reduce free length, or increase mean diameter.'}); }
    else if(R.bucklePct>=70){ pen+=12; flags.push({level:'warn',title:'Buckling risk ('+f(R.bucklePct,0)+'% of critical deflection)',
      rec:'Approaching the buckling limit. Consider a guide rod / bore or a shorter, larger-diameter spring.'}); }
  }
  if(R.slender>5.3){ flags.push({level:'info',title:'Slender spring (L0 / D = '+f(R.slender,1)+')',
    rec:'Slenderness above ~5 makes buckling sensitive to end conditions. Squared & ground ends and a guide are advisable.'}); }
  /* pitch / helix */
  if(R.helix>12){ pen+=10; flags.push({level:'warn',title:'Helix angle high ('+f(R.helix,1)+'°)',
    rec:'Helix angle above ~12° reduces coiling accuracy and the rate formula loses precision. Add coils or reduce free length.'}); }
  if(R.p<=R.d){ pen+=8; flags.push({level:'warn',title:'Pitch at or below wire diameter',
    rec:'Coils touch or overlap at free length. Increase free length or reduce coil count.'}); }
  /* coil count */
  if(R.Na<3){ pen+=10; flags.push({level:'warn',title:'Few active coils (Na = '+f(R.Na,1)+')',
    rec:'Below ~3 active coils the rate is hard to hold and end effects dominate. Add coils if the envelope allows.'}); }
  /* grinding feasibility */
  if(END_TYPES[STATE.comp.endType].ground){
    if(R.C>13){ pen+=6; flags.push({level:'warn',title:'Grinding feasibility risk',
      rec:'High index + ground ends: slender coils can deflect during grinding, hurting squareness and load tolerance.'}); }
    else flags.push({level:'info',title:'Ends are ground — secondary grinding operation required',
      rec:'Include end-grinding in routing and cost. Verify squareness and parallelism tolerances are achievable.'});
  }
  var score=clamp(Math.round(100-pen),0,100);
  return {score:score,flags:flags};
}

function scoreExtension(R){
  var flags=[],pen=0,mat=R.mat;
  if(R.C<4){ pen+=24; flags.push({level:'crit',title:'Spring index too low (C = '+f(R.C,2)+')',
    rec:'Low index is hard to coil and over-stresses tooling. Increase mean diameter or reduce wire diameter.'}); }
  else if(R.C<5){ pen+=9; flags.push({level:'warn',title:'Spring index low (C = '+f(R.C,2)+')',
    rec:'Coilable but hard on tooling. Aim for 5–12.'}); }
  else if(R.C>15){ pen+=18; flags.push({level:'crit',title:'Spring index too high (C = '+f(R.C,2)+')',
    rec:'Very high index gives an unstable, tangle-prone coil. Reduce mean diameter or increase wire diameter.'}); }
  else if(R.C>12){ pen+=7; flags.push({level:'warn',title:'Spring index high (C = '+f(R.C,2)+')',
    rec:'Tighten toward 5–12 to improve consistency.'}); }
  else flags.push({level:'ok',title:'Spring index in ideal range (C = '+f(R.C,2)+')',rec:''});
  pen+=scoreCommon(flags,R.d,mat);
  /* initial tension band */
  if(R.tauI<R.tauIbandLo){ pen+=10; flags.push({level:'warn',title:'Initial tension below preferred band',
    rec:'Coiled-in stress '+f(toDisp(R.tauI,'stress',STATE.unit),1)+' '+ul('stress')+
    ' is under the preferred range ('+f(toDisp(R.tauIbandLo,'stress',STATE.unit),1)+'–'+
    f(toDisp(R.tauIbandHi,'stress',STATE.unit),1)+' '+ul('stress')+'). Low initial tension is hard to hold consistently in production.'}); }
  else if(R.tauI>R.tauIbandHi){ pen+=14; flags.push({level:'warn',title:'Initial tension above preferred band',
    rec:'Coiled-in stress exceeds the preferred range. High initial tension is difficult to coil and may relax in service. Reduce it or accept tighter process control.'}); }
  else flags.push({level:'ok',title:'Initial tension within preferred band',rec:''});
  /* hook stresses - extension springs usually fail at the hook */
  var SFhook=Math.min(R.SFhookA,R.SFhookB);
  if(SFhook<1){ pen+=32; flags.push({level:'crit',title:'Hook overstressed (SF = '+f(SFhook,2)+')',
    rec:'Stress at the hook exceeds the allowable — hooks are the usual failure point. Increase the hook bend radius, reduce load, or use a heavier wire.'}); }
  else if(SFhook<1.5){ pen+=16; flags.push({level:'warn',title:'Low hook safety factor (SF = '+f(SFhook,2)+')',
    rec:'Hooks carry a stress concentration. Target SF ≥ 1.5 static and well above that for cyclic duty. Increase the bend radius.'}); }
  if(R.sigHookA>R.tauBody*1.25 || R.tauHookB>R.tauBody*1.25){
    flags.push({level:'info',title:'Hook is the limiting feature',
    rec:'Hook stress exceeds body stress — fatigue cracks will start at the hook. Generous bend radii and stress-relief help.'}); }
  if(R.SFbody<1.2 && R.SFbody>=0){ pen+=14; flags.push({level:'warn',title:'Low body safety factor (SF = '+f(R.SFbody,2)+')',
    rec:'Body operating stress is high. Target SF ≥ 1.2 static.'}); }
  /* hook-forming complexity */
  var hookPen={machine_full:0,machine_half:0,crossover:5,side:4,extended:8,special:12};
  var hp=hookPen[R.hookType]||0;
  if(hp>0){ pen+=hp; flags.push({level:'warn',title:'Hook type adds forming complexity',
    rec:'The selected hook style needs extra forming / secondary operations. Standard machine loops are the most economical and repeatable.'}); }
  /* set removal not possible */
  flags.push({level:'info',title:'Close-wound body — set cannot be removed',
    rec:'Extension springs are coiled solid, so cold-set / preset is not available. Keep body stress conservative.'});
  var score=clamp(Math.round(100-pen),0,100);
  return {score:score,flags:flags};
}

function scoreTorsion(R){
  var flags=[],pen=0,mat=R.mat;
  if(R.C<4){ pen+=24; flags.push({level:'crit',title:'Spring index too low (C = '+f(R.C,2)+')',
    rec:'Low index over-stresses coiling tooling and raises bending stress. Increase mean diameter or reduce wire diameter.'}); }
  else if(R.C<5){ pen+=9; flags.push({level:'warn',title:'Spring index low (C = '+f(R.C,2)+')',
    rec:'Coilable but hard on tooling. Aim for 5–12.'}); }
  else if(R.C>15){ pen+=18; flags.push({level:'crit',title:'Spring index too high (C = '+f(R.C,2)+')',
    rec:'High index gives a loose, unstable coil. Reduce mean diameter or increase wire diameter.'}); }
  else if(R.C>12){ pen+=7; flags.push({level:'warn',title:'Spring index high (C = '+f(R.C,2)+')',
    rec:'Tighten toward 5–12 for consistency.'}); }
  else flags.push({level:'ok',title:'Spring index in ideal range (C = '+f(R.C,2)+')',rec:''});
  pen+=scoreCommon(flags,R.d,mat);
  /* direction of wind / load */
  if(R.loadDir==='opening'){ pen+=22; flags.push({level:'crit',title:'Load unwinds the spring',
    rec:'Torsion springs must be loaded in the direction that winds them tighter (closing). Loading in the opening direction over-stresses the wire and loosens the coil over the mandrel. Reverse the wind direction or the load direction.'}); }
  else flags.push({level:'ok',title:'Load winds the spring closed (correct direction)',rec:''});
  /* stress / safety */
  if(R.SF<1){ pen+=34; flags.push({level:'crit',title:'Bending stress exceeds allowable (SF = '+f(R.SF,2)+')',
    rec:'The wire yields at the working angle. Increase wire diameter, raise index, or reduce the angle of rotation.'}); }
  else if(R.SF<1.2){ pen+=15; flags.push({level:'warn',title:'Low safety factor (SF = '+f(R.SF,2)+')',
    rec:'Operating bending stress is close to the allowable. Target SF ≥ 1.2 static, higher for cyclic duty.'}); }
  if(R.angle>R.angSafe){ pen+=20; flags.push({level:'crit',title:'Angle of rotation exceeds safe deflection',
    rec:'Working angle '+f(R.angle,0)+'° is beyond the safe '+f(R.angSafe,0)+'°. Reduce the angle or increase capacity.'}); }
  /* mandrel clearance */
  if(R.idLoad<=0){ pen+=20; flags.push({level:'crit',title:'Coil closes onto itself under load',
    rec:'Inside diameter under load computes to zero. Coil count or angle is excessive.'}); }
  else if(R.mandrelClear<0){ pen+=24; flags.push({level:'crit',title:'Mandrel interference under load',
    rec:'The coil ID shrinks to '+f(toDisp(R.idLoad,'len',STATE.unit),3)+' '+ul('len')+
    ' under load — smaller than the '+f(toDisp(R.mandrel,'len',STATE.unit),3)+' '+ul('len')+
    ' mandrel. The spring binds. Use a mandrel ≤ '+f(toDisp(R.mandrelRec,'len',STATE.unit),3)+' '+ul('len')+'.'}); }
  else if(R.mandrel>R.mandrelRec){ pen+=10; flags.push({level:'warn',title:'Tight mandrel clearance',
    rec:'Mandrel is above the recommended 90% of loaded ID. Drop to ≤ '+
    f(toDisp(R.mandrelRec,'len',STATE.unit),3)+' '+ul('len')+' to avoid binding and friction.'}); }
  else flags.push({level:'ok',title:'Mandrel clearance adequate',rec:''});
  /* leg manufacturability */
  if(R.legLen>2.5*R.D){ pen+=6; flags.push({level:'warn',title:'Long legs',
    rec:'Legs longer than ~2.5× mean diameter deflect under load and may need support or a heavier section. Confirm leg geometry with the customer.'}); }
  if(R.Nb<3){ pen+=8; flags.push({level:'warn',title:'Few body coils (Nb = '+f(R.Nb,1)+')',
    rec:'Below ~3 body coils the rate is dominated by the legs and is hard to hold. Add coils if possible.'}); }
  flags.push({level:'info',title:'Leg forming is a secondary operation',
    rec:'Account for leg bending / end forming in routing and cost. Sharp leg bends concentrate stress — use generous radii.'});
  var score=clamp(Math.round(100-pen),0,100);
  return {score:score,flags:flags};
}

/* =====================================================================
   9. MACHINE SELECTION
   ===================================================================== */
function selectMachine(type,d,OD,matId){
  /* Los seis pasos de la hoja de Rodea, en su orden. Antes esto puntuaba con un
     criterio propio -- posicion del alambre en el rango, clase de setup -- y no
     miraba siquiera si la maquina hace ese tipo de resorte. De ahi salia que la
     Nucoil CSF-200, que solo hace tension, torsion y wire form, se recomendara
     para resortes de compresion. */
  var orden = ORDEN_TALLER[type==='extension'?'extension':type] || [];
  var puesto = function(nombre){
    var i = orden.indexOf(nombre);
    return i<0 ? 99 : i;              /* fuera de la lista: al final */
  };
  var cand=[], near=[];
  for(var i=0;i<MACHINES.length;i++){
    var m=MACHINES[i];
    if(!m[type]) continue;                       /* 1. tipo permitido */
    var notas=[], falla=[];
    /* 2. diametro de alambre: esto SI bloquea */
    if(d<m.wireMin) falla.push('wire \u00f8 below min ('+f(toDisp(m.wireMin,'len',STATE.unit),3)+' '+ul('len')+')');
    if(d>m.wireMax) falla.push('wire \u00f8 above max ('+f(toDisp(m.wireMax,'len',STATE.unit),3)+' '+ul('len')+')');
    /* 3. el OD maximo AVISA, no bloquea -- y un OD sin declarar no restringe.
       Once de las 18 no lo tienen; compararlo contra null las descartaba todas. */
    if(m.odMax && OD>m.odMax)
      notas.push('OD above the machine maximum ('+f(toDisp(m.odMax,'len',STATE.unit),2)+' '+ul('len')+')');
    else if(m.odMax && OD>m.odMax*0.85) notas.push('OD near machine maximum');
    if(m.odMin && OD<m.odMin)
      notas.push('OD below the machine minimum ('+f(toDisp(m.odMin,'len',STATE.unit),2)+' '+ul('len')+')');
    /* 4. tope por material: hoy solo la MC 50 con temple en aceite.
       Sale de `capMaterial` y `capWireMaxMm`, no de leer la frase de Rodea con
       una expresion regular: la misma regla la aplica `bobinadora()` en la ruta
       de la cotizacion, y una frase leida en dos sitios se lee distinto. */
    var _r = _reglas();
    var _tope = _r ? _r.topeDeMaterial(m, getMat(matId), d) : null;
    if(_tope) falla.push(_tope);
    if(d<m.wireMin*1.15||d>m.wireMax*0.85) notas.push('wire \u00f8 near a machine limit');
    if(m.compSecondary && type==='compression')
      notas.push('compression on this machine needs a secondary operation');
    if(falla.length){ near.push({m:m,why:falla}); continue; }
    cand.push({m:m,score:100-puesto(m.name),notes:notas,pos:puesto(m.name)});
  }
  /* 5. gana la preferida del taller entre las que pasan */
  cand.sort(function(a,b){return a.pos-b.pos;});
  /* 6. si ninguna pasa, `feasible:false` y `near` dice por que. No se adivina. */
  return {feasible:cand.length>0,best:cand[0]||null,alt:cand[1]||null,all:cand,near:near};
}


const RESORTES = { configurar, desdeCatalogo, materialDelTexto, codigoDeMaterial, CONV, ULBL, END_TYPES, toDisp, toSI, ul,
                   getMat, num, f, clamp, esc, tensile, wahl, bergs,
                   kBendInner, resolveDia,
                   calcCompression, calcExtension, calcTorsion,
                   scoreCompression, scoreExtension, scoreTorsion,
                   selectMachine,
                   /* Con getter, no copiados: `configurar` los reemplaza, y una
                      copia se habria quedado apuntando al resorte anterior. */
                   get STATE() { return STATE; }, set STATE(v) { STATE = v; },
                   get MATERIALS() { return MATERIALS; },
                   get MACHINES() { return MACHINES; },
                   get ORDEN_TALLER() { return ORDEN_TALLER; } };

/* Para Node. En el navegador `module` no existe y esto no hace nada. */
if (typeof module !== 'undefined' && module.exports) { module.exports = RESORTES; }
