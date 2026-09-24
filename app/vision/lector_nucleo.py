"""Leer el plano con EL MISMO lector que la calculadora de la planta.

Por qué existe
--------------
Pohua tenía dos lectores de planos. La calculadora de precios, al pulsar
«AI Read Drawing», usa el del núcleo (``isc_extractor``): convierte las espiras
activas en totales, traduce «SPRING WIRE» a Music Wire, arma la lista de
factibilidad del plano —de ahí sale, por ejemplo, el horno cuando el dibujo
pide relevado de tensiones— y deja el veredicto. El flujo del correo usaba
otro, propio (``app/vision``), con otro prompt y sin nada de eso.

El mismo plano daba entonces dos resortes: el bueno en la calculadora suelta
y otro en el flujo, sin horno, sin lista de factibilidad y con la Spring Calc
diciendo «No customer drawing parsed yet». Aquí el flujo lee con el lector del
núcleo, y el de ``app/vision`` se queda sólo de respaldo por si el núcleo no
está o falla.

Lo que devuelve tiene la forma de siempre (``spring_extractor.interpretar``),
así que nada de lo que hay aguas abajo cambia, más una clave nueva:
``plano_calculadora``, lo que el lector entrega a la calculadora (cotas,
lista de factibilidad y veredicto). Con eso la calculadora abre el RFQ como si
alguien hubiera pulsado «AI Read Drawing», y las reglas del taller ven el
mismo plano que ven allí.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("cotizador.lector_nucleo")

RAIZ = Path(__file__).resolve().parent.parent.parent

# Del tipo del lector al vocabulario del flujo (spring_extractor.TIPOS_VALIDOS).
_TIPO = {"compresion": "compresion", "tension": "extension",
         "torsion": "torsion", "wireform": "desconocido"}

# De la clave de la calculadora a la del resorte del flujo. Todas en mm.
_COTAS = {"wireDia": "diametro_alambre_mm", "od": "diametro_exterior_mm",
          "id": "diametro_interior_mm", "meanDia": "diametro_medio_mm",
          "freeLength": "longitud_libre_mm", "bodyLength": "longitud_cuerpo_mm"}


def carpeta_lector() -> Optional[Path]:
    """Dónde está el lector: ``ISC_LECTOR_DIR``, la copia o el clon."""
    variable = os.environ.get("ISC_LECTOR_DIR")
    candidatos = ([Path(variable)] if variable else []) + [
        RAIZ / "vendor" / "lector", RAIZ / "ISCQuotingCore" / "apps" / "lector"]
    for ruta in candidatos:
        if (ruta / "config.json").is_file() or (ruta / "app.py").is_file():
            return ruta
    return None


def _importar():
    """``isc_extractor`` o None. Se añade AL FINAL de sys.path (ver api/lector)."""
    for ruta in (RAIZ / "vendor", RAIZ / "ISCQuotingCore" / "nucleo" / "extraccion"):
        texto = str(ruta)
        if ruta.is_dir() and texto not in sys.path:
            sys.path.append(texto)
    try:
        import isc_extractor  # type: ignore
        return isc_extractor
    except Exception as error:
        log.info("El lector del núcleo no se puede importar: %s", error)
        return None


def _clave(ie, carpeta: Path) -> str:
    """La clave del lector (entorno o api_key.txt) o, si no, la de Pohua."""
    try:
        clave = ie.config.get_api_key(carpeta)
    except Exception:
        clave = ""
    if clave:
        return clave
    try:
        import app.core.config as config
        return str(getattr(config.settings, "ANTHROPIC_API_KEY", "") or "")
    except Exception:
        return ""


def disponible() -> bool:
    """¿Se puede leer con el lector del núcleo? (el código y una clave)."""
    carpeta = carpeta_lector()
    ie = _importar()
    if ie is None or carpeta is None:
        return False
    return bool(_clave(ie, carpeta))


def _leer_fichero(ie, carpeta: Path, nombre: str, contenido: bytes) -> Dict[str, Any]:
    cfg = ie.config.load_config(carpeta)
    cfg["demo_mode"] = False
    sufijo = Path(nombre).suffix.lower() or ".pdf"
    with tempfile.TemporaryDirectory(prefix="pohua-lector-") as dir_tmp:
        ruta = os.path.join(dir_tmp, "plano" + sufijo)
        with open(ruta, "wb") as fichero:
            fichero.write(contenido)
        payload, _paginas = ie.parse_drawing(
            ruta, cfg=cfg, api_key=_clave(ie, carpeta),
            log=lambda s: log.debug("[lector] %s", s))
    return payload


def _campo(payload, clave):
    for f in payload.get("fields") or []:
        if f.get("key") == clave:
            return f
    return None


def _texto(v) -> Optional[str]:
    v = str(v or "").strip()
    return v or None


def a_resorte(payload: Dict[str, Any]) -> Dict[str, Any]:
    """El payload del lector, con la forma del resorte del flujo.

    Pasa por ``spring_extractor.interpretar`` para salir EXACTAMENTE con las
    mismas claves, tipos y comprobaciones que el lector de siempre.
    """
    from app.vision import spring_extractor

    spec = payload.get("spec") or {}
    espiras = spec.get("espiras") or {}
    material = spec.get("material") or {}
    extremos = spec.get("extremos") or {}
    titulo = payload.get("title") or {}

    crudo: Dict[str, Any] = {"tipo_resorte": _TIPO.get(payload.get("tipo"), "desconocido")}
    for clave, destino in _COTAS.items():
        f = _campo(payload, clave)
        if f and f.get("value") not in (None, ""):
            crudo[destino] = f["value"]
    espiras_f = _campo(payload, "coils")
    if espiras_f:
        crudo["numero_espiras_totales"] = espiras_f.get("value")
    if espiras.get("numero_espiras_activas") is not None:
        crudo["numero_espiras_activas"] = espiras.get("numero_espiras_activas")

    mat = _campo(payload, "material")
    crudo["material"] = _texto((mat or {}).get("value")) or _texto(material.get("designacion"))
    crudo["norma_material"] = _texto(material.get("norma"))
    # El mismo código de extremo que ve la calculadora ("closed_ground"…): de
    # él salen el rectificado en la ruta y las espiras muertas.
    crudo["tipo_extremos"] = (_texto((_campo(payload, "endType") or {}).get("value"))
                              or _texto(extremos.get("tipo"))
                              or ("ground" if extremos.get("rectificado") else None))
    crudo["acabado"] = _texto(material.get("acabado_superficial"))
    crudo["sentido_enrollado"] = _texto(espiras.get("sentido_enrollado"))
    crudo["num_parte"] = _texto(titulo.get("pn") or titulo.get("numero_parte"))
    crudo["unidad"] = "mm"
    crudo["confianza"] = 0.9
    crudo["notas"] = "\n".join(
        str((w or {}).get("text") if isinstance(w, dict) else w)
        for w in (payload.get("warnings") or []) if w) or None

    datos = spring_extractor.interpretar(json.dumps(crudo, ensure_ascii=False))

    # Lo que la calculadora recibe de «AI Read Drawing», sin los recortes (son
    # imágenes del servidor del lector, que aquí no se generan).
    datos["plano_calculadora"] = {
        "springType": payload.get("springType"),
        "fields": [{k: f.get(k) for k in ("key", "label", "value", "unit", "code",
                                          "note", "confidence", "derivado")
                    if k in f} for f in (payload.get("fields") or [])],
        "feasibility": [{k: it.get(k) for k in ("id", "label", "severity", "detalle",
                                                "valor", "source")
                         if k in it} for it in (payload.get("feasibility") or [])],
        "verdict": payload.get("feasibility_verdict"),
        "title": titulo,
        "remarks": payload.get("remarks"),
    }
    datos["material_codigo"] = (mat or {}).get("code") or None
    datos["lector"] = "nucleo"
    return datos


def leer(planos: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Lee el primer plano legible con el lector del núcleo.

    Devuelve el resorte (forma de ``interpretar``) o None si el núcleo no está
    o la lectura falla —quien llama usa entonces el lector de respaldo—.
    """
    if not planos:
        return None
    carpeta, ie = carpeta_lector(), _importar()
    if carpeta is None or ie is None:
        return None
    if not _clave(ie, carpeta):
        log.info("El lector del núcleo no tiene clave de API.")
        return None
    plano = planos[0]
    try:
        payload = _leer_fichero(ie, carpeta, plano.get("nombre") or "plano.pdf",
                                plano.get("contenido") or b"")
        datos = a_resorte(payload)
        log.info("Plano %s leído con el lector del núcleo (%s).",
                 plano.get("nombre"), payload.get("tipo"))
        return datos
    except Exception as error:
        log.warning("El lector del núcleo no pudo leer %s (%s); se usa el de "
                    "respaldo.", plano.get("nombre"), error)
        return None


def leer_planos(planos: List[Dict[str, Any]], cliente=None) -> Dict[str, Any]:
    """El resorte de estos planos: con el lector del núcleo y, si no, el de respaldo.

    ``cliente`` es el cliente de Anthropic del lector de respaldo (pruebas).
    """
    if cliente is None:
        datos = leer(planos)
        if datos is not None:
            return datos

    import app.vision.pipeline as pipeline
    import app.vision.spring_extractor as spring_extractor
    analisis = pipeline.analizar_dibujos(planos, cliente=cliente)
    datos = spring_extractor.interpretar(analisis["texto"])
    datos["lector"] = "vision"
    return datos
