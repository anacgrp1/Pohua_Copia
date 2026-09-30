"""El dictamen del Spring Engineering Calculator para un RFQ, en el servidor.

Por qué existe
--------------
La ficha del RFQ y la ventana de revisión dejaban aprobar resortes que la
planta no puede enrollar. El motor de factibilidad de Pohua los manda a
revisión con sus motivos, pero «a revisión» no es «no se puede»: el PM veía
tres avisos en ámbar y un botón verde de Aprobar.

Quien sí sabe decir «no se puede» es el Spring Engineering Calculator: sus
seis pasos de selección de bobinadora (``selectMachine``) y el límite de 15 mm
del motor de coste. Hasta ahora ese dictamen sólo existía con la calculadora
abierta. Aquí se corre el MISMO cálculo —``pricing/nucleo/resortes.js`` y las
tablas de la calculadora vendorizada— en un subproceso de Node, igual que el
motor de coste (``pricing/engine.py``) y las reglas (``pricing/reglas.py``).

Qué bloquea y qué no
--------------------
``factible`` es ``False`` sólo con un límite físico de la planta:

* ``alambre_maximo`` — el calibre llega al ``wireMaxIn`` del motor (0.59",
  15 mm): «NOT FEASIBLE at ISC. Do not price.»
* ``sin_maquina`` — ninguna bobinadora del taller admite ese alambre (y ese
  OD, y ese material) para ese tipo de resorte.

Las banderas de ingeniería (índice, pandeo, paso…) se enseñan pero no
bloquean: son las mismas que la calculadora llama «remarks, not blockers».

Si Node o el núcleo no están, esto devuelve ``None`` y nadie bloquea nada:
un dictamen que no se pudo calcular no es un «no».
"""

from __future__ import annotations

import importlib.util
import json
import logging
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from pricing import nucleo

log = logging.getLogger("cotizador.pricing.spring_calc")

JS_DIR = Path(__file__).resolve().parent
RUNNER_JS = JS_DIR / "resortes_runner.js"
HTML_SPRING = nucleo.RAIZ / "vendor" / "calculadora" / "Spring Engineering Calculator V2.html"
DICCIONARIO = nucleo.RAIZ / "scripts" / "isc_idioma_diccionario.py"

TIMEOUT_SEGUNDOS = 20

# Cómo llama el lector al tipo, y cómo lo llama la calculadora.
_TIPOS = {
    "compresion": "compression", "compression": "compression",
    "extension": "extension", "tension": "extension", "traccion": "extension",
    "torsion": "torsion",
    "wireform": "wireform", "wire form": "wireform", "forma de alambre": "wireform",
}


def _sin_acentos(texto: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).strip().lower()


def tipo_calculadora(tipo_resorte: Any) -> str:
    """'Compresión', 'compression spring'… → 'compression'. Por defecto, compresión."""
    t = _sin_acentos(tipo_resorte)
    for clave, valor in _TIPOS.items():
        if clave in t:
            return valor
    return "compression"


def tipo_de_extremos(texto: Any) -> str:
    """La clave de END_TYPES de la calculadora a partir de lo que diga el plano.

    Misma lectura que ``pricing/espiras.py``: "squared" = "closed", "open" =
    "plain", y sin decir nada se suponen cerrados.
    """
    t = _sin_acentos(texto)
    esmerilado = any(p in t for p in ("ground", "esmerilad", "rectificad"))
    cerrado = any(p in t for p in ("closed", "square", "cerrad", "cuadrad"))
    plano = any(p in t for p in ("plain", "open", "plano", "abierto"))
    if cerrado or not plano:
        return "closed_ground" if esmerilado else "closed"
    return "plain_ground" if esmerilado else "plain"


def disponible() -> bool:
    return (shutil.which("node") is not None and RUNNER_JS.is_file()
            and HTML_SPRING.is_file()
            and nucleo.ruta("resortes") is not None
            and not nucleo.es_hueco("resortes"))


def _entorno() -> Dict[str, str]:
    import os
    entorno = dict(os.environ)
    for pieza, variable in (("resortes", "ISC_NUCLEO_RESORTES"),
                            ("reglas", "ISC_NUCLEO_REGLAS"),
                            ("motor", "ISC_NUCLEO_MOTOR")):
        ruta = nucleo.ruta(pieza)
        if ruta is not None:
            entorno[variable] = str(ruta)
    entorno["ISC_SPRING_CALC_HTML"] = str(HTML_SPRING)
    return entorno


