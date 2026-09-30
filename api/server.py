"""CGR Cotizador — aplicación FastAPI.

Servidor central que:
1. Sirve la PWA como archivos estáticos.
2. Expone la API REST que consume la PWA.
3. Opcionalmente corre el worker de detección de correo en un hilo aparte.

Toda la lógica de negocio vive en ``app/``; este módulo sólo cablea el HTTP.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import app.core.config as config

# Routes
from api.routes import assistant as assistant_router
from api.routes import auth as auth_router
from api.routes import pricing as pricing_router
from api.routes import nube as nube_router
from api.routes import quoting as quoting_router
from api import lector as lector_montaje
from api.routes import rfqs as rfqs_router
from api.routes import status as status_router
from api.routes import notificaciones as notificaciones_router
from api.routes import push as push_router
from api.routes import legal as legal_router
from api.routes import users as users_router
from api.security import exige
import app.rfq.horario as horario
from app.auth.tokens import UsuarioSesion
from app.core.logging import configure_logging

# El logging se configura UNA vez, aquí (consola + archivo rotativo).
configure_logging()
log = logging.getLogger("cotizador.server")

# ---------------------------------------------------------------------------
# Background worker — corre ciclo_deteccion() cada cierto tiempo
# ---------------------------------------------------------------------------

_worker_thread: threading.Thread | None = None
_worker_stop = threading.Event()
_last_heartbeat_time: float = 0.0


def _worker_loop():
    """Corre el ciclo de detección periódicamente en un hilo demonio."""
    interval = config.intervalo_segundos()

    status_router.set_running(True)
    log.info("Worker en segundo plano arrancado (lectura continua, cada %d s).", interval)
    # Lo mismo que «dormido»: el aviso de que lee el escritorio se dice al
    # cambiar, no en cada vuelta (con un ciclo cada 20 s serían 180 líneas
    # por hora).
    apartado = False

    # ¿Ya se dijo que está cerrado? Para no repetirlo cada intervalo: una
    # noche entera son ~140 líneas idénticas y la primera de la mañana se
    # pierde entre ellas. Se dice al cerrar y al abrir, que es cuando cambia
    # algo.
    dormido = False

    while not _worker_stop.is_set():
        time_since_heartbeat = time.time() - _last_heartbeat_time
        escritorio_lee = time_since_heartbeat < config.TOLERANCIA_LATIDO_S
        if escritorio_lee and not apartado:
            log.info("Worker en espera: la aplicación de escritorio está leyendo los correos.")
        apartado = escritorio_lee
        if escritorio_lee:
            pass
        elif not horario.abierto():
            # Fuera de horario el buzón ni se abre: los correos esperan ahí y
            # entran en el primer ciclo de la apertura siguiente.
            if not dormido:
                log.info("Worker en reposo. %s", horario.motivo_cerrado())
                dormido = True
        else:
            if dormido:
                log.info("Horario de atención abierto: el worker vuelve a leer el buzón.")
                dormido = False
            try:
                log.debug("Worker activo: ejecutando ciclo de lectura.")
                from app.main import ciclo_deteccion
                resultado = ciclo_deteccion()
                status_router.registrar_ciclo(resultado)
            except Exception as error:
                log.exception("Error en el ciclo del worker: %s", error)
                status_router.registrar_error()

        # Espera el intervalo, o hasta que pidan parar
        _worker_stop.wait(timeout=interval)

    status_router.set_running(False)
    log.info("Worker en segundo plano detenido.")


def start_worker():
    global _worker_thread
    if _worker_thread and _worker_thread.is_alive():
        log.warning("El worker ya está corriendo.")
        return
    _worker_stop.clear()
    _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="detection-worker")
    _worker_thread.start()


def stop_worker():
    _worker_stop.set()
    if _worker_thread:
        _worker_thread.join(timeout=5)
    status_router.set_running(False)


# ---------------------------------------------------------------------------
# Ciclo de vida
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Arranque y apagado."""
    log.info("CGR Cotizador Web — arrancando (entorno=%s).", config.settings.APP_ENV)

    if not config.settings.JWT_SECRET:
        # En prod esto ya reventó en config._validate(); aquí sólo puede pasar
        # en dev, y conviene que se vea muy claro en la consola.
        log.warning(
            "JWT_SECRET no está configurada: los endpoints protegidos "
            "rechazarán cualquier sesión. Define JWT_SECRET en el .env."
        )

    # El esquema, antes que nada. Si el código llega a producción y las
    # migraciones no, la aplicación arranca contra una base vieja y falla al
    # usarla: eso fue exactamente el 500 de Perfil → Usuarios y de la foto de
    # perfil. Ahora el esquema viaja con el código.
    try:
        import app.persistence.migraciones as migraciones
        migraciones.aplicar_pendientes()
    except Exception as error:   # nunca debe impedir el arranque
        log.warning("No se pudo revisar el esquema al arrancar: %s", error)

    # Verificación de tablas (igual que hace app.main.main)
    try:
        import app.clients.mapper as mapper
        import app.persistence.duplicates as duplicates
        import app.persistence.spring_repository as spring_repository
        import app.rfq.repository as repository
        import app.rfq.thread_validator as thread_validator

        duplicates.inicializar_bd()
        thread_validator.inicializar_historial()
        spring_repository.inicializar_bd()
        repository.inicializar_bd()
        mapper.inicializar_bd()
        log.info("Tablas de la base verificadas.")
    except Exception as error:
        log.warning("Verificación de tablas omitida (¿sin conexión?): %s", error)

    auto_start = os.environ.get("WORKER_AUTOSTART", "false").lower() in ("1", "true", "yes")
    if auto_start:
        start_worker()

    yield

    stop_worker()
    log.info("CGR Cotizador Web — apagado.")


