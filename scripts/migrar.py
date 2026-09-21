#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Pone el esquema de la base al día desde aquí, sin desplegar.

Para qué
--------
Las migraciones las aplicaba UNA sola cosa: el servidor web al arrancar
(``api/server.py``). Eso está bien mientras todo el mundo pase por ahí, pero
no es el caso: el lector de escritorio escribe en la misma base —planos,
resortes, la bandeja de salida— con el código de este repositorio. Si el
código va por delante del esquema, falla al guardar, y falla lejos: un plano
que no se guarda, una oferta que no se encola, y ningún mensaje que lo
relacione con una tabla que no existe.

Con esto se puede poner la base al día antes de desplegar, que es justo lo que
hace falta cuando se está probando el recorrido desde la computadora.

    python scripts/migrar.py            # dice qué falta, no toca nada
    python scripts/migrar.py --aplicar  # las aplica

Es lo mismo que corre el servidor: ``app/persistence/migraciones.py``. No hay
una segunda versión de la verdad, y aplicar dos veces no hace nada —cada
archivo queda registrado—.
"""

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)


def main() -> int:
    aplicar = "--aplicar" in sys.argv[1:]

    import app.persistence.migraciones as migraciones

    estado = migraciones.estado()
    if not estado.get("disponible"):
        print(f"No se pudo mirar la base: {estado.get('motivo')}")
        return 1

    aplicadas = estado.get("aplicadas") or []
    pendientes = estado.get("pendientes") or []

    print(f"\nAplicadas: {len(aplicadas)}")
    for nombre in aplicadas:
        print(f"   [ya]     {nombre}")

    if not pendientes:
        print("\nEl esquema está al día. No hay nada que aplicar.\n")
        return 0

    print(f"\nPendientes: {len(pendientes)}")
    for nombre in pendientes:
        print(f"   [falta]  {nombre}")

    if not aplicar:
        print("\nNo se ha aplicado nada. Con --aplicar se hace de verdad.\n")
        return 0

    print("\nAplicando…")
    resumen = migraciones.aplicar_pendientes()

    if not resumen.get("habilitado"):
        print("AUTO_MIGRAR está apagado en la configuración: no se aplicó nada.")
        return 1

    for nombre in resumen.get("aplicadas") or []:
        print(f"   [ok]     {nombre}")
    if resumen.get("error"):
        print(f"\nSe cortó: {resumen['error']}")
        print("Lo aplicado antes del corte queda hecho; vuelve a correrlo "
              "cuando esté resuelto.\n")
        return 1

    print("\nEsquema al día.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
