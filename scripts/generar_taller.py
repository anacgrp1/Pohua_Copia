#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Genera la migración del catálogo de máquinas desde los datos del taller.

Por qué existe
--------------
Los números de `maquinas` y `maquina_tarifas` venían de derivarlos del precio
de compra: costo/hora = compra / (años x horas al año). Eso daba 11.16 $/h para
la TORIN W11A y 600 piezas/hora, y con esos números una pieza salía a un precio
y en la calculadora de la planta a otro.

El taller contestó los de verdad —`ISC Machine Selection Rules DATA REQUEST -
FILLED.xlsx`, que es lo que hay en `taller_2026.json`— y son otros: 15.00 $/h,
1500 piezas/hora, y unos rangos de alambre que no se parecen a los que había.
Esa misma tabla es la que usa la calculadora, así que cargarla aquí es lo que
hace que las dos den el mismo número para la misma pieza.

Se genera en vez de escribirse a mano para que, cuando el taller vuelva a
contestar, sea `python scripts/generar_taller.py` y no una tarde de teclear:

    python scripts/generar_taller.py            # lo enseña
    python scripts/generar_taller.py --escribir # escribe la migración
"""

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "pricing" / "nucleo" / "taller_2026.json"
DESTINO = RAIZ / "sql" / "migrations" / "025_taller_2026.sql"

CATALOGO = RAIZ / "pricing" / "nucleo" / "catalogo.json"

# El objetivo de CCV por hora NO es el mismo múltiplo para todas: el catálogo
# lo dice en `machineParams` —bobinadoras x3, secundarias x5— y las 31 filas
# que ya había lo confirman (AIM 3000: 52.0833 x 3 = 156.2499; Grinder A:
# 11.1607 x 5 = 55.8035). Aplicar un 3 plano a las secundarias las dejaba en
# 45 en vez de 75.
MULTIPLOS_POR_DEFECTO = {"COILER": 3.0, "SECONDARY": 5.0}


def multiplos():
    """Los multiplicadores de CCV, del catálogo si está."""
    try:
        p = json.loads(CATALOGO.read_text(encoding="utf-8")).get("machineParams") or {}
    except OSError:
        return dict(MULTIPLOS_POR_DEFECTO)
    return {"COILER": float(p.get("coilerMult") or MULTIPLOS_POR_DEFECTO["COILER"]),
            "SECONDARY": float(p.get("secondaryMult") or MULTIPLOS_POR_DEFECTO["SECONDARY"])}


def norm(nombre):
    """El mismo normalizado que usa `reglas.js`: sin (FENN) y sin puntuación.

    Hace falta porque el taller escribe "TORIN W11A" y el catálogo guarda
    "TORIN (FENN) W11A". Son la misma máquina, y sin esto se crearían filas
    duplicadas que luego compiten entre sí al elegir.
    """
    s = str(nombre or "").upper().replace("(FENN)", "")
    return re.sub(r"[^A-Z0-9]", "", s)


def rank(m):
    """El puesto de la máquina en el orden de preferencia del taller.

    `usageRank` es el número que contestó Rodea. Menor = antes. Las
    secundarias no lo traen: no se eligen entre sí, las pide el plano.
    """
    v = m.get("usageRank")
    return None if v is None else int(v)


def lit(v):
    return "NULL" if v is None else ("%g" % v)


def main():
    datos = json.loads(DATOS.read_text(encoding="utf-8"))
    fuente = datos.get("fuente", "taller_2026.json")

    mult = multiplos()
    filas = [("COILER", m) for m in datos.get("coilers", [])]
    filas += [("SECONDARY", m) for m in datos.get("secondary", [])]

    out = []
    w = out.append
    w("-- 025_taller_2026.sql")
    w("--")
    w("-- GENERADO por scripts/generar_taller.py desde")
    w("-- pricing/nucleo/taller_2026.json. No editar a mano: se regenera.")
    w("--")
    w("-- Fuente de los números: %s" % fuente)
    w("--")
    w("-- Qué cambia y por qué importa")
    w("-- -----------------------------")
    w("-- Los valores que había salían de derivarlos del precio de compra de la")
    w("-- máquina. Los de aquí los contestó el taller. No se parecen:")
    w("--")
    w("--     TORIN W11A     antes 11.16 $/h, 600 pzs/h   ahora 15.00 $/h, 1500 pzs/h")
    w("--     Grinder A      antes 11.16 $/h, sin pzs/h   ahora 15.00 $/h,  500 pzs/h")
    w("--     Stationary Oven antes 8.93 $/h, sin pzs/h   ahora 10.00 $/h,  400 pzs/h")
    w("--")
    w("-- Y los rangos de alambre cambian de quién puede hacer qué: la W11A")
    w("-- figuraba sin rango capturado, y toma de 0.381 a 1.829 mm.")
    w("--")
    w("-- Es la MISMA tabla que usa la calculadora de la planta. Que las dos den")
    w("-- el mismo precio para la misma pieza depende de eso.")
    w("--")
    w("-- El objetivo de CCV/hora sale de `machineParams` del catálogo:")
    w("-- bobinadoras x%g, secundarias x%g." % (mult["COILER"], mult["SECONDARY"]))
    w("")
    w("-- Las máquinas se localizan por el nombre normalizado —sin (FENN) y sin")
    w("-- puntuación— porque el taller escribe «TORIN W11A» y el catálogo")
    w("-- «TORIN (FENN) W11A». Son la misma máquina.")
    w("CREATE OR REPLACE FUNCTION isc_norm_maquina(t text) RETURNS text AS $$")
    w("    SELECT regexp_replace(replace(upper(coalesce(t, '')), '(FENN)', ''),")
    w("                          '[^A-Z0-9]', '', 'g');")
    w("$$ LANGUAGE sql IMMUTABLE;")
    w("")

    for familia, m in filas:
        nombre = m.get("name")
        pph = m.get("pph")
        setup = m.get("setupH")
        labor = m.get("laborRateH")
        costo = m.get("machineRateH")
        w("-- %s (%s)" % (nombre, familia))
        w("UPDATE maquinas SET")
        w("    horas_setup = %s," % lit(setup))
        w("    pph_default = %s," % ("NULL" if pph is None else "%d" % int(pph)))
        w("    horas_labor = %s," % lit(labor))
        w("    scrap_pct = %s," % lit(m.get("scrapPct")))
        # El orden de preferencia de Rodea. La migración 013 creó la columna
        # y nadie la llenó nunca, así que la consulta de selección ordenaba
        # por COSTE —que es otra regla y da otra máquina—. Éste es el número
        # que hace que Pohua elija la misma que la calculadora.
        w("    orden_uso = %s" % ("NULL" if rank(m) is None else "%d" % rank(m)))
        w("  WHERE isc_norm_maquina(nombre) = %s;" % sql_txt(norm(nombre)))
        if costo is not None:
            w("UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE")
            w("  WHERE vigente_hasta IS NULL AND maquina_id IN")
            w("        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = %s)"
              % sql_txt(norm(nombre)))
            w("    AND vigente_desde < CURRENT_DATE;")
            w("DELETE FROM maquina_tarifas")
            w("  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN")
            w("        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = %s);"
              % sql_txt(norm(nombre)))
            w("INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)")
            w("  SELECT id, %s, %s, CURRENT_DATE FROM maquinas"
              % (lit(costo), lit(round(costo * mult[familia], 4))))
            w("   WHERE isc_norm_maquina(nombre) = %s;" % sql_txt(norm(nombre)))
        if familia == "COILER":
            w("UPDATE maquina_capacidades SET")
            w("    alambre_min_mm = %s," % lit(m.get("wireMinMm")))
            w("    alambre_max_mm = %s," % lit(m.get("wireMaxMm")))
            w("    od_max_mm = %s," % lit(m.get("odMaxMm")))
            w("    hace_compresion = %s," % sql_bool(m.get("capC")))
            w("    hace_extension = %s," % sql_bool(m.get("capE")))
            w("    hace_torsion = %s," % sql_bool(m.get("capT")))
            w("    hace_wireform = %s" % sql_bool(m.get("capW")))
            w("  WHERE maquina_id IN")
            w("        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = %s);"
              % sql_txt(norm(nombre)))
            w("INSERT INTO maquina_capacidades")
            w("       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,")
            w("        hace_compresion, hace_extension, hace_torsion, hace_wireform)")
            w("  SELECT m.id, %s, %s, %s, %s, %s, %s, %s FROM maquinas m"
              % (lit(m.get("wireMinMm")), lit(m.get("wireMaxMm")),
                 lit(m.get("odMaxMm")), sql_bool(m.get("capC")),
                 sql_bool(m.get("capE")), sql_bool(m.get("capT")),
                 sql_bool(m.get("capW"))))
            w("   WHERE isc_norm_maquina(m.nombre) = %s" % sql_txt(norm(nombre)))
            w("     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c")
            w("                      WHERE c.maquina_id = m.id);")
        w("")

    texto = "\n".join(out) + "\n"
    if "--escribir" in sys.argv[1:]:
        DESTINO.write_text(texto, encoding="utf-8")
        print("Escrita %s (%d máquinas)" % (DESTINO, len(filas)))
    else:
        print(texto)
    return 0


def sql_txt(s):
    return "'" + str(s).replace("'", "''") + "'"


def sql_bool(v):
    return "NULL" if v is None else ("true" if v else "false")


if __name__ == "__main__":
    raise SystemExit(main())
