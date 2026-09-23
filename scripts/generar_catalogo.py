#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Genera la migración del catálogo de compra: precios de alambre y cajas.

Por qué existe
--------------
Pohua tenía la tabla `material_precios` VACÍA —cero filas de 186— y dos cajas
de dieciséis. No fallaba: simplemente cotizaba sin precio de alambre y sin
empaque, que son dos de las líneas del P&L.

El 004-222 lo enseña bien. El alambre es Music Wire de .039": en el catálogo
son 1.80 $/lb, que es el número que sale en la pantalla buena. Sin esa fila,
el precio base del material queda a lo que alguien teclee. Y la caja del
tramo es la COR11050 —11-1/4 x 8-3/4 x 12, 0.83 $— que en Pohua no existía,
así que el empaque salía en cero.

Los precios van por CALIBRE, no por material: el mismo Music Wire vale 2.80
a .020" y 1.80 a .039". Cargar sólo el material sin el calibre no sirve.

    python scripts/generar_catalogo.py            # lo enseña
    python scripts/generar_catalogo.py --escribir # escribe la migración
"""

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "pricing" / "nucleo" / "catalogo.json"
DESTINO = RAIZ / "sql" / "migrations" / "026_catalogo_compra.sql"


def txt(s):
    return "'" + str(s).replace("'", "''") + "'"


def num(v):
    return "NULL" if v is None else ("%g" % float(v))


def main():
    datos = json.loads(DATOS.read_text(encoding="utf-8"))
    precios = datos.get("materialPrices") or []
    cajas = datos.get("packing") or []

    out = []
    w = out.append
    w("-- 026_catalogo_compra.sql")
    w("--")
    w("-- GENERADO por scripts/generar_catalogo.py desde")
    w("-- pricing/nucleo/catalogo.json. No editar a mano: se regenera.")
    w("--")
    w("-- Qué llena y por qué faltaba")
    w("-- ---------------------------")
    w("-- `material_precios` estaba VACÍA —cero filas— y `empaques` tenía dos")
    w("-- de las dieciséis cajas. No fallaba nada: se cotizaba sin precio de")
    w("-- alambre y sin empaque, que son dos líneas del P&L.")
    w("--")
    w("-- Los precios van por CALIBRE, no por material: el mismo Music Wire")
    w("-- vale 2.80 $/lb a .020\" y 1.80 a .039\". El 004-222 es .039\", y 1.80")
    w("-- es el número que sale en la pantalla correcta.")
    w("--")
    w("-- La caja de ese tramo es la COR11050, que en Pohua no existía.")
    w("--")
    w("-- %d precios, %d empaques." % (len(precios), len(set(c["id"] for c in cajas))))
    w("")
    w("BEGIN;")
    w("")
    w("-- Las cajas. Se reemplazan por código: el catálogo manda.")

    vistas = set()
    for c in cajas:
        cod = c.get("id")
        if not cod or cod in vistas:
            continue          # el catálogo trae "barrels no lids" dos veces
        vistas.add(cod)
        w("DELETE FROM empaques WHERE codigo = %s;" % txt(cod))
        w("INSERT INTO empaques (codigo, descripcion, precio, unidad, activo)")
        w("  VALUES (%s, %s, %s, %s, true);"
          % (txt(cod), txt(c.get("desc") or cod), num(c.get("price")),
             txt(c.get("uom") or "EACH")))
    w("")
    w("-- Los precios de alambre, por material y calibre. Se borra el calibre")
    w("-- entero antes de meterlo: si no, al regenerar quedarían dos precios")
    w("-- para el mismo alambre y ganaría el que saliera primero.")

    n = 0
    for p in precios:
        cod = p.get("code")
        dia = p.get("dia")
        precio = p.get("latest")
        if not cod or dia is None or precio is None:
            continue
        n += 1
        w("DELETE FROM material_precios WHERE diam_pulg = %s AND material_id IN"
          % num(dia))
        w("       (SELECT id FROM materiales WHERE codigo = %s);" % txt(cod))
        w("INSERT INTO material_precios")
        w("       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)")
        w("  SELECT id, %s, %s, %s, %s, %s FROM materiales WHERE codigo = %s;"
          % (num(dia), num(precio), num(p.get("qtyLb")),
             txt(p.get("date") or "2026-01-01"), txt(p.get("sup") or ""),
             txt(cod)))
    w("")
    w("COMMIT;")

    texto = "\n".join(out) + "\n"
    if "--escribir" in sys.argv[1:]:
        DESTINO.write_text(texto, encoding="utf-8")
        print("Escrita %s (%d precios, %d empaques)" % (DESTINO, n, len(vistas)))
    else:
        print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
