"""Comprobaciones fisicas del spec: que los numeros leidos cuadren entre si.

Por que existe
--------------
El extractor puede **contar las espiras en la vista** cuando el plano no las
acota (ver `prompts/_comun.md`, apartado B quater). Eso desbloquea el calculo,
pero contar sobre un dibujo es lo mas fragil que hace: una espira de mas sobre
seis son ~17 % de error en la rigidez, y de ahi se propaga a carga, tension y
factor de seguridad.

Resulta que muchos planos traen la verificacion incorporada: si declaran uno o
mas **puntos de carga**, cada uno implica una rigidez, y de la rigidez se despeja
cuantas espiras deberia tener la pieza. Eso es una comprobacion **independiente**
-- las cargas no se usaron para contar -- y sale gratis.

Es la misma idea que validar el JSON contra su schema, aplicada a la fisica en
vez de a la forma.

Que NO hace
-----------
No corrige nada. Si el conteo y las cargas no cuadran, no sabemos cual de los dos
esta mal: puede fallar el conteo, o el plano puede traer un L0 antes del asentado
mientras las cargas se miden despues. Lo unico honesto es decirlo y que lo mire
un ingeniero.
"""

import math

# Modulo de cortadura en MPa, por codigo ISC de material. Tomados del propio
# Spring Engineering Calculator para que las dos herramientas no discrepen.
G_MPA = {
    "MW": 81000.0,      # music wire
    "CSI": 77200.0,     # chrome silicon
    "SS": 69000.0,      # 302/304
    "SS177": 75800.0,   # 17-7 PH
    "OT": 77200.0,      # oil tempered
    "HD": 78600.0,      # hard drawn
    "HAST": 79000.0,    # inconel / hastelloy
    "PHOSB": 41400.0,   # phosphor bronze
}

# Margen antes de avisar. Un resorte real se aparta de la formula ideal por los
# extremos y por el asentado, asi que por debajo de esto no hay nada que decir.
#
# Hay dos umbrales a proposito. Si el plano ACOTA las espiras, un desajuste es
# raro y puede venir de muchos sitios (fabricacion, asentado): se avisa solo
# cuando es grande. Si las CONTAMOS nosotros, el numero es lo mas fragil de la
# lectura -- el mismo plano leido dos veces dio 13 y 14 -- asi que el listón
# baja: ahi las cargas del plano son el dato duro y el conteo la conjetura.
TOLERANCIA_ACOTADO = 0.15
TOLERANCIA_CONTADO = 0.07

# Suelo absoluto, en espiras. El porcentaje solo no vale: con pocas espiras
# activas un 7 % son dos decimas de espira, y **nadie cuenta con esa finura**
# -- el prompt cuenta en incrementos de media espira. Sin este suelo, un resorte
# de 3 espiras con 2,8 exigidas se marcaba como descuadre cuando la diferencia
# esta por debajo de lo que el metodo puede distinguir.
DIFERENCIA_MINIMA_ESPIRAS = 0.5

# Modulo de Young en MPa, por codigo ISC. La torsion trabaja a flexion, asi
# que su rigidez va con E y no con G. Tomados del Spring Engineering Calculator.
E_MPA = {
    "MW": 203400.0, "CSI": 203400.0, "SS": 193000.0, "SS177": 200000.0,
    "OT": 203400.0, "HD": 203400.0, "HAST": 213700.0, "PHOSB": 103400.0,
}

# Espiras muertas que se descuentan cuando el plano no dice cuantas hay. Dos es
# lo normal en extremos cerrados, que es la mayoria.
MUERTAS_POR_DEFECTO = 2.0


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _nominal(cota):
    if not isinstance(cota, dict):
        return None
    n = _num(cota.get("nominal"))
    if n is not None:
        return n
    vmax, vmin = _num(cota.get("valor_maximo")), _num(cota.get("valor_minimo"))
    if vmax is not None and vmin is not None:
        return (vmax + vmin) / 2.0
    return vmax if vmax is not None else vmin


