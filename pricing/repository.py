"""Lectura del catálogo de costeo desde PostgreSQL.

Sustituye a los valores que estaban escritos a mano en ``rodea_adapter.py``
(precio de alambre 2.50 USD/lb, máquina «AIM 3000», setup 6 h, 327 pph…), que
se aplicaban a cualquier resorte viniera como viniera.

Todo sale de las tablas de la migración 005:

===========================  ==================================================
``param_juegos`` / ``param_valores``   parámetros del motor, versionados por fecha
``maquinas`` / ``maquina_capacidades`` / ``maquina_tarifas``   ruta y tarifa
``materiales`` / ``material_precios`` / ``aleacion_surcharges``  costo del alambre
``empaques``                           costo y piezas por caja
===========================  ==================================================

Regla de oro de este módulo: **nunca inventa un número**. Si un dato no está en
el catálogo, se devuelve ``None`` y el nombre del dato se acumula en la lista
de faltantes, para que la respuesta de la API pueda decir que ese precio no
está completo en vez de aparentar que sí.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

import app.persistence.duplicates as duplicates
import pricing.mensajes as mensajes

log = logging.getLogger("cotizador.pricing.repository")

# Tipo de resorte → columna de capacidad de la máquina.
_CAPACIDAD_POR_TIPO = {
    "compresion": "hace_compresion",
    "compression": "hace_compresion",
    "extension": "hace_extension",
    "tension": "hace_extension",
    "torsion": "hace_torsion",
}


@contextmanager
def _conexion(conexion=None):
    if conexion is not None:
        yield conexion
        return
    with duplicates.conexion_bd() as conn:
        yield conn


@dataclass
class Catalogo:
    """Lo que se pudo leer del catálogo para un resorte concreto.

    ``faltantes`` es la parte importante: enumera en lenguaje llano qué dato no
    estaba en la base. Si tiene algo, el precio resultante es orientativo.
    """

    parametros: Dict[str, Any] = field(default_factory=dict)
    maquina: Optional[Dict[str, Any]] = None
    material: Optional[Dict[str, Any]] = None
    empaque: Optional[Dict[str, Any]] = None
    faltantes: List[str] = field(default_factory=list)
    # Los mismos motivos, con su código y sus datos, para que la web los
    # pueda decir en el idioma que tenga puesto (pricing/mensajes.py).
    faltantes_i18n: List[Dict[str, Any]] = field(default_factory=list)
    origen: Dict[str, str] = field(default_factory=dict)
    # Las bases que el motor busca por código dentro de cada tramo (hoy, las
    # cajas con su precio). Las llena el adaptador y viajan en
    # ``ctx_overrides.dbs``: el motor no trae catálogo propio.
    dbs_motor: Dict[str, Any] = field(default_factory=dict)

    @property
    def completo(self) -> bool:
        return not self.faltantes


# ---------------------------------------------------------------------------
# Parámetros del motor
# ---------------------------------------------------------------------------

_SQL_PARAMS = """
    SELECT pv.clave, pv.valor
    FROM param_valores pv
    JOIN param_juegos pj ON pj.id = pv.param_juego_id
    WHERE pj.vigente_desde <= %s
      AND (pj.vigente_hasta IS NULL OR pj.vigente_hasta > %s)
    ORDER BY pj.vigente_desde DESC;
