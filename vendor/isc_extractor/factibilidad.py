# -*- coding: utf-8 -*-
"""El veredicto de factibilidad y el borrador del comentario.

Que decide, y que NO
--------------------
ISC no rechaza resortes por su diseno: los cotiza y les anade un comentario de
factibilidad. Lo confirmo Miguel Rodea. Asi que este modulo no opina sobre si un
resorte esta bien disenado -- eso va al comentario, nunca al veredicto.

Lo unico que impide cotizar es **no poder confiar en el dato**:

    1. el tipo de pieza detectado es el que se pidio
    2. el material se resolvio a un codigo ISC      -> $/lb y densidad
    3. estan el Ø de alambre, el Ø de cuerpo y las espiras   -> peso
    4. las espiras cuadran con la fisica del plano
    5. la geometria es posible

La quinta absorbe los cinco avisos que el Spring Calculator llama criticos y que
significan "esta pieza no puede existir" -- Ø interior negativo, longitud libre
por debajo de la de bloque. Eso no es un resorte dificil: es un dato mal leido,
y por eso vive aqui y no en el comentario.

Falta una sexta condicion, la maquina, que no se puede comprobar desde aqui: la
base de maquinas vive en el Spring Calculator y el usuario la edita alli. Se
deja marcada como pendiente y la completa la calculadora.

El idioma
---------
El codigo y los comentarios van en castellano, que los lee quien mantiene esto.
**Todo lo que sale va en ingles**, porque el comentario se pega en la oferta al
cliente y las ofertas de ISC son en ingles.
"""

from . import coherencia

FEASIBLE = "FEASIBLE"
REVIEW = "REQUIRES REVIEW"

_nominal = coherencia._nominal
_num = coherencia._num


def _diametros(spec):
    """-> (d, D_cuerpo) en mm. El de cuerpo es el que haya: exterior, medio o
    interior; para el peso sirve cualquiera porque los otros se derivan."""
    dims = spec.get("dimensiones_mm") or {}
    d = _nominal(dims.get("diametro_alambre"))
    cuerpo = (_nominal(dims.get("diametro_exterior"))
              or _nominal(dims.get("diametro_medio"))
              or _nominal(dims.get("diametro_interior")))
    return d, cuerpo


def _geometria_imposible(spec, tipo):
    """-> lista de razones por las que la pieza no puede existir tal como se leyo.

    Son las mismas cinco que el Spring Calculator marca como criticas de
    geometria, calculadas aqui para no depender de que la calculadora se haya
    abierto. Si alguna salta, algo se leyo mal.
    """
    if tipo != "compresion":
        return []
    dims = spec.get("dimensiones_mm") or {}
    d = _nominal(dims.get("diametro_alambre"))
    od = _nominal(dims.get("diametro_exterior"))
    di = _nominal(dims.get("diametro_interior"))
    L0 = _nominal(dims.get("longitud_libre_L0"))
    Nt = _num((spec.get("espiras") or {}).get("numero_espiras_totales"))
    fuera = []

    if od is not None and d and od - 2 * d <= 0:
        fuera.append("the inside diameter works out at %.2f mm or less: the wire "
                     "does not fit inside the stated outside diameter"
                     % (od - 2 * d))
    if di is not None and di <= 0:
        fuera.append("the stated inside diameter is zero or negative")

    if d and Nt and L0:
        ext = spec.get("extremos") or {}
        rect = ext.get("rectificado")
        if rect is None:
            rect = "ground" in str(ext.get("tipo") or "").lower()
        Ls = d * Nt if rect else d * (Nt + 1)
        if Ls >= L0:
            fuera.append("the solid height works out at %.1f mm, which meets or "
                         "exceeds the stated free length of %.1f mm" % (Ls, L0))
        else:
            h = None
            for c in (spec.get("cargas") or []):
                L = _num(c.get("longitud_mm")) if isinstance(c, dict) else None
                if L is not None and (h is None or L < h):
                    h = L
            if h is not None and h < Ls:
                fuera.append("the most demanding load point sits at %.1f mm, "
                             "below the solid height of %.1f mm: the spring "
                             "cannot reach it" % (h, Ls))
    return fuera