def rigidez_angular_declarada(spec):
    """-> k en N.mm por VUELTA si el plano acota la rigidez angular.

    El spec la guarda por GRADO, que es como la escriben los planos
    ("0,053 N.m/deg"), pero la formula de la espira trabaja por vuelta.
    Sin esta conversion el resultado salia 360 veces pequeno y el guardarrail
    de `espiras_de_la_rigidez` lo descartaba en silencio.
    """
    k = _num(spec.get("rigidez_angular_N_mm_por_grado"))
    return k * 360.0 if (k and k > 0) else None


def rigidez_declarada(spec):
    """-> k en N/mm si el plano la acota directamente. None si no.

    Muchos planos de compresion no dan puntos de carga pero si la constante del
    resorte. Sirve exactamente igual para verificar el conteo, y en la practica
    aparece mas a menudo: de los cuatro planos ISC de referencia, tres declaran
    rigidez y solo uno da cargas.
    """
    k = _num(spec.get("rigidez_lineal_N_por_mm"))
    return k if (k and k > 0) else None


def rigidez_de_las_cargas(spec):
    """-> (k en N/mm, n de puntos usados). None si el plano no da para calcularla.

    Cada punto de carga da `k = F / (L0 - L)`. Se promedian los que haya: un
    punto solo ya sirve, y con varios el promedio absorbe el ruido de medicion.
    """
    L0 = _nominal((spec.get("dimensiones_mm") or {}).get("longitud_libre_L0"))
    if not L0 or L0 <= 0:
        return None, 0
    ks = []
    for c in (spec.get("cargas") or []):
        if not isinstance(c, dict):
            continue
        F, L = _num(c.get("fuerza_N")), _num(c.get("longitud_mm"))
        if F is None or L is None or F <= 0:
            continue
        defl = L0 - L
        if defl <= 0:                       # una carga a longitud mayor que la
            continue                        # libre no es un punto de trabajo
        ks.append(F / defl)
    if not ks:
        return None, 0
    return sum(ks) / len(ks), len(ks)


def espiras_activas_de_la_rigidez(spec, k, codigo_material):
    """Na que haria falta para dar esa rigidez. -> None si falta algun dato.

        k = G * d^4 / (8 * D^3 * Na)   ->   Na = G * d^4 / (8 * D^3 * k)
    """
    G = G_MPA.get(str(codigo_material or "").upper())
    if not G or not k or k <= 0:
        return None
    dims = spec.get("dimensiones_mm") or {}
    d = _nominal(dims.get("diametro_alambre"))
    D = _nominal(dims.get("diametro_medio"))
    if D is None:
        od = _nominal(dims.get("diametro_exterior"))
        if od is not None and d is not None:
            D = od - d                      # Dm = OD - d
    if not d or not D or d <= 0 or D <= 0:
        return None
    return G * math.pow(d, 4) / (8.0 * math.pow(D, 3) * k)


def _fue_estimado(spec, ruta):
    meta = spec.get("metadatos_extraccion") or {}
    for e in (meta.get("campos_estimados") or []):
        if isinstance(e, dict) and str(e.get("campo") or "") == ruta:
            return True
    return False