"""


def parametros_vigentes(conexion=None, en_fecha: Optional[date] = None) -> Dict[str, Any]:
    """Parámetros del juego vigente (markups, escalera de overhead, pisos…).

    Si hay más de un juego vigente gana el más reciente: la consulta viene
    ordenada por ``vigente_desde`` descendente y se escribe en orden inverso.
    """
    hoy = en_fecha or date.today()
    valores: Dict[str, Any] = {}
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(_SQL_PARAMS, (hoy, hoy))
            filas = cur.fetchall()
    for clave, valor in reversed(filas):
        valores[clave] = valor
    return valores


# ---------------------------------------------------------------------------
# Máquina
# ---------------------------------------------------------------------------

_SQL_MAQUINA = """
    SELECT m.id, m.codigo, m.nombre, fm.codigo AS familia,
           m.horas_setup, m.pph_default, m.horas_labor,
           fm.multiplicador,
           t.costo_hora, t.ccv_objetivo_h
    FROM maquinas m
    JOIN familias_maquina fm ON fm.id = m.familia_id
    LEFT JOIN maquina_capacidades c ON c.maquina_id = m.id
    LEFT JOIN LATERAL (
        SELECT costo_hora, ccv_objetivo_h
        FROM maquina_tarifas mt
        WHERE mt.maquina_id = m.id
          AND mt.vigente_desde <= %(hoy)s
          AND (mt.vigente_hasta IS NULL OR mt.vigente_hasta > %(hoy)s)
        ORDER BY mt.vigente_desde DESC
        LIMIT 1
    ) t ON true
    WHERE m.activo
      AND fm.codigo = 'COILER'
      AND (%(diam)s IS NULL OR c.alambre_min_mm IS NULL OR c.alambre_min_mm <= %(diam)s)
      AND (%(diam)s IS NULL OR c.alambre_max_mm IS NULL OR c.alambre_max_mm >= %(diam)s)
      AND (%(od)s   IS NULL OR c.od_max_mm     IS NULL OR c.od_max_mm     >= %(od)s)
      AND ({capacidad} IS NOT false)
    ORDER BY
        -- Primero las máquinas cuyas capacidades están capturadas y encajan de
        -- verdad con este alambre. Ordenar sólo por costo hacía ganar siempre a
        -- las filas del catálogo legado sin capacidades: son las más baratas
        -- justamente porque nadie verificó que puedan hacer la pieza.
        (c.alambre_min_mm IS NOT NULL AND c.alambre_max_mm IS NOT NULL
         AND %(diam)s IS NOT NULL) DESC,
        ({capacidad} IS TRUE) DESC,
        -- Y entre las capaces, el ORDEN DE PREFERENCIA del taller, que es la
        -- regla que de verdad decide.
        --
        -- La columna la creó la migración 013 —"es LA regla que decide quién
        -- gana entre las máquinas capaces"— y se quedó sin llenar y sin usar,
        -- así que aquí mandaba el costo. Son dos reglas distintas y dan
        -- máquinas distintas: para el 004-222, por costo salía una que ni
        -- siquiera corre ese alambre, y por preferencia sale la TORIN W11A,
        -- que es la que dice la calculadora de la planta.
        --
        -- `NULLS LAST` deja detrás a las que no tienen puesto capturado: no
        -- se les inventa uno, van después de todas las que sí.
        m.orden_uso ASC NULLS LAST,
        t.costo_hora ASC NULLS LAST,
        m.horas_setup ASC
    LIMIT 1;
"""


def cajas(conexion=None) -> List[Dict[str, Any]]:
    """Las cajas activas del catálogo, con la forma que usa la regla de empaque.

    Es la misma lista que recibe la hoja (`pricing/proyeccion_hoja.py`), para
    que la caja que elige el servidor y la que elige la hoja salgan de las
    mismas filas.
    """
    from pricing import proyeccion_hoja
    try:
        with _conexion(conexion) as conn:
            with conn.cursor() as cur:
                return proyeccion_hoja.cajas(cur)
    except Exception as err:
        log.warning("No se pudieron leer las cajas del catálogo: %s", err)
        return []


_SQL_TIENE_TOPE = """
    SELECT count(*) FROM information_schema.columns
    WHERE table_name = 'maquinas'
      AND column_name IN ('tope_material', 'tope_alambre_max_mm');
