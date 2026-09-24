"""Normalizacion del spec despues de extraer.

Un prompt es una peticion, no una garantia: aunque se le diga al modelo como
debe escribir un campo, hay que asegurarlo en codigo. Aqui se arreglan las
ambiguedades que se han visto en planos reales.
"""

import re

CLAVES_TOLERANCIA = ("tolerancia_mas", "tolerancia_menos")


def _es_cota(d):
    return isinstance(d, dict) and any(
        k in d for k in ("nominal", "valor_maximo", "valor_minimo", "texto_original"))


def signos_tolerancia(spec):
    """`tolerancia_mas` y `tolerancia_menos` son MAGNITUDES, siempre positivas.

    El plano dice "25.6 +0.2/-0.1"; eso se guarda como
    tolerancia_mas: 0.2, tolerancia_menos: 0.1.
    El limite inferior es SIEMPRE nominal - tolerancia_menos.

    Sin esto, un modelo que escriba -0.1 hace que quien calcule
    nominal - tolerancia_menos obtenga 25.7 en vez de 25.5: la banda al reves.
    -> numero de valores corregidos
    """
    corregidos = [0]

    def recorrer(obj):
        if isinstance(obj, dict):
            if _es_cota(obj):
                for k in CLAVES_TOLERANCIA:
                    v = obj.get(k)
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and v < 0:
                        obj[k] = abs(v)
                        corregidos[0] += 1
            for v in obj.values():
                recorrer(v)
        elif isinstance(obj, list):
            for v in obj:
                recorrer(v)

    recorrer(spec)
    return corregidos[0]


def tolerancias_de_carga(spec):
    """Misma regla para las tolerancias de los puntos de carga."""
    corregidos = 0
    for c in spec.get("cargas") or []:
        if not isinstance(c, dict):
            continue
        for k in ("tolerancia_fuerza_absoluta_N", "tolerancia_fuerza_pct",
                  "tolerancia_torque_absoluta_Nmm", "tolerancia_torque_pct"):
            v = c.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v < 0:
                c[k] = abs(v)
                corregidos += 1
    return corregidos


# --- planos en pulgadas ------------------------------------------------------
#
# El esquema pide milimetros (las formulas del resorte los exigen) y el modelo
# convierte las pulgadas del plano por su cuenta, REDONDEANDO: ".039 in" llega
# como 0.991 mm (0.039 x 25.4 = 0.9906) y ".562" como 14.275 (14.2748). De
# vuelta a pulgadas eso da 0.039016 y 0.562008: milesimas que el plano no dice
# y que se arrastran al peso, al indice y al precio.
#
# Aqui se devuelve cada valor a la cota EXACTA del plano. Solo si el plano esta
# en pulgadas y solo si la diferencia cabe en el redondeo que hizo el modelo
# (media unidad del ultimo decimal que escribio): un valor que de verdad no es
# una cota del plano no se toca.

_NUMERO = re.compile(r"(?<![\d.])(\d*\.\d+|\d+)(?:\s*/\s*(\d+)(?![\d.]))?")
_PULGADAS = re.compile(r"\(\s*in\s*\)|\bin\b|\binch(es)?\b|\"", re.I)
_MM = re.compile(r"\bmm\b", re.I)
_CLAVES_COTA = ("nominal", "valor_maximo", "valor_minimo") + CLAVES_TOLERANCIA
_DENOMINADORES = (2, 4, 8, 16, 32, 64)
MM_POR_PULGADA = 25.4


