"""Puente entre el JSON de ingenieria (v4, mm/N) y lo que consume la calculadora.

La calculadora ISC espera una lista plana de `fields` con las claves
wireDia / material / od / id / meanDia / freeLength / bodyLength / coils /
developedLength, mas `springType` y una lista de `feasibility`.

Aqui se traduce el spec rico a esa forma SIN perder nada: el spec completo
viaja aparte en la clave `spec`. Todo lo que se deriva por calculo se marca
con `derivado: true` y una nota, para que nunca se confunda con una lectura.
"""

import re

# ---------------------------------------------------------------- tipos
TIPO_A_SPRINGTYPE = {
    "compresion": "compression",
    "tension": "extension",
    "torsion": "torsion",
    "wireform": "wireform",
}

# ---------------------------------------------------------------- material
# Orden = prioridad. El primero que casa, gana (lo especifico antes que lo generico).
MATERIAL_REGLAS = [
    ("SS177", [r"17[\s/\-]?7", r"\b631\b", r"17-7\s*PH"]),
    ("HAST",  [r"inconel", r"hastelloy", r"monel", r"nimonic", r"\bx[\s\-]?750\b",
               r"\b718\b", r"\ba[\s\-]?286\b", r"nickel\s+alloy", r"niquel"]),
    ("PHOSB", [r"phosphor\s*bronze", r"bronce\s*fosfor", r"b\s*159", r"c5[12]000",
               r"cusn"]),
    ("CSI",   [r"chrome\s*silicon", r"cromo\s*silicio", r"a\s*401", r"swosc",
               r"vdsicr", r"54sicr6", r"1\.7102", r"en\s*10270[\s\-]*2\s*sc"]),
    ("SS",    [r"\b30[24]\b", r"\b316\b", r"\b321\b", r"a\s*313", r"en\s*10270[\s\-]*3",
               r"1\.4310", r"1\.4401", r"x10crni", r"stainless", r"inoxidable",
               r"\bsus\s*30", r"g\s*4314"]),
    ("OT",    [r"oil\s*tempered", r"templado\s+en\s+aceite", r"a\s*229", r"\bswo\b",
               r"swosm", r"en\s*10270[\s\-]*2", r"\bvdc\b", r"\bfdc\b", r"g\s*3560"]),
    ("MW",    [r"music\s*wire", r"cuerda\s+de\s+piano", r"a\s*228", r"\bswp\b",
               r"en\s*10270[\s\-]*1", r"g\s*3522", r"patented.*cold.*drawn",
               r"\bdh\b", r"\bsh\b"]),
    ("HD",    [r"hard\s*drawn", r"estirado\s+en\s+duro", r"a\s*227", r"\bswc\b",
               r"g\s*3521", r"en\s*10270[\s\-]*1\s*(sl|sm|dm)"]),
]


# "SPRING WIRE" a secas no es un material: es la familia entera. Pero en ISC se
# cotiza como music wire, asi que se resuelve a MW. Va DESPUES de las reglas de
# arriba y no dentro de ellas: "stainless spring wire", "oil tempered spring
# wire" o "hard drawn spring wire" tienen que seguir cayendo en su material, y
# ahi la palabra concreta manda.
#
# Lo destapo el 004-222, que dice "SPRING WIRE" y nada mas: sin codigo no habia
# modulo G, y sin G el lector no podia ni calcular las espiras ni comprobarlas
# contra la rigidez del plano.
MATERIAL_GENERICO = (r"\bspring\s*(steel\s*)?wire\b",
                     r"\balambre\s+de\s+muelle\b")


def codigo_material(texto):
    """Texto libre del plano -> uno de los 8 codigos que entiende la calculadora."""
    if not texto:
        return None
    t = str(texto).lower()
    for codigo, patrones in MATERIAL_REGLAS:
        for p in patrones:
            if re.search(p, t):
                return codigo
    for p in MATERIAL_GENERICO:
        if re.search(p, t):
            return "MW"
    return None


# El plano lo escribe de mil maneras ("derecho", "RH", "right hand", "izq").
# El calculador solo entiende right / left.
SENTIDO = [
    ("right", ("derech", "right", "rh", "dextro", "horario", "cw")),
    ("left", ("izquierd", "left", "lh", "levo", "antihorario", "ccw")),
]


# Texto del plano -> id de END_TYPES del Spring Calculator. El orden importa:
# "closed and ground" tiene que casar con el par cerrado+rectificado antes que
# con el cerrado a secas.
_EXTREMO_CERRADO = ("closed", "squared", "cerrad", "cuadrad")
_EXTREMO_ABIERTO = ("plain", "open", "abiert", "libre")
_RECTIFICADO = ("ground", "grinding", "rectific", "esmerilad", "amolad")


def tipo_extremo(texto, rectificado=None):
    """-> 'closed_ground' | 'closed' | 'plain_ground' | 'plain' | None.

    `rectificado` es el booleano que el lector saca por separado
    (`extremos.rectificado`); si viene, manda sobre lo que diga el texto, porque
    algunos planos lo ponen en una nota aparte y no en la designacion.
    """
    t = str(texto or "").lower()
    if not t and rectificado is None:
        return None
    rect = rectificado if rectificado is not None else any(x in t for x in _RECTIFICADO)
    if any(x in t for x in _EXTREMO_CERRADO):
        return "closed_ground" if rect else "closed"
    if any(x in t for x in _EXTREMO_ABIERTO):
        return "plain_ground" if rect else "plain"
    return None


# Texto del plano -> id de FINISH_OPTS. En el Spring Calculator el acabado es
# solo una etiqueta de la ficha, pero en la COTIZACION es una operacion con
# coste, asi que interesa que llegue resuelto y no como texto libre.
_ACABADOS = (
    ("passiv", "passiv"), ("pasivad", "passiv"),
    ("black oxide", "boxide"), ("oxido negro", "boxide"),
    ("powder", "powder"), ("e-coat", "ecoat"), ("ecoat", "ecoat"),
    ("nickel", "nickel"), ("niquel", "nickel"),
    ("zinc", "zinc"), ("galvani", "zinc"), ("b-633", "zinc"), ("b633", "zinc"),
)


def acabado(texto):
    """-> id de FINISH_OPTS, o None si el plano no lo dice.

    'FINISH: NONE' es un dato, no un hueco: el cliente decidio que no lleva.
    """
    t = str(texto or "").lower().strip()
    if not t:
        return None
    if "none" in t or t in ("sin acabado", "ninguno", "-"):
        return "none"
    for pat, cod in _ACABADOS:
        if pat in t:
            return cod
    return None


def sentido_enrollado(texto):
    """Texto libre del plano -> "right" | "left" | None."""
    t = str(texto or "").strip().lower()
    if not t:
        return None
    for codigo, pistas in SENTIDO:
        for p in pistas:
            if p in t:
                return codigo
    return None