"""


def tope_de_maquina(nombre: str, conexion=None) -> Optional[Dict[str, Any]]:
    """El tope por material de una máquina: ``{material, alambre_max_mm}``.

    Hay materiales que una máquina sólo dobla hasta un diámetro MENOR que el
    suyo. Lo contestó Miguel Rodea y hoy afecta a una: la SIMPLEX MC 50 llega a
    .198" de alambre, pero en temple en aceite sólo a .165".

    Devuelve None con dos significados distintos, y quien llama tiene que
    distinguirlos: ``{}`` es "esa máquina no tiene tope", y ``None`` es "no se
    pudo comprobar" —porque `maquinas` todavía no tiene las dos columnas—. Un
    "no se pudo comprobar" tratado como "no hay tope" es exactamente el fallo
    que esto viene a evitar.
    """
    if not nombre:
        return None
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(_SQL_TIENE_TOPE)
            if (cur.fetchone() or [0])[0] < 2:
                return None          # el esquema aún no las tiene
            cur.execute("SELECT tope_material, tope_alambre_max_mm "
                        "FROM maquinas WHERE nombre = %(nombre)s LIMIT 1;",
                        {"nombre": nombre})
            fila = cur.fetchone()
    if not fila or not fila[0] or fila[1] is None:
        return {}                    # existe, y no tiene tope
    return {"material": fila[0], "alambre_max_mm": _f(fila[1])}


_SQL_CAPACIDAD_DE = """
    SELECT c.alambre_min_mm, c.alambre_max_mm, c.od_max_mm
    FROM maquinas m
    LEFT JOIN maquina_capacidades c ON c.maquina_id = m.id
    WHERE m.nombre = %(nombre)s
    LIMIT 1;
"""


def capacidad_de_maquina(nombre: str, conexion=None) -> Optional[Dict[str, Any]]:
    """El rango de alambre y el OD máximo capturados para una máquina.

    ``None`` si no hay fila o no se capturó nada: "no lo sabemos", que NO es lo
    mismo que "no tiene límite".
    """
    if not nombre:
        return None
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(_SQL_CAPACIDAD_DE, {"nombre": nombre})
            fila = cur.fetchone()
    if not fila or all(v is None for v in fila):
        return None
    return {"alambre_min_mm": _f(fila[0]), "alambre_max_mm": _f(fila[1]),
            "od_max_mm": _f(fila[2])}


_SQL_MAQUINA_NOMBRE = """
    SELECT m.id, m.codigo, m.nombre, fm.codigo AS familia,
           m.horas_setup, m.pph_default, m.horas_labor,
           fm.multiplicador,
           t.costo_hora, t.ccv_objetivo_h
    FROM maquinas m
    JOIN familias_maquina fm ON fm.id = m.familia_id
    LEFT JOIN LATERAL (
        SELECT costo_hora, ccv_objetivo_h
        FROM maquina_tarifas mt
        WHERE mt.maquina_id = m.id
          AND mt.vigente_desde <= %(hoy)s
          AND (mt.vigente_hasta IS NULL OR mt.vigente_hasta > %(hoy)s)
        ORDER BY mt.vigente_desde DESC
        LIMIT 1
    ) t ON true
    WHERE m.activo AND m.nombre = %(nombre)s
    LIMIT 1;
