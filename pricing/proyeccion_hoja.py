# -*- coding: utf-8 -*-
"""El catálogo de costeo de la hoja, servido desde las tablas de Neon.

El problema
-----------
La calculadora que va dentro de Pohua —la V7, la misma que se abre con doble
clic en la planta— guarda sus bases en el documento de ``cotizador_estado``:
máquinas, precios de alambre, cajas, recargos, subcontratistas. En la planta
esas bases salen de su propio ``SEED``, incrustado en el HTML.

En Pohua el ``SEED`` va VACÍO. Lo vacía ``scripts/vendorizar_nucleo.py`` al
copiar el HTML, y con razón: lleva 412 clientes y los precios de proveedor con
fecha, y el núcleo prohíbe versionarlos. La idea era que la hoja recibiera el
catálogo de Neon al abrirse. Pero eso sólo se llegó a hacer con los CLIENTES
(``app/clients/catalogo_hoja.py``). El resto se quedó en el documento, tal
como se sembró: vacío.

Y hay algo peor. La calculadora trae una migración, ``taller2026``, que al
abrir un documento REEMPLAZA su tabla de máquinas por la de su ``SEED``:

    if(!sh.migrations.taller2026){
      sh.dbs.machines = JSON.parse(JSON.stringify(SEED.machines));

Con el ``SEED`` vacío, eso borró las máquinas la primera vez que alguien abrió
la hoja en Pohua, marcó la migración como hecha y lo guardó en Neon.

El resultado es lo que se ve en pantalla: la máquina de la ruta sale en blanco
porque no está en la lista, la caja sale en blanco porque no hay cajas —y el
motor calcula el empaque como ``precio de la caja ÷ piezas por caja`` buscando
la caja en esa lista, así que da cero—, y el precio base del alambre no se
puede sugerir porque no hay precios. El 004-222 salía a $1.234 la pieza donde
la calculadora de la planta da $0.3946.

La solución
-----------
La misma que con los clientes: la tabla manda. Al servir el documento se
reemplazan esas cinco listas por lo que hay en Neon —que es lo que carga
``scripts/cargar_catalogo.py`` desde el extracto que validó Rodea—, con la
forma exacta que espera la calculadora. Y se marcan como hechas las migraciones
de la hoja que copiarían su ``SEED`` vacío encima.

Lo mismo con los parámetros (markups, overheads, suelo de ISC): el costeo del
servidor usa el juego vigente de Neon, y si la hoja usara otros, el precio que
se ve en la hoja y el que sale en la oferta serían dos.

Lo que NO se hace
-----------------
No se pisa una lista con vacío. Si una tabla de Neon está vacía —el catálogo
todavía no se cargó—, la hoja se queda con lo que tuviera. Un catálogo vacío
para todo el mundo es mucho peor que uno un poco viejo.

Consecuencia que conviene saber: como la tabla manda, lo que alguien cambie en
las bases DESDE la hoja no sobrevive a la siguiente lectura. El catálogo se
cambia en su sitio —el extracto y ``cargar_catalogo.py``—, que es además lo que
evita que la hoja y el servidor vuelvan a separarse.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("cotizador.proyeccion_hoja")

RAIZ = Path(__file__).resolve().parent.parent
CALCULADORA = RAIZ / "vendor" / "calculadora" / "ISC Price Calculator V7 to Automate.html"

# Las migraciones de la hoja que copian su SEED encima de las bases. Con el
# SEED vacío de Pohua cada una de ellas borra o deja sin rellenar algo, así que
# se dan por hechas: las tablas ya vienen de Neon.
MIGRACIONES_DEL_SEED = ("taller2026", "camposNuevos202609")


def _f(v) -> Optional[float]:
    return None if v is None else float(v)


def _fecha(v) -> Optional[str]:
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


# --------------------------------------------------------------------------- #
# Las cinco listas
# --------------------------------------------------------------------------- #

_SQL_MAQUINAS = """
    SELECT m.codigo, m.nombre, fm.codigo,
           m.horas_setup, m.pph_default, m.costo_compra, m.horas_labor,
           m.anios_amort, m.carga_pct, m.horas_anio, m.oee, m.clase_setup,
           t.costo_hora, t.ccv_objetivo_h,
           c.alambre_min_mm, c.alambre_max_mm, c.od_max_mm,
           c.hace_compresion, c.hace_extension, c.hace_torsion,
           c.usos, c.riesgos,
           {extra}
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
    ORDER BY fm.codigo, m.orden_uso NULLS LAST, m.nombre