# ---------------------------------------------------------------- acceso
def _get(obj, ruta):
    """_get(spec, 'dimensiones_mm.diametro_alambre') / 'cargas[0].fuerza_N'."""
    cur = obj
    for parte in ruta.split("."):
        m = re.match(r"^([^\[]+)((\[\d+\])*)$", parte)
        if not m:
            return None
        nombre, indices = m.group(1), m.group(2)
        if not isinstance(cur, dict):
            return None
        cur = cur.get(nombre)
        for idx in re.findall(r"\[(\d+)\]", indices or ""):
            if not isinstance(cur, list) or int(idx) >= len(cur):
                return None
            cur = cur[int(idx)]
    return cur


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _nominal(cota):
    """Valor representativo de una cota: nominal, o el limite, o el centro."""
    if not isinstance(cota, dict):
        return None, None
    n = _num(cota.get("nominal"))
    if n is not None:
        return n, "nominal"
    vmax, vmin = _num(cota.get("valor_maximo")), _num(cota.get("valor_minimo"))
    if vmax is not None and vmin is not None:
        return (vmax + vmin) / 2.0, "midpoint of %s/%s" % (vmin, vmax)
    if vmax is not None:
        return vmax, "maximum limit only"
    if vmin is not None:
        return vmin, "minimum limit only"
    return None, None


_EN_PULGADAS = re.compile(r"\(\s*in\s*\)|\bin\b|\binch(es)?\b|\"", re.I)
_EN_MM = re.compile(r"\bmm\b", re.I)


def unidad_del_plano(texto):
    """`in`, `mm` o None, segun como este acotado el plano.

    Se decide por lo que el modelo copio del plano, no por el esquema: el
    esquema siempre es mm porque las formulas lo exigen, y eso no dice nada de
    como esta dibujada la pieza.

    Si el texto menciona las dos -- pasa cuando el plano trae la conversion
    escrita -- gana la que aparece primero, que es la que acota.
    """
    t = str(texto or "")
    if not t.strip():
        return None
    i = _EN_PULGADAS.search(t)
    m = _EN_MM.search(t)
    if i and m:
        return "in" if i.start() < m.start() else "mm"
    if i:
        return "in"
    return "mm" if m else None


def _cifras(v):
    """Un numero sin ceros de relleno: 1.53, no 1.5300000000000002."""
    return "%g" % round(v, 4)


def fmt_cota(cota, unidad="mm"):
    """Cota -> texto legible para una linea de feasibility.

    PRIMERO LA UNIDAD DEL PLANO. Todo se guarda en milimetros porque las
    formulas del resorte lo exigen -- `Sut = A / d^m` con A en MPa·mm^m no
    admite pulgadas --, pero la mitad de los planos estan acotados en pulgadas.

    Quien revisa no esta depurando una formula: esta comprobando que lo leido
    coincide con el plano que tiene delante. Ver `38.862 mm` frente a un plano
    que dice `1.53` le obliga a convertir de cabeza, que es exactamente el
    trabajo que la checklist existe para ahorrarle. Asi que la linea empieza
    por como esta dibujado, y los milimetros van detras entre parentesis.

    Y se conserva lo que el plano DICE, porque a veces no es un numero:

        derived: (OD - ID)/2 = (1.94 - 1.53)/2 = 0.205 in

    Ahi lo importante no es el valor, es que ese diametro NO estaba acotado y
    se dedujo. Sin esa linea, una cota medida y una calculada se ven igual.
    """
    if not isinstance(cota, dict):
        return None
    n = _num(cota.get("nominal"))
    tm, tn = _num(cota.get("tolerancia_mas")), _num(cota.get("tolerancia_menos"))
    vmax, vmin = _num(cota.get("valor_maximo")), _num(cota.get("valor_minimo"))
    original = str(cota.get("texto_original") or "").strip()

    def linea(f, u):
        """La cota escrita en la unidad `u`, aplicando `f` a cada valor."""
        if n is not None and tm is not None and tn is not None:
            if abs(tm - tn) < 1e-9:
                return "%s +/-%s %s" % (f(n), f(tm), u)
            return "%s +%s/-%s %s" % (f(n), f(tm), f(tn), u)
        if vmax is not None and vmin is None:
            return "max %s %s" % (f(vmax), u)
        if vmin is not None and vmax is None:
            return "min %s %s" % (f(vmin), u)
        if vmax is not None and vmin is not None:
            return "%s to %s %s" % (f(vmin), f(vmax), u)
        if n is not None:
            return "%s %s" % (f(n), u)
        return None

    en_mm = linea(lambda v: "%g" % v, unidad)
    if en_mm is None:
        return None

    partes = [en_mm]
    if unidad == "mm" and unidad_del_plano(original) == "in":
        # El plano esta en pulgadas: se ensena asi, y el milimetro detras.
        en_in = linea(lambda v: _cifras(v / 25.4), "in")
        if en_in:
            partes = ["%s  (%s)" % (en_in, en_mm)]
    if original:
        partes.append("on the drawing: %s" % original)
    return "  ·  ".join(partes)


def _es_cerrada(cota):
    """True si la tolerancia es estrecha (<=1% del nominal o <=0.05 mm en total)."""
    if not isinstance(cota, dict):
        return False
    n = _num(cota.get("nominal"))
    tm, tn = _num(cota.get("tolerancia_mas")) or 0.0, _num(cota.get("tolerancia_menos")) or 0.0
    total = tm + tn
    if total <= 0:
        return False
    if total <= 0.05:
        return True
    return bool(n) and (total / abs(n)) <= 0.01


def _carga_gobernante(spec, clave):
    """El punto de carga mas exigente: el de mayor `clave` (fuerza o angulo).

    El calculador tiene UNA altura de trabajo y UN angulo, asi que hay que
    elegir. Se coge el mas grande porque es el que decide la tension maxima y,
    con ella, si la pieza es fabricable.
    """
    mejor, valor = None, None
    for c in (spec.get("cargas") or []):
        if not isinstance(c, dict):
            continue
        v = _num(c.get(clave))
        if v is None:
            continue
        if valor is None or v > valor:
            mejor, valor = c, v
    return mejor


