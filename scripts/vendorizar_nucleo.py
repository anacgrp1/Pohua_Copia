#!/usr/bin/env python3
"""Trae el núcleo de cotización al Cotizador, para que Render no lo necesite.

    python scripts/vendorizar_nucleo.py --revisar     # dice qué haría
    python scripts/vendorizar_nucleo.py

EL PROBLEMA QUE RESUELVE. El motor de coste, el lector de planos y las dos
calculadoras viven en `dasniela/ISCQuotingCore`, que es **privado**. Dar acceso
de lectura a una persona no se lo da al build: la máquina que construye en
Render no tiene sesión de GitHub, así que cualquier forma de traérselo desde
allí —`pip install` desde git, un submódulo— necesita un token que alguien crea,
guarda y renueva, y el día que caduca el despliegue deja de construir.

Este script hace que no haga falta: copia el núcleo **dentro** de este
repositorio y anota de qué commit salió. A partir de ahí Render construye con lo
que hay en el repositorio y ya está.

LO QUE SÍ SE COPIA Y LO QUE NO. Se copia **código**: los tres `.js` del motor,
el paquete `isc_extractor` y el servidor del lector. Todo eso es lógica, se lee
en una revisión y no dice nada de nadie.

Lo que **no** se copia es el catálogo. Los dos HTML de la calculadora lo llevan
incrustado —412 clientes, 186 precios de proveedor con fecha y 116 registros de
lo que ISC paga por recubrir— y por eso el núcleo prohíbe que entren a ningún
repositorio. Aquí se vacían al copiarlos, que es lo que los vuelve
commiteables: desde que el catálogo vive en Neon, la calculadora lo recibe al
abrirse (`frontend/js/isc-nube.js`) y la copia incrustada ya no pinta nada.

Se conserva sólo lo que es vocabulario y física —los nombres de material y las
constantes elásticas—, que no son datos de ISC y que el cálculo del resorte
necesita para arrancar.

EL PRECIO DE ESTO. Una copia es lo que el núcleo existe para evitar: dos
versiones del mismo motor acaban dando dos precios de la misma pieza. Por eso el
script escribe `vendor/NUCLEO_SHA.txt` con el commit de origen y la fecha, y por
eso conviene volver a pasarlo cuando el núcleo cambie. La copia sin fecha es la
que se queda atrás sin que nadie lo note.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

RAIZ = Path(__file__).resolve().parent.parent
CLON = RAIZ / "ISCQuotingCore"

# Dónde queda cada pieza dentro de este repositorio.
DESTINO_JS = RAIZ / "pricing" / "nucleo"
DESTINO_EXTRACTOR = RAIZ / "vendor" / "isc_extractor"
DESTINO_LECTOR = RAIZ / "vendor" / "lector"
# Las calculadoras van al LADO del lector y no bajo frontend/ porque quien las
# sirve es él: su `buscar_html()` mira en su carpeta padre y en `calculadora/`
# de esa carpeta, exactamente como en el núcleo. Ponerlas en otro sitio
# obligaría a tocar su código, que es lo que esta copia existe para no hacer.
DESTINO_HTML = RAIZ / "vendor" / "calculadora"
SELLO = RAIZ / "vendor" / "NUCLEO_SHA.txt"

MOTOR = ["engine.js", "reglas.js", "resortes.js"]
LECTOR = ["app.py", "quote_pdf.py", "config.json"]
CALCULADORAS = ["ISC Price Calculator V7 to Automate.html",
                "Spring Engineering Calculator V2.html"]

# Las marcas que pone `apps/calculadora/construir.py` alrededor del catálogo.
# Se buscan literalmente: si el núcleo las cambia, este script para y lo dice,
# en vez de copiar el HTML con los datos dentro creyendo que los quitó.
MARCA_INI = "/* ===== DATOS: generado desde nucleo/datos/catalogo.json — no editar aqui ===== */"
MARCA_FIN = "/* ===== fin de los datos ===== */"

# El Spring Engineering Calculator lleva SUS PROPIOS bloques generados, con
# otras marcas, y se copian enteros. Conviene saber por qué y no confundirlo
# con "no lleva datos":
#
#   MATERIALES (3 KB)  MAT_DEFAULTS: G, E, densidad, factores de corte y
#                      flexión. Física, la misma en cualquier taller.
#   MAQUINAS   (7 KB)  MCH_DEFAULTS: rangos de alambre, OD, qué tipos hace...
#                      y `rateH`, el costo por hora de cada máquina.
#
# `rateH` es dato interno de ISC, sí. Pero ya estaba en este repositorio: la
# copia vieja del motor, `pricing/engine.js` (retirada en 2026-09), llevaba
# `costRateH` de las 30 máquinas en su SEED, sigue en el historial de git, y
# de ahí salió la migración 007. Conservarlo no expone nada nuevo.
#
# Y vaciarlo rompería algo real: a diferencia de la calculadora de precios,
# este HTML NO recibe el catálogo de Neon —el adaptador reemplaza el documento
# de la otra— así que sin `MCH_DEFAULTS` se queda sin poder decir qué máquina
# puede hacer el resorte.
MARCAS_SPRING = [
    ("/* ===== MATERIALES: generado desde nucleo/datos/catalogo.json — no editar aqui ===== */",
     "/* ===== fin de los materiales ===== */", "MAT_DEFAULTS (física)"),
    ("/* ===== MAQUINAS: generado desde nucleo/datos/catalogo.json — no editar aqui ===== */",
     "/* ===== fin de las maquinas ===== */", "MCH_DEFAULTS (capacidades + rateH)"),
]

# Qué se queda del catálogo incrustado.
#
# La regla no es "lo pequeño": es que sea VOCABULARIO O FÍSICA y no un dato de
# ISC. `matReference` son constantes elásticas —el módulo de rigidez de un
# alambre es el mismo en cualquier taller del mundo— y sin ellas el Spring
# Calculator no puede calcular una fuerza al abrirse. `materialLegend` son los
# nombres de los materiales.
#
# Todo lo demás se vacía: clientes, precios, historial de recubrimiento,
# máquinas (que llevan lo que costaron y su tarifa por hora), empaques,
# subcontratistas y las cuentas de la calculadora, que además ya no se usan
# porque quien entra lo dice Pohua.
CONSERVAR = {"matReference", "materialLegend", "machineParams", "surchargeAppliesTo"}


def sha_del_clon() -> Optional[str]:
    if not (CLON / ".git").exists():
        return None
    try:
        r = subprocess.run(["git", "-C", str(CLON), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=15, check=True)
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def vaciar_catalogo(html: str, nombre: str, hechos: List[str]) -> str:
    """Devuelve el HTML con el catálogo incrustado vacío.

    Si no encuentra las marcas no se inventa nada: levanta. Copiar el HTML tal
    cual sería publicar la cartera de clientes en un repositorio, y hacerlo en
    silencio es peor que no copiarlo.
    """
    a = html.find(MARCA_INI)
    b = html.find(MARCA_FIN)
    if a < 0 or b < 0 or b < a:
        # No es el de precios. Se copia entero, pero se dice qué lleva dentro:
        # llamarlo "sin catálogo" sería falso y taparía una decisión.
        propios = [etiqueta for ini, fin, etiqueta in MARCAS_SPRING
                   if html.find(ini) >= 0 and html.find(fin) > html.find(ini)]
        if propios:
            hechos.append(f"    {nombre}: se copia entero.")
            hechos.append(f"      lleva      {', '.join(propios)}")
            hechos.append("      sin        clientes, precios de proveedor ni "
                          "historial de recubrimiento")
        else:
            hechos.append(f"    {nombre}: sin bloques generados, se copia entero.")
        return html

    crudo = html[a + len(MARCA_INI):b].strip()
    m = re.match(r"^const\s+SEED\s*=\s*(.*);?\s*$", crudo, re.S)
    if not m:
        raise SystemExit(
            f"{nombre}: el bloque de datos ya no declara `const SEED`. "
            "Revisa construir.py del núcleo antes de seguir: sin entender el "
            "bloque no se puede garantizar que el catálogo salga fuera.")

    seed = json.loads(m.group(1).rstrip(";"))
    vaciadas, conservadas = [], []
    limpio: Dict[str, object] = {}
    for clave, valor in seed.items():
        if clave in CONSERVAR:
            limpio[clave] = valor
            conservadas.append(f"{clave} ({len(valor) if isinstance(valor,(list,dict)) else 1})")
        elif isinstance(valor, list):
            limpio[clave] = []
            vaciadas.append(f"{clave} ({len(valor)})")
        elif isinstance(valor, dict):
            limpio[clave] = {}
            vaciadas.append(f"{clave} ({len(valor)})")
        else:
            limpio[clave] = valor

    nuevo = ("\n/* El catálogo va VACÍO a propósito. Los datos los pone Pohua\n"
             "   desde Neon al abrir la calculadora (frontend/js/isc-nube.js).\n"
             "   Sólo se conserva lo que es física y vocabulario: sin las\n"
             "   constantes elásticas el cálculo del resorte no arranca. */\n"
             "const SEED = " + json.dumps(limpio, ensure_ascii=False) + ";\n")

    hechos.append(f"    {nombre}:")
    hechos.append(f"      vaciado    {', '.join(vaciadas) or '—'}")
    hechos.append(f"      conservado {', '.join(conservadas) or '—'}")
    hechos.append(f"      el bloque pasa de {len(crudo)//1024} KB a {len(nuevo)//1024} KB")
    return html[:a + len(MARCA_INI)] + nuevo + html[b:]



# ---------------------------------------------------------------------------
# Adaptación al tema de Pohua
# ---------------------------------------------------------------------------
#
# Las calculadoras están escritas sobre papel blanco: `background:#fff`,
# `color:#1F2937`, avisos en pastel. Dentro de Pohua eso es una mancha blanca
# en medio del modo oscuro, y al recargar se ve un instante antes de que nada
# pueda corregirlo.
#
# La corrección NO se hace persiguiendo selectores desde fuera —son cientos, y
# cada versión del núcleo trae unos nuevos—. Se hace aquí: al vendorizar, cada
# color literal del CSS se cambia por una variable `--n-*` que `isc-tema.js`
# define leyendo el tema del padre. El HTML generado no se edita a mano nunca;
# si hay que cambiar algo, se cambia esta función y se vuelve a vendorizar.
#
# Qué NO se toca, y por qué:
#   · La marca (#1B3D79 navy, #148EC2 cyan, #D67C2F naranja, #A4AE2D verde).
#     Son los mismos tonos que Pohua ya usa: la cabecera azul y las cabeceras
#     de tabla se ven igual en los dos temas, y así deben verse.
#   · El blanco que va ENCIMA de la marca: el rótulo de la cabecera navy, el
#     borde de los botones del topbar, el `border-top-color` del spinner que
#     gira sobre un botón de color. Ese blanco está bien en los dos temas.
#     Por eso `#fff` sólo se cambia cuando es FONDO —ahí es papel—; como
#     texto o como línea se queda.
#   · El `:root` de la calculadora. Se lee (es la fuente autorizada de qué
#     tono es cada aviso) pero no se reescribe: esos nombres los redefine
#     `isc-tema.js` en tiempo de ejecución.

# Los nombres que las calculadoras declaran en su propio `:root`.
#
# Si el CSS dice `--crit:#c0392b`, ese rojo es "crítico" en ESTA hoja, y el
# `#C0392B` suelto de `.badge.LOST` es el mismo aviso aunque por matiz —está
# justo en la frontera— pudiera pasar por naranja.
POR_NOMBRE = {
    "warn": "mal", "crit": "mal", "error": "mal",
    "orange": "avi", "gold": "avi", "goldline": "avi",
    "ok": "ok", "green": "ok", "success": "ok",
    "cyan": "info", "info": "info", "accent": "info",
    "navy": "marca", "accent-deep": "marca",
    "ink": "tinta", "ink-soft": "apagado", "muted": "apagado", "grey": "apagado",
    "line": "linea", "line-strong": "linea",
    "bg": "papel", "panel": "papel",
}

_AVISOS = ("ok", "avi", "mal", "info")

# Un color cuenta como "de color" cuando sus canales se separan al menos esto.
#
# Se mide con CROMA (max-min), no con la saturación de HSL. La saturación
# miente en los extremos: #f7f9fb —cuatro puntos entre canales, un gris de
# papel a simple vista— da saturación 0.33, y con eso se iba a "azul de
# información". Su croma es 4, y con este umbral se queda en los grises.
CROMA_TONO = 12

# A partir de aquí un color es un tono PLENO, no un pastel. Sólo los plenos se
# comparan contra los avisos declarados: un pastel siempre queda más cerca del
# crema de `--gold` que de su propia familia, y comparándolo se iban todos los
# avisos al ámbar. Los pasteles se deciden por matiz, que en ellos acierta.
CROMA_PLENO = 60

# Cuánto puede alejarse un color de uno declarado y seguir siendo el mismo.
CERCA_TONO = 60      # entre tonos plenos
CERCA_GRIS = 50      # entre grises: #374151 es la misma tinta que #1F2937

# Dos grises son el mismo gris si además su croma no se separa más que esto.
CROMA_GEMELO = 6

# Un texto más claro que esto no está escrito sobre papel: es un rótulo encima
# de una superficie de color —`#CBD5E8` son las pestañas sobre la cabecera
# navy—. Cambiarlo por una tinta de tema lo borra del sitio donde vive.
LUZ_ROTULO = 150

# Y un FONDO más oscuro que esto no es un tinte: es un relleno sólido —la barra
# llena de una gráfica, una placa de color—. Convertirlo al tinte del 14 % lo
# dejaba casi invisible sobre su propio carril. Esos van al tono pleno.
LUZ_RELLENO = 150

# El papel del color según la propiedad donde aparece.
_ROL = {
    "background": "fondo", "background-color": "fondo",
    "border": "linea", "border-color": "linea",
    "border-top": "linea", "border-right": "linea",
    "border-bottom": "linea", "border-left": "linea",
    "border-top-color": "linea", "border-right-color": "linea",
    "border-bottom-color": "linea", "border-left-color": "linea",
    "outline": "linea", "outline-color": "linea", "stroke": "linea",
    "color": "tinta", "fill": "tinta",
}

# Qué nombres de chasis puede tomar cada rol. Sin esto, `#e9eef3` —un fondo
# gris— se iba a `--n-linea` por parecerse a `--line:#E2E8F0`.
_GRIS_POR_ROL = {"fondo": ("papel",), "linea": ("linea",),
                 "tinta": ("tinta", "apagado")}

# La marca, intacta.
MARCA = {
    (0x1B, 0x3D, 0x79), (0x14, 0x8E, 0xC2), (0xD6, 0x7C, 0x2F),
    (0xA4, 0xAE, 0x2D), (0x1F, 0x5F, 0xA8), (0x14, 0x3A, 0x66),
}

_HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
_REGLA = re.compile(r"(?P<sel>[^{}]*)\{(?P<cuerpo>[^{}]*)\}")
_DECL = re.compile(
    r"(?P<prop>[a-zA-Z-]+)\s*:\s*(?P<valor>[^;{}]*?"
    r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b[^;{}]*?)(?=\s*[;}!]|\s*$)")

# El suelo de la página: su fondo es el de Pohua, no el de una tarjeta.
_SUELO = re.compile(r"(^|[\s,])(html|body)([\s,.:#\[]|$)")

# La placa del logo. Es blanca a propósito y en los dos temas: el logotipo de
# ISC está hecho para ir sobre blanco, y es la misma excepción que Pohua se
# permite ("el único blanco que queda es la placa de los logos, y ese es de
# marca"). Va aquí y no en una regla general porque no hay forma de deducirlo
# del color: hay que saber qué es.
_PLACA = re.compile(r"logo|\.brand\b", re.I)

# Una regla que escribe en blanco está pintando sobre color sólido.
_BLANCO = re.compile(r"color\s*:\s*(#fff\b|#ffffff\b|white\b|rgba?\(\s*255)",
                     re.I)


def _rgb(hexa: str) -> Tuple[int, int, int]:
    h = hexa.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _croma(rgb: Tuple[int, int, int]) -> int:
    return max(rgb) - min(rgb)


def _luz(rgb: Tuple[int, int, int]) -> float:
    return (max(rgb) + min(rgb)) / 2.0


def _distancia(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _familia(rgb: Tuple[int, int, int]) -> str:
    """La familia de aviso a la que pertenece un color con tono."""
    r, g, b = rgb
    mx, mn = max(rgb), min(rgb)
    d = mx - mn
    if d == 0:
        return "info"
    if mx == r:
        matiz = ((g - b) / d) % 6
    elif mx == g:
        matiz = (b - r) / d + 2
    else:
        matiz = (r - g) / d + 4
    matiz *= 60
    if matiz < 20 or matiz >= 330:
        return "mal"                       # rojo
    if matiz < 70:
        return "avi"                       # ámbar y naranja
    if matiz < 175:
        return "ok"                        # verde
    if matiz < 265:
        return "info"                      # cian y azul
    return "mal"                           # morado y magenta


def _declarados(css: str) -> Dict[Tuple[int, int, int], str]:
    """Los colores del `:root` de la calculadora, por familia."""
    fuera: Dict[Tuple[int, int, int], str] = {}
    m = re.search(r":root\s*\{(.*?)\}", css, re.S)
    if not m:
        return fuera
    for nombre, valor in re.findall(r"--([a-zA-Z0-9-]+)\s*:\s*([^;]+)",
                                    m.group(1)):
        h = _HEX.search(valor)
        familia = POR_NOMBRE.get(nombre.lower())
        if h and familia:
            fuera[_rgb(h.group(0))] = familia
    return fuera


def clasificar(hexa: str, prop: str, suelo: bool, chip: bool,
               declarados: Dict[Tuple[int, int, int], str]) -> Optional[str]:
    """El nombre `--n-*` que sustituye a este color, o None para dejarlo."""
    rgb = _rgb(hexa)
    if rgb in MARCA:
        return None
    rol = _ROL.get(prop)
    if rol is None:
        return None

    # La regla escribe en blanco: lo que pinta es una placa de color sólido
    # —`.vtag`, el banner naranja—, no papel. Sus colores se quedan; puestos
    # en un pastel de tema, el rótulo blanco se volvería ilegible.
    if chip and rol == "fondo":
        return None

    # Un rótulo claro va encima de una superficie de color: se queda.
    if rol == "tinta" and _luz(rgb) >= LUZ_ROTULO:
        return None

    # Blanco: como fondo es papel; como texto o línea va encima de la marca.
    if rgb == (255, 255, 255):
        return "papel" if rol == "fondo" else None

    croma = _croma(rgb)

    # ¿Es uno de los grises que la calculadora declaró? `#6B7280` ES `--muted`
    # y `#374151` es la misma tinta pizarra que `--ink:#1F2937`, aunque su
    # croma (21 y 26) quede por encima del umbral de gris.
    #
    # Se exige que los dos tengan croma PARECIDO, no sólo que estén cerca en
    # distancia: `#EFF6E7` —el verde suave de `.flag.ok`— queda a 20 de
    # `--panel:#F5F7FA`, y sin esta condición se iba a "papel" y el aviso se
    # quedaba sin color. Su croma es 15 contra los 5 del panel: no es el mismo
    # gris, es un verde muy lavado.
    nombre, cerca = None, CERCA_GRIS
    for color, fam in declarados.items():
        if fam not in _GRIS_POR_ROL.get(rol, ()):
            continue
        if abs(croma - _croma(color)) > CROMA_GEMELO:
            continue
        d = _distancia(rgb, color)
        if d < cerca:
            cerca, nombre = d, fam
    if nombre and not (rol == "fondo" and suelo):
        return nombre

    # Un tono pleno cerca de un aviso declarado ES ese aviso.
    if croma >= CROMA_PLENO:
        familia, cerca = None, CERCA_TONO
        for color, fam in declarados.items():
            if fam not in _AVISOS or _croma(color) < CROMA_PLENO:
                continue
            d = _distancia(rgb, color)
            if d < cerca:
                cerca, familia = d, fam
        if familia:
            return f"{familia}-{rol}"

    if croma < CROMA_TONO:
        # Gris. El fondo del suelo es el fondo de Pohua; el resto, papel.
        if rol == "fondo" and suelo:
            return "sutil"
        if rol == "tinta":
            return "tinta" if _luz(rgb) < 90 else "apagado"
        if rol == "linea":
            return "linea"
        return "papel"

    familia = _familia(rgb)
    if rol == "fondo" and _luz(rgb) < LUZ_RELLENO:
        return familia + "-solido"
    return f"{familia}-{rol}"


# `--warn` no quiere decir lo mismo en las dos calculadoras: en la de precios
# es el ROJO (#C0392B, el de los flags y el parser caído) y en la de resortes
# el ÁMBAR (#b9770e). No se puede resolver en el navegador: `isc-tema.js` se
# ejecuta en el <head>, ANTES de que exista el <style> que declara el `:root`,
# así que ahí `--warn` todavía no vale nada. Aquí sí se sabe —el `:root` está
# delante— y se deja resuelto en el CSS.
_AMBIGUOS = {"warn": None, "warn-bg": "fondo"}


def _resolver_ambiguos(css: str, declarados: Dict[Tuple[int, int, int], str],
                       cuenta: Dict[str, int]) -> str:
    """Cambia `var(--warn)` por el aviso que de verdad es en esta hoja."""
    familia = None
    m = re.search(r"--warn\s*:\s*(#[0-9a-fA-F]{3,6})", css)
    if m:
        familia = _familia(_rgb(m.group(1)))
    if familia is None:
        return css

    def por_uso(u: "re.Match") -> str:
        prop = u.group("prop").lower()
        rol = _AMBIGUOS[u.group("nombre")] or _ROL.get(prop)
        if rol is None:
            return u.group(0)
        cuenta["aviso"] += 1
        return f"{u.group('prop')}:{u.group('antes')}var(--n-{familia}-{rol})"

    return re.sub(
        r"(?P<prop>[a-zA-Z-]+)\s*:\s*(?P<antes>[^;{}]*?)"
        r"var\(\s*--(?P<nombre>warn-bg|warn)\s*\)", por_uso, css)


# El azul de marca usado como TEXTO.
#
# `--navy` y `--accent-deep` son el azul marino del logotipo y `--cyan` su
# acompañante. Como FONDO son intocables: la cabecera de cada tarjeta, las
# cabeceras de tabla y la barra de acciones son de marca y se ven igual en los
# dos temas. Pero la calculadora los usa también como color de LETRA —los
# rótulos "Routing", "Tooling", "Subcontracting", "Packaging", "Spring
# Calculator feasibility:"— y ahí el mismo azul, sobre el panel oscuro, da
# 1.4:1. Desaparecían.
#
# Se distingue por la PROPIEDAD, que es lo único que separa un caso del otro, y
# aquí se ve; en el navegador no, porque es la misma variable. Los fondos y los
# bordes no se tocan.
_MARCA_TEXTO = re.compile(
    r"(?P<prop>color)\s*:\s*var\(\s*--(?:navy|accent-deep|cyan)\s*\)")


def _marca_como_texto(css: str, cuenta: Dict[str, int]) -> str:
    def por_uso(m: "re.Match") -> str:
        cuenta["aviso"] += 1
        return f"{m.group('prop')}:var(--n-marca-tinta)"

    return _MARCA_TEXTO.sub(por_uso, css)


def tematizar_css(css: str, cuenta: Dict[str, int]) -> str:
    """Cambia los colores literales del CSS por variables `--n-*`."""
    declarados = _declarados(css)
    chasis = ("papel", "sutil", "linea", "tinta", "apagado")

    def por_regla(m: "re.Match") -> str:
        sel = m.group("sel")
        if ":root" in sel:
            return m.group(0)
        if _PLACA.search(sel):
            return m.group(0)
        suelo = bool(_SUELO.search(sel))
        chip = bool(_BLANCO.search(m.group("cuerpo")))

        def por_declaracion(d: "re.Match") -> str:
            prop = d.group("prop").lower()

            def por_color(c: "re.Match") -> str:
                nombre = clasificar(c.group(0), prop, suelo, chip, declarados)
                if nombre is None:
                    return c.group(0)
                cuenta["chasis" if nombre in chasis else "aviso"] += 1
                return f"var(--n-{nombre})"

            return f"{d.group('prop')}:{_HEX.sub(por_color, d.group('valor'))}"

        return sel + "{" + _DECL.sub(por_declaracion, m.group("cuerpo")) + "}"

    return _marca_como_texto(
        _resolver_ambiguos(_REGLA.sub(por_regla, css), declarados, cuenta), cuenta)


# La marca de "esta copia lleva las variables del tema".
#
# `isc-tema.js` la necesita para saber si puede pintar tinta clara encima. Y la
# necesita ANTES del primer pintado, corriendo dentro del <head>, cuando el
# <style> de la calculadora todavía no existe y `document.styleSheets` está
# vacío: mirar el CSS no sirve, ahí siempre diría que no.
#
# Va en el <html> porque esa etiqueta se analiza antes que el <head>: cuando
# nuestro script arranca, el atributo ya se puede leer.
MARCA_TEMA = "data-nube-tema"


def marcar(html: str) -> str:
    if MARCA_TEMA in html[:2048]:
        return html
    return re.sub(r"<html\b", '<html ' + MARCA_TEMA + '="1"', html, count=1,
                  flags=re.I)


# Declaraciones sueltas: las que NO están en el <style>.
#
# La calculadora pinta media tabla del CBD desde JavaScript, con cadenas como
#   ctrl('<b>Selling price</b>', t=>t.sell, 'background:#FBEFE3;font-weight:700')
# y con atributos `style="..."` en su HTML. Eso queda fuera del <style>, así
# que el pase de arriba no lo veía: en oscuro, esas filas se quedaban con su
# papel crema original y encima la tinta clara del tema. Bandas blancas con
# letra blanca, ilegibles, que es justo lo que se veía en el modelo de costes.
#
# Se reconoce por la forma —`propiedad: #color`—, que es la misma dentro y
# fuera de una hoja de estilos. Un hexadecimal suelto en el JavaScript (un
# color de gráfica, una constante) no lleva propiedad delante y no se toca.
_SUELTA = re.compile(
    r"(?P<prop>background-color|background|border-left-color|border-right-color"
    r"|border-top-color|border-bottom-color|border-left|border-right|border-top"
    r"|border-bottom|border-color|border|outline-color|outline|color|fill|stroke)"
    r"\s*:\s*(?P<valor>[^;\"'{}]*?"
    r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b[^;\"'{}]*?)(?=[;\"'}]|$)")


def tematizar_sueltas(trozo: str, declarados: Dict[Tuple[int, int, int], str],
                      cuenta: Dict[str, int]) -> str:
    chasis = ("papel", "sutil", "linea", "tinta", "apagado")

    def por_declaracion(m: "re.Match") -> str:
        prop = m.group("prop").lower()
        # El mismo criterio que en la hoja: si alrededor se escribe en blanco,
        # es una placa de color sólido y sus fondos se quedan.
        chip = bool(_BLANCO.search(trozo[max(0, m.start() - 160):m.end() + 160]))

        def por_color(c: "re.Match") -> str:
            nombre = clasificar(c.group(0), prop, False, chip, declarados)
            if nombre is None:
                return c.group(0)
            cuenta["chasis" if nombre in chasis else "aviso"] += 1
            return f"var(--n-{nombre})"

        return f"{m.group('prop')}:{_HEX.sub(por_color, m.group('valor'))}"

    return _marca_como_texto(_SUELTA.sub(por_declaracion, trozo), cuenta)


def tematizar(html: str, hechos: List[str]) -> str:
    """Aplica `tematizar_css` a cada `<style>` del documento."""
    cuenta = {"chasis": 0, "aviso": 0}
    sueltos = {"chasis": 0, "aviso": 0}
    declarados = {}
    m0 = re.search(r"(<style[^>]*>)(.*?)(</style>)", html, flags=re.S | re.I)
    if m0:
        declarados = _declarados(m0.group(2))

    def por_bloque(m: "re.Match") -> str:
        return m.group(1) + tematizar_css(m.group(2), cuenta) + m.group(3)

    fuera = marcar(re.sub(r"(<style[^>]*>)(.*?)(</style>)", por_bloque, html,
                          flags=re.S | re.I))

    # Y ahora lo de fuera del <style>, troceando por los bloques de estilo para
    # no volver a pasar por encima de lo ya hecho.
    partes, ultimo = [], 0
    for m in re.finditer(r"<style[^>]*>.*?</style>", fuera, flags=re.S | re.I):
        partes.append(tematizar_sueltas(fuera[ultimo:m.start()], declarados, sueltos))
        partes.append(m.group(0))
        ultimo = m.end()
    partes.append(tematizar_sueltas(fuera[ultimo:], declarados, sueltos))
    fuera = "".join(partes)
    cuenta["chasis"] += sueltos["chasis"]
    cuenta["aviso"] += sueltos["aviso"]
    total = cuenta["chasis"] + cuenta["aviso"]
    hechos.append(f"      colores    {total} a variables "
                  f"({cuenta['chasis']} de chasis, {cuenta['aviso']} de aviso)")
    hechos.append(f"      de esos    {sueltos['chasis'] + sueltos['aviso']} "
                  f"estaban fuera del <style> (atributos y cadenas del JS)")
    hechos.append("      intactos   la marca, los rótulos blancos y los realces")
    return fuera


def copiar(origen: Path, destino: Path, revisar: bool, hechos: List[str]) -> None:
    if not origen.exists():
        raise SystemExit(f"No está {origen}. ¿Se clonó el núcleo en {CLON}?")
    hechos.append(f"    {origen.relative_to(CLON)} -> {destino.relative_to(RAIZ)}")
    if revisar:
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    if origen.is_dir():
        if destino.exists():
            shutil.rmtree(destino)
        shutil.copytree(origen, destino,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        shutil.copy2(origen, destino)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--revisar", action="store_true",
                   help="Dice qué haría y no toca nada.")
    p.add_argument("--clon", default=str(CLON),
                   help="Dónde está el clon del núcleo.")
    args = p.parse_args()

    clon = Path(args.clon)
    if not clon.is_dir():
        print(f"No existe {clon}. Clónalo con:\n"
              f"  git clone https://github.com/dasniela/ISCQuotingCore.git \"{clon}\"",
              file=sys.stderr)
        return 2

    globals()["CLON"] = clon
    hechos: List[str] = []

    hechos.append("  El motor, las reglas y el cálculo del resorte")
    for js in MOTOR:
        copiar(clon / "nucleo" / "motor" / js, DESTINO_JS / js, args.revisar, hechos)

    hechos.append("  El lector de planos")
    copiar(clon / "nucleo" / "extraccion" / "isc_extractor", DESTINO_EXTRACTOR,
           args.revisar, hechos)
    for f in LECTOR:
        copiar(clon / "apps" / "lector" / f, DESTINO_LECTOR / f, args.revisar, hechos)

    hechos.append("  Las calculadoras, sin el catálogo dentro")
    for nombre in CALCULADORAS:
        origen = clon / "apps" / "calculadora" / nombre
        if not origen.is_file():
            raise SystemExit(f"No está {origen}.")
        html = origen.read_text(encoding="utf-8")
        limpio = tematizar(vaciar_catalogo(html, nombre, hechos), hechos)
        if not args.revisar:
            DESTINO_HTML.mkdir(parents=True, exist_ok=True)
            (DESTINO_HTML / nombre).write_text(limpio, encoding="utf-8", newline="")

    sha = sha_del_clon() or "desconocido"
    sello = (f"origen  https://github.com/dasniela/ISCQuotingCore\n"
             f"commit  {sha}\n"
             f"fecha   {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
             f"\n"
             f"Copia hecha por scripts/vendorizar_nucleo.py.\n"
             f"El catálogo de las calculadoras se vació al copiar: los datos\n"
             f"salen de Neon. Para actualizar, vuelve a pasar el script sobre un\n"
             f"clon al día y revisa el diff.\n")
    if not args.revisar:
        SELLO.parent.mkdir(parents=True, exist_ok=True)
        SELLO.write_text(sello, encoding="utf-8", newline="")

    print("\n" + ("ESTO ES LO QUE HARÍA — no se tocó nada" if args.revisar else "COPIADO"))
    print("-" * 66)
    for h in hechos:
        print(h)
    print(f"\n  commit de origen: {sha}")
    if sha == "desconocido":
        print("  · No se pudo leer el commit del clon. La copia queda sin sello,\n"
              "    y una copia sin fecha es la que se queda atrás sin que nadie lo note.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