# ---------------------------------------------------------------------------
# App FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CGR Cotizador · LEAN AI-LAB",
    description="Automatic RFQ Quoter — API Backend",
    version="1.1.0",
    lifespan=lifespan,
)

# CORS — la PWA se sirve desde este mismo servidor, así que por defecto no se
# abre nada.  CORS_ORIGINS enumera orígenes extra (p.ej. el frontend en otro
# puerto durante el desarrollo).  Antes esto era allow_origins=["*"] junto con
# allow_credentials=True, que es justo la combinación que permite a cualquier
# página de internet llamar a esta API con la sesión del usuario.
_origenes = config.settings.cors_origins
if _origenes:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origenes,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    log.info("CORS habilitado para: %s", ", ".join(_origenes))

# Routers
app.include_router(auth_router.router)
app.include_router(assistant_router.router)
app.include_router(status_router.router)
app.include_router(rfqs_router.router)
app.include_router(pricing_router.router)
app.include_router(quoting_router.router)
app.include_router(nube_router.router)
app.include_router(users_router.router)
app.include_router(notificaciones_router.router)
app.include_router(push_router.router)
app.include_router(legal_router.router)


# ---------------------------------------------------------------------------
# El lector de planos, montado entero
# ---------------------------------------------------------------------------
# No son rutas copiadas: es el programa Flask del núcleo montado tal cual, y
# con él entran de una vez la calculadora de precios (en la raíz del montaje),
# el Spring Engineering Calculator (que la calculadora abre como hermano suyo)
# y los endpoints de lectura de planos.
#
# Va AQUÍ, antes del catch-all de la SPA que se registra más abajo: ese
# catch-all devuelve el index.html para cualquier ruta que no reconozca, así
# que si el montaje llegara después, /quoting/lector/ contestaría la PWA en vez
# del lector, y sin ningún error que lo delatara.
#
# Si no se puede montar, no pasa nada más que eso: el motivo queda guardado y
# lo enseña el diagnóstico de la pantalla de Cotización.
lector_montaje.montar(app)


# ---------------------------------------------------------------------------
# Control del worker
# ---------------------------------------------------------------------------

@app.post("/api/worker/start", tags=["worker"])
def api_start_worker(usuario: UsuarioSesion = Depends(exige("worker:operar"))):
    log.info("Worker arrancado a mano por %s.", usuario.correo)
    start_worker()
    return {"status": "started"}


@app.post("/api/worker/stop", tags=["worker"])
def api_stop_worker(usuario: UsuarioSesion = Depends(exige("worker:operar"))):
    log.info("Worker detenido a mano por %s.", usuario.correo)
    stop_worker()
    return {"status": "stopped"}