# ---------------------------------------------------------------- campos
# key de la calculadora -> (ruta en el spec, etiqueta)
CAMPOS_POR_TIPO = {
    "compresion": [
        ("wireDia",    "dimensiones_mm.diametro_alambre",   "Wire diameter"),
        ("od",         "dimensiones_mm.diametro_exterior",  "Outside diameter"),
        ("id",         "dimensiones_mm.diametro_interior",  "Inside diameter"),
        ("meanDia",    "dimensiones_mm.diametro_medio",     "Mean diameter"),
        ("freeLength", "dimensiones_mm.longitud_libre_L0",  "Free length L0"),
    ],
    "tension": [
        ("wireDia",    "dimensiones_mm.diametro_alambre",   "Wire diameter"),
        ("od",         "dimensiones_mm.diametro_exterior",  "Outside diameter"),
        ("id",         "dimensiones_mm.diametro_interior",  "Inside diameter"),
        ("meanDia",    "dimensiones_mm.diametro_medio",     "Mean diameter"),
        ("freeLength", "dimensiones_mm.longitud_libre_L0",  "Free length L0 (over hooks)"),
        ("bodyLength", "dimensiones_mm.longitud_cuerpo",    "Body length"),
    ],
    "torsion": [
        ("wireDia",    "dimensiones_mm.diametro_alambre",   "Wire diameter"),
        ("meanDia",    "dimensiones_mm.diametro_medio",     "Mean diameter"),
        ("od",         "dimensiones_mm.diametro_exterior",  "Outside diameter"),
        ("id",         "dimensiones_mm.diametro_interior",  "Inside diameter"),
    ],
    "wireform": [
        ("wireDia",         "dimensiones_mm.diametro_alambre",      "Wire diameter"),
        ("developedLength", "dimensiones_mm.longitud_desarrollada",  "Developed length"),
    ],
}

RUTA_ESPIRAS = {
    "compresion": ["espiras.numero_espiras_totales", "espiras.numero_espiras_activas"],
    "tension":    ["espiras.numero_espiras_totales", "espiras.numero_espiras_activas"],
    "torsion":    ["espiras.numero_espiras_posicion_inicial", "espiras.numero_espiras_totales"],
    "wireform":   ["espiras.numero_espiras_totales"],
}


def campos(spec, tipo):
    """-> lista de fields para la calculadora, en mm (ella convierte a pulgadas)."""
    out = []
    vistos = set()
    est = estimados(spec)

    def add(key, label, valor, unidad="mm", ruta=None, conf=0.9,
            derivado=False, nota=None):
        if key in vistos or valor is None:
            return
        vistos.add(key)
        # Un valor estimado del dibujo no puede llegar como si fuera una cota:
        # baja la confianza y la nota dice como se obtuvo.
        e = est.get(ruta) if ruta else None
        if e:
            conf = min(conf, CONFIANZA_ESTIMADO.get(e["confianza"], 0.6))
            nota = _nota_estimado(e) + ((" " + nota) if nota else "")
        out.append({
            "key": key, "label": label,
            "value": ("%g" % valor) if isinstance(valor, float) else str(valor),
            "unit": unidad, "confidence": round(float(conf), 2),
            "source": ruta, "derivado": bool(derivado),
            "estimado": bool(e), "note": nota,
        })

    for key, ruta, label in CAMPOS_POR_TIPO.get(tipo, []):
        cota = _get(spec, ruta)
        valor, origen = _nominal(cota)
        if valor is None:
            continue
        conf = 0.95 if origen == "nominal" else 0.7
        nota = None if origen == "nominal" else "Value taken from: %s" % origen
        if isinstance(cota, dict) and cota.get("es_referencia"):
            conf, nota = 0.6, "Reference dimension on the drawing (not toleranced)."
        add(key, label, valor, "mm", ruta, conf, False, nota)

    # --- derivaciones geometricas estandar, siempre marcadas -------------
    d = _nominal(_get(spec, "dimensiones_mm.diametro_alambre"))[0]
    od = _nominal(_get(spec, "dimensiones_mm.diametro_exterior"))[0]
    di = _nominal(_get(spec, "dimensiones_mm.diametro_interior"))[0]
    dm = _nominal(_get(spec, "dimensiones_mm.diametro_medio"))[0]
    if d is not None:
        if od is None and dm is not None:
            add("od", "Outside diameter", dm + d, "mm", None, 0.75, True,
                "Derived: OD = Dm + d (%g + %g)." % (dm, d))
        elif od is None and di is not None:
            add("od", "Outside diameter", di + 2 * d, "mm", None, 0.75, True,
                "Derived: OD = ID + 2d (%g + 2x%g)." % (di, d))
        if dm is None and od is not None:
            add("meanDia", "Mean diameter", od - d, "mm", None, 0.75, True,
                "Derived: Dm = OD - d (%g - %g)." % (od, d))
        if di is None and od is not None:
            add("id", "Inside diameter", od - 2 * d, "mm", None, 0.75, True,
                "Derived: ID = OD - 2d (%g - 2x%g)." % (od, d))

    # --- espiras ---------------------------------------------------------
    for ruta in RUTA_ESPIRAS.get(tipo, []):
        n = _num(_get(spec, ruta))
        if n is not None:
            nota = None
            conf = 0.9
            if ruta.endswith("activas"):
                nota, conf = "The drawing states ACTIVE coils only, not total coils.", 0.7
            elif ruta.endswith("posicion_inicial"):
                nota = "Coils at the initial position (torsion)."
            add("coils", "Total coils", n, "", ruta, conf, False, nota)
            break

    # --- datos de calculo (los consume el Spring Calculator) -------------
    # No los mira la calculadora de precios; viajan en el mismo `fields`.
    if tipo == "torsion":
        for k in ("longitud_brazo_1_mm", "longitud_brazo_2_mm"):
            L = _nominal(_get(spec, "brazos." + k))[0]
            if L is not None:
                add("legLength", "Leg length", L, "mm", "brazos." + k, 0.9, False,
                    "Both legs assumed equal by the calculator.")
                break
        c = _carga_gobernante(spec, "angulo_grados")
        if c:
            ang = _num(c.get("angulo_grados"))
            par = _num(c.get("torque_N_mm"))
            et = c.get("etiqueta") or "working"
            if ang is not None:
                add("angle", "Angle of rotation", ang, "deg", None, 0.9, False,
                    "Most demanding load point on the drawing (%s)." % _linea(et, 60))
            if par is not None:
                add("torque", "Torque stated on the drawing", par, "N.mm", None,
                    0.9, False,
                    "The drawing REQUIRES this torque at %s deg - compare it "
                    "against the calculated value." % (ang if ang is not None else "?"))
        sentido = sentido_enrollado((spec.get("espiras") or {}).get("sentido_enrollado"))
        if sentido:
            add("windDir", "Direction of wind", sentido, "", "espiras.sentido_enrollado",
                0.9)
    elif tipo == "compresion":
        c = _carga_gobernante(spec, "fuerza_N")
        if c:
            L = _num(c.get("longitud_mm"))
            F = _num(c.get("fuerza_N"))
            et = c.get("etiqueta") or "working"
            if L is not None:
                add("workingHeight", "Working height L1", L, "mm", None, 0.9, False,
                    "Most demanding load point on the drawing (%s)." % _linea(et, 60))
            if F is not None:
                add("loadAtHeight", "Load stated on the drawing", F, "N", None,
                    0.9, False,
                    "The drawing REQUIRES this load at %s mm - compare it against "
                    "the calculated value." % (L if L is not None else "?"))
    elif tipo == "tension":
        Fi = _num(spec.get("pretension_N"))
        if Fi is not None:
            add("initialTension", "Initial tension", Fi, "N", "pretension_N")

    # --- material --------------------------------------------------------
    mat = spec.get("material") or {}
    texto = " ".join(str(x) for x in [mat.get("designacion"), mat.get("norma"),
                                      mat.get("tipo_o_grado")] if x).strip()
    if texto:
        codigo = codigo_material(texto)
        f = {
            "key": "material", "label": "Material",
            "value": mat.get("designacion") or texto,
            "unit": "", "confidence": 0.9 if codigo else 0.5,
            "source": "material.designacion", "derivado": False,
            "code": codigo,
            "note": None if codigo else
                    "Could not be mapped to an ISC code - set it by hand.",
        }
        out.append(f)

    # --- lo que hasta ahora se elegia a mano en el Spring Calculator ---------
    ext = spec.get("extremos") or {}
    te = tipo_extremo(ext.get("tipo"), ext.get("rectificado"))
    if te:
        add("endType", "End type", te, "", "extremos.tipo", conf=0.85,
            nota="Mapped from the drawing: %s. It sets the dead coils - and with "
                 "them the rate - and the buckling end-fixity factor."
                 % _linea(ext.get("tipo") or
                          ("ground ends" if ext.get("rectificado") else "?"), 60))
    ac = acabado((spec.get("material") or {}).get("acabado_superficial"))
    if ac:
        add("finish", "Finish", ac, "", "material.acabado_superficial", conf=0.85,
            nota="Mapped from the drawing: %s"
                 % _linea((spec.get("material") or {}).get("acabado_superficial"), 60))
    return out


