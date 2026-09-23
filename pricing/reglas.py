"""Envoltorio Python de las reglas del taller.

Mismo planteamiento que ``pricing/engine.py``: las reglas viven en JavaScript,
en el núcleo (``nucleo/motor/reglas.js`` de github.com/dasniela/ISCQuotingCore),
y aquí se ejecutan en un subproceso de Node **para no tener una segunda copia
en Python**. Dos implementaciones de la misma regla acaban eligiendo máquinas
distintas para la misma pieza, y eso son dólares.

Si el núcleo no está disponible, esto NO se inventa una respuesta: devuelve
``None`` y quien llama lo declara como dato faltante. Una ruta incompleta que
se sabe incompleta es mucho mejor que una que parece completa.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from pricing import nucleo

log = logging.getLogger("cotizador.pricing.reglas")

JS_DIR = Path(__file__).resolve().parent
RUNNER_JS = JS_DIR / "reglas_runner.js"

TIMEOUT_SEGUNDOS = 30


def disponible() -> bool:
    """True si se puede preguntar a las reglas de verdad.

    Tres cosas: Node, el runner, y unas reglas que no sean un hueco. La
    tercera no sobra —`pricing/nucleo/reglas.js` fueron diez bytes durante
    semanas, la línea ``// reglas``—: el fichero estaba, así que todo decía
    que sí, y dentro no había ninguna regla. Con el hueco, `secundarias` no
    existe, el subproceso revienta y esto devuelve `None`; comprobarlo aquí
    convierte ese fallo en una respuesta clara y ahorra abrir un proceso para
    nada.
    """
    return (shutil.which("node") is not None
            and RUNNER_JS.is_file()
            and nucleo.ruta("reglas") is not None
            and not nucleo.es_hueco("reglas"))


def _entorno() -> Dict[str, str]:
    """El entorno del subproceso, con las reglas que localizó `nucleo.py`.

    Pohua no tiene el núcleo donde el runner lo buscaría por su cuenta —aquí
    va vendorizado en `pricing/nucleo/`, que es lo que encuentra Render— así
    que se le dice explícitamente. Una sola forma de localizar el núcleo, la
    de `pricing/nucleo.py`, en vez de dos que pueden discrepar.
    """
    import os
    entorno = dict(os.environ)
    ruta = nucleo.ruta("reglas")
    if ruta is not None:
        entorno["ISC_NUCLEO_REGLAS"] = str(ruta)
    return entorno


def _preguntar(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not disponible():
        return None
    try:
        proc = subprocess.run(
            ["node", str(RUNNER_JS)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=True,
            timeout=TIMEOUT_SEGUNDOS,
            env=_entorno(),
        )
        return json.loads(proc.stdout)
    except subprocess.CalledProcessError as err:
        # El caso normal aquí es que el núcleo no esté instalado todavía. Se
        # registra una vez y se sigue: quien llama lo cuenta como faltante.
        log.warning("Las reglas del taller no respondieron: %s",
                    (err.stderr or "").strip()[:300])
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as err:
        log.warning("No se pudieron consultar las reglas del taller: %s", err)
    return None


def operaciones_secundarias(descripcion: str,
                            tipo_extremos: Optional[str] = None,
                            tratamiento_termico: Optional[str] = None,
                            material_codigo: Optional[str] = None,
                            ) -> Optional[List[Dict[str, str]]]:
    """Las operaciones que van DESPUÉS de la bobinadora.

    Devuelve una lista de ``{"m": nombre, "why": motivo}``, o ``None`` si no se
    pudo preguntar. Ojo con la diferencia: una lista vacía significa "el plano
    no pide ninguna" y ``None`` significa "no lo sabemos".

    El plano se le pasa con la forma que esperan las reglas -- los campos que
    la calculadora saca del dibujo -- para no tener dos formatos del mismo dato.
    """
    plano: Dict[str, Any] = {"fields": [], "feasibility": []}
    if tipo_extremos:
        plano["fields"].append({"key": "endType", "value": tipo_extremos})
    if tratamiento_termico:
        plano["feasibility"].append({"label": f"Heat treatment: {tratamiento_termico}"})

    r = _preguntar({"op": "secundarias", "descripcion": descripcion,
                    "plano": plano, "material_codigo": material_codigo})
    if r is None:
        return None
    return r.get("secundarias") or []


def empaque(peso_lb: Optional[float], descripcion: str,
            cantidad: Optional[float],
            cajas: Optional[List[Dict[str, Any]]] = None
            ) -> Optional[Dict[str, Any]]:
    """La caja del tramo y cuántas piezas van en ella.

    La elige el PESO TOTAL del tramo, no la pieza: 10.000 piezas de un resorte
    pequeño caben en cajas y 50.000 ya son tambores. Por eso se pregunta una
    vez por tramo y no una vez por PN.

    Devuelve ``{"id", "ppb", "boxWt", "tierWt"}`` o ``None`` si no se pudo
    preguntar o faltan el peso y la cantidad.
    """
    if not peso_lb or not cantidad:
        return None
    r = _preguntar({"op": "empaque", "peso_lb": peso_lb,
                    "descripcion": descripcion, "cantidad": cantidad,
                    "cajas": cajas or _cajas_del_catalogo()})
    if r is None:
        return None
    return r.get("empaque")


def _cajas_del_catalogo() -> List[Dict[str, Any]]:
    """La lista de cajas del catálogo vendorizado.

    La regla necesita saber qué cajas EXISTEN para no devolver una que la
    planta no compra. Se lee del mismo `catalogo.json` que usa la calculadora.
    """
    try:
        ruta = Path(__file__).resolve().parent / "nucleo" / "catalogo.json"
        return json.loads(ruta.read_text(encoding="utf-8")).get("packing") or []
    except (OSError, ValueError):
        return []


def tope_por_material(maquina_nombre: str,
                      tope: Optional[Dict[str, Any]],
                      material_nombre: Optional[str],
                      diam_mm: Optional[float]) -> Optional[str]:
    """Por qué esa máquina NO puede con ese material, o ``None`` si puede.

    Hay materiales que una máquina sólo dobla hasta un diámetro menor que el
    suyo. Lo contestó Miguel Rodea y hoy afecta a una: la SIMPLEX MC 50 llega a
    .198" de alambre, pero en temple en aceite sólo a .165". Poner esa máquina
    en un alambre de .177" no es un matiz: la que sí puede cuesta cuatro veces
    más por pieza, así que la oferta sale muy por debajo de lo que cuesta.

    La regla no está aquí: es ``topeDeMaterial`` del núcleo, la misma que aplica
    la calculadora. Aquí sólo se le da la forma que espera.
    """
    if not tope or not material_nombre or diam_mm is None:
        return None
    r = _preguntar({
        "op": "tope",
        "maquina": {"name": maquina_nombre,
                    "capMaterial": tope.get("material"),
                    "capWireMaxMm": tope.get("alambre_max_mm")},
        "material": {"name": material_nombre},
        "diam_mm": diam_mm,
    })
    return (r or {}).get("tope")


def bobinadora(descripcion: str, diam_pulg: Optional[float],
               maquinas: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
    """La bobinadora según el ORDEN DE PREFERENCIA del taller.

    No sustituye a `repository.elegir_maquina`, que ordena por capacidades
    capturadas y coste: sirve para compararlas. Cuando las dos no coinciden no
    hay un fallo que corregir sino una decisión que tomar, y quien aprueba
    necesita verla.
    """
    r = _preguntar({"op": "bobinadora", "descripcion": descripcion,
                    "diam_pulg": diam_pulg, "maquinas": maquinas or []})
    if r is None:
        return None
    return r.get("bobinadora")
