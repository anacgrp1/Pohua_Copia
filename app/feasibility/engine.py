"""COT-75 [Lógica] Motor de factibilidad: resorte extraído vs. directrices.

Propósito
---------
Comparar las variables que entrega ``extractor_resorte`` (COT-69) contra las
directrices cargadas por ``reglas_factibilidad`` (COT-74) y devolver:

    {"veredicto": "feasible" | "requires review", "motivos": [...]}

Alcance
-------
* **Sí hace:** dictaminar con las reglas vigentes y explicar por qué, campo
  por campo.
* **NO hace:** leer la BD, mandar correos ni decidir el estado del RFQ. Es
  una función pura: mismos datos + mismas reglas = mismo veredicto. Quien la
  llame (COT-72 / COT-36) decide qué hacer con el resultado.

Dos veredictos, no tres
-----------------------
COT-75 define exactamente dos salidas: ``feasible`` y ``requires review``. El
sistema no declina por su cuenta.

Cómo se elige entre las dos (modelo de ISC)
-------------------------------------------
Cada hallazgo resta puntos de 100 y el resultado se compara contra un umbral,
igual que el Spring Engineering Calculator de la planta. Es factible cuando se
cumplen **las dos** condiciones:

* Ningún hallazgo ``crit`` — son límites duros (el alambre de 15 mm que el
  negocio marca "do not price", un tipo que no se fabrica, un material fuera
  de catálogo). No se compensan con que el resto esté bien.
* Score en el umbral o por encima — 70, que es donde ISC pone la frontera
  entre ``Manufacturable`` y ``Engineering review``.

Así un aviso suelto ya no manda un RFQ al PM, pero tres sí. Las
penalizaciones, las bandas y el umbral viven en el archivo de directrices
(COT-74): ajustar la severidad no toca código. Si el archivo no trae modelo de
puntuación, se cae al criterio anterior — cualquier hallazgo va a revisión.

Regla de negocio (definida por el equipo, 20/ago/26)
----------------------------------------------------
Cuando el sistema detecta que un RFQ no es factible, el RFQ **pasa a revisión
del plant manager**, y es él quien dictamina si es factible o no. Si el PM
resuelve que no lo es, **entonces sí** se le manda al cliente el correo
diciendo que el RFQ no es factible.

De ahí el circuito completo::

    motor (aquí)          -> rfqs.veredicto_sistema = "requires review"
    plant manager (COT-31/COT-77) -> rfqs.veredicto_final
        "feasible"      -> el RFQ sigue a cotización
        "not feasible"  -> templates.construir_correo("declinar_rfq", ...)

El motor no emite nunca ``not feasible`` ni construye ese correo: sólo deja
los motivos para que el PM decida con ellos a la vista. Las constantes
``FINAL_*`` están abajo para que la pantalla del PM y este módulo hablen el
mismo vocabulario, porque ``rfqs.veredicto_final`` es ``text`` sin CHECK.

Dato ausente ≠ dato fuera de rango
----------------------------------
Un plano al que no se le pudo leer la longitud libre **no es infactible**: es
un plano incompleto. Los dos casos mandan el RFQ a revisión, pero con
``codigo`` y ``nivel`` distintos, para que el PM (COT-77) distinga de un
vistazo "no lo podemos hacer" de "no lo pudimos leer".

Vocabulario de salida
---------------------
* ``veredicto`` va a ``rfqs.veredicto_sistema`` (migración 004). El PM
  resuelve ``rfqs.veredicto_final``.
* ``score`` va a ``rfqs.score``, y ``banda`` viaja en ``datos_json``. Se
  calculan con el mismo modelo que produjo los scores históricos de esa
  columna, así que las filas nuevas se pueden comparar con las migradas.
* ``nivel`` de cada motivo usa ``ok``/``info``/``warn``/``crit``, que es el
  CHECK de ``rfq_banderas.nivel`` (migración 005): cada motivo se puede
  insertar tal cual como bandera del RFQ. Es, además, el mismo vocabulario
  que ya usan las banderas del Spring Engineering Calculator de ISC.

**Ojo al consultar** ``rfqs.veredicto_sistema``: las filas históricas que
migró ``02_migrate.py`` no traen ``feasible``/``requires review``, sino la
banda del modelo ISC (``Easy to manufacture``, ``Engineering review``,
``Not recommended``…). Conviven dos vocabularios en la misma columna hasta
que se decida unificarlos.

Función pública
---------------
``evaluar_factibilidad(resorte, reglas=None) -> dict``
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import app.feasibility.rules as rules

log = logging.getLogger("cotizador.factibilidad")

# --- Veredicto del sistema (contrato de COT-75) ---------------------------- #
# Lo que emite este módulo. Va a `rfqs.veredicto_sistema`.
VEREDICTO_FACTIBLE = "feasible"
VEREDICTO_REVISION = "requires review"

# --- Veredicto final: lo dicta el plant manager, no el sistema ------------- #
# Va a `rfqs.veredicto_final`. Este módulo NUNCA los emite; están aquí para
# que la pantalla del PM (COT-31/COT-77) escriba el mismo vocabulario.
# `FINAL_NO_FACTIBLE` es lo único que dispara el correo de declinación al
# cliente (`templates.declinar_rfq`, COT-59).
FINAL_FACTIBLE = "feasible"
FINAL_NO_FACTIBLE = "not feasible"

# --- Niveles, alineados con el CHECK de rfq_banderas.nivel ----------------- #
NIVEL_INFO = "info"
NIVEL_WARN = "warn"
NIVEL_CRIT = "crit"

# --- Códigos de motivo ------------------------------------------------------ #
TIPO_DESCONOCIDO = "tipo_desconocido"
TIPO_NO_FABRICABLE = "tipo_no_fabricable"
MATERIAL_AUSENTE = "material_ausente"
MATERIAL_NO_SOPORTADO = "material_no_soportado"
MATERIAL_FUERA_DE_RANGO = "material_fuera_de_rango"
DATO_AUSENTE = "dato_ausente"
DATO_NO_NUMERICO = "dato_no_numerico"
FUERA_DE_RANGO = "fuera_de_rango"
FUERA_DEL_PREFERIDO = "fuera_del_preferido"
TOLERANCIA_MAS_FINA = "tolerancia_mas_fina"
CONFIANZA_BAJA = "confianza_baja"

# Campo calculado, no viene del extractor: C = Dm / d.
INDICE_RESORTE = "indice_resorte"

_TIPO_DESCONOCIDO = "desconocido"

# Etiquetas legibles para el texto de los motivos.
_ETIQUETAS = {
    "diametro_alambre_mm": "diámetro de alambre",
    "diametro_exterior_mm": "diámetro exterior",
    "diametro_interior_mm": "diámetro interior",
    "diametro_medio_mm": "diámetro medio",
    "longitud_libre_mm": "longitud libre",
    "longitud_cuerpo_mm": "longitud del cuerpo",
    "numero_espiras_totales": "número de espiras",
    "numero_espiras_activas": "espiras activas",
    "angulo_brazos_grados": "ángulo entre brazos",
    "longitud_gancho_mm": "longitud del gancho",
    "constante_resorte_N_mm": "constante del resorte",
    "material": "material",
    INDICE_RESORTE: "índice del resorte (Dm/d)",
}

_UNIDADES = {
    "diametro_alambre_mm": "mm", "diametro_exterior_mm": "mm",
    "diametro_interior_mm": "mm", "diametro_medio_mm": "mm",
    "longitud_libre_mm": "mm", "longitud_cuerpo_mm": "mm",
    "longitud_gancho_mm": "mm", "angulo_brazos_grados": "°",
    "numero_espiras_totales": "espiras", "numero_espiras_activas": "espiras",
}


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #

def evaluar_factibilidad(resorte, reglas=None) -> dict:
    """Dictamina la factibilidad de un resorte contra las directrices.

    Args:
        resorte: dict de ``ResorteCotizacion.to_dict()`` (o el propio objeto,
            o el dict fusionado de ``flow.fusionar``).
        reglas: ``Reglas`` ya cargadas. Por defecto, las del archivo vigente.

    Returns:
        ``{"veredicto", "score", "banda", "motivos", "reglas_version",
        "tipo_resorte"}``. ``motivos`` es una lista de dicts
        ``{codigo, nivel, campo, valor, limite, texto, nota, penalizacion}``,
        vacía si el resorte no tiene un solo hallazgo. ``score`` y ``banda``
        van en ``None`` si las directrices no traen modelo de puntuación.

    Raises:
        ReglasInvalidasError: si no se pudieron cargar las directrices. No se
            silencia: sin reglas no hay veredicto que dar, y devolver
            "factible" por defecto sería peor que fallar.
    """
    datos = _a_dict(resorte)
    reglas = reglas or rules.cargar_reglas()

    tipo, motivos = _evaluar_tipo(datos, reglas)
    motivos += _evaluar_material(datos, reglas)
    motivos += _evaluar_rangos(datos, reglas, tipo)
    motivos += _evaluar_tolerancias(datos, reglas)
    motivos += _evaluar_confianza(datos, reglas)
    _puntuar(motivos, reglas)

    score = calcular_score(motivos) if reglas.puntua else None
    banda = reglas.banda(score)
    veredicto = _dictaminar(motivos, score, reglas)

    log.info("Factibilidad: %s (score=%s %s, tipo=%s, motivos=%d, reglas=%s)",
             veredicto, score, banda or "-", tipo or _TIPO_DESCONOCIDO,
             len(motivos), reglas.version)
    return {
        "veredicto": veredicto,
        "score": score,
        "banda": banda,
        "motivos": motivos,
        "reglas_version": reglas.version,
        "tipo_resorte": tipo,
    }


def calcular_score(motivos) -> int:
    """100 menos la suma de las penalizaciones, acotado a 0-100.

    Es el modelo del Spring Engineering Calculator de ISC, que es también el
    que produjo los scores históricos de ``rfqs.score``: calcularlo distinto
    haría incomparables las filas nuevas con las migradas.
    """
    penalizacion = sum(float(m.get("penalizacion") or 0) for m in motivos)
    return max(0, min(100, round(100 - penalizacion)))


def _dictaminar(motivos, score, reglas) -> str:
    """Traduce hallazgos y score a uno de los dos veredictos de COT-75.

    Dos condiciones, y las dos tienen que cumplirse para dar por factible:

    * **Ningún hallazgo ``crit``.** Son límites duros — el alambre de 15 mm
      que el negocio marca como "do not price", un tipo que la planta no
      fabrica, un material que no existe en su catálogo. No se compensan
      teniendo todo lo demás bien, así que no entran al juego de sumar puntos.
    * **Score en el umbral o por encima** (70 = banda ``Manufacturable`` de
      ISC). Debajo de eso su propia banda se llama "Engineering review", que
      es exactamente lo que hacemos: mandarlo al plant manager.

    Sin modelo de puntuación en las directrices se cae al criterio anterior:
    cualquier hallazgo manda a revisión.
    """
    if any(motivo["nivel"] == NIVEL_CRIT for motivo in motivos):
        return VEREDICTO_REVISION
    if not reglas.puntua:
        return VEREDICTO_FACTIBLE if not motivos else VEREDICTO_REVISION
    return (VEREDICTO_FACTIBLE if score >= reglas.umbral_factible
            else VEREDICTO_REVISION)


def es_factible(resultado: dict) -> bool:
    """Azúcar para los llamadores: ``True`` si el veredicto fue ``feasible``."""
    return resultado.get("veredicto") == VEREDICTO_FACTIBLE


def resumen(resultado: dict) -> str:
    """Una línea por motivo, para el log o para el correo al PM."""
    if not resultado.get("motivos"):
        return "Sin observaciones."
    return "\n".join(f"- [{m['nivel']}] {m['texto']}" for m in resultado["motivos"])


# --------------------------------------------------------------------------- #
# Comprobaciones
# --------------------------------------------------------------------------- #

def _evaluar_tipo(datos, reglas):
    """El tipo manda: define qué rangos y qué campos requeridos aplican."""
    crudo = datos.get("tipo_resorte")
    tipo = str(crudo).strip() if crudo not in (None, "") else _TIPO_DESCONOCIDO

    if reglas.tipo_fabricable(tipo):
        return tipo, []

    if tipo.lower() == _TIPO_DESCONOCIDO:
        motivo = _motivo(
            TIPO_DESCONOCIDO, NIVEL_WARN, "tipo_resorte", crudo, None,
            "No se pudo determinar el tipo de resorte; se evalúa sólo con los "
            "rangos comunes.")
    else:
        motivo = _motivo(
            TIPO_NO_FABRICABLE, NIVEL_CRIT, "tipo_resorte", crudo,
            list(reglas.tipos_fabricables),
            f"Tipo de resorte no fabricable: {crudo!r}. La planta fabrica "
            f"{', '.join(reglas.tipos_fabricables)}.")
    # Sin tipo válido se sigue evaluando con `_comun`: si además el alambre
    # está fuera de rango, el PM merece verlo en el mismo dictamen.
    return None, [motivo]


def _evaluar_material(datos, reglas):
    crudo = datos.get("material")
    if crudo in (None, "") or not str(crudo).strip():
        return [_motivo(MATERIAL_AUSENTE, NIVEL_WARN, "material", crudo, None,
                        "El plano no declara material.")]

    canonico = reglas.material_soportado(crudo)
    if canonico is None:
        return [_motivo(
            MATERIAL_NO_SOPORTADO, NIVEL_CRIT, "material", crudo,
            list(reglas.materiales),
            f"Material no soportado: {crudo!r}. No coincide con ninguno de los "
            f"{len(reglas.materiales)} materiales de la planta.")]

    # El alambre se compra en ciertos calibres: fuera de ellos, el material
    # existe pero no en ese diámetro. Es aviso, no impedimento: lo confirma
    # el proveedor de alambre.
    banda = reglas.rango_alambre_material(canonico)
    valor = _a_float(datos.get("diametro_alambre_mm"))
    lado = (_lado_fuera(valor, banda.get("min"), banda.get("max"))
            if banda and valor is not None else None)
    if lado:
        texto_banda = _texto_banda("diametro_alambre_mm", banda.get("min"),
                                   banda.get("max"))
        return [_motivo(
            MATERIAL_FUERA_DE_RANGO, NIVEL_WARN, "diametro_alambre_mm", valor,
            texto_banda,
            f"El alambre de {_fmt(valor)} mm queda fuera de los calibres en que "
            f"se consigue {canonico} ({texto_banda}).",
            nota=banda.get("nota"),
            penalizacion=reglas.penalizacion(MATERIAL_FUERA_DE_RANGO, banda, lado))]
    return []


def _evaluar_rangos(datos, reglas, tipo):
    """Compara cada variable numérica contra su rango, y avisa de las ausentes."""
    motivos = []
    rangos = reglas.rangos(tipo)
    requeridos = reglas.requeridos(tipo)

    # El índice del resorte no lo entrega el extractor: se calcula si hay con qué.
    calculados = {INDICE_RESORTE: _indice_resorte(datos)}

    for campo, limites in rangos.items():
        crudo = calculados.get(campo, datos.get(campo))
        valor = _a_float(crudo)

        if valor is None:
            if campo in requeridos:
                codigo = DATO_NO_NUMERICO if crudo not in (None, "") else DATO_AUSENTE
                motivos.append(_motivo(
                    codigo, NIVEL_WARN, campo, crudo, _texto_limite(campo, limites),
                    f"Falta {_etiqueta(campo)} para dictaminar."
                    if codigo == DATO_AUSENTE else
                    f"{_Etiqueta(campo)} no es un número: {crudo!r}.",
                    penalizacion=reglas.penalizacion(codigo, limites)))
            continue

        # Dos bandas: fuera de la fabricable no se puede; entre la fabricable y
        # la preferida se puede, pero no sin que alguien lo mire.
        lado = _lado_fuera(valor, limites.get("min"), limites.get("max"))
        if lado:
            banda = _texto_banda(campo, limites.get("min"), limites.get("max"))
            motivos.append(_motivo(
                FUERA_DE_RANGO, NIVEL_CRIT, campo, valor, banda,
                f"{_Etiqueta(campo)} fuera de rango: "
                f"{_fmt(valor)}{_unidad(campo)} (fabricable {banda}).",
                nota=limites.get("nota"),
                penalizacion=reglas.penalizacion(FUERA_DE_RANGO, limites, lado)))
            continue

        lado = _lado_fuera(valor, limites.get("preferido_min"),
                           limites.get("preferido_max"))
        if lado:
            banda = _texto_banda(campo, limites.get("preferido_min"),
                                 limites.get("preferido_max"))
            motivos.append(_motivo(
                FUERA_DEL_PREFERIDO, NIVEL_WARN, campo, valor, banda,
                f"{_Etiqueta(campo)} en {_fmt(valor)}"
                f"{_unidad(campo)}: fabricable, pero fuera del rango habitual "
                f"({banda}).",
                nota=limites.get("nota"),
                penalizacion=reglas.penalizacion(FUERA_DEL_PREFERIDO, limites, lado)))

    # Requeridos que no tienen rango declarado (p. ej. `material` ya se revisó
    # aparte): sólo se comprueba que estén.
    for campo in requeridos:
        if campo in rangos or campo == "material":
            continue
        if datos.get(campo) in (None, ""):
            motivos.append(_motivo(
                DATO_AUSENTE, NIVEL_WARN, campo, None, None,
                f"Falta {_etiqueta(campo)} para dictaminar."))

    return motivos


def _evaluar_tolerancias(datos, reglas):
    """Una tolerancia más fina que la de la planta no se puede garantizar."""
    minima = reglas.tolerancia_minima_mm
    if minima is None:
        return []

    declarada = _tolerancia_declarada(datos.get("tolerancias"))
    if declarada is None or declarada >= minima:
        return []

    return [_motivo(
        TOLERANCIA_MAS_FINA, NIVEL_CRIT, "tolerancias", declarada, minima,
        f"El plano pide ±{_fmt(declarada)} mm y la tolerancia mínima de la "
        f"planta es ±{_fmt(minima)} mm.")]


def _evaluar_confianza(datos, reglas):
    """Un dictamen sobre una lectura dudosa no vale: que lo confirme el PM.

    El umbral sale de las directrices (``confianza_minima``), no de
    ``config.UMBRAL_CONFIANZA``, aunque hoy los dos valgan 0.7. Son decisiones
    distintas: config decide **qué campos acepta la extracción del correo**
    (COT-61) y éste decide **cuánto pesa una lectura dudosa en el dictamen**.
    Que coincidan es casualidad, y acoplarlos impediría afinar uno sin mover
    el otro.
    """
    umbral = reglas.confianza_minima
    confianza = _a_float(datos.get("confianza"))
    if umbral is None or confianza is None or confianza >= umbral:
        return []
    return [_motivo(
        CONFIANZA_BAJA, NIVEL_WARN, "confianza", confianza, umbral,
        f"La extracción del plano quedó en {_fmt(confianza)} de confianza, por "
        f"debajo del mínimo de {_fmt(umbral)}.")]


# --------------------------------------------------------------------------- #
# Auxiliares
# --------------------------------------------------------------------------- #

def _a_dict(resorte) -> dict:
    """Acepta el dict del extractor, el dict fusionado o el propio dataclass."""
    if resorte is None:
        return {}
    if isinstance(resorte, dict):
        # `flow.fusionar` deja el resorte anidado bajo "resorte".
        anidado = resorte.get("resorte")
        if isinstance(anidado, dict) and "tipo_resorte" in anidado:
            return anidado
        return resorte
    if hasattr(resorte, "to_dict"):
        return resorte.to_dict()
    raise TypeError(
        "evaluar_factibilidad espera un dict o un objeto con to_dict(); "
        f"llegó {type(resorte).__name__}.")


def _indice_resorte(datos) -> Optional[float]:
    """C = Dm / d. Si no vino Dm, se deduce del exterior o del interior."""
    d = _a_float(datos.get("diametro_alambre_mm"))
    if not d:
        return None
    dm = _a_float(datos.get("diametro_medio_mm"))
    if dm is None:
        exterior = _a_float(datos.get("diametro_exterior_mm"))
        interior = _a_float(datos.get("diametro_interior_mm"))
        if exterior is not None:
            dm = exterior - d
        elif interior is not None:
            dm = interior + d
    if dm is None or dm <= 0:
        return None
    return dm / d


_NUMERO_TOLERANCIA = re.compile(
    r"(?:±|\+\s*/\s*-|\+/-|\+-)\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)
_PULGADAS = re.compile(r"(?:\bin\b|\binch\b|\bpulg|\")", re.IGNORECASE)


def _tolerancia_declarada(texto) -> Optional[float]:
    """La tolerancia más estrecha declarada en el plano, en mm.

    Sólo interpreta valores marcados con ±: un número suelto en ese campo
    puede ser cualquier cosa. Si el plano viene en pulgadas se ignora, porque
    compararlo contra un mínimo en mm daría un falso "más fina" — queda como
    limitación conocida hasta que COT-73 defina la conversión.
    """
    if not texto or not str(texto).strip():
        return None
    crudo = str(texto)
    if _PULGADAS.search(crudo):
        return None
    valores = [float(m.replace(",", ".")) for m in _NUMERO_TOLERANCIA.findall(crudo)]
    valores = [v for v in valores if v > 0]
    return min(valores) if valores else None


def _a_float(valor) -> Optional[float]:
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace(",", ".")
    if not texto:
        return None
    encontrado = re.search(r"-?\d+(?:\.\d+)?", texto)
    return float(encontrado.group()) if encontrado else None


def _lado_fuera(valor, minimo, maximo) -> Optional[str]:
    """Qué lado de la banda se violó: ``"min"``, ``"max"`` o ``None``.

    Hace falta el lado, y no sólo el sí/no, porque ISC cobra distinto cada
    extremo: un índice de resorte por debajo de 4 castiga más que uno por
    encima de 15, y por buenas razones de taller (enrollar apretado castiga
    el herramental; enrollar flojo sólo da una espira inconsistente).
    """
    if minimo is not None and valor < float(minimo):
        return "min"
    if maximo is not None and valor > float(maximo):
        return "max"
    return None


def _fuera_de_banda(valor, minimo, maximo) -> bool:
    """``True`` si el valor cae fuera de una banda; una banda sin límites no acota."""
    return _lado_fuera(valor, minimo, maximo) is not None


def _motivo(codigo, nivel, campo, valor, limite, texto, nota=None,
            penalizacion=None) -> dict:
    """Un motivo del dictamen.

    ``texto`` es la línea corta que va a ``rfq_banderas.titulo``; ``nota`` es
    la explicación larga que trae el archivo de directrices ("de dónde sale
    este límite") y viaja aparte, en ``datos_json``, para no inflar el título.
    ``penalizacion`` son los puntos que resta del score; se rellena después
    para los motivos que no la traen (ver ``_puntuar``).
    """
    return {
        "codigo": codigo,
        "nivel": nivel,
        "campo": campo,
        "valor": valor,
        # La unidad del campo, para que quien rearme la frase en otro idioma
        # no tenga que llevar una copia de la tabla de unidades. Va con el
        # espacio delante, como se escribe: " mm".
        "unidad": _unidad(campo),
        "limite": limite,
        "texto": texto,
        "nota": nota,
        "penalizacion": penalizacion,
    }


def _puntuar(motivos, reglas):
    """Completa la penalización de los motivos que no la traen ya calculada.

    Los de rango la calculan ellos, porque su rango puede declarar una tabla
    propia; el resto usa la general de las directrices.
    """
    for motivo in motivos:
        if motivo.get("penalizacion") is None:
            motivo["penalizacion"] = reglas.penalizacion(motivo["codigo"])
    return motivos


def _etiqueta(campo: str) -> str:
    return _ETIQUETAS.get(campo, campo.replace("_", " "))


def _Etiqueta(campo: str) -> str:
    """La etiqueta con la inicial en mayúscula, sin tocar el resto.

    `str.capitalize()` no sirve: baja el resto de la cadena y deja
    "índice del resorte (dm/d)" en vez de "(Dm/d)".
    """
    texto = _etiqueta(campo)
    return texto[:1].upper() + texto[1:]


def _unidad(campo: str) -> str:
    unidad = _UNIDADES.get(campo, "")
    return f" {unidad}" if unidad else ""


def _texto_limite(campo: str, limites: dict) -> str:
    """Banda fabricable del campo; si sólo hay banda preferida, ésa."""
    texto = _texto_banda(campo, limites.get("min"), limites.get("max"))
    if texto:
        return texto
    return _texto_banda(campo, limites.get("preferido_min"),
                        limites.get("preferido_max"))


def _texto_banda(campo: str, minimo, maximo) -> str:
    unidad = _unidad(campo)
    if minimo is not None and maximo is not None:
        return f"{_fmt(minimo)}–{_fmt(maximo)}{unidad}"
    if minimo is not None:
        return f"≥ {_fmt(minimo)}{unidad}"
    if maximo is not None:
        return f"≤ {_fmt(maximo)}{unidad}"
    return ""


def _fmt(valor) -> str:
    numero = float(valor)
    texto = f"{numero:.2f}".rstrip("0").rstrip(".")
    return texto or "0"
