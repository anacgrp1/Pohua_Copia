#!/usr/bin/env python3
"""Carga en Neon el extracto del catálogo de taller.

    python scripts/cargar_catalogo.py --carpeta "C:\\ruta\\al\\extracto" --seco
    python scripts/cargar_catalogo.py --carpeta "C:\\ruta\\al\\extracto"

Son los datos que validó Miguel Rodea el 2026-09-03: precios de alambre,
surcharges, empaques, acabados, subcontratistas, historial de recubrimiento,
las fichas de material y los valores reales de las máquinas. Hasta ahora las
tablas de costeo estaban creadas y **vacías** —o sembradas con los valores de
marcador que la migración 007 sacó de `pricing/engine.js`—, y por eso todo
costeo salía declarado como incompleto.

CÓMO LEER ESTE SCRIPT. Cada tabla tiene su función `cargar_*`, todas con la
misma forma: leer el CSV, resolver las claves ajenas por **clave natural** y
escribir. Se resuelven por nombre y no por id a propósito: el extracto viene de
otra base y apostar a que las dos numeraciones coinciden es cómo se acaba
metiendo el precio de un material en otro.

TRES COSAS QUE HACE Y CONVIENE SABER

  * **Va en una sola transacción.** O entra todo o no entra nada. A medias
    quedaría un catálogo que parece completo y no lo está, que es peor que uno
    vacío: uno vacío se nota, uno a medias cotiza.

  * **`--seco` no escribe.** Hace el trabajo entero, cuenta lo que haría, y
    deshace. Es la forma de ver los avisos antes de tocar producción, y esto
    cambia precios.

  * **Lo que no casa se dice, no se inventa.** Si un material o un proveedor
    del CSV no existe en Neon, la fila se cuenta como omitida y su motivo sale
    al final. Nunca se crea una fila a medias para que cuadre el número.

LOS PARÁMETROS CAMBIAN PRECIOS. `param_valores.csv` trae la escalera de
overheads de la V7 —30 plano— frente a la 12/16/20/24 que sembró la 007 desde
la V5. La diferencia en una pieza de una operación es del 40 %. Por eso no se
sobrescribe el juego que hubiera: se crea uno nuevo y se cierra el anterior,
que además deja ver en la base cuándo cambió y qué había antes.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# El `tipo` del extracto no es el de este esquema. Traducir aquí y no en el CSV
# porque el CSV es de otra base: cambiarlo allí sería adaptarles su fichero a
# nuestra restricción, y la próxima exportación volvería a traer los suyos.
TIPOS_PROVEEDOR = {
    "MATERIAL": "ALAMBRE",
    "SUBCONTRATISTA": "RECUBRIMIENTO",
    "EMPAQUE": "EMPAQUE",
}

avisos: List[str] = []
resumen: List[str] = []


def avisar(texto: str) -> None:
    avisos.append(texto)


def contar(tabla: str, insertadas: int, actualizadas: int = 0, omitidas: int = 0) -> None:
    linea = f"  {tabla:<28} {insertadas:>4} nuevas"
    if actualizadas:
        linea += f"  {actualizadas:>4} actualizadas"
    if omitidas:
        linea += f"  {omitidas:>4} omitidas"
    resumen.append(linea)


# --------------------------------------------------------------------- leer

def filas(carpeta: Path, nombre: str) -> List[Dict[str, str]]:
    ruta = carpeta / nombre
    if not ruta.is_file():
        avisar(f"No está {nombre}: esa tabla se queda como estaba.")
        return []
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def num(valor: Optional[str]) -> Optional[float]:
    """Un número, o None si la celda venía vacía.

    Vacío es "no lo sabemos" y tiene que llegar a la base como null. Convertir
    un vacío en 0 es lo que hace que un transporte sin capturar parezca gratis.
    """
    if valor is None:
        return None
    valor = valor.strip()
    if not valor:
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def entero(valor: Optional[str]) -> Optional[int]:
    n = num(valor)
    return None if n is None else int(round(n))


def bool_o_none(valor: Optional[str]) -> Optional[bool]:
    if valor is None:
        return None
    v = valor.strip().lower()
    if v in ("true", "t", "1", "si", "sí", "yes"):
        return True
    if v in ("false", "f", "0", "no"):
        return False
    return None


def fecha(valor: Optional[str]) -> Optional[str]:
    v = (valor or "").strip()
    return v or None


# ------------------------------------------------------------- diccionarios

def mapa(cur, sql: str) -> Dict[str, int]:
    """`{clave natural: id}` para resolver las ajenas sin adivinar."""
    cur.execute(sql)
    return {str(clave): int(ident) for clave, ident in cur.fetchall()}


# ----------------------------------------------------------------- cargas

def cargar_proveedores(cur, carpeta: Path) -> None:
    nuevos = actualizados = 0
    for f in filas(carpeta, "proveedores.csv"):
        tipo = TIPOS_PROVEEDOR.get((f["tipo"] or "").strip().upper(), "OTRO")
        cur.execute("""
            INSERT INTO proveedores (codigo, nombre, tipo, activo)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (codigo) DO UPDATE
               SET nombre = EXCLUDED.nombre,
                   tipo   = EXCLUDED.tipo,
                   activo = EXCLUDED.activo
            RETURNING (xmax = 0) AS insertada
        """, (f["codigo"].strip(), f["nombre"].strip(), tipo,
              bool_o_none(f.get("activo")) is not False))
        nuevos += 1 if cur.fetchone()[0] else 0
    actualizados = len(filas(carpeta, "proveedores.csv")) - nuevos
    contar("proveedores", nuevos, actualizados)


def cargar_materiales(cur, carpeta: Path) -> None:
    """Actualiza las fichas. No da de alta materiales nuevos.

    La lista de materiales ya existe en Neon; lo que trae el extracto son las
    columnas vacías (densidad, rango de alambre, temperatura, fatiga). Un
    material del CSV que no exista aquí no se crea: se avisa, porque darlo de
    alta es una decisión de ISC y no de una carga.
    """
    actualizados = omitidos = 0
    for f in filas(carpeta, "materiales_ficha.csv"):
        codigo = (f.get("codigo") or "").strip()
        if not codigo:
            avisar(f"materiales_ficha: «{f.get('nombre')}» viene sin código; "
                   "no se puede casar con ningún material. Hay que decidir si "
                   "se da de alta.")
            omitidos += 1
            continue
        cur.execute("""
            UPDATE materiales SET
                nombre          = COALESCE(NULLIF(%s,''), nombre),
                astm            = COALESCE(NULLIF(%s,''), astm),
                densidad_kg_m3  = COALESCE(%s, densidad_kg_m3),
                d_min_mm        = COALESCE(%s, d_min_mm),
                d_max_mm        = COALESCE(%s, d_max_mm),
                temp_max_c      = COALESCE(%s, temp_max_c),
                factor_costo    = COALESCE(%s, factor_costo),
                fatiga          = COALESCE(NULLIF(%s,''), fatiga),
                lleva_surcharge = COALESCE(%s, lleva_surcharge),
                nota            = COALESCE(NULLIF(%s,''), nota)
            WHERE codigo = %s
        """, ((f.get("nombre") or "").strip(), (f.get("astm") or "").strip(),
              entero(f.get("densidad_kg_m3")), num(f.get("d_min_mm")),
              num(f.get("d_max_mm")), entero(f.get("temp_max_c")),
              num(f.get("factor_costo")), (f.get("fatiga") or "").strip(),
              bool_o_none(f.get("lleva_surcharge")), (f.get("nota") or "").strip(),
              codigo))
        if cur.rowcount:
            actualizados += 1
        else:
            avisar(f"materiales_ficha: el código «{codigo}» no existe en materiales.")
            omitidos += 1

    # La marca de surcharge viene en su propio fichero, para los 14 códigos.
    for f in filas(carpeta, "materiales_surcharge.csv"):
        cur.execute("UPDATE materiales SET lleva_surcharge = %s WHERE codigo = %s",
                    (bool_o_none(f.get("lleva_surcharge")), (f.get("codigo") or "").strip()))
    contar("materiales (fichas)", 0, actualizados, omitidos)


def cargar_precios(cur, carpeta: Path) -> None:
    """Los 186 precios de alambre, con sus proveedores.

    45 los cotizaron varios proveedores a la vez («GIBBS, INTER, ISW»). Eso no
    cabe en `proveedor_id`, que es uno solo, y para eso está
    `material_precio_proveedores`: el precio va con `proveedor_id` nulo y los
    nombres se reparten en la tabla puente. Meter el primero de la lista en
    `proveedor_id` habría sido más fácil y habría dicho una mentira.
    """
    materiales = mapa(cur, "SELECT codigo, id FROM materiales")
    proveedores = mapa(cur, "SELECT nombre, id FROM proveedores")
    proveedores.update(mapa(cur, "SELECT codigo, id FROM proveedores"))

    nuevos = omitidos = varios = 0
    for f in filas(carpeta, "material_precios.csv"):
        material_id = materiales.get((f["material_codigo"] or "").strip())
        if material_id is None:
            avisar(f"material_precios: material «{f['material_codigo']}» "
                   "desconocido; ese precio no entra.")
            omitidos += 1
            continue

        crudo = (f.get("proveedor_nombre") or "").strip()
        nombres = [n.strip() for n in crudo.split(",") if n.strip()]
        uno = proveedores.get(nombres[0]) if len(nombres) == 1 else None
        if len(nombres) == 1 and uno is None:
            avisar(f"material_precios: proveedor «{nombres[0]}» desconocido; "
                   "el precio entra sin proveedor.")

        cur.execute("""
            INSERT INTO material_precios
                   (material_id, diam_pulg, precio_lb, cantidad_lb,
                    fecha_cotizado, proveedor_id, origen, pos_legado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (material_id, diam_pulg, fecha_cotizado, proveedor_id)
            DO UPDATE SET precio_lb   = EXCLUDED.precio_lb,
                          cantidad_lb = EXCLUDED.cantidad_lb,
                          origen      = EXCLUDED.origen
            RETURNING id, (xmax = 0)
        """, (material_id, num(f["diam_pulg"]), num(f["precio_lb"]),
              num(f.get("cantidad_lb")), fecha(f.get("fecha_cotizado")),
              uno, (f.get("origen") or "").strip() or None,
              entero(f.get("pos_legado"))))
        precio_id, insertada = cur.fetchone()
        nuevos += 1 if insertada else 0

        if len(nombres) > 1:
            varios += 1
            for nombre in nombres:
                pid = proveedores.get(nombre)
                if pid is None:
                    avisar(f"material_precios: proveedor «{nombre}» desconocido "
                           "en una cotización conjunta.")
                    continue
                cur.execute("""
                    INSERT INTO material_precio_proveedores (material_precio_id, proveedor_id)
                    VALUES (%s, %s) ON CONFLICT DO NOTHING
                """, (precio_id, pid))

    contar("material_precios", nuevos, 0, omitidos)
    if varios:
        resumen.append(f"  {'  · de varios proveedores':<28} {varios:>4}")


def cargar_surcharges(cur, carpeta: Path) -> None:
    materiales = mapa(cur, "SELECT codigo, id FROM materiales")
    nuevos = sin_material = 0
    for f in filas(carpeta, "aleacion_surcharges.csv"):
        codigo = (f.get("material_codigo") or "").strip()
        material_id = materiales.get(codigo)
        if material_id is None and codigo:
            # No es un fallo: el proveedor publica surcharges de aleaciones que
            # ISC no compra. La columna admite null justamente para esto.
            sin_material += 1
        cur.execute("""
            INSERT INTO aleacion_surcharges
                   (material_id, codigo_aleacion, etiqueta, precio_lb,
                    vigente_desde, publicado_en, nota)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (codigo_aleacion, vigente_desde)
            DO UPDATE SET precio_lb = EXCLUDED.precio_lb,
                          etiqueta  = EXCLUDED.etiqueta
            RETURNING (xmax = 0)
        """, (material_id, (f["codigo_aleacion"] or "").strip(),
              (f["etiqueta"] or "").strip(), num(f["precio_lb"]),
              fecha(f.get("vigente_desde")), fecha(f.get("publicado_en")),
              (f.get("nota") or "").strip() or None))
        nuevos += 1 if cur.fetchone()[0] else 0
    contar("aleacion_surcharges", nuevos)
    if sin_material:
        avisar(f"aleacion_surcharges: {sin_material} aleación(es) que el "
               "proveedor publica y que no están en materiales. Entran sin "
               "material, que es lo correcto.")


def cargar_empaques(cur, carpeta: Path) -> None:
    proveedores = mapa(cur, "SELECT nombre, id FROM proveedores")
    proveedores.update(mapa(cur, "SELECT codigo, id FROM proveedores"))
    nuevos = 0
    for f in filas(carpeta, "empaques.csv"):
        cur.execute("""
            INSERT INTO empaques (codigo, descripcion, proveedor_id, precio,
                                  unidad, piezas_por_caja, activo)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (codigo) DO UPDATE
               SET descripcion     = EXCLUDED.descripcion,
                   proveedor_id    = EXCLUDED.proveedor_id,
                   precio          = EXCLUDED.precio,
                   unidad          = EXCLUDED.unidad,
                   piezas_por_caja = EXCLUDED.piezas_por_caja
            RETURNING (xmax = 0)
        """, ((f["codigo"] or "").strip(), (f["descripcion"] or "").strip(),
              proveedores.get((f.get("proveedor_nombre") or "").strip()),
              num(f.get("precio")), (f.get("unidad") or "").strip() or None,
              entero(f.get("piezas_por_caja")),
              bool_o_none(f.get("activo")) is not False))
        nuevos += 1 if cur.fetchone()[0] else 0
    contar("empaques", nuevos)


def cargar_acabados(cur, carpeta: Path) -> None:
    nuevos = 0
    for f in filas(carpeta, "acabados.csv"):
        cur.execute("""
            INSERT INTO acabados (codigo, nombre, activo)
            VALUES (%s, %s, %s)
            ON CONFLICT (codigo) DO UPDATE SET nombre = EXCLUDED.nombre
            RETURNING (xmax = 0)
        """, ((f["codigo"] or "").strip(), (f["nombre"] or "").strip(),
              bool_o_none(f.get("activo")) is not False))
        nuevos += 1 if cur.fetchone()[0] else 0
    contar("acabados", nuevos)

    por_nombre = mapa(cur, "SELECT nombre, id FROM acabados")
    alias_nuevos = alias_omitidos = 0
    for f in filas(carpeta, "acabado_alias.csv"):
        acabado_id = por_nombre.get((f.get("acabado_nombre") or "").strip())
        if acabado_id is None:
            avisar(f"acabado_alias: acabado «{f.get('acabado_nombre')}» desconocido.")
            alias_omitidos += 1
            continue
        cur.execute("""
            INSERT INTO acabado_alias (acabado_id, alias) VALUES (%s, %s)
            ON CONFLICT (alias) DO UPDATE SET acabado_id = EXCLUDED.acabado_id
            RETURNING (xmax = 0)
        """, (acabado_id, (f["alias"] or "").strip()))
        alias_nuevos += 1 if cur.fetchone()[0] else 0
    contar("acabado_alias", alias_nuevos, 0, alias_omitidos)


# El día que Miguel Rodea validó el extracto. Es la fecha que se le pone a un
# precio que llegó SIN la suya: no dice cuándo empezó a valer, pero sí que valía
# como muy tarde ese día, que es lo único que se sabe de él.
FECHA_VALIDACION = "2026-09-03"


def _vigencia_servicio(f) -> str:
    """Desde cuándo vale un servicio de subcontrato.

    `subcontratista_servicios.vigente_desde` no admite null, y los tres
    servicios de Commercial Plating llegaron sin fecha —su proveedor tampoco la
    trae—. El INSERT reventaba en la primera de las tres filas.

    Y reventaba en el peor sitio: esta función corre DESPUÉS de precios y
    cajas y ANTES de máquinas y parámetros. Mientras la conexión iba en
    autocommit, eso dejaba en Neon los precios de alambre cargados y las
    máquinas de 2026 y los overheads de la V7 sin cargar: un catálogo a medias
    que cotiza con los valores de marcador de la migración 007.

    No se tiran las filas —son precios reales de un proveedor— ni se les
    inventa una fecha: se les pone la de la validación y se dice.
    """
    propia = fecha(f.get("vigente_desde"))
    if propia:
        return propia
    avisar(f"subcontratista_servicios: «{(f.get('etiqueta') or '').strip()}» de "
           f"{f.get('subcontratista_nombre')} no trae fecha de vigencia; se le "
           f"pone la de la validación del extracto ({FECHA_VALIDACION}).")
    return FECHA_VALIDACION


def cargar_subcontratistas(cur, carpeta: Path) -> None:
    proveedores = mapa(cur, "SELECT nombre, id FROM proveedores")
    nuevos = 0
    for f in filas(carpeta, "subcontratistas.csv"):
        pid = proveedores.get((f.get("proveedor_nombre") or "").strip())
        if pid is None:
            avisar(f"subcontratistas: proveedor «{f.get('proveedor_nombre')}» "
                   "desconocido; no entra.")
            continue
        cur.execute("""
            INSERT INTO subcontratistas (proveedor_id, viaje_usd, tarima_max_lb,
                                         certs_usd, fecha_cotizado)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (proveedor_id) DO UPDATE
               SET viaje_usd      = EXCLUDED.viaje_usd,
                   tarima_max_lb  = EXCLUDED.tarima_max_lb,
                   certs_usd      = EXCLUDED.certs_usd,
                   fecha_cotizado = EXCLUDED.fecha_cotizado
            RETURNING (xmax = 0)
        """, (pid, num(f.get("viaje_usd")), num(f.get("tarima_max_lb")),
              num(f.get("certs_usd")), fecha(f.get("fecha_cotizado"))))
        nuevos += 1 if cur.fetchone()[0] else 0
    contar("subcontratistas", nuevos)

    subs = mapa(cur, """SELECT p.nombre, s.id FROM subcontratistas s
                          JOIN proveedores p ON p.id = s.proveedor_id""")
    acabados = mapa(cur, "SELECT nombre, id FROM acabados")
    serv_nuevos = sin_acabado = 0
    for f in filas(carpeta, "subcontratista_servicios.csv"):
        sid = subs.get((f.get("subcontratista_nombre") or "").strip())
        if sid is None:
            avisar(f"subcontratista_servicios: subcontratista "
                   f"«{f.get('subcontratista_nombre')}» desconocido.")
            continue
        nombre_acabado = (f.get("acabado_nombre") or "").strip()
        acabado_id = acabados.get(nombre_acabado)
        if acabado_id is None:
            # No es un fallo. Las 14 grafías de Rodea son todas de zinc; estos
            # servicios (Passivate, Plating Certs...) se alcanzan porque el
            # plano los nombra tal cual, no por la tabla de alias.
            sin_acabado += 1
        cur.execute("""
            INSERT INTO subcontratista_servicios
                   (subcontratista_id, acabado_id, etiqueta, minimo_usd,
                    precio_lb, precio_pieza, vigente_desde)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (subcontratista_id, etiqueta, vigente_desde)
            DO UPDATE SET minimo_usd   = EXCLUDED.minimo_usd,
                          precio_lb    = EXCLUDED.precio_lb,
                          precio_pieza = EXCLUDED.precio_pieza,
                          acabado_id   = EXCLUDED.acabado_id
            RETURNING (xmax = 0)
        """, (sid, acabado_id, (f["etiqueta"] or "").strip(),
              num(f.get("minimo_usd")), num(f.get("precio_lb")),
              num(f.get("precio_pieza")), _vigencia_servicio(f)))
        serv_nuevos += 1 if cur.fetchone()[0] else 0
    contar("subcontratista_servicios", serv_nuevos)
    if sin_acabado:
        avisar(f"subcontratista_servicios: {sin_acabado} servicio(s) sin acabado "
               "asociado (Passivate, Plating Certs, Commercial Plating). Es lo "
               "esperado: se alcanzan por el nombre del servicio en el plano.")


def cargar_historial_plating(cur, carpeta: Path) -> None:
    """El historial de lo que ISC pagó por recubrir, tal cual vino.

    `cliente_texto` y `acabado_texto` se guardan sin resolver a propósito: son
    lo que decía cada cotización vieja, con sus grafías, y ahí está su valor.
    Casarlos a la fuerza con la cartera actual convertiría un historial en una
    afirmación sobre clientes de hoy.
    """
    nuevos = 0
    for f in filas(carpeta, "historial_plating.csv"):
        cur.execute("""
            INSERT INTO historial_plating
                   (num_parte, cliente_texto, acabado_texto, precio_lb, nota_origen)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, ((f.get("num_parte") or "").strip() or None,
              (f.get("cliente_texto") or "").strip() or None,
              (f.get("acabado_texto") or "").strip() or None,
              num(f.get("precio_lb")),
              (f.get("nota_origen") or "").strip() or None))
        nuevos += 1
    contar("historial_plating", nuevos)