@lru_cache(maxsize=512)
def _correr(payload_json: str) -> Optional[Dict[str, Any]]:
    """Una evaluación por geometría: la ficha se abre muchas veces."""
    try:
        proc = subprocess.run(
            ["node", str(RUNNER_JS)], input=payload_json, text=True,
            capture_output=True, check=True, timeout=TIMEOUT_SEGUNDOS,
            env=_entorno())
        return json.loads(proc.stdout)
    except subprocess.CalledProcessError as err:
        log.warning("Spring Calc falló: %s", (err.stderr or "").strip()[:500])
    except (subprocess.TimeoutExpired, OSError, ValueError) as err:
        log.warning("Spring Calc no respondió: %s", err)
    return None


# ---------------------------------------------------------------------------
# Traducción: el diccionario de la calculadora, el mismo de isc-idioma.js
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _diccionario() -> Tuple[dict, list]:
    try:
        spec = importlib.util.spec_from_file_location("_isc_idioma_dic", DICCIONARIO)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)             # type: ignore[union-attr]
        plantillas = [(re.compile(p), es, fr) for p, es, fr in mod.PLANTILLAS]
        return dict(mod.D), plantillas
    except Exception as err:                     # sin diccionario, en inglés
        log.debug("Sin diccionario de la calculadora: %s", err)
        return {}, []


def traducir(texto: str) -> Dict[str, str]:
    """``{'en', 'es', 'fr'}`` de un texto de la calculadora; inglés si no se conoce."""
    texto = str(texto or "").strip()
    D, plantillas = _diccionario()
    if texto in D:
        es, fr = D[texto]
        return {"en": texto, "es": es, "fr": fr}
    for patron, es, fr in plantillas:
        if patron.match(texto):
            return {"en": texto, "es": patron.sub(es, texto).strip(),
                    "fr": patron.sub(fr, texto).strip()}
    return {"en": texto, "es": texto, "fr": texto}


# ---------------------------------------------------------------------------
# Lo público
# ---------------------------------------------------------------------------

def _num(v) -> Optional[float]:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _material(texto: Optional[str]) -> Optional[str]:
    """El código de compra (SS, MW…) con la tabla de alias de factibilidad."""
    if not texto:
        return None
    try:
        from pricing import repository
        return repository.codigo_de_material(texto) or texto
    except Exception:
        return texto


def evaluar(resorte: Optional[dict], material_rfq: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """El dictamen del Spring Calc para este resorte, o ``None`` si no se pudo.

    ``material_rfq`` es el material del correo (``rfqs.material``); si el plano
    trae el suyo, manda el del plano.
    """
    resorte = resorte or {}
    if not _num(resorte.get("diametro_alambre_mm")):
        return None
    if not disponible():
        log.info("Spring Calc no disponible (Node o núcleo): sin dictamen.")
        return None

    nt = _num(resorte.get("numero_espiras_totales"))
    if not nt:
        try:
            from pricing import espiras
            nt, _ = espiras.espiras_totales(resorte)
        except Exception:
            nt = None

    material = _material(resorte.get("material") or material_rfq)
    payload = {
        "tipo": tipo_calculadora(resorte.get("tipo_resorte")),
        "material": material,
        "d": _num(resorte.get("diametro_alambre_mm")),
        "od": _num(resorte.get("diametro_exterior_mm")),
        "L0": _num(resorte.get("longitud_libre_mm")),
        "Nt": _num(nt),
        "Na": _num(resorte.get("numero_espiras_activas")),
        "endType": tipo_de_extremos(resorte.get("tipo_extremos")),
    }
    crudo = _correr(json.dumps(payload, sort_keys=True))
    if not crudo:
        return None

    resultado = dict(crudo)
    resultado["banderas"] = [
        {"nivel": b.get("nivel"), "titulo": b.get("titulo"),
         "textos": traducir(b.get("titulo"))}
        for b in (crudo.get("banderas") or [])
    ]
    if resultado.get("banda"):
        resultado["banda_textos"] = traducir(resultado["banda"])
    return resultado


def bloquea(resultado: Optional[dict]) -> bool:
    """True si el Spring Calc dice que la planta NO puede hacer este resorte."""
    return bool(resultado) and resultado.get("factible") is False
