#!/usr/bin/env python3
"""Genera los iconos de la aplicación a partir de `frontend/assets/icon.png`.

QUÉ HACE, EN UNA FRASE
----------------------
Coge el icono de marca y lo saca en los siete tamaños que pide la web y la PWA.
Nada más: NO recorta, NO recompone, NO cambia el encuadre. Decisión de ISC —el
icono es el que entregó diseño y se ve igual en todas partes—, y por eso este
script es corto: sólo escala.

Los siete no son un capricho; cada destino pide el suyo:

    icon-192 / icon-512          los del manifest, `purpose: any`. La web.
    icon-maskable-192 / -512     `purpose: maskable`. La aplicación instalada
                                 en Android: su pantalla de inicio y su
                                 pantalla de arranque.
    apple-touch-icon             iOS, que no lee el manifest.
    favicon-32 / favicon-48      la pestaña del navegador.

EL ICONO ES EL ARCHIVO, FILO BLANCO INCLUIDO. `icon.png` viene con la forma de
squircle y un filo blanco alrededor, y ese filo es parte del icono: tiene que
verse en la pestaña, en la web, en la pantalla de arranque y en la de inicio.

Lo que complica el asunto es que ese filo está pegado al borde del archivo, y
la pantalla de inicio de Android y el icono de iOS recortan el icono con su
propia forma. Ver SALIDAS: ahí está cómo se le da a cada uno lo que necesita
para que el filo llegue entero.

Cambiar el icono de la aplicación es sustituir `frontend/assets/icon.png` y
volver a ejecutar esto. Los siete archivos NO se editan a mano: se regeneran.

Uso:
    python3 scripts/generar_iconos.py
    python3 scripts/generar_iconos.py --hoja   # deja una hoja de contactos
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Falta Pillow. Instálalo con: pip install Pillow")

RAIZ = Path(__file__).resolve().parent.parent
ASSETS = RAIZ / "frontend" / "assets"

FUENTE = ASSETS / "icon.png"

BLANCO = (255, 255, 255, 255)

#: Lo que el sistema hace con el icono decide cómo hay que entregárselo.
#:
#: DONDE NADIE RECORTA —la pestaña, la web, la pantalla de arranque— el icono
#: va al 100 % y con sus esquinas transparentes: es el archivo, tal cual, con
#: su silueta de squircle y su filo blanco.
#:
#: DONDE EL SISTEMA RECORTA —la pantalla de inicio de Android y el icono de
#: iOS— hacen falta dos cosas:
#:
#:   1. Un cuadrado OPACO de donde recortar. Las esquinas transparentes del
#:      original se rellenan de blanco; el recorte cae justo ahí, así que ese
#:      blanco no llega a verse.
#:   2. En Android, además, holgura. Y este número NO es a ojo, que es donde me
#:      equivoqué dos veces: la especificación de `maskable` sólo garantiza lo
#:      que cae dentro del CÍRCULO central del 80 % del lado, porque cada
#:      fabricante usa la forma que quiere. Midiendo la silueta de `icon.png`,
#:      su punto más lejano está a 1.101 veces el medio-lado (el filo blanco
#:      llega al canto), así que la escala máxima con la que TODO cabe en ese
#:      círculo es 0.80 / 1.101 = 0.727. Por debajo de eso no hay máscara que
#:      pueda cortar el filo; por encima, alguna lo corta —y lo cortaba—.
#:
#: A iOS no se le aplica esa regla: su curva es un cuadrado redondeado de radio
#: ~22 % y, medida contra la silueta, no llega a tocar el dibujo ni al 100 %.
#: Así que ahí el icono va entero, sin encoger.
ESCALA_ANDROID = 0.72      # 0.727 redondeado hacia abajo

#: (archivo, lado, proporción, ¿rellenar de blanco?)
SALIDAS = [
    ("icon-192.png", 192, 1.00, False),
    ("icon-512.png", 512, 1.00, False),
    ("icon-maskable-192.png", 192, ESCALA_ANDROID, True),
    ("icon-maskable-512.png", 512, ESCALA_ANDROID, True),
    ("apple-touch-icon.png", 180, 1.00, True),
    ("favicon-32.png", 32, 1.00, False),
    ("favicon-48.png", 48, 1.00, False),
]


def componer(fuente: Image.Image, lado: int, proporcion: float,
             rellenar: bool) -> Image.Image:
    """El icono al tamaño pedido, centrado.

    LANCZOS y no el redimensionado por defecto: bajar de 2600 a 32 px con un
    filtro pobre convierte las teclas de la calculadora en una papilla gris.
    """
    caja = max(1, round(lado * proporcion))
    puesto = fuente.resize((caja, caja), Image.LANCZOS)
    if caja == lado and not rellenar:
        return puesto
    fondo = BLANCO if rellenar else (255, 255, 255, 0)
    lienzo = Image.new("RGBA", (lado, lado), fondo)
    lienzo.alpha_composite(puesto, ((lado - caja) // 2, (lado - caja) // 2))
    return lienzo


def hoja_de_contactos(rutas, destino: Path) -> None:
    """Todos los iconos juntos y al tamaño real, sobre un fondo OSCURO.

    Oscuro a propósito: sobre blanco no se ve si a un icono le sobra un margen
    blanco, y es justo donde acaban —la pestaña del navegador y la pantalla de
    inicio de un teléfono suelen serlo—. Mirarlos pequeños y sobre oscuro es la
    única forma de saber si un icono funciona.
    """
    fondo = (20, 25, 40)
    anchos = [min(Image.open(r).width, 192) for r in rutas]
    hoja = Image.new("RGB", (40 + sum(w + 24 for w in anchos), 252), fondo)
    x = 20
    for ruta, ancho in zip(rutas, anchos):
        im = Image.open(ruta).convert("RGBA")
        if im.width > ancho:
            im = im.resize((ancho, ancho), Image.LANCZOS)
        detras = Image.new("RGBA", im.size, fondo + (255,))
        hoja.paste(Image.alpha_composite(detras, im).convert("RGB"), (x, 30))
        x += ancho + 24
    hoja.save(destino)


def main() -> None:
    if not FUENTE.is_file():
        sys.exit(f"No encuentro {FUENTE}")

    fuente = Image.open(FUENTE).convert("RGBA")
    if fuente.width != fuente.height:
        print(f"  aviso: {FUENTE.name} no es cuadrada ({fuente.size}); "
              f"se estirará al escalar.")

    generados = []
    for nombre, lado, proporcion, rellenar in SALIDAS:
        ruta = ASSETS / nombre
        componer(fuente, lado, proporcion, rellenar).save(ruta, optimize=True)
        generados.append(ruta)

    for r in generados:
        im = Image.open(r)
        print(f"  {r.relative_to(RAIZ)}  {im.size[0]}x{im.size[1]}  "
              f"{r.stat().st_size // 1024} KB")

    if "--hoja" in sys.argv:
        destino = RAIZ / "iconos-hoja.png"
        hoja_de_contactos(generados, destino)
        print(f"  hoja de contactos: {destino}")


if __name__ == "__main__":
    main()