# Nombre de cada cota tal y como se ensena en la calculadora. Sin esto, una
# linea de feasibility salia como "Tight tolerance: diametro alambre 1.1 mm":
# medio ingles y medio castellano en el mismo renglon.
NOMBRE_COTA = {
    "diametro_alambre": "wire diameter",
    "diametro_exterior": "outside diameter",
    "diametro_interior": "inside diameter",
    "diametro_medio": "mean diameter",
    "diametro_stud_montaje": "mounting stud diameter",
    "longitud_libre_L0": "free length L0",
    "longitud_libre_unsprung_L0max": "free length before set L0max",
    "longitud_comprimida_Ls": "solid length Ls",
    "longitud_minima_L3": "minimum length L3",
    "longitud_cuerpo": "body length",
    "longitud_entre_ganchos_LBH": "length inside hooks LBH",
    "longitud_desarrollada": "developed length",
    "longitud_total": "overall length",
    "altura_total": "overall height",
    "ancho_total": "overall width",
    "altura_paquete_espiras": "coil stack height",
    "ancho_material": "material width",
    "espesor_material": "material thickness",
    "paso": "pitch",
}


def nombre_cota(clave):
    return NOMBRE_COTA.get(clave, str(clave).replace("_", " "))


# Los avisos citan rutas del spec ("material.tratamiento_termico"). Para quien
# cotiza eso no significa nada, asi que se ensena el nombre y, entre parentesis,
# la ruta: el nombre sirve para decidir, la ruta para diagnosticar.
NOMBRE_RUTA = {
    "material.designacion": "material",
    "material.norma": "material standard",
    "material.tipo_o_grado": "material grade",
    "material.tratamiento_termico": "heat treatment",
    "material.acabado_superficial": "finish / coating",
    "espiras.numero_espiras_totales": "total coils",
    "espiras.numero_espiras_activas": "active coils",
    "espiras.numero_espiras_posicion_inicial": "coils at initial position",
    "espiras.numero_espiras_muertas_totales": "dead coils, total",
    "espiras.numero_espiras_muertas_por_extremo": "dead coils per end",
    "extremos.rebabeo": "deburring",
    "ganchos.tipo": "hook type",
    "brazos.configuracion": "leg configuration",
    "brazos.longitud_brazo_1_mm": "leg 1 length",
    "brazos.longitud_brazo_2_mm": "leg 2 length",
    "cargas": "load points",
    "carrera_trabajo_mm": "working stroke",
    "identificacion.fecha_revision": "revision date",

    "espiras.sentido_enrollado": "coiling direction",
    "espiras.mano_resorte": "spring hand",
    "extremos.tipo": "end type",
    "extremos.rectificado": "ground ends",
    "identificacion.numero_parte": "part number",
    "identificacion.numero_plano": "drawing number",
    "identificacion.revision": "revision",
    "identificacion.cliente": "customer",
    "identificacion.nombre_parte": "part description",
    "pretension_N": "initial tension",
    "rigidez_lineal_N_por_mm": "spring rate",
    "rigidez_angular_N_mm_por_grado": "angular rate",
    "esfuerzo_trabajo_MPa": "working stress",
}

# El schema fija estos tres valores; la calculadora es en ingles.
CONFIANZA = {"alta": "high", "media": "medium", "baja": "low"}
SEVERIDAD = {"alta": "high", "media": "medium", "info": "info"}


# Las claves de un punto de carga. Van indexadas -- "cargas[0].fuerza_N" -- asi
# que no pueden vivir en NOMBRE_RUTA, que es una tabla de rutas fijas.
NOMBRE_CARGA = {
    "fuerza_N": "force",
    "longitud_mm": "length",
    "deflexion_mm": "deflection",
    "par_N_mm": "torque",
    "angulo_grados": "angle",
    "tolerancia_pct": "tolerance",
}

_CARGA_RE = re.compile(r"^cargas\[(\d+)\]\.(.+)$")


def nombre_ruta(ruta):
    """"material.tratamiento_termico" -> "heat treatment".

    Esto lo lee quien va a cotizar, en un panel en ingles. La ruta interna no
    le dice nada: esta en español, lleva el sufijo de unidad y delata la
    estructura del JSON. Se traduce y se calla.
    """
    r = str(ruta or "").strip()
    if r in NOMBRE_RUTA:
        return NOMBRE_RUTA[r]
    if r.startswith("dimensiones_mm."):
        clave = r.split(".", 1)[1]
        if clave in NOMBRE_COTA:
            return NOMBRE_COTA[clave]
    # Los puntos de carga van indexados; se cuenta desde 1, como en el plano.
    m = _CARGA_RE.match(r)
    if m:
        clave = m.group(2)
        return "%s at load point %d" % (
            NOMBRE_CARGA.get(clave, _legible(clave)), int(m.group(1)) + 1)
    return _legible(r.split(".")[-1])


def _legible(clave):
    """Ultimo recurso: una ruta sin traduccion, sin que parezca codigo.

    Quita el sufijo de unidad ("_mm", "_N", "_pct") y los guiones bajos. No
    traduce del español -- para eso estan las tablas -- pero deja algo que se
    lee, en vez de un identificador.
    """
    t = re.sub(r"_(mm|N|N_mm|MPa|pct|grados|deg|in|lbf)$", "", str(clave or ""))
    return t.replace("_", " ").strip() or "field"


# ---------------------------------------------------------------- feasibility
def _linea(texto, limite=140):
    t = " ".join(str(texto).split())
    return t if len(t) <= limite else t[:limite - 3] + "..."


