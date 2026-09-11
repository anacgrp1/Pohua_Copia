"""Normalizacion del spec despues de extraer.

Un prompt es una peticion, no una garantia: aunque se le diga al modelo como
debe escribir un campo, hay que asegurarlo en codigo. Aqui se arreglan las
ambiguedades que se han visto en planos reales.
"""

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


def aplicar(spec):
    """Todas las normalizaciones. -> lista de avisos para el usuario."""
    avisos = []
    n = signos_tolerancia(spec) + tolerancias_de_carga(spec)
    if n:
        avisos.append(
            "%d tolerances came back from the model with a negative sign and "
            "were normalised (they are always stored as a positive magnitude)."
            % n)
    return avisos