def revisar_espiras(spec, codigo_material):
    """Contrasta las espiras con las cargas que declara el plano. -> aviso o None.

    Solo aplica a resortes helicoidales de compresion y tension: en torsion la
    rigidez es angular y la formula es otra.
    """
    esp = spec.get("espiras") or {}
    Nt = _num(esp.get("numero_espiras_totales"))
    Na = _num(esp.get("numero_espiras_activas"))
    if Nt is None and Na is None:
        return None

    # La rigidez acotada gana sobre la deducida de las cargas: es un dato
    # directo del plano, sin la resta L0 - L de por medio.
    k = rigidez_declarada(spec)
    # La frase cambia segun de donde salga la rigidez: si el plano la acota es
    # un hecho, si sale de las cargas es una implicacion. Decir "the rate ...
    # implies a rate" quedaba redundante.
    origen_k, n_puntos = "the rate stated on the drawing is %.3f N/mm", 0
    if k is None:
        k, n_puntos = rigidez_de_las_cargas(spec)
        if k is None:
            return None                      # el plano no trae con que comprobar
        origen_k = ("the %d load point%s on the drawing impl%s a rate of "
                    "%%.3f N/mm" % (n_puntos, "" if n_puntos == 1 else "s",
                                    "ies" if n_puntos == 1 else "y"))

    Na_teorica = espiras_activas_de_la_rigidez(spec, k, codigo_material)
    if Na_teorica is None or Na_teorica <= 0:
        return None

    if Na is None:
        muertas = _num(esp.get("numero_espiras_muertas_totales"))
        Na = Nt - (MUERTAS_POR_DEFECTO if muertas is None else muertas)
    if Na is None or Na <= 0:
        return None

    estimado = _fue_estimado(spec, "espiras.numero_espiras_totales")
    desvio = (Na - Na_teorica) / Na_teorica
    if abs(desvio) <= (TOLERANCIA_CONTADO if estimado else TOLERANCIA_ACOTADO):
        return None
    if abs(Na - Na_teorica) < DIFERENCIA_MINIMA_ESPIRAS:
        return None                          # por debajo de la resolucion del conteo

    origen = ("counted from the drawing" if estimado
              else "stated on the drawing")
    return (
        "COIL COUNT DOES NOT MATCH THE STATED RATE: the spring has %.1f active "
        "coils (%s), but %s, which needs about %.1f. That is %+.0f%%. %s"
        % (Na, origen, origen_k % k, Na_teorica, desvio * 100,
           "The rate is stated by the customer; the count was inferred from "
           "the view, so trust the rate: about %.0f total coils. Recount before "
           "quoting - the coil count drives rate, load and stress."
           % (Na_teorica + MUERTAS_POR_DEFECTO)
           if estimado else
           "Either the drawing is internally inconsistent, or a value was "
           "misread. Worth a look before quoting."))


def _rigidez_de_dos_cargas(spec):
    """-> (k, "de dos puntos de carga") usando la diferencia entre dos cargas.

    Es la mejor forma de obtener k: al restar dos puntos se cancela la longitud
    libre, asi que un L0 mal leido no contamina el resultado.

        k = (F2 - F1) / (L1 - L2)
    """
    pts = []
    for c in (spec.get("cargas") or []):
        if not isinstance(c, dict):
            continue
        F, L = _num(c.get("fuerza_N")), _num(c.get("longitud_mm"))
        if F is not None and L is not None and F > 0:
            pts.append((L, F))
    if len(pts) < 2:
        return None, None
    pts.sort()
    (L1, F1), (L2, F2) = pts[0], pts[-1]
    if L2 - L1 <= 0:
        return None, None
    return (F1 - F2) / (L2 - L1), "the slope between two load points"


def rigidez(spec):
    """-> (k en N/mm, de donde salio). La mejor fuente disponible, en orden.

    1. La que acota el plano: es una especificacion firmada por el cliente.
    2. El promedio de los puntos de carga contra la longitud libre.
    3. La pendiente entre dos cargas, solo si no hay longitud libre.

    El orden 2/3 puede sorprender -- la pendiente entre dos puntos es mas
    "pura", porque al restar se cancela L0. Pero **toda la calculadora modela
    la carga como F = k (L0 - L)**, asi que si se escoge la pendiente, sus
    cargas dejan de cuadrar con las del plano.

    Medido en PIEZA-09: la pendiente da 2,224 N/mm y el promedio 1,933. Con la
    pendiente, la carga calculada en el punto de trabajo sale un 12 % por
    encima de la que acota el cliente; con el promedio, un 2 % por debajo.
    La discrepancia entre ambas no se tira: se usa como comprobacion.
    """
    # La torsion tiene su propia rigidez y sus propias unidades.
    if (spec.get("tipo_resorte") or spec.get("tipo")) == "torsion":
        k = rigidez_angular_declarada(spec)
        return ((k, "the angular rate stated on the drawing") if k
                else (None, None))

    k = rigidez_declarada(spec)
    if k:
        return k, "the spring rate stated on the drawing"
    k, n = rigidez_de_las_cargas(spec)
    if k and k > 0:
        return k, "%d load point%s on the drawing" % (n, "" if n == 1 else "s")
    k, como = _rigidez_de_dos_cargas(spec)
    if k and k > 0:
        return k, como
    return None, None