def cargar_maquinas(cur, carpeta: Path) -> None:
    """Los valores reales del taller, frente a los de marcador de la 007.

    Actualiza; no da de alta. Una máquina del CSV que no esté en Neon se avisa:
    crearla necesitaría un código y una familia que aquí no se pueden inventar.
    """
    tiene_extra = _columna_existe(cur, "maquinas", "orden_uso")
    actualizadas = omitidas = tarifas = 0

    for f in filas(carpeta, "maquinas_valores.csv"):
        nombre = (f.get("nombre") or "").strip()
        cur.execute("SELECT id FROM maquinas WHERE nombre = %s", (nombre,))
        fila = cur.fetchone()
        if fila is None:
            avisar(f"maquinas_valores: «{nombre}» no existe en Neon; darla de "
                   "alta necesita código y familia, así que no se toca.")
            omitidas += 1
            continue
        maquina_id = fila[0]

        cur.execute("""
            UPDATE maquinas SET
                horas_setup = COALESCE(%s, horas_setup),
                pph_default = COALESCE(%s, pph_default),
                horas_labor = COALESCE(%s, horas_labor)
            WHERE id = %s
        """, (num(f.get("horas_setup")), entero(f.get("pph_default")),
              num(f.get("horas_labor")), maquina_id))

        if tiene_extra:
            cur.execute("""
                UPDATE maquinas SET orden_uso = COALESCE(%s, orden_uso),
                                    scrap_pct = COALESCE(%s, scrap_pct)
                 WHERE id = %s
            """, (entero(f.get("orden_uso")), num(f.get("scrap_pct")), maquina_id))

        columnas = """maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
                      hace_compresion, hace_extension, hace_torsion, usos, riesgos"""
        valores: List[Any] = [maquina_id, num(f.get("alambre_min_mm")),
                              num(f.get("alambre_max_mm")), num(f.get("od_max_mm")),
                              bool_o_none(f.get("hace_compresion")),
                              bool_o_none(f.get("hace_extension")),
                              bool_o_none(f.get("hace_torsion")),
                              (f.get("usos") or "").strip() or None,
                              (f.get("riesgos") or "").strip() or None]
        actualiza = """alambre_min_mm = EXCLUDED.alambre_min_mm,
                       alambre_max_mm = EXCLUDED.alambre_max_mm,
                       od_max_mm      = EXCLUDED.od_max_mm,
                       hace_compresion= EXCLUDED.hace_compresion,
                       hace_extension = EXCLUDED.hace_extension,
                       hace_torsion   = EXCLUDED.hace_torsion,
                       usos           = EXCLUDED.usos,
                       riesgos        = EXCLUDED.riesgos"""
        if _columna_existe(cur, "maquina_capacidades", "hace_wireform"):
            columnas += ", hace_wireform"
            valores.append(bool_o_none(f.get("hace_wireform")))
            actualiza += ", hace_wireform = EXCLUDED.hace_wireform"
        huecos = ", ".join(["%s"] * len(valores))
        cur.execute(f"""
            INSERT INTO maquina_capacidades ({columnas}) VALUES ({huecos})
            ON CONFLICT (maquina_id) DO UPDATE SET {actualiza}
        """, valores)

        # La tarifa es histórica: no se pisa la anterior, se cierra y se abre
        # una nueva. Así se puede explicar por qué una oferta de marzo salió a
        # otro precio que la misma pieza hoy.
        costo, ccv = num(f.get("costo_hora")), num(f.get("ccv_objetivo_h"))
        if costo is not None or ccv is not None:
            cur.execute("""
                SELECT id FROM maquina_tarifas
                 WHERE maquina_id = %s AND vigente_hasta IS NULL
                   AND (costo_hora IS DISTINCT FROM %s
                        OR ccv_objetivo_h IS DISTINCT FROM %s)
            """, (maquina_id, costo, ccv))
            if cur.fetchone():
                # Si la tarifa abierta empezó HOY, no hay histórico que
                # conservar: es una corrección del mismo día, y se corrige en su
                # sitio. Cerrarla con fecha de hoy la dejaría con
                # vigente_hasta = vigente_desde, que la restricción
                # `ck_tarifa_rango` prohíbe —con razón: sería una tarifa que no
                # estuvo vigente ni un día—. Pasaba al correr esto dos veces el
                # mismo día, y la carga entera se deshacía por ello.
                cur.execute("""
                    UPDATE maquina_tarifas
                       SET costo_hora = %s, ccv_objetivo_h = %s
                     WHERE maquina_id = %s AND vigente_hasta IS NULL
                       AND vigente_desde = CURRENT_DATE
                """, (costo, ccv, maquina_id))
                if cur.rowcount == 0:
                    cur.execute("""
                        UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
                         WHERE maquina_id = %s AND vigente_hasta IS NULL
                           AND vigente_desde < CURRENT_DATE
                    """, (maquina_id,))
                    cur.execute("""
                        INSERT INTO maquina_tarifas
                               (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
                        VALUES (%s, %s, %s, CURRENT_DATE)
                    """, (maquina_id, costo, ccv))
                tarifas += 1
        actualizadas += 1

    contar("maquinas", 0, actualizadas, omitidas)
    if tarifas:
        resumen.append(f"  {'  · tarifas nuevas':<28} {tarifas:>4}")
    if not tiene_extra:
        avisar("maquinas: faltan las columnas orden_uso / scrap_pct / "
               "hace_wireform. Aplica sql/migrations/013 y vuelve a pasar esto: "
               "sin ellas la elección de máquina sigue siendo la de Neon, no la "
               "de Rodea.")