"""


def maquina_por_nombre(nombre: str,
                       conexion=None,
                       en_fecha: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """Una máquina concreta, por su nombre, con su tarifa vigente.

    `elegir_maquina` busca la mejor para un resorte; esto es lo contrario: las
    reglas del taller dicen que hace falta "Grinder A" y aquí se trae esa fila.
    Devuelve None si no existe o está inactiva -- quien llama lo declara como
    dato faltante en vez de saltarse la operación en silencio.
    """
    if not nombre:
        return None
    hoy = en_fecha or date.today()
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(_SQL_MAQUINA_NOMBRE, {"hoy": hoy, "nombre": nombre})
            fila = cur.fetchone()
    if not fila:
        return None
    return {
        "id": fila[0], "codigo": fila[1], "nombre": fila[2], "familia": fila[3],
        "horas_setup": _f(fila[4]), "pph": _f(fila[5]), "horas_labor": _f(fila[6]),
        "multiplicador": _f(fila[7]),
        "costo_hora": _f(fila[8]), "ccv_objetivo_h": _f(fila[9]),
    }


def elegir_maquina(tipo_resorte: str,
                   diametro_alambre_mm: Optional[float] = None,
                   diametro_exterior_mm: Optional[float] = None,
                   conexion=None,
                   en_fecha: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """Máquina más barata capaz de hacer ese resorte, con su tarifa vigente.

    "Capaz" se mide contra ``maquina_capacidades``: rango de alambre, OD máximo
    y si la máquina hace ese tipo de resorte. Una capacidad ``NULL`` se trata
    como desconocida y no descarta la máquina (hay filas del catálogo legado sin
    capturar), pero un ``false`` explícito sí.
    """
    columna = _CAPACIDAD_POR_TIPO.get((tipo_resorte or "").strip().lower(), "hace_compresion")
    sql = _SQL_MAQUINA.format(capacidad=f"c.{columna}")
    hoy = en_fecha or date.today()

    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"hoy": hoy,
                              "diam": diametro_alambre_mm,
                              "od": diametro_exterior_mm})
            fila = cur.fetchone()

    if not fila:
        return None
    return {
        "id": fila[0], "codigo": fila[1], "nombre": fila[2], "familia": fila[3],
        "horas_setup": _f(fila[4]), "pph": _f(fila[5]), "horas_labor": _f(fila[6]),
        "multiplicador": _f(fila[7]),
        "costo_hora": _f(fila[8]), "ccv_objetivo_h": _f(fila[9]),
    }


# ---------------------------------------------------------------------------
# Material
# ---------------------------------------------------------------------------

_SQL_MATERIAL = """
    SELECT m.id, m.codigo, m.nombre, m.lleva_surcharge,
           mp.precio_lb, mp.diam_pulg, mp.fecha_cotizado
    FROM materiales m
    LEFT JOIN LATERAL (
        SELECT precio_lb, diam_pulg, fecha_cotizado
        FROM material_precios p
        WHERE p.material_id = m.id
        ORDER BY abs(p.diam_pulg - %(diam_pulg)s) ASC, p.fecha_cotizado DESC
        LIMIT 1
    ) mp ON true
    WHERE m.activo AND upper(m.codigo) = upper(%(codigo)s)
    LIMIT 1;
"""

_SQL_SURCHARGE = """
    SELECT precio_lb
    FROM aleacion_surcharges
    WHERE material_id = %(material_id)s
      AND vigente_desde <= %(hoy)s
      AND (vigente_hasta IS NULL OR vigente_hasta > %(hoy)s)
    ORDER BY vigente_desde DESC
    LIMIT 1;
"""


_SQL_MATERIAL_POR_TEXTO = """
    SELECT m.id, m.codigo, m.nombre, m.lleva_surcharge,
           mp.precio_lb, mp.diam_pulg, mp.fecha_cotizado
    FROM materiales m
    LEFT JOIN LATERAL (
        SELECT precio_lb, diam_pulg, fecha_cotizado
        FROM material_precios p
        WHERE p.material_id = m.id
        ORDER BY abs(p.diam_pulg - %(diam_pulg)s) ASC, p.fecha_cotizado DESC
        LIMIT 1
    ) mp ON true
    WHERE m.activo
      AND (upper(m.nombre) = upper(%(texto)s)
           OR (m.astm IS NOT NULL AND upper(m.astm) = upper(%(texto)s)))
    LIMIT 1;