def _geometria(spec):
    """-> (d, D) en mm, o (None, None). D medio: acotado o derivado de OD - d."""
    dims = spec.get("dimensiones_mm") or {}
    d = _nominal(dims.get("diametro_alambre"))
    D = _nominal(dims.get("diametro_medio"))
    if D is None:
        od, di = (_nominal(dims.get("diametro_exterior")),
                  _nominal(dims.get("diametro_interior")))
        if od is not None and d is not None:
            D = od - d
        elif di is not None and d is not None:
            D = di + d
    if not d or not D or d <= 0 or D <= 0:
        return None, None
    return d, D


def espiras_de_la_rigidez(spec, tipo, codigo_material):
    """Calcula las espiras en vez de contarlas. -> dict o None.

    Devuelve {activas, totales, muertas, k, fuente, comprobacion} o None si el
    plano no da con que. NUNCA mira el dibujo.
    """
    d, D = _geometria(spec)
    if not d:
        return None
    k, fuente = rigidez(spec)
    if not k:
        return None
    cod = str(codigo_material or "").upper()

    if tipo == "torsion":
        E = E_MPA.get(cod)
        if not E:
            return None
        Na = E * math.pow(d, 4) / (10.8 * D * k)
    else:
        G = G_MPA.get(cod)
        if not G:
            return None
        Na = G * math.pow(d, 4) / (8.0 * math.pow(D, 3) * k)
    # Un resorte real no baja de media espira activa ni pasa de unos cientos.
    # Fuera de eso, algun dato de entrada esta mal y es mejor no dar nada.
    if not (0.5 <= Na <= 500):
        return None

    muertas = _num((spec.get("espiras") or {}).get("numero_espiras_muertas_totales"))
    if muertas is None:
        ext = str(((spec.get("extremos") or {}).get("tipo")) or "").lower()
        # Extremos abiertos no aportan espiras muertas; cerrados, dos.
        muertas = 0.0 if any(x in ext for x in ("plain", "open", "abiert")) \
                  else MUERTAS_POR_DEFECTO
    return {"activas": Na, "totales": Na + muertas, "muertas": muertas,
            "k": k, "fuente": fuente,
            "comprobacion": _comprobar_calculo(spec, tipo, cod, d, D, Na, k)}


def bloque_util(spec):
    """-> (Ls, es_maximo) si el plano acota la longitud de bloque de verdad.

    Devuelve None en dos casos que parecen validos y no lo son:

    * cuando la cota la **calculo el propio lector** como Nt x d. Verificar las
      espiras contra un numero derivado de las espiras no verifica nada.
    * cuando no hay ni nominal ni maximo.

    Un "MAX SOLID HEIGHT" si vale, pero solo como cota superior: dice que el
    bloque no puede pasar de ahi, no cuanto mide.
    """
    est = {e.get("campo") for e in
           ((spec.get("metadatos_extraccion") or {}).get("campos_estimados") or [])
           if isinstance(e, dict)}
    if "dimensiones_mm.longitud_comprimida_Ls" in est:
        return None, None
    cota = (spec.get("dimensiones_mm") or {}).get("longitud_comprimida_Ls")
    if not isinstance(cota, dict):
        return None, None
    # Si hay una CARGA especificada a esa misma longitud, no es la altura de
    # bloque: es el punto donde el cliente mide esa carga. Muchos planos
    # escriben "COMPRESSED LENGTH 12,63 mm" y justo debajo "MAXIMUM LOAD AT
    # COMPRESSED LENGTH 6,58 N" -- son la misma cota, y es un ensayo.
    # A bloque el resorte esta colapsado; no se especifica una carga de trabajo
    # ahi. Tomarlo por bloque daba 24,7 espiras contra las 12,8 de la rigidez.
    n0 = _num(cota.get("nominal")) or _num(cota.get("valor_maximo"))
    if n0 is not None:
        for c in (spec.get("cargas") or []):
            L = _num(c.get("longitud_mm")) if isinstance(c, dict) else None
            if L is not None and abs(L - n0) < 0.01:
                return None, None
    n = _num(cota.get("nominal"))
    if n and n > 0:
        return n, False
    mx = _num(cota.get("valor_maximo"))
    if mx and mx > 0:
        return mx, True
    return None, None


