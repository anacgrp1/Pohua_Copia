#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Por qué el catálogo no encuentra máquina para un resorte.

Para qué
--------
La ventana de revisión dice «Sin ruta: el catálogo aún no tiene máquina para
este resorte» y ahí se acaba. Esa frase es verdad pero no sirve: no distingue
entre que no haya NINGUNA máquina dada de alta, que las que hay no lleguen a
ese diámetro de alambre, o que sí lleguen pero no tengan tarifa vigente —y las
tres se arreglan en sitios distintos—.

Sin máquina no hay ruta, y sin ruta la cotización sale con el costo de
proceso en cero. Es el segundo motivo, después del peso, por el que un RFQ que
parece completo no acaba de costearse.

Esto corre la MISMA consulta que usa `pricing.repository.elegir_maquina`
—filtro a filtro— y dice en cuál se cae cada máquina.

    python scripts/por_que_sin_ruta.py --alambre 5.21 --od 49.28
    python scripts/por_que_sin_ruta.py --alambre 5.21 --od 49.28 --tipo extension
    python scripts/por_que_sin_ruta.py --rfq INT-8D50E3A5

El modo ``--rfq`` es el que de verdad zanja la duda: en vez de las cotas que
uno teclea, usa las que están GUARDADAS para ese RFQ y llama al mismo
``cargar_catalogo`` que usa el costeo. Si con las cotas tecleadas sí hay
máquina y con las guardadas no, el problema no es el catálogo de máquinas:
son los datos del resorte, y ahí se ve cuál.

No escribe nada: sólo lee.
"""

import argparse
import os
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)


SQL = """
SELECT m.codigo, m.nombre, fm.codigo AS familia, m.activo,
       c.alambre_min_mm, c.alambre_max_mm, c.od_max_mm,
       c.hace_compresion, c.hace_extension, c.hace_torsion,
       t.costo_hora
