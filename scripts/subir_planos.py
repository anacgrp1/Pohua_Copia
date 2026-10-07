"""Sube a la base los planos que ya están en el disco, para no volver a pedirlos.

    python scripts/subir_planos.py              # enseña lo que subiría
    python scripts/subir_planos.py --subir      # lo sube de verdad
    python scripts/subir_planos.py --rfq INT-15E30DF2 --subir

Hasta ahora el dibujo adjunto se guardaba SÓLO en el disco de quien leyó el
correo: si lee el lector de escritorio, el fichero se queda en esa
computadora y la web —que corre en otro sitio— no lo tiene, así que "Abrir
cotización completa" no podía ponerlo en la casilla del lector de planos.

Desde la migración 021 el plano se guarda también en la base y lo ve todo el
mundo, pero eso vale para los correos que entren A PARTIR de ahora. Los RFQ de
antes tienen su plano en `planos/<rfq_id>/` y en ningún otro sitio. Esto los
sube de una vez, sin tener que reenviar correos ni arrastrar ficheros a mano.

Se puede repetir: un plano que ya está se sustituye, no se duplica.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)          # el .env vive aquí, se lance desde donde se lance

# Lo que el lector de planos sabe abrir. Lo demás (un .xlsx con la orden, la
# firma del comprador) no es un plano y no hay por qué moverlo.
_EXTENSIONES = {".pdf", ".png", ".jpg", ".jpeg"}

# Sólo carpetas de RFQ de verdad. Las pruebas dejaban en `planos/` cosas como
# «RFQ-1» (un «plano.pdf» de 9 bytes); subirlas metía en Neon planos de un RFQ
# que no existe (2026-10).
_RFQ_REAL = re.compile(r"^INT-[0-9A-F]{8}$")


def _opcion(argumentos, nombre, por_defecto=None):
    if nombre in argumentos:
        i = argumentos.index(nombre)
        if i + 1 < len(argumentos):
            return argumentos[i + 1]
    return por_defecto


def main() -> int:
    argumentos = sys.argv[1:]
    subir = "--subir" in argumentos
    uno = _opcion(argumentos, "--rfq")

    import app.core.config as config
    import app.persistence.blueprint_store as almacen

    base = Path(getattr(config.settings, "PLANOS_DIR", None) or "planos")
    if not base.is_dir():
        print(f"No hay carpeta de planos en {base.resolve()}.")
        return 0

    todas = sorted(c for c in base.iterdir() if c.is_dir())
    carpetas = [c for c in todas if _RFQ_REAL.match(c.name)]
    ignoradas = [c.name for c in todas if c not in carpetas]
    if ignoradas:
        print(f"Se ignoran {len(ignoradas)} carpeta(s) que no son de un RFQ real: "
              f"{', '.join(ignoradas)}")
    if uno:
        carpetas = [c for c in carpetas if c.name == almacen._slug(uno)]
        if not carpetas:
            print(f"No hay planos guardados de {uno}.")
            return 0

    total_ficheros = 0
    total_subidos = 0
    for carpeta in carpetas:
        rfq_id = carpeta.name
        ficheros = [f for f in sorted(carpeta.iterdir())
                    if f.is_file() and f.suffix.lower() in _EXTENSIONES]
        if not ficheros:
            continue

        ya = {p["nombre"] for p in almacen.listar_de_base(rfq_id)}
        print(f"\n{rfq_id}")
        adjuntos = []
        for f in ficheros:
            total_ficheros += 1
            marca = "ya está" if f.name in ya else "sube"
            print(f"   {f.name:45} {f.stat().st_size:>9,} B   {marca}")
            adjuntos.append({"nombre": f.name, "contenido": f.read_bytes()})

        if subir:
            subidos = almacen.guardar_en_base(rfq_id, adjuntos)
            total_subidos += subidos

    if not total_ficheros:
        print("No se encontró ningún plano en el disco.")
        return 0

    if not subir:
        print(f"\n{total_ficheros} plano(s) en disco. No se ha subido nada: "
              f"con --subir se hace de verdad.")
    else:
        print(f"\nHecho: {total_subidos} de {total_ficheros} plano(s) en la base.")
        if total_subidos < total_ficheros:
            print("Los que no subieron pesan más de 8 MB o la base no respondió; "
                  "mira el registro.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