def _textos(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _textos(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _textos(v)


def plano_en_pulgadas(spec):
    """True si el plano esta acotado en pulgadas."""
    ident = spec.get("identificacion") or {}
    u = str(ident.get("unidad_dimensional") or "").strip().lower()
    if u in ("in", "inch", "inches", "pulgadas", "pulg", '"'):
        return True
    if u in ("mm", "milimetros", "millimeters", "metric"):
        return False
    pulgadas = milimetros = 0

    def contar(obj):
        nonlocal pulgadas, milimetros
        if isinstance(obj, dict):
            t = obj.get("texto_original") if _es_cota(obj) else None
            if isinstance(t, str):
                i, m = _PULGADAS.search(t), _MM.search(t)
                if i and (not m or i.start() < m.start()):
                    pulgadas += 1
                elif m:
                    milimetros += 1
            for v in obj.values():
                contar(v)
        elif isinstance(obj, list):
            for v in obj:
                contar(v)

    contar(spec)
    return pulgadas > milimetros


def _cotas_del_plano(spec):
    """Los numeros escritos en el plano (en pulgadas), para ajustar a ellos."""
    vistos = set()
    for texto in _textos(spec):
        for m in _NUMERO.finditer(texto):
            try:
                v = float(m.group(1))
                if m.group(2):
                    b = int(m.group(2))
                    if b not in _DENOMINADORES or "." in m.group(1):
                        vistos.add(v)
                        continue
                    v = v / b
            except (ValueError, ZeroDivisionError):
                continue
            if 0 < v < 1000:
                vistos.add(v)
    return sorted(vistos)


def _decimales(v):
    t = repr(float(v))
    if "e" in t or "E" in t:
        return 6
    return len(t.split(".")[1].rstrip("0")) if "." in t else 0


def _ajustar(v, candidatas):
    """El valor en mm devuelto a la cota exacta en pulgadas, o None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
        return None
    k = _decimales(v)
    # Un entero no da un margen de medio milimetro: como mucho 0.05 mm.
    margen = 0.5 * 10 ** (-max(k, 1)) + 1e-9
    mejor = None
    for c in candidatas:
        d = abs(c * MM_POR_PULGADA - v)
        if d <= margen and (mejor is None or d < mejor[0]):
            mejor = (d, c)
    if mejor is None and k >= 2:
        # Sin el texto a mano: la milesima de pulgada mas cercana. Con dos o
        # mas decimales el margen (<= 0.005 mm) es menor que media milesima
        # (0.0127 mm), asi que solo puede haber una.
        c = round(v / MM_POR_PULGADA, 3)
        if abs(c * MM_POR_PULGADA - v) <= margen:
            mejor = (0, c)
    if mejor is None:
        return None
    exacto = round(mejor[1] * MM_POR_PULGADA, 6)
    return exacto if exacto != v else None


def cotas_en_pulgadas(spec):
    """Deshace el redondeo del modelo en planos en pulgadas. -> n ajustados."""
    if not isinstance(spec, dict) or not plano_en_pulgadas(spec):
        return 0
    candidatas = _cotas_del_plano(spec)
    ajustados = [0]

    def poner(obj, clave):
        nuevo = _ajustar(obj.get(clave), candidatas)
        if nuevo is not None:
            obj[clave] = nuevo
            ajustados[0] += 1

    def recorrer(obj, en_mm):
        if isinstance(obj, dict):
            if en_mm and _es_cota(obj):
                for k in _CLAVES_COTA:
                    poner(obj, k)
            for k, v in list(obj.items()):
                es_mm = en_mm or (isinstance(k, str) and k.endswith("_mm"))
                if isinstance(k, str) and k.endswith("_mm") and not isinstance(v, (dict, list)):
                    poner(obj, k)
                else:
                    recorrer(v, es_mm)
        elif isinstance(obj, list):
            for v in obj:
                recorrer(v, en_mm)

    recorrer(spec, False)
    return ajustados[0]


def aplicar(spec):
    """Todas las normalizaciones. -> lista de avisos para el usuario."""
    avisos = []
    n = signos_tolerancia(spec) + tolerancias_de_carga(spec)
    # Sin aviso: no cambia ninguna cota, solo quita el redondeo del modelo.
    cotas_en_pulgadas(spec)
    if n:
        avisos.append(
            "%d tolerances came back from the model with a negative sign and "
            "were normalised (they are always stored as a positive magnitude)."
            % n)
    return avisos