def feasibilidad(spec, tipo):
    """Items de revision derivados del spec de forma DETERMINISTA (sin IA)."""
    items = []
    vistos = set()

    def add(label, severidad="media", fuente=None):
        if not label:
            return
        lab = _linea(label)
        if lab.lower() in vistos:
            return
        vistos.add(lab.lower())
        items.append({"label": lab, "severidad": severidad,
                      "severity": SEVERIDAD.get(severidad, severidad),
                      "source": fuente})

    dims = spec.get("dimensiones_mm") or {}

    # 1. cotas con limite o tolerancia cerrada
    for nombre, cota in dims.items():
        if not isinstance(cota, dict):
            continue
        ruta = "dimensiones_mm." + nombre
        etiqueta = nombre_cota(nombre)
        vmax, vmin = _num(cota.get("valor_maximo")), _num(cota.get("valor_minimo"))
        if vmax is not None or vmin is not None:
            add("Limit dimension: %s %s" % (etiqueta, fmt_cota(cota)), "alta", ruta)
        elif _es_cerrada(cota):
            add("Tight tolerance: %s %s" % (etiqueta, fmt_cota(cota)), "alta", ruta)
        elif _num(cota.get("tolerancia_mas")) is not None:
            add("Tolerance: %s %s" % (etiqueta, fmt_cota(cota)), "media", ruta)

    # 2. cargas: la especificacion funcional
    for i, c in enumerate(spec.get("cargas") or []):
        if not isinstance(c, dict):
            continue
        ruta = "cargas[%d]" % i
        et = c.get("etiqueta") or ("Load %d" % (i + 1))
        if tipo == "torsion":
            t = _num(c.get("torque_N_mm"))
            ang = _num(c.get("angulo_grados"))
            tmin, tmax = _num(c.get("torque_min_N_mm")), _num(c.get("torque_max_N_mm"))
            partes = []
            if t is not None:
                partes.append("%g N.mm" % t)
            if tmin is not None or tmax is not None:
                partes.append("(min %s / max %s)" % (tmin, tmax))
            if ang is not None:
                partes.append("at %g deg" % ang)
            if partes:
                add("Torque %s: %s" % (et, " ".join(partes)), "alta", ruta)
        else:
            f = _num(c.get("fuerza_N"))
            L = _num(c.get("longitud_mm"))
            tol = _num(c.get("tolerancia_fuerza_pct"))
            tola = _num(c.get("tolerancia_fuerza_absoluta_N"))
            if f is not None:
                s = "Load %s: %g N" % (et, f)
                if L is not None:
                    s += " at %g mm" % L
                if tol is not None:
                    s += " +/-%g%%" % tol
                elif tola is not None:
                    s += " +/-%g N" % tola
                sev = "alta" if (tol is not None and tol <= 7) or (
                    tola is not None and f and (tola / f) <= 0.07) else "media"
                add(s, sev, ruta)
        if c.get("condiciones_medicion"):
            add("Measuring condition (%s): %s" % (et, c["condiciones_medicion"]),
                "media", ruta)

    # 3. parametros declarados que hay que cumplir
    if _num(spec.get("pretension_N")) is not None:
        add("Initial tension: %g N" % _num(spec["pretension_N"]),
            "alta", "pretension_N")
    if _num(spec.get("rigidez_lineal_N_por_mm")) is not None:
        add("Declared rate k = %g N/mm - check it against the design"
            % _num(spec["rigidez_lineal_N_por_mm"]), "media", "rigidez_lineal_N_por_mm")
    if _num(spec.get("rigidez_angular_N_mm_por_grado")) is not None:
        add("Declared angular rate %g N.mm/deg"
            % _num(spec["rigidez_angular_N_mm_por_grado"]), "media",
            "rigidez_angular_N_mm_por_grado")
    if _num(spec.get("esfuerzo_trabajo_MPa")) is not None:
        add("Declared working stress %g MPa" % _num(spec["esfuerzo_trabajo_MPa"]),
            "info", "esfuerzo_trabajo_MPa")

    # 4. operaciones secundarias (impactan coste directo)
    mat = spec.get("material") or {}
    if mat.get("tratamiento_termico"):
        add("Heat treatment: %s" % mat["tratamiento_termico"], "alta",
            "material.tratamiento_termico")
    if mat.get("acabado_superficial"):
        add("Finish / coating: %s" % mat["acabado_superficial"], "alta",
            "material.acabado_superficial")
    if mat.get("referencia_documento_externo"):
        add("Refers to an external customer document: %s"
            % mat["referencia_documento_externo"], "alta",
            "material.referencia_documento_externo")
    if mat.get("alternativas"):
        add("Alternative material allowed: %s" % ", ".join(mat["alternativas"]),
            "info", "material.alternativas")

    # Lo que no se leyo del plano no puede figurar como requisito del cliente.
    _est_ext = {e.get("campo") for e in
                ((spec.get("metadatos_extraccion") or {}).get("campos_estimados") or [])
                if isinstance(e, dict)}
    ext = spec.get("extremos") or {}
    if ext.get("rectificado"):
        # Solo si lo ESCRIBE el plano. El rectificado es una operacion
        # secundaria con coste: si se lista como requisito del cliente cuando
        # en realidad lo supusimos nosotros, alguien lo marca OK y la oferta
        # carga un rectificado que nadie pidio.
        if "extremos.tipo" not in _est_ext:
            add("Ends ground (grinding operation)", "alta", "extremos.rectificado")
    if ext.get("tipo"):
        if "extremos.tipo" not in _est_ext:
            add("End type: %s" % ext["tipo"], "media", "extremos.tipo")
    if ext.get("rebabeo"):
        add("Deburring: %s" % ext["rebabeo"], "media", "extremos.rebabeo")

    esp = spec.get("espiras") or {}
    if esp.get("sentido_enrollado"):
        add("Coiling direction: %s" % esp["sentido_enrollado"], "media",
            "espiras.sentido_enrollado")
    if esp.get("mano_resorte"):
        add("Spring hand: %s" % esp["mano_resorte"], "media", "espiras.mano_resorte")

    gan = spec.get("ganchos") or {}
    if gan.get("tipo") or gan.get("geometria"):
        add("Hooks: %s" % (gan.get("tipo") or gan.get("geometria")), "alta", "ganchos")
    if _num(gan.get("angulo_entre_ganchos_grados")) is not None:
        tol = _num(gan.get("angulo_entre_ganchos_tolerancia_grados"))
        add("Angle between hooks %g deg%s"
            % (_num(gan["angulo_entre_ganchos_grados"]),
               (" +/-%g" % tol) if tol is not None else ""), "alta", "ganchos")

    br = spec.get("brazos") or {}
    if br.get("configuracion"):
        add("Leg configuration: %s" % br["configuracion"], "alta", "brazos")
    for k, et in (("longitud_brazo_1_mm", "leg 1"), ("longitud_brazo_2_mm", "leg 2")):
        if _num(br.get(k)) is not None:
            add("Length of %s: %g mm" % (et, _num(br[k])), "media", "brazos." + k)
    if _num(br.get("angulo_entre_brazos_libre_grados")) is not None:
        add("Angle between legs, free: %g deg"
            % _num(br["angulo_entre_brazos_libre_grados"]), "alta",
            "brazos.angulo_entre_brazos_libre_grados")

    # 5. wire form
    dobl = spec.get("doblados") or []
    if dobl:
        add("%d dimensioned bends - this sets the number of operations" % len(dobl),
            "alta", "doblados")
        for i, db in enumerate(dobl):
            if isinstance(db, dict) and _num(db.get("tolerancia_angulo_grados")) is not None \
                    and _num(db["tolerancia_angulo_grados"]) <= 1:
                add("Bend %s with a tight angular tolerance (+/-%g deg)"
                    % (db.get("etiqueta") or (i + 1), _num(db["tolerancia_angulo_grados"])),
                    "alta", "doblados[%d]" % i)
    for i, tg in enumerate(spec.get("tolerancias_geometricas") or []):
        if isinstance(tg, dict) and tg.get("caracteristica"):
            add("Geometric tolerance: %s %s%s" % (
                tg["caracteristica"],
                ("%g mm" % _num(tg["valor_mm"])) if _num(tg.get("valor_mm")) is not None else "",
                (" (datum %s)" % tg["datum"]) if tg.get("datum") else ""),
                "alta", "tolerancias_geometricas[%d]" % i)

    # 6. caracteristicas clasificadas del cliente
    for i, cc in enumerate(spec.get("caracteristicas_clasificadas") or []):
        if not isinstance(cc, dict):
            continue
        add("Classified characteristic %s: %s %s" % (
            cc.get("clasificacion") or "?", cc.get("designacion") or cc.get("dim_no") or "",
            cc.get("valor") or ""), "alta", "caracteristicas_clasificadas[%d]" % i)

    # 7. condiciones de operacion
    co = spec.get("condiciones_operacion") or {}
    if _num(co.get("temperatura_min_C")) is not None or _num(co.get("temperatura_max_C")) is not None:
        add("Service temperature: %s to %s C" % (co.get("temperatura_min_C"),
                                                    co.get("temperatura_max_C")),
            "media", "condiciones_operacion")
    if _num(co.get("frecuencia_ciclos")) is not None:
        add("Required life: %g cycles" % _num(co["frecuencia_ciclos"]), "alta",
            "condiciones_operacion.frecuencia_ciclos")
    if co.get("resistencia_corrosion"):
        add("Corrosion resistance: %s" % co["resistencia_corrosion"], "alta",
            "condiciones_operacion.resistencia_corrosion")

    # 8. normas de ensayo / calidad / acabado
    for i, n in enumerate(spec.get("normas_aplicables") or []):
        if not isinstance(n, dict):
            continue
        if n.get("tipo") in ("ensayo", "calidad", "acabado"):
            add("Standard (%s): %s%s" % (n["tipo"], n.get("norma"),
                                      (" - " + n["descripcion"]) if n.get("descripcion") else ""),
                "alta" if n["tipo"] == "ensayo" else "media",
                "normas_aplicables[%d]" % i)

    # 9. notas del plano
    for i, nota in enumerate(spec.get("notas_generales") or []):
        add("Note: %s" % nota, "info", "notas_generales[%d]" % i)

    orden = {"alta": 0, "media": 1, "info": 2}
    items.sort(key=lambda x: orden.get(x["severidad"], 3))
    return items