def cargar_parametros(cur, carpeta: Path, nombre_juego: str) -> None:
    """Un juego nuevo, y el anterior cerrado. Nunca se sobrescribe.

    La escalera de overheads de la V7 (30 plano) frente a la de la V5
    (12/16/20/24) cambia el precio de una pieza de una operación un 40 %. Un
    cambio así tiene que quedar fechado y con el anterior a la vista, no
    aplicado encima del que había.
    """
    datos = filas(carpeta, "param_valores.csv")
    if not datos:
        return

    cur.execute("SELECT id FROM param_juegos WHERE nombre = %s", (nombre_juego,))
    fila = cur.fetchone()
    if fila:
        juego_id = fila[0]
        avisar(f"param_juegos: «{nombre_juego}» ya existía; se actualizan sus "
               "valores en vez de crear otro igual.")
    else:
        cur.execute("""
            UPDATE param_juegos SET vigente_hasta = CURRENT_DATE
             WHERE vigente_hasta IS NULL
        """)
        cerrados = cur.rowcount
        cur.execute("""
            INSERT INTO param_juegos (nombre, vigente_desde, nota)
            VALUES (%s, CURRENT_DATE, %s) RETURNING id
        """, (nombre_juego, "Cargado desde el extracto del taller (Rodea, 2026-09-03)."))
        juego_id = cur.fetchone()[0]
        if cerrados:
            resumen.append(f"  {'  · juegos anteriores cerrados':<28} {cerrados:>4}")

    for f in datos:
        crudo = (f.get("valor_json") or "").strip()
        try:
            valor = json.dumps(json.loads(crudo))
        except json.JSONDecodeError:
            valor = json.dumps(crudo)   # un texto suelto sigue siendo un valor
        cur.execute("""
            INSERT INTO param_valores (param_juego_id, clave, valor)
            VALUES (%s, %s, %s::jsonb)
            ON CONFLICT (param_juego_id, clave) DO UPDATE SET valor = EXCLUDED.valor
        """, (juego_id, (f["clave"] or "").strip(), valor))
    contar("param_valores", len(datos))
    avisar("param_valores: la columna `descripcion` del CSV no se guarda; el "
           "esquema no la tiene y el texto está en el propio extracto.")