"""


def codigo_de_material(texto: Optional[str]) -> Optional[str]:
    """Código de catálogo para el material tal como viene escrito en el RFQ.

    El comprador no escribe códigos: escribe "ASTM A228 music wire, zinc
    plated finish". El catálogo de costeo guarda "MW". Sin traducir, la
    consulta buscaba una fila cuyo código fuera esa frase entera, no la
    encontraba y el costeo declaraba faltante un material que la planta tiene
    en existencia.

    La tabla de equivalencias es la de factibilidad
    (``reglas/factibilidad.json``), a propósito: es donde ya están los alias
    del material, y así el dictamen y el precio no pueden opinar distinto
    sobre si un material existe. Si las reglas no se pueden leer, se devuelve
    ``None`` y se sigue con el texto crudo: traducir es una mejora, no un
    requisito para costear.
    """
    if not texto or not str(texto).strip():
        return None
    try:
        import app.feasibility.rules as reglas_mod
        return reglas_mod.cargar_reglas().codigo_material(texto)
    except Exception as err:
        log.debug("No se pudo traducir el material %r a código: %s", texto, err)
        return None


def precio_material(codigo: str, diametro_pulg: Optional[float] = None,
                    conexion=None, en_fecha: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """Material y su precio por libra más cercano al calibre pedido.

    ``codigo`` admite tanto el código del catálogo ("MW") como el texto libre
    del correo o del plano ("ASTM A228 music wire, zinc plated finish"): se
    prueba primero tal cual, luego el código al que lo traducen los alias de
    factibilidad, y por último el nombre o la norma ASTM completos.

    Se elige el precio del diámetro más próximo al del resorte, y entre varios
    del mismo diámetro, el más reciente. Si el material lleva surcharge de
    aleación (inoxidables), se suma el vigente.
    """
    if not codigo:
        return None
    hoy = en_fecha or date.today()
    diam = diametro_pulg if diametro_pulg is not None else 0.0

    crudo = str(codigo).strip()
    candidatos = [crudo]
    canonico = codigo_de_material(crudo)
    if canonico and canonico.upper() != crudo.upper():
        candidatos.append(canonico)

    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            fila = None
            for candidato in candidatos:
                cur.execute(_SQL_MATERIAL, {"codigo": candidato, "diam_pulg": diam})
                fila = cur.fetchone()
                if fila:
                    if candidato != crudo:
                        log.info("Material %r resuelto al código de catálogo %r.",
                                 crudo, candidato)
                    break
            if not fila:
                # Último intento: el RFQ trae el nombre del catálogo o la norma
                # tal cual ("Stainless Steel 316 (ASTM A313 Type 316)", "A228").
                cur.execute(_SQL_MATERIAL_POR_TEXTO, {"texto": crudo, "diam_pulg": diam})
                fila = cur.fetchone()
            if not fila:
                return None

            datos = {
                "id": fila[0], "codigo": fila[1], "nombre": fila[2],
                "lleva_surcharge": bool(fila[3]),
                "precio_lb": _f(fila[4]),
                "diam_pulg_cotizado": _f(fila[5]),
                "fecha_cotizado": fila[6].isoformat() if fila[6] else None,
                "surcharge_lb": 0.0,
            }

            if datos["lleva_surcharge"]:
                cur.execute(_SQL_SURCHARGE, {"material_id": datos["id"], "hoy": hoy})
                fila_s = cur.fetchone()
                datos["surcharge_lb"] = _f(fila_s[0]) if fila_s else 0.0

    return datos


# ---------------------------------------------------------------------------
# Empaque
# ---------------------------------------------------------------------------

_SQL_EMPAQUE = """
    SELECT codigo, descripcion, precio, piezas_por_caja
    FROM empaques
    WHERE activo AND (%(codigo)s IS NULL OR codigo = %(codigo)s)
    ORDER BY (codigo = COALESCE(%(codigo)s, codigo)) DESC, precio ASC NULLS LAST
    LIMIT 1;