def espiras_del_bloque(spec, d):
    """-> Nt segun la longitud de bloque acotada, o None.

    Es una via **independiente** de la rigidez: no usa el material ni el
    diametro medio, solo Ls y el grueso del alambre.

        extremos rectificados     Ls = Nt x d        -> Nt = Ls / d
        sin rectificar            Ls = (Nt + 1) x d  -> Nt = Ls / d - 1
    """
    Ls, es_max = bloque_util(spec)
    if not Ls or es_max or not d:
        return None
    ext = spec.get("extremos") or {}
    txt = (str(ext.get("tipo") or "") + " ").lower()
    rect = ext.get("rectificado")
    if rect is None:
        rect = any(x in txt for x in ("ground", "rectific", "esmerilad"))
    return Ls / d - (0.0 if rect else 1.0)


# El extremo mas frecuente en los planos de ISC. De los seis de compresion que
# dicen algo, cinco dicen "closed and ground".
EXTREMO_POR_DEFECTO = "closed_ground"


def extremo_escrito(spec):
    """-> el tipo de extremo si el PLANO lo dice, no si el modelo lo dedujo.

    Se descarta lo que venga marcado como estimado: en 9907008666 el modelo lo
    saco de la vista y dio dos respuestas distintas en dos lecturas.
    """
    est = {e.get("campo") for e in
           ((spec.get("metadatos_extraccion") or {}).get("campos_estimados") or [])
           if isinstance(e, dict)}
    if "extremos.tipo" in est:
        return None
    ext = spec.get("extremos") or {}
    # SIN CITA NO HAY AUTORIDAD. Confiar en que el modelo marque lo que dedujo
    # no basta: en 9907008666 devolvio {"tipo": "closed", "rectificado": false}
    # sin marcarlo como estimado, y el plano no dice ni una palabra de los
    # extremos. Asi que se exige el texto literal del plano; si no lo hay, se
    # trata como no acotado y se despeja o se supone.
    if not str(ext.get("texto_original") or "").strip():
        return None
    t = str(ext.get("tipo") or "").lower()
    if not t:
        return None
    rect = ext.get("rectificado")
    if rect is None:
        rect = any(x in t for x in ("ground", "rectific", "esmerilad", "amolad"))
    if any(x in t for x in ("plain", "open", "abiert")):
        return "plain_ground" if rect else "plain"
    if any(x in t for x in ("closed", "squared", "cerrad", "cuadrad")):
        return "closed_ground" if rect else "closed"
    return None


def extremo_del_bloque(spec, d, Nt):
    """-> 'closed_ground' | 'closed' | None, despejado de la longitud de bloque.

        rectificado      Ls = Nt x d
        sin rectificar   Ls = (Nt + 1) x d

    Un diametro de alambre separa las dos, asi que solo se decide cuando la
    diferencia es clara: si Ls cae a medio camino, se devuelve None en vez de
    escoger a suertes.
    """
    Ls, es_max = bloque_util(spec)
    if not Ls or es_max or not d or not Nt:
        return None
    con = abs(Ls - Nt * d)
    sin = abs(Ls - (Nt + 1) * d)
    if abs(con - sin) < d * 0.4:          # ninguna gana con claridad
        return None
    return "closed_ground" if con < sin else "closed"