"""


def _tiene_columnas(cur, tabla: str, columnas) -> bool:
    cur.execute("""
        SELECT count(*) FROM information_schema.columns
         WHERE table_name = %s AND column_name = ANY(%s)
    """, (tabla, list(columnas)))
    return (cur.fetchone() or [0])[0] == len(columnas)


def maquinas(cur, hoy: date) -> List[Dict[str, Any]]:
    """`dbs.machines`, con los campos que lee la hoja."""
    # `orden_uso`, `scrap_pct` y `hace_wireform` los añadió la migración 013.
    # Si una base no la tiene, se sirve lo demás en vez de reventar.
    extra = _tiene_columnas(cur, "maquinas", ("orden_uso", "scrap_pct")) and \
        _tiene_columnas(cur, "maquina_capacidades", ("hace_wireform",))
    columnas = ("m.orden_uso, m.scrap_pct, c.hace_wireform" if extra
                else "NULL::int, NULL::numeric, NULL::boolean")
    sql = _SQL_MAQUINAS.format(extra=columnas)
    if not extra:
        sql = sql.replace("m.orden_uso NULLS LAST, ", "")
    cur.execute(sql, {"hoy": hoy})
    lista = []
    for f in cur.fetchall():
        (codigo, nombre, familia, setup, pph, compra, labor, anios, carga,
         horas, oee, clase, costo, ccv, wmin, wmax, odmax, cc, ce, ct,
         usos, riesgos, rank, scrap, cw) = f
        lista.append({
            "family": familia, "name": nombre, "m1": codigo,
            "setupH": _f(setup), "pph": _f(pph), "purchase": _f(compra),
            "laborH": _f(labor), "amortYrs": _f(anios), "loadPct": _f(carga),
            "hPerYr": _f(horas), "oee": _f(oee),
            "costRateH": _f(costo), "ccvTargetH": _f(ccv),
            "wireMinMm": _f(wmin), "wireMaxMm": _f(wmax), "odMaxMm": _f(odmax),
            "capC": cc, "capE": ce, "capT": ct, "capW": cw,
            "setupClass": clase or "", "uses": usos or "", "risk": riesgos or "",
            "rank": _f(rank), "scrapPct": _f(scrap),
        })
    return lista


def precios(cur) -> List[Dict[str, Any]]:
    """`dbs.materialPrices`: una fila por material y calibre.

    La hoja espera el resumen —último precio, media ponderada, mínimo y
    máximo— y Neon guarda cada cotización por separado, así que se agrega aquí.
    Con una sola cotización por calibre, que es lo que trae el extracto, las
    cuatro cifras coinciden, igual que en el catálogo de la planta.
    """
    cur.execute("""
        SELECT m.codigo, p.id, p.diam_pulg, p.precio_lb, p.cantidad_lb,
               p.fecha_cotizado, p.origen, pr.nombre
          FROM material_precios p
          JOIN materiales m ON m.id = p.material_id
          LEFT JOIN proveedores pr ON pr.id = p.proveedor_id
         ORDER BY m.codigo, p.diam_pulg, p.fecha_cotizado DESC, p.id DESC
    """)
    filas = cur.fetchall()

    # Las cotizaciones de varios proveedores a la vez viven en su tabla puente.
    varios: Dict[int, List[str]] = {}
    try:
        cur.execute("""
            SELECT mpp.material_precio_id, pr.nombre
              FROM material_precio_proveedores mpp
              JOIN proveedores pr ON pr.id = mpp.proveedor_id
             ORDER BY pr.nombre
        """)
        for pid, nombre in cur.fetchall():
            varios.setdefault(pid, []).append(nombre)
    except Exception:          # la tabla puente es opcional
        cur.connection.rollback() if hasattr(cur, "connection") else None

    grupos: Dict[tuple, List[tuple]] = {}
    for codigo, pid, dia, precio, qty, fecha, origen, prov in filas:
        grupos.setdefault((codigo, float(dia)), []).append(
            (pid, float(precio), _f(qty), fecha, origen, prov))

    lista = []
    for (codigo, dia), obs in grupos.items():
        ultimo = obs[0]                       # la más reciente
        con_qty = [(p, q) for (_, p, q, *_r) in obs if q]
        total = sum(q for _, q in con_qty)
        wavg = (sum(p * q for p, q in con_qty) / total) if total else ultimo[1]
        valores = [p for (_, p, *_r) in obs]
        sup = ", ".join(varios.get(ultimo[0]) or []) or ultimo[5] or ultimo[4] or ""
        lista.append({
            "code": codigo, "dia": dia,
            "latest": ultimo[1], "wavg": round(wavg, 6),
            "min": min(valores), "max": max(valores),
            "pos": float(len(obs)), "qtyLb": ultimo[2],
            "date": _fecha(ultimo[3]), "sup": sup,
        })
    return lista


def cajas(cur) -> List[Dict[str, Any]]:
    """`dbs.packing`."""
    cur.execute("""
        SELECT e.codigo, e.descripcion, pr.nombre, e.precio, e.unidad,
               e.piezas_por_caja
          FROM empaques e
          LEFT JOIN proveedores pr ON pr.id = e.proveedor_id
         WHERE e.activo
         ORDER BY e.id
    """)
    return [{"id": c, "desc": d or c, "supplier": s or "", "price": _f(p),
             "uom": u or "EACH", "defaultPerBox": ppb}
            for c, d, s, p, u, ppb in cur.fetchall()]


def recargos(cur, hoy: date) -> List[Dict[str, Any]]:
    """`dbs.surcharges`: el vigente de cada aleación, con el anterior al lado."""
    cur.execute("""
        SELECT a.codigo_aleacion, a.etiqueta, m.codigo, a.precio_lb,
               a.vigente_desde, a.publicado_en, a.nota,
               (SELECT b.precio_lb FROM aleacion_surcharges b
                 WHERE b.codigo_aleacion = a.codigo_aleacion
                   AND b.vigente_desde < a.vigente_desde
                 ORDER BY b.vigente_desde DESC LIMIT 1)
          FROM aleacion_surcharges a
          LEFT JOIN materiales m ON m.id = a.material_id
         WHERE a.vigente_desde <= %(hoy)s
           AND (a.vigente_hasta IS NULL OR a.vigente_hasta > %(hoy)s)
         ORDER BY a.id
    """, {"hoy": hoy})
    return [{"alloy": etiqueta or aleacion, "code": codigo or aleacion,
             "perLb": _f(precio), "prev": _f(anterior),
             "effective": _fecha(desde), "updated": _fecha(publicado),
             "note": nota or ""}
            for aleacion, etiqueta, codigo, precio, desde, publicado, nota, anterior
            in cur.fetchall()]


def subcontratistas(cur, hoy: date) -> List[Dict[str, Any]]:
    """`dbs.subcontractors`, cada uno con sus servicios vigentes."""
    cur.execute("""
        SELECT s.id, pr.nombre, s.fecha_cotizado, s.certs_usd, s.viaje_usd,
               s.tarima_max_lb
          FROM subcontratistas s
          JOIN proveedores pr ON pr.id = s.proveedor_id
         ORDER BY s.id
    """)
    subs = cur.fetchall()
    cur.execute("""
        SELECT subcontratista_id, etiqueta, minimo_usd, precio_lb
          FROM subcontratista_servicios
         WHERE vigente_desde <= %(hoy)s
           AND (vigente_hasta IS NULL OR vigente_hasta > %(hoy)s)
         ORDER BY id
    """, {"hoy": hoy})
    servicios: Dict[int, List[Dict[str, Any]]] = {}
    for sid, etiqueta, minimo, precio in cur.fetchall():
        servicios.setdefault(sid, []).append(
            {"service": etiqueta, "min": _f(minimo), "perLb": _f(precio)})
    return [{"name": nombre, "quoteDate": _fecha(fecha),
             "services": servicios.get(sid, []),
             "certs": _f(certs), "loopTrip": _f(viaje), "skidMaxLb": _f(tarima)}
            for sid, nombre, fecha, certs, viaje, tarima in subs]


# --------------------------------------------------------------------------- #
# La versión del SEED de la hoja
# --------------------------------------------------------------------------- #

_version_cache: Optional[str] = None


def version_semilla() -> Optional[str]:
    """El `SEED_VERSION` del HTML que sirve Pohua.

    Hace falta para que la hoja no pregunte al entrar si quiere "actualizar
    las bases a la semilla": con la semilla vacía, contestar que sí las
    borraría todas.
    """
    global _version_cache
    if _version_cache is None:
        try:
            texto = CALCULADORA.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"const SEED_VERSION\s*=\s*'([^']+)'", texto)
            _version_cache = m.group(1) if m else ""
        except OSError:
            _version_cache = ""
    return _version_cache or None


# --------------------------------------------------------------------------- #
# Aplicar
# --------------------------------------------------------------------------- #

def aplicar(documento: Dict[str, Any], conn, hoy: Optional[date] = None
            ) -> Dict[str, int]:
    """Pone en el documento el catálogo de Neon. Devuelve cuántas filas puso.

    Nunca revienta la lectura del documento: si algo falla, se registra y la
    hoja se queda con lo que traía. Sin catálogo nuevo la hoja sigue abriendo;
    sin documento, no.
    """
    if not isinstance(documento, dict):
        return {}
    hoy = hoy or date.today()
    dbs = documento.setdefault("dbs", {})
    puestas: Dict[str, int] = {}

    listas = (("machines", lambda c: maquinas(c, hoy)),
              ("materialPrices", precios),
              ("packing", cajas),
              ("surcharges", lambda c: recargos(c, hoy)),
              ("subcontractors", lambda c: subcontratistas(c, hoy)))

    for clave, leer in listas:
        try:
            with conn.cursor() as cur:
                filas = leer(cur)
        except Exception as error:
            log.warning("No se pudo proyectar %s en la hoja: %s", clave, error)
            try:
                conn.rollback()
            except Exception:
                pass
            continue
        if filas:                 # nunca se pisa con vacío
            dbs[clave] = filas
            puestas[clave] = len(filas)

    # Los parámetros: los del juego vigente, encima de los que tuviera.
    try:
        from pricing import repository
        params = repository.parametros_vigentes(conexion=conn, en_fecha=hoy)
        if params:
            documento.setdefault("params", {}).update(params)
            puestas["params"] = len(params)
    except Exception as error:
        log.warning("No se pudieron proyectar los parámetros en la hoja: %s", error)

    # Que la hoja no copie su SEED vacío encima de lo que se acaba de poner.
    if puestas:
        mig = documento.setdefault("migrations", {})
        if "machines" in puestas:
            for nombre in MIGRACIONES_DEL_SEED:
                mig[nombre] = True
        version = version_semilla()
        if version:
            mig["seedVersion"] = version
        mig.pop("seedPendiente", None)

    return puestas
