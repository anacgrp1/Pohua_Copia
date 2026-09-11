"""Configuracion central del extractor. Todo se puede sobreescribir desde config.json."""

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROMPT_DIR = HERE / "prompts"
SCHEMA_DIR = HERE / "schemas"
ROOT = HERE.parent

# ---------------------------------------------------------------- modelos
# Router: barato, solo clasifica. Extractor: calidad, lee el plano entero.
# El router decide con que prompt y schema se leera el plano: si falla, la
# extraccion entera (que cuesta 30x mas) sale inservible. Por eso NO va en el
# modelo mas barato. Sonnet 5 lee bien escaneos y planos bilingues; ante una
# clasificacion dudosa se escala sola a Opus 5.
MODEL_ROUTER = "claude-sonnet-5"
MODEL_ROUTER_ESCALADO = "claude-opus-5"
MODEL_EXTRACTOR = "claude-opus-5"

# Opus 5 lleva thinking adaptativo activado por defecto; lo declaramos explicito
# para que el codigo siga siendo correcto si alguien cambia el modelo.
THINKING = {"type": "adaptive"}
EFFORT = "high"                 # low | medium | high | xhigh | max
EFFORT_ROUTER = "low"           # clasificar no necesita razonamiento profundo

MAX_TOKENS_ROUTER = 512
MAX_TOKENS_EXTRACTOR = 16000    # antes 4096: se truncaban los planos muy anotados
MAX_TOKENS_REPARACION = 16000

# ---------------------------------------------------------------- imagen
DPI = 200
MAX_SIDE = 1600                 # lado largo maximo en px antes de enviar
MAX_PAGES = 4                   # tope de hojas por plano (control de coste)

# ---------------------------------------------------------------- varios
TIPOS_VALIDOS = ("compresion", "tension", "torsion", "wireform")
REINTENTOS_VALIDACION = 1       # reparaciones tras un JSON que no conforma
REINTENTO_SI_TIPO_DISCREPA = True   # el extractor puede contradecir al router
PALABRAS_ROUTER = 350           # palabras del plano que se pasan al clasificador

# Prompt caching del prefijo estable (system + schema) del extractor.
#   "5m"  -> TTL 5 minutos. Escribir cuesta 1,25x y leer 0,1x: se amortiza
#            a partir de la SEGUNDA lectura del mismo tipo dentro del TTL.
#            Es lo normal aqui, porque la calculadora lee los planos de una
#            oferta en lote, uno detras de otro.
#   "1h"  -> TTL 1 hora. Escribir cuesta 2x: hacen falta 3 lecturas para
#            amortizarlo. Solo compensa si se leen planos sueltos con huecos
#            de mas de 5 minutos entre ellos.
#   False -> desactivado. Un plano suelto y sin reparaciones cuesta ~1 centimo
#            MENOS sin cache, porque se paga la escritura y nadie la lee.
# El router NO se cachea: su prompt no llega al minimo de 1.024 tokens que
# exige Sonnet 5, asi que marcarlo no haria nada.
PROMPT_CACHE = "5m"

# Aviso de saldo bajo. La API NO expone el saldo (ver isc_extractor/gasto.py),
# asi que esto es un contador de lo que gasta ESTE lector, comparado con las
# recargas que se le hayan apuntado. Se avisa cuando lo estimado que queda
# baja de este umbral. En dolares.
AVISO_SALDO_USD = 5.00

# Retencion. Los recortes y los planos subidos se borran pasados estos dias:
# los recortes son una ayuda de revision reproducible, y el plano ya lo
# archiva la calculadora en QUOTES/<cliente>/RFQ Info con su nombre real.
# `_specs/` NO se toca nunca. 0 desactiva la limpieza.
RETENCION_DIAS = 7

# Raiz de la carpeta compartida (la que contiene ISC_V4_DATA.json y QUOTES).
# Si esta puesta, cada lectura archiva su spec junto al plano del que salio.
# Vacia = no se archiva y el spec solo queda en _specs/.
CARPETA_COMPARTIDA = ""
CROP_PAD = 0.014                # padding del recorte, fraccion del ancho de pagina

DEFAULTS = {
    "demo_mode": False,
    "port": 8765,
    "model_router": MODEL_ROUTER,
    "model_router_escalado": MODEL_ROUTER_ESCALADO,
    "effort_router": EFFORT_ROUTER,
    "reintento_si_tipo_discrepa": REINTENTO_SI_TIPO_DISCREPA,
    "model_extractor": MODEL_EXTRACTOR,
    "effort": EFFORT,
    "dpi": DPI,
    "max_pages": MAX_PAGES,
    "max_tokens": MAX_TOKENS_EXTRACTOR,
    "reintentos_validacion": REINTENTOS_VALIDACION,
    "guardar_spec": True,
    "prompt_cache": PROMPT_CACHE,
    "aviso_saldo_usd": AVISO_SALDO_USD,
    "retencion_dias": RETENCION_DIAS,
    "carpeta_compartida": CARPETA_COMPARTIDA,
}


def load_config(base=None):
    """DEFAULTS + config.json (si existe) junto al servidor."""
    cfg = dict(DEFAULTS)
    p = Path(base or ROOT) / "config.json"
    if p.exists():
        try:
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def _leer_texto(p):
    """Lee un fichero de texto adivinando la codificacion por su BOM.

    El Bloc de notas ofrece guardar como 'Unicode' (UTF-16) y PowerShell anade
    BOM con Out-File y con >. Cualquiera de esas variantes debe funcionar.
    """
    crudo = p.read_bytes()
    for bom, codec in ((b"\xff\xfe\x00\x00", "utf-32"), (b"\x00\x00\xfe\xff", "utf-32"),
                       (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16"),
                       (b"\xef\xbb\xbf", "utf-8-sig")):
        if crudo.startswith(bom):
            return crudo.decode(codec, errors="replace")
    return crudo.decode("utf-8", errors="replace")


def _limpiar_clave(linea):
    """Tolera BOM, comillas, espacios y un prefijo tipo ANTHROPIC_API_KEY=.

    En Windows es facil acabar con un BOM (PowerShell lo anade con Out-File y
    con >) o con comillas al pegar. Sin esto, la clave se ignoraba en silencio
    y el sistema caia a modo demo sin explicar por que.
    """
    t = (linea or "").replace("﻿", "").strip()
    if "=" in t and not t.startswith("sk-"):
        izq, _, der = t.partition("=")
        if "key" in izq.strip().lower():
            t = der.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        t = t[1:-1].strip()
    return t


def get_api_key(base=None):
    """ANTHROPIC_API_KEY del entorno, o la primera linea sk- de api_key.txt."""
    k = _limpiar_clave(os.environ.get("ANTHROPIC_API_KEY", ""))
    if k.startswith("sk-"):
        return k
    p = Path(base or ROOT) / "api_key.txt"
    if p.exists():
        try:
            texto = _leer_texto(p)
        except Exception:
            return ""
        for linea in texto.splitlines():
            limpia = _limpiar_clave(linea)
            if limpia.startswith("sk-"):
                return limpia
    return ""


def leer_prompt(nombre):
    return (PROMPT_DIR / nombre).read_text(encoding="utf-8")


def leer_schema_texto(tipo):
    return (SCHEMA_DIR / ("%s.json" % tipo)).read_text(encoding="utf-8")


def leer_schema(tipo):
    return json.loads(leer_schema_texto(tipo))
