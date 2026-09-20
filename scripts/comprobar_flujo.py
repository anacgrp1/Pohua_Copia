"""Antes de probar el flujo completo: ¿está todo puesto?

    python scripts/comprobar_flujo.py              # comprueba también el buzón
    python scripts/comprobar_flujo.py --sin-buzon  # sin tocar la red

Es la misma comprobación que enseña Pohua en **Perfil → Sistema** (la hace
``app/core/preflight.py``), dicha en la consola. Para el servidor desplegado
suele ser más cómodo mirarla en la aplicación: ahí no hay que abrir una
consola ni tener el `.env` a mano.

No manda correos, no marca nada como leído y no escribe en la base: sólo mira.
Devuelve 1 si falta algo que impida la prueba.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

MARCAS = {"ok": "  OK  ", "falta": " FALTA", "ojo": " OJO  "}


def main() -> int:
    # El informe lo escribe esto, línea a línea. Los módulos de debajo son
    # habladores —el proveedor de correo escupe la traza entera de un fallo de
    # red— y aquí eso sepulta la única línea que hay que leer.
    import logging
    logging.disable(logging.ERROR)

    import app.core.preflight as preflight

    informe = preflight.revisar(con_buzon="--sin-buzon" not in sys.argv)

    print("Comprobación del flujo — Pohua")
    print("=" * 40)

    grupo = None
    for punto in informe["puntos"]:
        if punto["grupo"] != grupo:
            grupo = punto["grupo"]
            print()
            print(grupo)
            print("-" * len(grupo))
        print(f"[{MARCAS.get(punto['estado'], '  ?   ')}] {punto['titulo']}")
        if punto["detalle"]:
            print(f"         {punto['detalle']}")

    print()
    print("Resumen")
    print("-------")
    if informe["listo"]:
        print("No falta nada para empezar la prueba.")
    else:
        print(f"Falta {informe['bloqueantes']} cosa(s) antes de poder probar:")
        for p in informe["puntos"]:
            if p["estado"] == "falta":
                print(f"  · {p['titulo']}")
    if informe["avisos"]:
        print(f"\nY {informe['avisos']} cosa(s) que conviene mirar:")
        for p in informe["puntos"]:
            if p["estado"] == "ojo":
                print(f"  · {p['titulo']}")
    print()
    return 0 if informe["listo"] else 1


if __name__ == "__main__":
    sys.exit(main())