# ---------------------------------------------------------------- cajetin
def titulo(spec):
    idf = spec.get("identificacion") or {}
    notas = []
    meta = spec.get("metadatos_extraccion") or {}
    if meta.get("comentarios"):
        notas.append(_linea(meta["comentarios"], 300))
    return {
        "pn": idf.get("numero_parte") or idf.get("numero_plano"),
        "customer": idf.get("cliente"),
        "revision": idf.get("revision"),
        "description": idf.get("nombre_parte"),
        "notes": " | ".join(notas) or None,
        "drawingNo": idf.get("numero_plano"),
        "date": idf.get("fecha_revision"),
        "mass": idf.get("masa"),
        "scale": idf.get("escala"),
        "unidadOriginal": idf.get("unidad_dimensional"),
    }


# ---------------------------------------------------------------- avisos
CONFIANZA_ESTIMADO = {"alta": 0.75, "media": 0.6, "baja": 0.45}


def estimados(spec):
    """-> {ruta: {metodo, confianza}} con lo que el extractor dedujo del dibujo.

    Vive en `metadatos_extraccion.campos_estimados`. Se indexa por ruta para que
    `campos()` pueda marcar el campo correspondiente sin recorrer la lista.
    """
    meta = spec.get("metadatos_extraccion") or {}
    out = {}
    for e in (meta.get("campos_estimados") or []):
        if not isinstance(e, dict):
            continue
        campo = str(e.get("campo") or "").strip()
        if campo:
            out[campo] = {"metodo": str(e.get("metodo") or "").strip(),
                          "confianza": str(e.get("confianza") or "media").strip()}
    return out


def _nota_estimado(est):
    """Nota que acompaña a un valor estimado. Siempre empieza igual, para que se
    reconozca de un vistazo entre las demas notas."""
    m = est.get("metodo")
    return "ESTIMATED from the drawing, not a stated dimension%s. Confirm it." % (
        " - " + _linea(m, 120) if m else "")


def _campo_no_visible(c):
    """Una entrada de campos_no_visibles -> una linea legible.

    El schema acepta las dos formas que devuelve el modelo: una cadena suelta
    ("material.norma: no aparece") o un objeto {campo, motivo}. Sin esto, la
    segunda salia por pantalla como un dict de Python.
    """
    if isinstance(c, dict):
        campo = nombre_ruta(str(c.get("campo") or "").strip())
        motivo = str(c.get("motivo") or c.get("razon") or "").strip()
        if campo and motivo:
            return "%s - %s" % (campo, _linea(motivo, 120))
        return campo or _linea(motivo, 160)
    texto = _linea(c, 160)
    # "ruta: motivo" -> se traduce la ruta y se deja el motivo tal cual
    if ":" in texto:
        ruta, _, motivo = texto.partition(":")
        legible = nombre_ruta(ruta.strip())
        if legible != ruta.strip():
            return "%s -%s" % (legible, motivo)
    return nombre_ruta(texto)


# Orden en que se pintan. No es estetico: quien cotiza mira la lista una vez y
# tiene que ver primero lo que le obliga a hacer algo.
ORDEN_SEVERIDAD = {"high": 0, "medium": 1, "info": 2}

# Campos cuya estimacion es ARITMETICA (ID = OD-2d, MD = OD-d, Ls = Nt x d).
# El calculador los recalcula por su cuenta, asi que avisar de ellos es ruido.
# Lo comprobamos: de 15 campos marcados como estimados en once planos reales,
# once eran de estos.
_ESTIMADO_ARITMETICO = (
    "dimensiones_mm.diametro_interior",
    "dimensiones_mm.diametro_medio",
    "dimensiones_mm.diametro_exterior",
    "dimensiones_mm.longitud_comprimida_Ls",
)


