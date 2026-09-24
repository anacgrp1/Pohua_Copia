#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""RETIRADO. El catálogo de costeo se carga con scripts/cargar_catalogo.py.

Este generador escribía una migración a partir de ficheros del núcleo que no
deben estar en el repositorio (precios de proveedor con fecha, clientes), y
duplicaba lo que ya hace cargar_catalogo.py desde el extracto validado:

    python scripts/cargar_catalogo.py --carpeta _extracto_catalogo --seco
    python scripts/cargar_catalogo.py --carpeta _extracto_catalogo
"""
import sys

if __name__ == "__main__":
    print(__doc__)
    sys.exit(1)
