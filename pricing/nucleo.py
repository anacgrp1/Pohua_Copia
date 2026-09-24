"""Dónde está el núcleo de cotización, y si lo que hay es lo que se espera.

El motor de coste, las reglas del taller y el cálculo del resorte viven en un
repositorio aparte —`dasniela/ISCQuotingCore`— porque son los MISMOS ficheros
que ejecuta la calculadora que se usa en la planta. Que el Cotizador y la
calculadora den el mismo número para la misma pieza depende de que los dos
corran ese código, no dos copias parecidas.

Este módulo no calcula nada: sólo localiza el núcleo y dice qué encontró. Lo
busca por orden, y el orden importa:

  1. ``ISC_NUCLEO_MOTOR`` / ``ISC_NUCLEO_REGLAS`` / ``ISC_NUCLEO_RESORTES``
     apuntando a un fichero concreto. Es la salida de emergencia: sirve para
     fijar una versión en un despliegue sin tocar código.
  2. El paquete ``isc_nucleo`` instalado (``pip install -e ISCQuotingCore``).
  3. La copia de ``pricing/nucleo/`` que vive en este repositorio. Es la que
     encuentra Render, donde no hay clon ni credenciales para traerse un
     repositorio privado durante el build.
  4. Un clon en ``ISCQuotingCore/nucleo/motor/`` al lado del proyecto, que es
     lo que hay mientras se trabaja en local con el núcleo delante.

Si no encuentra nada NO se inventa una ruta: devuelve ``None`` y quien llame
tiene que decirlo. Un costeo que se sabe incompleto vale mucho más que uno que
parece completo.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Dict, Optional

RAIZ = Path(__file__).resolve().parent.parent
CLON = RAIZ / "ISCQuotingCore"

# La copia que vive dentro de este repositorio (scripts/vendorizar_nucleo.py).
# Es la que usa Render: allí no hay clon ni se puede instalar desde un
# repositorio privado sin credenciales.
VENDOR = RAIZ / "pricing" / "nucleo"

# Los tres ficheros del núcleo y la variable de entorno que los fija a mano.
PIEZAS = {
    "motor":    ("engine.js",   "ISC_NUCLEO_MOTOR"),
    "reglas":   ("reglas.js",   "ISC_NUCLEO_REGLAS"),
    "resortes": ("resortes.js", "ISC_NUCLEO_RESORTES"),
}


def _por_entorno(variable: str) -> Optional[Path]:
    valor = os.environ.get(variable)
    if not valor:
        return None
    ruta = Path(valor)
    return ruta if ruta.is_file() else None


def _por_paquete(pieza: str) -> Optional[Path]:
    """La ruta que da el paquete instalado, si está instalado."""
    try:
        import isc_nucleo  # type: ignore
    except ImportError:
        return None
    funcion = getattr(isc_nucleo, "ruta_" + pieza, None)
    if funcion is None:
        return None
    try:
        return Path(funcion())
    except FileNotFoundError:
        # El paquete está pero le falta el fichero: un `pip install -e` hecho
        # desde el sitio equivocado. Que no pase por bueno.
        return None


def _por_vendor(nombre: str) -> Optional[Path]:
    ruta = VENDOR / nombre
    return ruta if ruta.is_file() else None


def _por_clon(nombre: str) -> Optional[Path]:
    ruta = CLON / "nucleo" / "motor" / nombre
    return ruta if ruta.is_file() else None


def ruta(pieza: str) -> Optional[Path]:
    """Ruta de una pieza del núcleo, o ``None`` si no se encontró."""
    nombre, variable = PIEZAS[pieza]
    return (_por_entorno(variable) or _por_paquete(pieza)
            or _por_vendor(nombre) or _por_clon(nombre))


def origen(pieza: str) -> Optional[str]:
    """De dónde salió: ``entorno``, ``paquete``, ``copia`` o ``clon``."""
    nombre, variable = PIEZAS[pieza]
    if _por_entorno(variable):
        return "entorno"
    if _por_paquete(pieza):
        return "paquete"
    if _por_vendor(nombre):
        return "copia"
    if _por_clon(nombre):
        return "clon"
    return None


def parametros_del_motor() -> Dict[str, object]:
    """``DEFAULT_PARAMS`` del motor: los parámetros con los que cotiza la calculadora.

    Se leen del propio ``engine.js`` para no tener una segunda copia que
    envejezca por su cuenta. Son la referencia con la que se comparan los
    parámetros vigentes en la base (``param_juegos``): si Neon dice una
    escalera de overheads y el motor otra, la ventana del RFQ y la calculadora
    de la planta dan dos precios del mismo resorte. Vacío si no hay motor.
    """
    import json
    import re

    motor = ruta("motor")
    if motor is None or not motor.is_file():
        return {}
    texto = motor.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"const DEFAULT_PARAMS\s*=\s*\{(.*?)\};", texto, re.S)
    if not m:
        return {}
    # Un objeto JS con claves sin comillas: se le ponen y se lee como JSON.
    cuerpo = re.sub(r"([A-Za-z_]\w*)\s*:", r'"\1":', m.group(1))
    try:
        return json.loads("{" + cuerpo + "}")
    except ValueError:
        return {}


def huella(ruta_fichero: Optional[Path]) -> Optional[str]:
    """Los 12 primeros caracteres del SHA-256, para comparar dos copias.

    No es criptografía: es para poder decir «el motor que corre el Cotizador y
    el que lleva incrustado la calculadora NO son el mismo fichero» sin tener
    que abrir los dos.
    """
    if ruta_fichero is None or not ruta_fichero.is_file():
        return None
    h = hashlib.sha256(ruta_fichero.read_bytes()).hexdigest()
    return h[:12]


def sha_vendorizado() -> Optional[str]:
    """El commit del que salió la copia, según vendor/NUCLEO_SHA.txt."""
    sello = RAIZ / "vendor" / "NUCLEO_SHA.txt"
    if not sello.is_file():
        return None
    for linea in sello.read_text(encoding="utf-8").splitlines():
        if linea.startswith("commit"):
            return linea.split(maxsplit=1)[1].strip()[:12]
    return None


def sha_del_clon() -> Optional[str]:
    """El commit del clon, si el núcleo viene de un clon con git."""
    if not (CLON / ".git").exists():
        return None
    try:
        salida = subprocess.run(
            ["git", "-C", str(CLON), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return salida.stdout.strip() or None


# Un fichero del núcleo por debajo de esto no es el núcleo: es un hueco con su
# nombre. El más pequeño de verdad —`reglas.js`— pasa de 14 KB; el motor, de 19.
# 2 KB deja margen de sobra para una versión futura más escueta y sigue cazando
# el placeholder.
_MINIMO_CREIBLE = 2048


def es_hueco(pieza: str) -> bool:
    """¿Lo que hay en el sitio de esa pieza es un placeholder?

    Por qué existe esta comprobación
    --------------------------------
    `pricing/nucleo/reglas.js` eran DIEZ bytes: la línea ``// reglas``. El
    fichero existía, así que `ruta()` lo encontraba, `origen()` decía "copia" y
    el diagnóstico de la API daba el núcleo por presente. Pero dentro no había
    ninguna regla del taller.

    Lo que se perdía por eso no daba ningún error: las operaciones secundarias
    —el esmerilado que pide un plano con extremos Ground— no se añadían a la
    ruta, la caja no se elegía, y la cotización salía con UNA operación en vez
    de tres. Un precio construido sobre media ruta, sin una sola línea roja en
    ninguna pantalla.

    Un hueco es peor que un fichero ausente: ausente se nota y se cae; hueco se
    encuentra, contesta que sí, y devuelve nada.
    """
    r = ruta(pieza)
    if r is None:
        return False           # ausente no es hueco: son dos cosas distintas
    try:
        return r.stat().st_size < _MINIMO_CREIBLE
    except OSError:
        return False


def huecos() -> list:
    """Las piezas del núcleo que están, pero vacías. Vacío cuando todo va bien."""
    return [p for p in PIEZAS if es_hueco(p)]


def disponible() -> bool:
    """¿Está el motor, que es la pieza sin la cual no hay costeo?

    Un motor que es un placeholder cuenta como ausente: es lo único que evita
    que el costeo siga adelante creyendo que tiene con qué.
    """
    return ruta("motor") is not None and not es_hueco("motor")


def estado() -> Dict[str, object]:
    """Qué hay del núcleo, pieza por pieza. Para el diagnóstico de la API."""
    piezas = {}
    for pieza in PIEZAS:
        r = ruta(pieza)
        piezas[pieza] = {
            "encontrado": r is not None,
            "ruta": str(r) if r else None,
            "origen": origen(pieza),
            "huella": huella(r),
            # Encontrado y vacío a la vez. Va en el diagnóstico porque es el
            # estado que no se nota de ninguna otra forma.
            "hueco": es_hueco(pieza),
        }
    return {
        "disponible": disponible(),
        "sha_clon": sha_del_clon() or sha_vendorizado(),
        "huecos": huecos(),
        "piezas": piezas,
    }