def _comprobar_calculo(spec, tipo, cod, d, D, Na, k):
    """El calculo tambien puede salir mal. -> texto con lo que se comprobo.

    Tres verificaciones, todas con datos del propio plano y ninguna con el
    dibujo:
      a) si hay rigidez acotada Y puntos de carga, cada via da su Na: deben
         coincidir. Es la comprobacion fuerte -- son datos independientes.
      b) el paso resultante tiene que caber entre el alambre y la longitud libre.
      c) la altura de bloque resultante no puede pasarse de la longitud libre.
    """
    avisos = []
    G = G_MPA.get(cod)
    k_ac = rigidez_declarada(spec)
    k_car, _ = _rigidez_de_dos_cargas(spec)
    if k_car is None:
        k_car, _n = rigidez_de_las_cargas(spec)
    if k_ac and k_car and G and tipo != "torsion":
        Na_ac = G * math.pow(d, 4) / (8.0 * math.pow(D, 3) * k_ac)
        Na_car = G * math.pow(d, 4) / (8.0 * math.pow(D, 3) * k_car)
        dif = abs(Na_ac - Na_car) / max(Na_ac, Na_car)
        if dif <= 0.10:
            avisos.append("confirmed two independent ways - the stated rate "
                          "gives %.1f active coils and the load points %.1f"
                          % (Na_ac, Na_car))
        else:
            avisos.append("WARNING: the stated rate implies %.1f active coils "
                          "and the load points imply %.1f - a %.0f%% gap. The "
                          "drawing contradicts itself"
                          % (Na_ac, Na_car, dif * 100))

    # La pendiente entre dos cargas no depende de L0. Si no coincide con la
    # media contra L0, es que las cargas no describen una recta que pase por
    # cero en la longitud libre acotada -- lo tipico de un resorte
    # especificado DESPUES de asentar, que se acorta al asentarlo.
    L0v = _nominal((spec.get("dimensiones_mm") or {}).get("longitud_libre_L0"))
    k_pend, _ = _rigidez_de_dos_cargas(spec)
    k_med, _n = rigidez_de_las_cargas(spec)
    if k_pend and k_med and L0v and abs(k_pend - k_med) / k_med > 0.10:
        pts = sorted((_num(c.get("longitud_mm")), _num(c.get("fuerza_N")))
                     for c in (spec.get("cargas") or [])
                     if isinstance(c, dict) and _num(c.get("fuerza_N"))
                     and _num(c.get("longitud_mm")))
        L0imp = pts[0][0] + pts[0][1] / k_pend if pts else None
        avisos.append(
            "the load points describe a line reaching zero at %.1f mm, not at "
            "the stated free length of %.1f mm - the spring may be specified "
            "after set removal" % (L0imp, L0v) if L0imp else
            "the load points do not fit the stated free length")

    # Segunda via independiente: la longitud de bloque acotada. No pasa por la
    # rigidez ni por el material, asi que un error en cualquiera de los dos se
    # delataria aqui.
    if tipo != "torsion":
        muertas = _num((spec.get("espiras") or {}).get(
            "numero_espiras_muertas_totales")) or MUERTAS_POR_DEFECTO
        Nt_calc = Na + muertas
        Nt_bloque = espiras_del_bloque(spec, d)
        if Nt_bloque and Nt_bloque > 0:
            dif = abs(Nt_calc - Nt_bloque) / Nt_bloque
            if dif <= 0.10:
                avisos.append("confirmed against the solid length stated on the "
                              "drawing: it implies %.1f total coils and the rate "
                              "gives %.1f" % (Nt_bloque, Nt_calc))
            else:
                avisos.append("WARNING: the solid length stated on the drawing "
                              "implies %.1f total coils but the rate gives %.1f "
                              "(%.0f%% apart) - one of the two is misread"
                              % (Nt_bloque, Nt_calc, dif * 100))
        else:
            Ls_max, es_max = bloque_util(spec)
            if Ls_max and es_max:
                Ls_calc = d * Nt_calc
                if Ls_calc > Ls_max:
                    avisos.append("WARNING: the resulting solid height (%.1f mm) "
                                  "exceeds the maximum stated on the drawing "
                                  "(%.1f mm)" % (Ls_calc, Ls_max))
                else:
                    avisos.append("within the maximum solid height stated on the "
                                  "drawing (%.1f mm of %.1f mm allowed)"
                                  % (Ls_calc, Ls_max))

    L0 = L0v
    if L0 and tipo != "torsion" and Na >= 1:
        paso = (L0 - 2 * d) / Na
        if paso <= d:
            avisos.append("WARNING: the resulting pitch (%.2f mm) does not "
                          "clear the wire diameter (%.2f mm)" % (paso, d))
        bloque = d * (Na + 2)
        if bloque >= L0:
            avisos.append("WARNING: the resulting solid height (%.1f mm) "
                          "meets or exceeds the free length (%.1f mm)"
                          % (bloque, L0))
    return avisos


def revisar(spec, tipo, codigo_material=None):
    """Todas las comprobaciones que aplican. -> lista de avisos."""
    avisos = []
    if tipo in ("compresion", "tension"):
        a = revisar_espiras(spec, codigo_material)
        if a:
            avisos.append(a)
    return avisos