class HeartbeatRequest(BaseModel):
    secret_key: str
    # Lo que la aplicación de escritorio quiere que el Monitor enseñe: sus
    # últimas líneas de registro (marca en UTC, nivel, origen, mensaje, id),
    # sus contadores acumulados y en qué está. Todo opcional: un latido a
    # secas sigue valiendo.
    lineas: list[dict] = []
    totales: dict | None = None
    estado: str | None = None


@app.post("/api/worker/heartbeat", tags=["worker"])
def api_worker_heartbeat(payload: HeartbeatRequest):
    """Latido de la app de escritorio, que avisa de que ella lee el correo.

    No usa sesión de usuario porque no la tiene: se autentica con un secreto
    compartido (WORKER_SECRET_KEY).  Si ese secreto no está configurado, el
    endpoint se apaga en lugar de aceptar un valor por defecto conocido: quien
    lo supiera podía dejar el worker del servidor en espera indefinida y las
    RFQ dejaban de procesarse sin que nada fallara a la vista.
    """
    secreto = config.settings.WORKER_SECRET_KEY
    if not secreto:
        log.error("Heartbeat recibido pero WORKER_SECRET_KEY no está configurada.")
        raise HTTPException(
            status_code=503,
            detail="El heartbeat está deshabilitado: falta configurar WORKER_SECRET_KEY.",
        )

    # Comparación en tiempo constante para no filtrar el secreto carácter a carácter.
    import hmac
    if not hmac.compare_digest(payload.secret_key, secreto):
        log.warning("Heartbeat rechazado: secreto incorrecto.")
        raise HTTPException(status_code=403, detail="Secreto inválido.")

    global _last_heartbeat_time
    _last_heartbeat_time = time.time()
    nuevas = 0
    if payload.lineas or payload.totales or payload.estado:
        from api.routes import status as estado_mod
        nuevas = estado_mod.registrar_escritorio(
            payload.lineas[-200:], payload.totales, payload.estado)
    return {"status": "ok", "message": "Heartbeat received", "lineas": nuevas}


# ---------------------------------------------------------------------------
# Frontend PWA como archivos estáticos
# ---------------------------------------------------------------------------
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
_FRONTEND_RAIZ = FRONTEND_DIR.resolve()


def _ruta_segura(peticion: str) -> Path | None:
    """Resuelve una ruta pedida por el navegador dentro de ``frontend/``.

    Devuelve None si la ruta se sale de esa carpeta o no es un archivo.

    El catch-all hacía ``FRONTEND_DIR / full_path`` y servía lo que saliera.
    Como Starlette no normaliza la ruta, ``GET /%2e%2e/.env`` se traducía a
    ``frontend/../.env`` y el servidor devolvía el .env entero — con el DSN de
    Neon, la ANTHROPIC_API_KEY y la contraseña de IMAP dentro.  Resolver la
    ruta y comprobar que sigue colgando de ``frontend/`` es lo que lo corta.
    """
    if not peticion:
        return None
    try:
        candidato = (_FRONTEND_RAIZ / peticion).resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    if candidato != _FRONTEND_RAIZ and _FRONTEND_RAIZ not in candidato.parents:
        log.warning("Intento de salir de frontend/ con la ruta %r.", peticion)
        return None
    if candidato.is_dir():
        # `/legal/` es una página con su propio index.html, no la SPA.
        candidato = candidato / "index.html"
    return candidato if candidato.is_file() else None


if FRONTEND_DIR.is_dir():
    app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
    app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")
    if (FRONTEND_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/manifest.json", include_in_schema=False)
    async def manifest():
        return FileResponse(FRONTEND_DIR / "manifest.json")

    @app.get("/sw.js", include_in_schema=False)
    async def service_worker():
        return FileResponse(FRONTEND_DIR / "sw.js", media_type="application/javascript")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_catchall(full_path: str):
        """Cualquier ruta no capturada por la API devuelve la SPA."""
        if full_path.startswith("api/"):
            # Que la API responda 404 de verdad y no el index.html, que hacía
            # que un endpoint mal escrito pareciera funcionar.
            raise HTTPException(status_code=404, detail="Not Found")
        archivo = _ruta_segura(full_path)
        if archivo is not None:
            return FileResponse(archivo)
        return FileResponse(FRONTEND_DIR / "index.html")