def avisos(spec, tipo, diag=None, router=None, extra=None):
    """-> lista de {text, severity}, ordenada por severidad.

    `extra` son los avisos de coherencia fisica: van como `high` porque
    significan que un numero del calculo esta mal, no que falte informacion.
    """
    out = []

    def add(texto, sev="medium"):
        if texto:
            out.append({"text": texto, "severity": sev})

    # `extra` mezcla dos cosas: los avisos de coherencia fisica, que son graves
    # por definicion, y los que explican como se obtuvo un dato, que no lo son.
    # Los que ya traen severidad la conservan.
    for t in (extra or []):
        if isinstance(t, dict):
            add(t.get("text"), t.get("severity", "high"))
        else:
            add(t, "high")

    meta = spec.get("metadatos_extraccion") or {}

    # Lo estimado: separado en dos. Lo que el calculador recalcula solo es
    # informativo; lo que de verdad entra en el resultado, no.
    for e in (meta.get("campos_estimados") or [])[:12]:
        if not isinstance(e, dict):
            continue
        campo = str(e.get("campo") or "?")
        add("ESTIMATED, not stated on the drawing: %s = %s (%s). Confirm "
            "before quoting."
            % (nombre_ruta(campo),
               e.get("valor") if e.get("valor") is not None else "?",
               _linea(e.get("metodo") or "no method given", 110)),
            "info" if campo in _ESTIMADO_ARITMETICO else "medium")

    # El comentario del extractor: conversiones de unidades, cotas raras. Util
    # para quien revisa, pero rara vez obliga a nada.
    com = meta.get("comentarios")
    if com:
        add("Parser note: %s" % _linea(com, 400), "info")

    conf = meta.get("confianza_general")
    if conf in ("media", "baja"):
        add("Confidence declared by the parser: %s. Check the drawing." % conf,
            "medium" if conf == "baja" else "info")

    for c in (meta.get("campos_no_visibles") or [])[:12]:
        add("Not readable on the drawing: %s" % _campo_no_visible(c), "info")

    if router and router.get("confianza") in ("media", "baja"):
        add("The classifier was unsure of the spring type (%s): %s"
            % (router.get("confianza"), _linea(router.get("razon") or "", 160)),
            "high")

    if diag:
        if diag.get("truncado"):
            add("The model reply was cut short by max_tokens: information may "
                "be missing.", "high")
        for e in (diag.get("errores_schema") or [])[:8]:
            add("JSON outside the schema: %s" % e, "high")
        if diag.get("sin_jsonschema"):
            add("jsonschema is not installed: the JSON was not validated.",
                "medium")

    out.sort(key=lambda a: ORDEN_SEVERIDAD.get(a["severity"], 1))
    return out


def _completar_extremos(spec, tipo):
    """Resuelve el tipo de extremo sin mirar el dibujo. -> (spec, avisos).

    Mueve la altura de bloque y el factor de pandeo, pero NO las espiras
    muertas -- son 2 en las dos variantes cerradas -- asi que la rigidez, el
    peso y el precio quedan igual pase lo que pase aqui.
    """
    import copy
    from . import coherencia

    if tipo != "compresion":
        return spec, []

    escrito = coherencia.extremo_escrito(spec)
    if escrito:
        return spec, []                     # el plano lo dice: manda el plano

    d = coherencia._nominal((spec.get("dimensiones_mm") or {})
                            .get("diametro_alambre"))
    Nt = _num((spec.get("espiras") or {}).get("numero_espiras_totales"))
    delbloque = coherencia.extremo_del_bloque(spec, d, Nt)

    nuevo = copy.deepcopy(spec)
    ext = nuevo.setdefault("extremos", {})
    def _marcar(valor, metodo, confianza):
        """Lo que no se leyo del plano queda registrado como tal. Sin esto, la
        suposicion se cuela en la lista de requisitos del cliente."""
        meta = nuevo.setdefault("metadatos_extraccion", {})
        est = [e for e in (meta.get("campos_estimados") or [])
               if not (isinstance(e, dict) and e.get("campo") == "extremos.tipo")]
        est.append({"campo": "extremos.tipo", "valor": valor,
                    "metodo": metodo, "confianza": confianza})
        meta["campos_estimados"] = est

    if delbloque:
        ext["tipo"] = delbloque
        ext["rectificado"] = delbloque.endswith("_ground")
        _marcar(delbloque, "worked out from the stated solid length, "
                           "not read from the drawing", "media")
        return nuevo, [{"text": "END TYPE DERIVED: the drawing does not state "
                                "it, so it was worked out from the stated solid "
                                "length: %s. The spring view is not used."
                                % delbloque.replace("_", " "),
                        "severity": "info"}]

    ext["tipo"] = coherencia.EXTREMO_POR_DEFECTO
    ext["rectificado"] = True
    _marcar(coherencia.EXTREMO_POR_DEFECTO,
            "assumed: the drawing does not state the ends", "baja")
    return nuevo, [{"text": "END TYPE ASSUMED: the drawing does not state it and "
                            "there is no solid length to work it out from, so "
                            "'squared and ground' was assumed - it is what 5 of "
                            "the 6 ISC compression drawings say. It changes the "
                            "solid height by one wire diameter and the buckling "
                            "factor; if the ends are NOT ground the buckling risk "
                            "is higher. It does not affect the rate, the weight "
                            "or the price.",
                    "severity": "medium"}]