def _columna_existe(cur, tabla: str, columna: str) -> bool:
    cur.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = %s AND column_name = %s
    """, (tabla, columna))
    return cur.fetchone() is not None


# ------------------------------------------------------------------- main

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--carpeta", required=True,
                   help="Carpeta con los CSV del extracto.")
    p.add_argument("--seco", action="store_true",
                   help="Hace el trabajo entero y lo deshace. No escribe nada.")
    p.add_argument("--juego", default="ISC V7 — overheads planos (V18)",
                   help="Nombre del juego de parámetros que se crea.")
    args = p.parse_args()

    carpeta = Path(args.carpeta)
    if not carpeta.is_dir():
        print(f"No existe la carpeta {carpeta}", file=sys.stderr)
        return 2

    import app.persistence.duplicates as duplicates

    conn = duplicates.conectar_bd()
    # `conectar_bd()` devuelve la conexión en AUTOCOMMIT: cada sentencia se
    # confirma sola. Con eso, las dos promesas de este script eran falsas:
    #
    #   · `--seco` escribía de verdad. El `rollback()` del final no tenía nada
    #     que deshacer, porque cada INSERT ya se había confirmado al ejecutarse.
    #     Correrlo "para ver los avisos antes de tocar producción" tocaba
    #     producción.
    #
    #   · "O entra todo o no entra nada" tampoco: un error a mitad de la carga
    #     dejaba confirmado todo lo anterior. Un catálogo a medias, que es
    #     justo lo que la cabecera de este fichero dice que es peor que uno
    #     vacío, porque cotiza.
    #
    # Apagarlo aquí hace que la carga entera sea UNA transacción, que es lo
    # que el resto del script ya daba por hecho.
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # El orden no es negociable: los proveedores primero porque casi
            # todo lo demás los referencia por nombre, y los acabados antes que
            # los servicios por lo mismo.
            cargar_proveedores(cur, carpeta)
            cargar_materiales(cur, carpeta)
            cargar_precios(cur, carpeta)
            cargar_surcharges(cur, carpeta)
            cargar_empaques(cur, carpeta)
            cargar_acabados(cur, carpeta)
            cargar_subcontratistas(cur, carpeta)
            cargar_historial_plating(cur, carpeta)
            cargar_maquinas(cur, carpeta)
            cargar_parametros(cur, carpeta, args.juego)

        if args.seco:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        print("\nNADA SE ESCRIBIÓ: la carga entera se deshizo por este error.\n",
              file=sys.stderr)
        raise
    finally:
        conn.close()

    print("\n" + ("SIMULACRO — no se escribió nada" if args.seco else "CARGADO"))
    print("-" * 62)
    for linea in resumen:
        print(linea)
    if avisos:
        print("\nAvisos")
        print("-" * 62)
        for a in avisos:
            print("  · " + a)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
