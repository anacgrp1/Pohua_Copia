"""Envoltorio Python del motor de costeo.

Ejecuta el motor JavaScript del núcleo en un subproceso de Node: el mismo
fichero que lleva la calculadora de la planta, localizado por
``pricing/nucleo.py``. Así el precio de la ventana del RFQ y el de la
calculadora salen del mismo cálculo.

Como esto depende de que exista ``node`` en el entorno de despliegue, el error
de "Node no está instalado" se distingue del error "el motor calculó mal": el
primero es un problema de infraestructura y el segundo, de datos.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, cast

from pricing import nucleo

log = logging.getLogger("cotizador.pricing.engine")

JS_DIR = Path(__file__).resolve().parent
RUNNER_JS = JS_DIR / "runner.js"

# El motor es rápido (milisegundos), así que un minuto es de sobra y evita que
# un Node colgado deje al worker de FastAPI esperando para siempre.
TIMEOUT_SEGUNDOS = 60


class ErrorMotorCosteo(RuntimeError):
    """El motor de costeo no pudo entregar un resultado utilizable."""


def node_disponible() -> bool:
    """True si hay un ejecutable ``node`` en el PATH."""
    return shutil.which("node") is not None


def compute_price_via_node(
    pn: Dict[str, Any],
    ctx_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ejecuta el motor de Rodea vía Node.js y devuelve su resultado."""
    if ctx_overrides is None:
        ctx_overrides = {}

    if not node_disponible():
        raise ErrorMotorCosteo(
            "Node.js no está instalado en este entorno y el motor de costeo lo "
            "necesita. En el despliegue se instala con la imagen del Dockerfile."
        )
    if not RUNNER_JS.is_file():
        raise ErrorMotorCosteo(f"No se encontró el motor de costeo en {RUNNER_JS}.")

    motor = nucleo.ruta("motor")
    if motor is None or nucleo.es_hueco("motor"):
        raise ErrorMotorCosteo(
            "No está el motor del núcleo (pricing/nucleo/engine.js). Se "
            "vendoriza con scripts/vendorizar_nucleo.py."
        )

    payload = {"pn": pn, "ctx_overrides": ctx_overrides}
    entorno = dict(os.environ, ISC_NUCLEO_MOTOR=str(motor))

    try:
        proc = subprocess.run(
            ["node", str(RUNNER_JS)],
            input=json.dumps(payload),
            env=entorno,
            text=True,
            capture_output=True,
            check=True,
            timeout=TIMEOUT_SEGUNDOS,
        )
    except subprocess.TimeoutExpired as err:
        log.error("El motor de costeo excedió %d s.", TIMEOUT_SEGUNDOS)
        raise ErrorMotorCosteo(
            f"El motor de costeo no respondió en {TIMEOUT_SEGUNDOS} segundos."
        ) from err
    except subprocess.CalledProcessError as err:
        log.error("El motor de costeo falló: %s\n%s", err.stderr, err.stdout)
        raise ErrorMotorCosteo(
            f"El motor de costeo terminó con error: {(err.stderr or '').strip()[:500]}"
        ) from err
    except OSError as err:  # node desapareció entre el which() y el run()
        raise ErrorMotorCosteo(f"No se pudo ejecutar Node.js: {err}") from err

    try:
        return cast(Dict[str, Any], json.loads(proc.stdout))
    except json.JSONDecodeError as err:
        log.error("Salida ilegible del motor de costeo: %r", proc.stdout[:500])
        raise ErrorMotorCosteo("El motor de costeo devolvió una salida ilegible.") from err
