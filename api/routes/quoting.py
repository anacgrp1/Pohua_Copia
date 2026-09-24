"""Diagnóstico de la pantalla de Cotización.

La pantalla de Cotización va a alojar las tres caras del núcleo de ISC —la
calculadora de precios, el Spring Engineering Calculator y el lector de
planos—, y las tres dependen de piezas que pueden faltar: el paquete
``isc_nucleo``, Node, la clave del modelo, los HTML construidos.

Antes de enseñar ninguna de las tres hay que poder contestar *qué hay puesto y
qué no*, y contestarlo con lo que de verdad se encuentra en el disco, no con lo
que debería estar. Eso es lo que devuelve ``GET /api/quoting/diagnostico``, y es
lo que pinta la pestaña «Conexiones» de la pantalla.

Regla de la casa, la misma que en el costeo: lo que falta se declara. Aquí no
se degrada nada en silencio ni se enseña una pantalla a medias como si
estuviera entera.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from api import lector as lector_montaje
from api.security import exige
from app.auth.tokens import UsuarioSesion
from pricing import nucleo

log = logging.getLogger("cotizador.api.quoting")

router = APIRouter(prefix="/api/quoting", tags=["quoting"])

RAIZ = Path(__file__).resolve().parent.parent.parent

# Los dos HTML que se abren con doble clic en la planta y que la pantalla va a
# alojar. Se generan desde el núcleo con `apps/calculadora/construir.py`: no se
# editan a mano.
CALCULADORAS = {
    "precio":   "ISC Price Calculator V7 to Automate.html",
    "resortes": "Spring Engineering Calculator V2.html",
}

# El prefijo del montaje, el nombre de la cookie y el permiso los define
# api/lector.py, que es quien monta: aquí se usan para repartir la cookie y
# para decirle a la pantalla dónde están las tres caras.
PREFIJO_LECTOR = lector_montaje.PREFIJO
RAIZ_QUOTING = lector_montaje.RAIZ_QUOTING
COOKIE_LECTOR = lector_montaje.COOKIE
PERMISO = lector_montaje.PERMISO


def _pieza(ok: bool, detalle: str, **extra: Any) -> Dict[str, Any]:
    return {"ok": ok, "detalle": detalle, **extra}


def _node() -> Dict[str, Any]:
    """Node hace falta: el motor de coste es JavaScript y corre en subproceso."""
    binario = shutil.which("node")
    if binario is None:
        return _pieza(False, "Node no está en el PATH. Sin él no hay costeo: el "
                             "motor es JavaScript y corre en un subproceso.")
    try:
        salida = subprocess.run([binario, "--version"], capture_output=True,
                                text=True, timeout=10, check=True)
        version = salida.stdout.strip()
    except (OSError, subprocess.SubprocessError) as err:
        return _pieza(False, f"Node está en {binario} pero no se pudo ejecutar: {err}")
    return _pieza(True, f"Node {version}", ruta=binario)


def _motor() -> Dict[str, Any]:
    """El motor de coste: el del núcleo, que es el único que hay.

    El costeo del servidor (``pricing/runner.js``) y la calculadora de la
    planta corren el mismo fichero. Hasta 2026-09 el servidor llevaba su
    propia copia en ``pricing/engine.js``, que daba otro precio con las mismas
    entradas; este diagnóstico existía para ver esa diferencia, y ya no hay
    dos que comparar.
    """
    estado = nucleo.estado()
    motor = estado["piezas"]["motor"]
    if not motor["encontrado"] or motor.get("hueco"):
        return _pieza(False, "No está el motor del núcleo: el costeo del servidor "
                             "no puede calcular. Se vendoriza con "
                             "scripts/vendorizar_nucleo.py.", nucleo=estado)
    return _pieza(True, "El costeo usa el motor del núcleo, el mismo que la "
                        "calculadora de la planta.", nucleo=estado)


def _lector() -> Dict[str, Any]:
    """El lector de planos: si el programa se montó, y si tiene con qué leer.

    Son dos preguntas distintas y hay que separarlas. Que el lector arranque no
    quiere decir que lea: sin ``ANTHROPIC_API_KEY`` contesta igual, en modo
    demo, con valores que NO salen del plano. Un lector en demo que se presenta
    como listo es la peor de las tres situaciones posibles.
    """
    montado, motivo = lector_montaje.estado()
    if not montado:
        return _pieza(False, f"El lector no se pudo montar. {motivo}",
                      montado=False, clave=False)

    clave = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not clave:
        return _pieza(False, "El lector está montado pero no hay "
                             "ANTHROPIC_API_KEY: leería en modo demo, y los "
                             "valores de demo NO salen del plano.",
                      montado=True, clave=False, url=PREFIJO_LECTOR)
    return _pieza(True, "Lector montado y con clave.",
                  montado=True, clave=True, url=PREFIJO_LECTOR)


def _calculadoras() -> Dict[str, Any]:
    """Los dos HTML construidos, que viven en el clon del núcleo."""
    # Donde las busca el propio lector: al lado de su app.py, en
    # `calculadora/`. Si no está montado, se mira igualmente para poder
    # distinguir "faltan los HTML" de "falta el lector que los sirve".
    dir_lector = lector_montaje.carpeta()
    carpeta = ((dir_lector.parent / "calculadora") if dir_lector
               else nucleo.CLON / "apps" / "calculadora")
    encontradas: Dict[str, Any] = {}
    faltan: List[str] = []
    for clave, nombre in CALCULADORAS.items():
        ruta = carpeta / nombre
        if ruta.is_file():
            encontradas[clave] = {"nombre": nombre, "bytes": ruta.stat().st_size}
        else:
            faltan.append(nombre)
    if faltan:
        return _pieza(False, "Faltan HTML de la calculadora: " + ", ".join(faltan)
                             + f" (se buscaron en {carpeta})",
                      encontradas=encontradas, carpeta=str(carpeta))

    montado, motivo = lector_montaje.estado()
    if not montado:
        return _pieza(False, "Los HTML están, pero quien los sirve es el lector "
                             f"y no se pudo montar. {motivo}",
                      encontradas=encontradas)

    # La de precios se sirve en la raíz del montaje (el lector la elige por
    # nombre) y el Spring Calculator como hermano suyo, que es exactamente
    # como se abren cuando la calculadora corre en la planta.
    return _pieza(True, "Las dos calculadoras están construidas y servidas.",
                  encontradas=encontradas,
                  url_precio=PREFIJO_LECTOR + "/",
                  url_resortes=PREFIJO_LECTOR + "/" + CALCULADORAS["resortes"])


@router.get("/diagnostico")
def diagnostico(usuario: UsuarioSesion = Depends(exige("precio:calcular"))) -> Dict[str, Any]:
    """Qué piezas del núcleo hay puestas, una por una.

    Devuelve ``listo`` sólo si están las cuatro. Cada pieza trae su ``detalle``
    en lenguaje llano, para que la pantalla no tenga que traducir códigos.
    """
    piezas = {
        "node": _node(),
        "motor": _motor(),
        "lector": _lector(),
        "calculadoras": _calculadoras(),
    }
    listo = all(p["ok"] for p in piezas.values())
    log.info("Diagnóstico de Cotización pedido por %s: listo=%s", usuario.correo, listo)
    return {
        "listo": listo,
        "piezas": piezas,
        # Desde dónde se está mirando. Sin esto, un "no se encontró el núcleo"
        # no distingue entre «falta el clon» y «este servidor no es el que
        # crees», que es la primera pregunta cuando algo no aparece.
        "raiz": str(RAIZ),
        "clon": str(nucleo.CLON),
    }


@router.post("/sesion", status_code=204)
def abrir_sesion_lector(
    peticion: Request,
    respuesta: Response,
    usuario: UsuarioSesion = Depends(exige(PERMISO)),
) -> None:
    """Abre la puerta del lector para este navegador.

    El lector se enseña dentro de un ``<iframe>``, y un iframe pide su página
    como una navegación normal: no lleva la cabecera ``Authorization`` que usa
    el resto de la API. Sin algo más, la única forma de dejarlo entrar sería
    servirlo sin sesión — y ahí dentro va la calculadora, que lleva incrustada
    la cartera de clientes y los precios de proveedor.

    Así que se reparte una cookie, y se reparte con cuidado:

      - **el mismo token de sesión**, no un permiso nuevo. Caduca cuando caduca
        la sesión, sin un segundo reloj que mantener ni otra forma de revocar;
      - **``path`` atado a ``/quoting``**: el navegador sólo la manda al
        lector y a la API de estado de la calculadora, no al resto de la API
        ni a la PWA;
      - **``httponly``**: ningún script de la página puede leerla, y eso incluye
        a la propia calculadora, que es código que no escribimos nosotros;
      - **de sesión**, sin ``max_age``: se va al cerrar el navegador;
      - **``secure`` en https**, para que no viaje en claro donde no toca.
    """
    cabecera = peticion.headers.get("authorization", "")
    token = cabecera[7:].strip() if cabecera[:7].lower() == "bearer " else ""
    if not token:
        # No debería pasar: `exige` ya validó el token para llegar aquí.
        raise HTTPException(status_code=401, detail="Sesión requerida.")

    respuesta.set_cookie(
        COOKIE_LECTOR, token,
        path=RAIZ_QUOTING,
        httponly=True,
        samesite="lax",
        secure=peticion.url.scheme == "https",
    )
    log.info("Sesión del lector abierta para %s.", usuario.correo)


@router.delete("/sesion", status_code=204)
def cerrar_sesion_lector(respuesta: Response) -> None:
    """Cierra la puerta. La llama la PWA al cerrar sesión."""
    respuesta.delete_cookie(COOKIE_LECTOR, path=RAIZ_QUOTING)