"""


def empaque(codigo: Optional[str] = None, conexion=None) -> Optional[Dict[str, Any]]:
    """Empaque pedido, o el más barato activo si no se especifica ninguno."""
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(_SQL_EMPAQUE, {"codigo": codigo})
            fila = cur.fetchone()
    if not fila:
        return None
    return {"codigo": fila[0], "descripcion": fila[1],
            "precio": _f(fila[2]), "piezas_por_caja": fila[3]}


# ---------------------------------------------------------------------------
# Carga completa
# ---------------------------------------------------------------------------

def cargar_catalogo(tipo_resorte: str,
                    material_codigo: Optional[str],
                    diametro_alambre_mm: Optional[float],
                    diametro_exterior_mm: Optional[float] = None,
                    empaque_codigo: Optional[str] = None,
                    conexion=None) -> Catalogo:
    """Lee de una sola vez todo lo que el motor necesita para este resorte.

    Nunca lanza por dato ausente: registra el hueco en ``faltantes`` y sigue,
    para que la API pueda responder "esto es lo que hay" en vez de un 500.
    """
    cat = Catalogo()
    diam_pulg = (diametro_alambre_mm / 25.4) if diametro_alambre_mm else None

    with _conexion(conexion) as conn:
        try:
            cat.parametros = parametros_vigentes(conexion=conn)
            cat.origen["parametros"] = "bd" if cat.parametros else "defaults del motor"
            if not cat.parametros:
                mensajes.falta(cat, "PARAMETROS_SIN_JUEGO")
        except Exception as err:
            log.warning("No se pudieron leer los parámetros de costeo: %s", err)
            mensajes.falta(cat, "PARAMETROS_ILEGIBLES", error=str(err))
            cat.origen["parametros"] = "defaults del motor"

        if diametro_alambre_mm is None:
            mensajes.falta(cat, "SIN_DIAMETRO_ALAMBRE")

        try:
            cat.maquina = elegir_maquina(tipo_resorte, diametro_alambre_mm,
                                         diametro_exterior_mm, conexion=conn)
            if cat.maquina is None:
                mensajes.falta(cat, "SIN_MAQUINA_CAPAZ", tipo=tipo_resorte,
                               diametro=diametro_alambre_mm)
                cat.origen["maquina"] = "sin dato"
            else:
                cat.origen["maquina"] = f"bd: {cat.maquina['nombre']}"
                if cat.maquina["costo_hora"] is None:
                    mensajes.falta(cat, "MAQUINA_SIN_TARIFA",
                                   maquina=cat.maquina["nombre"])
        except Exception as err:
            log.warning("No se pudo elegir máquina: %s", err)
            mensajes.falta(cat, "MAQUINA_FALLO", error=str(err))
            cat.origen["maquina"] = "sin dato"

        if material_codigo:
            try:
                cat.material = precio_material(material_codigo, diam_pulg, conexion=conn)
                if cat.material is None:
                    mensajes.falta(cat, "MATERIAL_SIN_CATALOGO", material=material_codigo)
                    cat.origen["material"] = "sin dato"
                elif cat.material["precio_lb"] is None:
                    mensajes.falta(cat, "MATERIAL_SIN_PRECIO", material=material_codigo)
                    cat.origen["material"] = f"bd: {cat.material['codigo']} sin precio"
                else:
                    cat.origen["material"] = (
                        f"bd: {cat.material['codigo']} a {cat.material['precio_lb']} USD/lb "
                        f"(cotizado {cat.material['fecha_cotizado']})")
            except Exception as err:
                log.warning("No se pudo leer el precio del material: %s", err)
                mensajes.falta(cat, "MATERIAL_ILEGIBLE", error=str(err))
                cat.origen["material"] = "sin dato"
        else:
            mensajes.falta(cat, "SIN_MATERIAL")
            cat.origen["material"] = "sin dato"

        try:
            cat.empaque = empaque(empaque_codigo, conexion=conn)
            cat.origen["empaque"] = f"bd: {cat.empaque['codigo']}" if cat.empaque else "sin dato"
            if cat.empaque is None:
                mensajes.falta(cat, "SIN_EMPAQUES")
        except Exception as err:
            log.warning("No se pudo leer el empaque: %s", err)
            mensajes.falta(cat, "EMPAQUE_ILEGIBLE", error=str(err))
            cat.origen["empaque"] = "sin dato"

    return cat


def _f(valor) -> Optional[float]:
    """Numeric de psycopg2 (Decimal) → float. None se queda en None."""
    return float(valor) if valor is not None else None