def evaluar(spec, tipo, codigo_material, tipo_pedido=None, avisos=None):
    """-> dict con el veredicto, sus motivos y lo que se comprobo.

    `avisos` son los de coherencia fisica ya calculados, para no repetirlos.
    """
    checks, razones = [], []

    def check(etiqueta, ok, detalle=""):
        checks.append({"label": etiqueta, "ok": bool(ok), "detail": detalle})
        if not ok:
            razones.append(detalle or etiqueta)

    # 1. el tipo detectado es el que se pidio ---------------------------------
    detectado = spec.get("tipo_detectado") or tipo
    coincide = (not tipo_pedido) or (detectado == tipo_pedido)
    check("Spring type", coincide,
          "" if coincide else
          "the drawing is a %s spring, not the %s that was requested"
          % (detectado, tipo_pedido))

    # 2. el material -----------------------------------------------------------
    hay_mat = bool(codigo_material)
    des = ((spec.get("material") or {}).get("designacion") or "").strip()
    check("Material resolved", hay_mat,
          "" if hay_mat else
          ("the drawing states \"%s\", which does not map to an ISC material code"
           % des[:60] if des else
           "the drawing does not state the material"))

    # 3. lo que hace falta para el peso ----------------------------------------
    d, cuerpo = _diametros(spec)
    Nt = _num((spec.get("espiras") or {}).get("numero_espiras_totales"))
    faltan = [n for n, v in (("wire diameter", d), ("body diameter", cuerpo),
                             ("coil count", Nt)) if not v]
    check("Geometry for weight", not faltan,
          "" if not faltan else
          "no weight can be computed without the %s" % " and the ".join(faltan))

    # 4. las espiras cuadran con la fisica -------------------------------------
    # Cualquier contradiccion entre dos datos del plano cuenta, no solo el
    # descuadre con la rigidez: si la longitud de bloque implica unas espiras y
    # la rigidez otras, uno de los dos esta mal leido y el peso saldra mal.
    def _t(x):
        return x if isinstance(x, str) else str((x or {}).get("text", ""))
    descuadre = [a for a in (avisos or [])
                 if "DOES NOT MATCH" in _t(a)
                 or (_t(a).startswith("Coil check:") and "WARNING" in _t(a))]
    check("Coil count consistent", not descuadre,
          "" if not descuadre else
          _t(descuadre[0]).replace("Coil check: WARNING: ", "")
          .replace("COIL COUNT DOES NOT MATCH THE STATED RATE: ", "")[:150])

    # 5. la geometria es posible ------------------------------------------------
    imposible = _geometria_imposible(spec, tipo)
    check("Geometry is possible", not imposible,
          "" if not imposible else imposible[0])

    return {
        "verdict": REVIEW if razones else FEASIBLE,
        "reasons": razones,
        "checks": checks,
        # La maquina no se puede comprobar aqui: su base vive en el Spring
        # Calculator y el usuario la edita alli.
        "pending": ["machine capability"],
    }


# --------------------------------------------------------------- el comentario

def _punto_de_trabajo(spec):
    """-> (altura, etiqueta del plano) del punto de carga mas exigente.

    La etiqueta importa: en los planos de ISC ese punto suele ser una condicion
    de ENSAYO -- "MAXIMUM LOAD AT COMPRESSED LENGTH", "Length Under Load" -- y
    no donde el resorte vive. Evaluar la tension ahi hace que todos salgan
    sobretensionados, asi que el comentario tiene que decirlo.
    """
    mejor = None
    for c in (spec.get("cargas") or []):
        if not isinstance(c, dict):
            continue
        L = _num(c.get("longitud_mm"))
        if L is None:
            continue
        if mejor is None or L < mejor[0]:
            mejor = (L, str(c.get("etiqueta") or "").strip())
    return mejor or (None, "")


_ENSAYO = ("max", "maximum", "compressed length", "under load", "test",
           "block", "solid")


def redactar(spec, tipo, verdicto, avisos=None):
    """-> lista de frases en INGLES para el comentario de factibilidad.

    Solo la mitad que sabe el lector: como se obtuvieron los datos y que no se
    pudo comprobar. La otra mitad -- las banderas de diseno -- la anade la
    calculadora, que es quien las calcula.
    """
    lineas = []

    # como se obtuvieron las espiras
    for a in (avisos or []):
        t = a if isinstance(a, str) else str(a.get("text", ""))
        if t.startswith("COILS COMPUTED"):
            lineas.append("Coil count was computed from the rate stated on the "
                          "drawing, not counted on the view: the drawing does "
                          "not state it.")
        elif t.startswith("END TYPE ASSUMED"):
            lineas.append("End type is not stated on the drawing; squared and "
                          "ground was assumed. It affects the solid height and "
                          "the buckling margin, and it implies a grinding "
                          "operation that the drawing does not actually call "
                          "for - confirm before pricing. It does not affect "
                          "the rate or the weight.")

    if tipo != "compresion":
        return lineas

    h, etiqueta = _punto_de_trabajo(spec)
    if h is None:
        # Sin punto de trabajo la nota sube porque no hay nada que penalizar.
        # Callarlo haria que un 100 pareciera un resorte impecable.
        lineas.append("The drawing gives no working point, so working stress, "
                      "buckling and set at solid were NOT evaluated. Any "
                      "manufacturability score reflects geometry and "
                      "coilability only.")
    elif any(p in etiqueta.lower() for p in _ENSAYO):
        lineas.append("Stress and buckling were evaluated at %.2f mm, the most "
                      "demanding point on the drawing (\"%s\"). That reads as a "
                      "test condition rather than a service point, so the "
                      "margins below are worst case."
                      % (h, etiqueta[:48]))
    return lineas
