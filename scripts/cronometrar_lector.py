#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cuánto tarda cada modelo en leer TU plano, y qué saca cada uno.

Para qué
--------
"El lector va lento" y "el lector lee bien" tiran en direcciones contrarias, y
la respuesta correcta no es la misma para todos los planos: depende de cuán
acotado esté el tuyo. Elegir a ojo sale caro en los dos sentidos —un modelo
lento que nadie espera, o uno rápido que deja cotas sin leer y para el RFQ—.

Esto lee el MISMO plano con varios modelos y enseña, uno al lado del otro,
cuánto tardó y qué cotas sacó. Con eso se decide con datos.

    python scripts/cronometrar_lector.py --rfq INT-097CBB6A
    python scripts/cronometrar_lector.py --plano C:\\ruta\\al\\dibujo.pdf
    python scripts/cronometrar_lector.py --rfq INT-097CBB6A --modelos claude-sonnet-5

Gasta una llamada por modelo. No guarda nada: no toca `resortes_cotizacion`
ni el RFQ, sólo mide.
"""

import argparse
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)

# De más capaz a más rápido. El orden importa para leer la tabla.
MODELOS = ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5-20251001"]

# Lo que de verdad decide si un RFQ se puede cotizar.
CLAVE = [("diametro_alambre_mm", "alambre"),
         ("diametro_exterior_mm", "exterior"),
         ("diametro_interior_mm", "interior"),
         ("longitud_libre_mm", "libre"),
         ("numero_espiras_totales", "esp.tot"),
         ("numero_espiras_activas", "esp.act")]


def planos_del_rfq(rfq_id):
    import app.rfq.relectura as relectura
    planos = relectura.planos_guardados(rfq_id)
    return relectura.legibles(planos)


def plano_de_disco(ruta):
    p = Path(ruta)
    if not p.is_file():
        print(f"No existe: {ruta}\n")
        return []
    return [{"nombre": p.name, "contenido": p.read_bytes()}]


def una_pasada(archivos, modelo):
    """Lee con ese modelo. Devuelve (segundos, datos, error)."""
    import app.core.config as config
    import app.vision.pipeline as pipeline
    import app.vision.spring_extractor as extractor

    antes = config.settings.VISION_MODEL
    config.settings.VISION_MODEL = modelo
    reloj = time.perf_counter()
    try:
        analisis = pipeline.analizar_dibujos(archivos)
        datos = extractor.interpretar(analisis["texto"])
        return time.perf_counter() - reloj, datos, None
    except Exception as e:
        return time.perf_counter() - reloj, None, str(e)[:120]
    finally:
        config.settings.VISION_MODEL = antes


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rfq", help="lee el plano guardado de ese RFQ")
    p.add_argument("--plano", help="lee un archivo de disco")
    p.add_argument("--modelos", help="lista separada por comas")
    args = p.parse_args()

    if not args.rfq and not args.plano:
        print("\nHace falta --rfq o --plano.\n")
        return 2

    modelos = ([m.strip() for m in args.modelos.split(",") if m.strip()]
               if args.modelos else MODELOS)

    try:
        archivos = (plano_de_disco(args.plano) if args.plano
                    else planos_del_rfq(args.rfq))
    except Exception as e:
        print(f"\nNo se pudo tomar el plano: {e}\n")
        return 1

    if not archivos:
        print("\nNo hay ningún plano legible que medir.\n")
        return 1

    nombres = ", ".join(a["nombre"] for a in archivos)
    pesos = sum(len(a["contenido"]) for a in archivos)
    print(f"\nPlano: {nombres}  ({pesos/1024:.0f} KB)")
    print(f"Modelos: {', '.join(modelos)}")
    print("Una llamada por modelo. No se guarda nada.\n")

    filas = []
    for modelo in modelos:
        print(f"  leyendo con {modelo}…", flush=True)
        segundos, datos, error = una_pasada(archivos, modelo)
        filas.append((modelo, segundos, datos, error))

    cab = f"\n{'modelo':<28}{'seg':>7}  " + "".join(f"{e:>9}" for _, e in CLAVE)
    print(cab)
    print("-" * len(cab))
    for modelo, segundos, datos, error in filas:
        if error:
            print(f"{modelo:<28}{segundos:>7.1f}  falló: {error}")
            continue
        celdas = ""
        for campo, _ in CLAVE:
            v = datos.get(campo)
            celdas += f"{'—' if v in (None, '') else f'{v:g}':>9}"
        print(f"{modelo:<28}{segundos:>7.1f}  {celdas}")

    print()
    buenos = [(m, s, d) for m, s, d, e in filas if d]
    if not buenos:
        print("Ninguno leyó. El plano o la clave son el problema, no el modelo.\n")
        return 1

    def cuantas(d):
        return sum(1 for c, _ in CLAVE if d.get(c) not in (None, ""))

    mejor = max(cuantas(d) for _, _, d in buenos)
    iguales = [(m, s) for m, s, d in buenos if cuantas(d) == mejor]
    if len(iguales) > 1:
        rapido = min(iguales, key=lambda x: x[1])
        lento = max(iguales, key=lambda x: x[1])
        print(f"Sacan lo mismo ({mejor} de {len(CLAVE)} cotas). El más rápido "
              f"es {rapido[0]} con {rapido[1]:.1f} s, "
              f"frente a {lento[1]:.1f} s.")
        print("Si esto se repite con dos o tres planos más, el rápido es el "
              "que toca: VISION_MODEL en el .env y en Render.\n")
    else:
        m, s = iguales[0]
        print(f"{m} saca más cotas que los demás ({mejor} de {len(CLAVE)}) "
              f"en {s:.1f} s. La lentitud se está pagando por algo.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