FROM maquinas m
JOIN familias_maquina fm ON fm.id = m.familia_id
LEFT JOIN maquina_capacidades c ON c.maquina_id = m.id
LEFT JOIN LATERAL (
    SELECT costo_hora FROM maquina_tarifas mt
    WHERE mt.maquina_id = m.id
      AND mt.vigente_desde <= %(hoy)s
      AND (mt.vigente_hasta IS NULL OR mt.vigente_hasta > %(hoy)s)
    ORDER BY mt.vigente_desde DESC LIMIT 1
) t ON true
ORDER BY m.codigo;
"""

def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


COLUMNA = {"compression": "hace_compresion", "compresion": "hace_compresion",
           "extension": "hace_extension", "extensión": "hace_extension",
           "torsion": "hace_torsion", "torsión": "hace_torsion"}


def motivos(fila, tipo_col, diam, od):
    """Por qué ESTA máquina no sirve. Vacío = sí sirve."""
    (cod, nom, familia, activo, a_min, a_max, od_max,
     comp, ext, tor, costo) = fila
    porque = []

    if not activo:
        porque.append("está dada de baja (activo = false)")
    if familia != "COILER":
        porque.append(f"su familia es {familia}, y la ruta sólo mira COILER")

    # Una capacidad NULL es "no se capturó", y no descarta: así lo hace la
    # consulta de verdad. Se avisa aparte, porque pasar por no saberlo no es
    # lo mismo que pasar por encajar.
    if diam is not None:
        if a_min is not None and float(a_min) > diam:
            porque.append(f"su alambre mínimo son {a_min} mm y el resorte "
                          f"lleva {diam} mm")
        if a_max is not None and float(a_max) < diam:
            porque.append(f"su alambre máximo son {a_max} mm y el resorte "
                          f"lleva {diam} mm")
    if od is not None and od_max is not None and float(od_max) < od:
        porque.append(f"su OD máximo son {od_max} mm y el resorte mide {od} mm")

    hace = {"hace_compresion": comp, "hace_extension": ext,
            "hace_torsion": tor}[tipo_col]
    if hace is False:
        porque.append(f"tiene {tipo_col} = false")

    return porque


def por_rfq(rfq_id: str) -> int:
    """Lo que el costeo ve de verdad para ese RFQ, con sus cotas guardadas.

    Existe porque las cotas que uno teclea en la línea de comandos y las que
    están en la base pueden no ser las mismas —y cuando no lo son, la pantalla
    dice "sin ruta" mientras la consulta a mano encuentra máquina de sobra—.
    """
    import json
    from pricing.repository import _conexion, cargar_catalogo

    with _conexion(None) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT datos_json FROM resortes_cotizacion "
                        "WHERE rfq_id = %s ORDER BY id DESC LIMIT 1;", (rfq_id,))
            fila = cur.fetchone()

    if not fila:
        print(f"No hay resorte guardado para {rfq_id} en `resortes_cotizacion`.")
        print("Sin cotas guardadas no hay nada que enrutar: el plano no se "
              "llegó a leer, o se leyó y no se guardó.\n")
        return 1

    d = fila[0]
    if isinstance(d, str):
        d = json.loads(d)
    d = d or {}

    interesan = ("tipo_resorte", "material", "diametro_alambre_mm",
                 "diametro_exterior_mm", "diametro_interior_mm",
                 "diametro_medio_mm", "numero_espiras_totales",
                 "numero_espiras_activas", "longitud_libre_mm")
    print("Cotas guardadas:")
    for k in interesan:
        v = d.get(k)
        print(f"   {k:28} {'—' if v in (None, '') else v}")
    otros = [k for k in d if k not in interesan and d.get(k) not in (None, "")]
    if otros:
        print(f"   (y {len(otros)} campo(s) más)")
    print()

    tipo = d.get("tipo_resorte") or "compresion"
    diam = _f(d.get("diametro_alambre_mm"))
    od = _f(d.get("diametro_exterior_mm"))

    cat = cargar_catalogo(tipo_resorte=tipo, material_codigo=d.get("material"),
                          diametro_alambre_mm=diam, diametro_exterior_mm=od)

    if cat.maquina:
        tarifa = (f"${cat.maquina['costo_hora']}/h" if cat.maquina.get("costo_hora")
                  else "SIN TARIFA VIGENTE")
        print(f"El costeo SÍ encuentra máquina: {cat.maquina['codigo']} — "
              f"{cat.maquina['nombre']} ({tarifa})")
        print("Así que un 'sin ruta' en pantalla no viene de aquí: viene de un "
              "dictamen guardado ANTES, con otras cotas. Pulsa Recalculate y "
              "se rehace con éstas.\n")
    else:
        print(f"El costeo NO encuentra máquina con estas cotas "
              f"(alambre {diam}, OD {od}, tipo {tipo}).")
        print("Arriba, con --alambre y --od, se ve máquina por máquina "
              "por qué.\n")

    if cat.faltantes:
        # `faltantes` son frases ya redactadas; `faltantes_i18n` las mismas con
        # su código. Se prefiere la frase, que es la que ve el PM.
        print("Lo que el costeo apunta como faltante:")
        for f in cat.faltantes:
            print(f"   - {f}")
        print()

    return 0 if cat.maquina else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--alambre", type=float, default=None,
                   help="diámetro de alambre en mm")
    p.add_argument("--od", type=float, default=None,
                   help="diámetro exterior en mm")
    p.add_argument("--tipo", default="compression",
                   help="compression | extension | torsion")
    p.add_argument("--rfq", default=None,
                   help="usa las cotas GUARDADAS de ese RFQ en vez de --alambre/--od")
    args = p.parse_args()

    if args.rfq:
        print(f"\nRFQ {args.rfq}\n")
        try:
            return por_rfq(args.rfq)
        except Exception as e:
            print(f"No se pudo leer el RFQ: {e}\n")
            return 1

    tipo_col = COLUMNA.get(args.tipo.strip().lower(), "hace_compresion")

    from pricing.repository import _conexion, elegir_maquina

    print(f"\nResorte: alambre {args.alambre} mm · OD {args.od} mm · {args.tipo}\n")

    try:
        with _conexion(None) as conn:
            with conn.cursor() as cur:
                cur.execute(SQL, {"hoy": date.today()})
                filas = cur.fetchall()
    except Exception as e:
        print(f"No se pudo leer la base: {e}\n")
        return 1

    if not filas:
        print("La tabla `maquinas` está VACÍA.")
        print("Sin una sola máquina dada de alta no puede haber ruta para "
              "ningún resorte, no sólo para éste.\n")
        return 1

    print(f"{len(filas)} máquina(s) en el catálogo:\n")
    sirven = []
    for fila in filas:
        cod, nom = fila[0], fila[1]
        porque = motivos(fila, tipo_col, args.alambre, args.od)
        costo = fila[10]
        if porque:
            print(f"   [no]  {cod} — {nom}")
            for m in porque:
                print(f"           {m}")
        else:
            sin_capturar = fila[4] is None or fila[5] is None
            nota = "  (sin capacidades capturadas: pasa por no saberlo)" \
                if sin_capturar else ""
            falta_tarifa = "  SIN TARIFA VIGENTE" if costo is None else \
                f"  ${costo}/h"
            print(f"   [sí]  {cod} — {nom}{nota}{falta_tarifa}")
            sirven.append((cod, costo))

    print()
    if not sirven:
        print("Ninguna máquina del catálogo puede con este resorte.")
        print("Lo de arriba dice qué habría que cambiar en "
              "`maquina_capacidades` —o qué máquina falta dar de alta—.\n")
        return 1

    sin_tarifa = [c for c, costo in sirven if costo is None]
    if len(sin_tarifa) == len(sirven):
        print("Hay máquina capaz, pero NINGUNA tiene tarifa vigente hoy en "
              "`maquina_tarifas`.")
        print("La ruta se elige igual; lo que sale en cero es el costo por "
              "hora.\n")

    try:
        elegida = elegir_maquina(args.tipo, args.alambre, args.od)
    except Exception as e:
        print(f"La consulta real falló: {e}\n")
        return 1

    if elegida:
        tarifa = (f"${elegida['costo_hora']}/h" if elegida.get("costo_hora")
                  else "sin tarifa vigente")
        print(f"La ruta elegiría: {elegida['codigo']} — "
              f"{elegida['nombre']} ({tarifa})\n")
        return 0

    print("Y aun así `elegir_maquina` no devuelve nada. Si arriba salía "
          "alguna en [sí], el filtro que sobra está en la consulta, no en "
          "los datos.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