def _completar_espiras(spec, tipo, codigo_material):
    """Rellena las espiras calculandolas. -> (spec, avisos).

    El spec se copia: no se toca el que guarda el servidor como leido del plano,
    para que siempre se pueda ver que dijo el modelo y que anadimos nosotros.
    """
    import copy
    from . import coherencia

    esp = spec.get("espiras") or {}
    if _num(esp.get("numero_espiras_totales")) is not None:
        return spec, []                       # el plano las acota: mandan ellas

    # LAS ACTIVAS, QUE MUCHOS PLANOS DAN EN VEZ DE LAS TOTALES. Sumarles las
    # espiras muertas de sus extremos es todo lo que hace falta: ni material ni
    # rigidez. Por eso va ANTES del calculo por rigidez, que necesita las dos
    # cosas.
    #
    # El 004-222 ensena por que importa. Dice "ACTIVE COILS 10 TO 10.5 APPROX"
    # y, en material, "SPRING WIRE" -- una categoria, no un material, asi que no
    # resuelve a ningun codigo ISC y el calculo por rigidez no podia. Sin
    # totales, las activas acababan viajando en el campo de las TOTALES con una
    # nota de aviso; la nota la lee una persona, la calculadora no, y les
    # restaba las dos espiras de los extremos: 8,25 activas en vez de 10,25. Con
    # ellas, un 24 % mas de rigidez, un 24 % mas de carga y un 16 % menos de
    # peso, que es el que va al precio.
    #
    # Solo compresion: en extension el numero del plano ya son las espiras del
    # cuerpo, y la calculadora lo usa tal cual.
    Na = _num(esp.get("numero_espiras_activas"))
    if tipo == "compresion" and Na is not None and Na > 0:
        muertas, de_donde = coherencia.muertas_por_extremo(spec, tipo)
        Nt = Na + muertas
        nuevo_spec = copy.deepcopy(spec)
        nuevo_spec.setdefault("espiras", {})["numero_espiras_totales"] = round(Nt, 2)
        meta = nuevo_spec.setdefault("metadatos_extraccion", {})
        est = [e for e in (meta.get("campos_estimados") or [])
               if not (isinstance(e, dict)
                       and str(e.get("campo") or "") == "espiras.numero_espiras_totales")]
        est.append({"campo": "espiras.numero_espiras_totales",
                    "valor": round(Nt, 2),
                    "metodo": "active coils + %.1f dead coils, from %s"
                              % (muertas, de_donde),
                    "confianza": "alta" if "stated" in de_donde else "media"})
        meta["campos_estimados"] = est
        return nuevo_spec, [{
            "text": "TOTAL COILS WORKED OUT: the drawing states %.2f ACTIVE "
                    "coils and not the total, so the total is the active coils "
                    "plus %.1f dead ones (%s): %.2f. The calculator subtracts "
                    "the same dead coils, so it works with the %.2f active "
                    "coils the drawing states."
                    % (Na, muertas, de_donde, Nt, Na),
            "severity": "info"}]

    r = coherencia.espiras_de_la_rigidez(spec, tipo, codigo_material)
    if not r:
        return spec, [{"text": "COIL COUNT NOT AVAILABLE: the drawing does not "
                               "state the number of coils, and there is not "
                               "enough data to compute it (it needs the material, "
                               "the wire and body diameters, and either the "
                               "spring rate or a load point). Without it there is "
                               "no weight and no price.",
                       "severity": "high"}]

    nuevo = copy.deepcopy(spec)
    nuevo.setdefault("espiras", {})
    nuevo["espiras"]["numero_espiras_totales"] = round(r["totales"], 1)
    if _num(esp.get("numero_espiras_activas")) is None:
        nuevo["espiras"]["numero_espiras_activas"] = round(r["activas"], 1)

    # Si el modelo dejo una nota de "contado en la vista" de una version
    # anterior, se sustituye: ya no es como se obtuvo el numero.
    meta = nuevo.setdefault("metadatos_extraccion", {})
    est = [e for e in (meta.get("campos_estimados") or [])
           if not (isinstance(e, dict)
                   and str(e.get("campo") or "").startswith("espiras."))]
    meta["campos_estimados"] = est
    est.append({
        "campo": "espiras.numero_espiras_totales",
        "valor": round(r["totales"], 1),
        "metodo": "computed from %s (%.3f N/mm), not counted on the view"
                  % (r["fuente"], r["k"]),
        "confianza": "alta" if any("confirmado" in c for c in r["comprobacion"])
                     else "media"})

    avisos = [{"text": "COILS COMPUTED, NOT COUNTED: the drawing does not state "
                       "the coil count, so it was derived from %s (%.3f N/mm): "
                       "%.1f active, %.1f total. The spring view is not used - "
                       "customer drawings often show a schematic coil count."
                       % (r["fuente"], r["k"], r["activas"], r["totales"]),
               "severity": "medium"}]
    for c in r["comprobacion"]:
        # "WARNING:" significa que dos datos del plano no cuadran; lo demas
        # solo cuenta con que se comprobo.
        avisos.append({"text": "Coil check: %s" % c,
                       "severity": "high" if c.startswith("WARNING") else "info"})
    return nuevo, avisos


def adaptar(spec, tipo, ubicaciones=None, diag=None, router=None, extra_avisos=None):
    """Payload completo para la calculadora. Los recortes los anade el servidor."""
    from . import coherencia

    ubic = ubicaciones or {}

    # Si el plano no acota las espiras, se CALCULAN de la rigidez. No se cuentan
    # en el dibujo: ISC confirmo que la vista del resorte es orientativa, y
    # medirla daba errores del 100 %. Va antes de `campos()` para que todo lo de
    # abajo -- cotas, feasibility y avisos -- vea ya el valor bueno.
    mat0 = next((f for f in campos(spec, tipo) if f.get("key") == "material"), None)
    spec, aviso_esp = _completar_espiras(spec, tipo, (mat0 or {}).get("code"))
    # Los extremos van DESPUES de las espiras: para despejarlos de la longitud
    # de bloque hace falta Nt, que puede acabar de calcularse ahi arriba.
    spec, aviso_ext = _completar_extremos(spec, tipo)
    extra_avisos = list(extra_avisos or []) + list(aviso_esp) + list(aviso_ext)

    fields = campos(spec, tipo)

    # Comprobacion fisica: que las espiras cuadren con las cargas que declara el
    # plano. Va la PRIMERA de los avisos porque invalida el calculo entero.
    mat = next((f for f in fields if f.get("key") == "material"), None)
    extra_avisos = list(coherencia.revisar(
        spec, tipo, (mat or {}).get("code"))) + list(extra_avisos or [])
    feas = feasibilidad(spec, tipo)

    for i, f in enumerate(fields):
        f["id"] = "field%d" % (i + 1)
        u = ubic.get(f.get("source") or "")
        if u:
            f["box"], f["page"] = u["nbox"], u["pagina"]
    # El veredicto y el borrador del comentario. Van despues de los avisos
    # porque se apoyan en ellos: el descuadre de espiras es una de las cinco
    # condiciones, y de "COILS COMPUTED" sale una frase del comentario.
    from . import factibilidad
    veredicto = factibilidad.evaluar(
        spec, tipo, (mat or {}).get("code"),
        tipo_pedido=tipo, avisos=extra_avisos)
    remarks = factibilidad.redactar(spec, tipo, veredicto, extra_avisos)

    for i, ft in enumerate(feas):
        ft["id"] = "feas%d" % (i + 1)
        u = ubic.get(ft.get("source") or "")
        if u:
            ft["box"], ft["page"] = u["nbox"], u["pagina"]

    return {
        "springType": TIPO_A_SPRINGTYPE.get(tipo, tipo),
        "tipo": tipo,
        "fields": fields,
        "feasibility": feas,
        "title": titulo(spec),
        "spec": spec,
        "warnings": avisos(spec, tipo, diag, router, extra_avisos),
        # Condiciones 1 a 5. La maquina la completa la calculadora, que es
        # donde vive su base de datos.
        "feasibility_verdict": veredicto,
        # La mitad del comentario que sabe el lector, en ingles: como se
        # obtuvieron los datos y que no se pudo comprobar.
        "remarks": remarks,
        "diagnostico": diag or {},
        "router": router or {},
    }
