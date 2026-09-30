"""Rutas de estado del servicio y control del pipeline.

GET  /api/status         → estado actual del servicio
GET  /api/logs           → últimas líneas de app.log (sólo admin)
POST /api/pipeline/run   → ejecuta un ciclo de detección a mano

El ciclo en sí NO se implementa aquí: se llama a ``app.main.ciclo_deteccion``.
Antes este módulo llevaba una copia literal de esas ~40 líneas y las dos
versiones ya habían empezado a divergir (la de aquí contaba, la otra no).
"""

from __future__ import annotations

import logging
import os
import re
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.models.schemas import CycleResult, EstadoHorario, LogLine, LogTail, ServiceStatus
from api.security import exige, usuario_actual
from app.auth.tokens import UsuarioSesion

log = logging.getLogger("cotizador.api.status")

router = APIRouter(prefix="/api", tags=["status"])

# ---------------------------------------------------------------------------
# Estado en memoria, compartido con el worker en segundo plano.
# El worker corre en OTRO hilo, así que las escrituras van bajo un lock:
# `_state["total_errors"] += 1` desde dos hilos puede perder incrementos.
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False,
    "last_cycle": None,
    "next_cycle": None,
    "total_processed": 0,
    "total_rfqs": 0,
    "total_errors": 0,
}


def update_state(**kwargs):
    """Actualiza campos sueltos del estado."""
    with _lock:
        _state.update(kwargs)


def set_running(value: bool):
    with _lock:
        _state["running"] = value


def registrar_ciclo(resultado) -> None:
    """Acumula el resultado de un ciclo en los contadores del servicio.

    ``total_rfqs`` se rellena aquí: antes se exponía en /api/status pero nadie
    lo incrementaba nunca, así que el tablero mostraba siempre 0 RFQ.
    """
    if not getattr(resultado, "en_horario", True):
        # Fuera de horario no hubo ciclo: apuntar la hora como "último ciclo"
        # haría creer que se miró el buzón y no llegó nada.
        return
    with _lock:
        _state["last_cycle"] = getattr(resultado, "timestamp", None) or datetime.now().isoformat()
        _state["total_processed"] += getattr(resultado, "procesados", 0)
        _state["total_rfqs"] += getattr(resultado, "rfqs", 0)
        _state["total_errors"] += getattr(resultado, "errores", 0)


def registrar_error() -> None:
    """Suma un error de ciclo (el ciclo entero reventó, no un correo suelto)."""
    with _lock:
        _state["total_errors"] += 1


def _snapshot() -> dict[str, Any]:
    with _lock:
        return dict(_state)


# ---------------------------------------------------------------------------
# Lo que cuenta el lector de escritorio
#
# Cuando el buzón lo lee la aplicación de escritorio (Outlook), el servidor
# se aparta y su propio registro no dice nada de los correos: el Monitor de
# la web enseñaba «0 correos, 0 RFQ» y un registro sin lecturas mientras en
# la planta el lector trabajaba. La aplicación manda con cada latido sus
# últimas líneas y sus contadores, y aquí se guardan en memoria para que el
# Monitor enseñe UNA sola historia: la del servidor y la del lector, juntas.
# ---------------------------------------------------------------------------
_MAX_LINEAS_ESCRITORIO = 600
_escritorio: dict[str, Any] = {
    "lineas": deque(maxlen=_MAX_LINEAS_ESCRITORIO),
    "vistas": set(),                    # ids ya recibidos: un reintento no duplica
    "totales": {"procesados": 0, "rfqs": 0, "errores": 0},
    "estado": None,                     # "leyendo" / "espera" / "parado"
    "ultimo": None,                     # cuándo llegó el último latido (ISO)
}


def registrar_escritorio(lineas: list[dict] | None, totales: dict | None,
                         estado: str | None) -> int:
    """Guarda lo que trae un latido. Devuelve cuántas líneas nuevas entraron."""
    nuevas = 0
    with _lock:
        for linea in lineas or []:
            ident = str(linea.get("id") or "")
            if ident and ident in _escritorio["vistas"]:
                continue
            if ident:
                _escritorio["vistas"].add(ident)
                if len(_escritorio["vistas"]) > _MAX_LINEAS_ESCRITORIO * 2:
                    _escritorio["vistas"] = set(
                        str(x.get("id")) for x in _escritorio["lineas"] if x.get("id"))
            _escritorio["lineas"].append({
                "id": ident,
                "marca": str(linea.get("marca") or ""),
                "nivel": str(linea.get("nivel") or "INFO").upper(),
                "origen": str(linea.get("origen") or "lector.escritorio"),
                "mensaje": str(linea.get("mensaje") or ""),
            })
            nuevas += 1
        if totales:
            for clave in ("procesados", "rfqs", "errores"):
                try:
                    _escritorio["totales"][clave] = int(totales.get(clave) or 0)
                except (TypeError, ValueError):
                    pass
        if estado:
            _escritorio["estado"] = str(estado)
        _escritorio["ultimo"] = datetime.now().isoformat()
    return nuevas


def _lineas_escritorio() -> list[dict]:
    with _lock:
        return list(_escritorio["lineas"])


def _totales_escritorio() -> dict[str, int]:
    with _lock:
        return dict(_escritorio["totales"])


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

@router.get("/status", response_model=ServiceStatus)
def get_status(usuario: UsuarioSesion = Depends(usuario_actual)):
    """Estado actual del servicio. Requiere sesión, pero ningún permiso extra."""
    import app.core.config as config

    import app.rfq.horario as horario

    estado = _snapshot()
    # Los contadores suman lo del servidor y lo del lector de escritorio: el
    # Monitor cuenta correos, no quién los leyó.
    de_fuera = _totales_escritorio()
    return ServiceStatus(
        horario=EstadoHorario(**horario.estado()),
        running=estado["running"],
        mode=config.settings.MAIL_MODE,
        folder=getattr(config.settings, "MAIL_FOLDER", "") or "INBOX",
        last_cycle=estado["last_cycle"],
        next_cycle=estado["next_cycle"],
        interval_seconds=config.intervalo_segundos(),
        total_processed=estado["total_processed"] + de_fuera["procesados"],
        total_rfqs=estado["total_rfqs"] + de_fuera["rfqs"],
        total_errors=estado["total_errors"] + de_fuera["errores"],
    )


@router.get("/health", tags=["status"], include_in_schema=False)
def health():
    """Sonda de vida para Render. Sin sesión y sin tocar la base a propósito."""
    return {"status": "ok"}


@router.post("/pipeline/run", response_model=CycleResult)
def run_pipeline(usuario: UsuarioSesion = Depends(exige("worker:operar"))):
    """Ejecuta un ciclo de detección a mano y devuelve el resultado.

    Este ciclo se salta el horario de atención a propósito. El horario existe
    para que el sistema no conteste solo de madrugada; si a alguien con permiso
    le hace falta leer el buzón un domingo, la respuesta correcta es leerlo, no
    una puerta cerrada. Queda dicho en el registro quién lo pidió y cuándo.
    """
    import app.rfq.horario as horario

    if not horario.abierto():
        log.info("Ciclo manual FUERA DE HORARIO solicitado por %s. %s",
                 usuario.correo, horario.motivo_cerrado())
    else:
        log.info("Ciclo manual solicitado por %s.", usuario.correo)

    try:
        from app.main import ciclo_deteccion
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backend import error: {e}")

    resultado = ciclo_deteccion(forzar=True)
    registrar_ciclo(resultado)

    log.info("Ciclo manual terminado: %d encontrados, %d procesados, %d errores.",
             resultado.encontrados, resultado.procesados, resultado.errores)

    return CycleResult(
        messages_found=resultado.encontrados,
        new_processed=resultado.procesados,
        errors=resultado.errores,
        timestamp=resultado.timestamp,
        details=resultado.detalles,
        en_horario=resultado.en_horario,
    )


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

# El formato que escribe app/core/logging.py:
#   2026-09-07 11:02:03,123 [INFO] [nombre] [fichero.py:42]: mensaje
_PATRON_LINEA = re.compile(
    r"^(?P<marca>\d{4}-\d{2}-\d{2} [\d:,]+) "
    r"\[(?P<nivel>[A-Z]+)\] "
    r"\[(?P<origen>[^\]]+)\] "
    r"\[[^\]]+\]: "
    r"(?P<mensaje>.*)$"
)

# Tope duro de lectura. app.log rota a los 5 MB: leerlo entero para enseñar las
# últimas líneas cargaría el servidor sin necesidad.
_MAX_BYTES_COLA = 256 * 1024


def _fichero_log() -> Path:
    """Dónde escribe el logger. Es relativo al directorio de trabajo.

    El import va dentro, como en el resto de este módulo: config se valida al
    importarse y hacerlo arriba ataría el arranque de la API a que la
    configuración esté completa.
    """
    import app.core.config as config
    return Path(getattr(config, "LOG_FILE", "") or "app.log")


@router.get("/logs", response_model=LogTail)
def logs(
    lines: int = Query(200, ge=1, le=2000),
    usuario: UsuarioSesion = Depends(exige("monitor:ver")),
):
    """Últimas líneas del registro del servicio.

    Lee sólo la cola del fichero, no el fichero entero: se salta a los últimos
    256 KB y se descarta la primera línea, que casi siempre queda cortada por
    la mitad.
    """
    ruta = _fichero_log()
    if not ruta.is_file():
        return LogTail(
            disponible=False,
            archivo=str(ruta),
            aviso="Todavía no hay fichero de registro. Aparecerá en cuanto el "
                  "servicio escriba la primera línea.",
        )

    try:
        with ruta.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            tamano = fh.tell()
            fh.seek(max(0, tamano - _MAX_BYTES_COLA))
            crudo = fh.read()
        texto = crudo.decode("utf-8", errors="replace")
        if tamano > _MAX_BYTES_COLA:
            texto = texto.split("\n", 1)[-1]   # fuera la línea partida
    except OSError as err:
        log.warning("No se pudo leer %s: %s", ruta, err)
        raise HTTPException(status_code=503,
                            detail="No se pudo leer el registro del servicio.") from err

    crudas = [ln for ln in texto.splitlines() if ln.strip()]
    ultimas = crudas[-lines:]

    resultado = []
    for linea in ultimas:
        casa = _PATRON_LINEA.match(linea)
        if casa:
            resultado.append(LogLine(**casa.groupdict()))
        else:
            # Los rastros de excepción ocupan varias líneas y no casan con el
            # patrón: se enseñan tal cual en vez de tirarlas.
            resultado.append(LogLine(nivel="TRACE", mensaje=linea))

    return LogTail(lineas=_con_el_escritorio(resultado, lines),
                   archivo=str(ruta), total=len(crudas))


def _con_el_escritorio(del_servidor: list[LogLine], lines: int) -> list[LogLine]:
    """Las líneas del servidor y las del lector de escritorio, en orden de hora.

    Las dos llevan la misma marca («2026-09-24 21:44:11,000», en UTC), así
    que se ordenan juntas. Un rastro de excepción (sin marca) se queda pegado
    a la línea que lo precede.
    """
    de_fuera = [LogLine(**{k: v for k, v in x.items() if k != "id"})
                for x in _lineas_escritorio()]
    if not de_fuera:
        return del_servidor

    # Cada línea hereda la marca de la anterior si no tiene: así el orden es
    # estable y los rastros no se van al principio.
    def con_marca(lineas):
        ultima = ""
        fuera = []
        for i, linea in enumerate(lineas):
            ultima = linea.marca or ultima
            fuera.append((ultima, i, linea))
        return fuera

    juntas = con_marca(del_servidor) + con_marca(de_fuera)
    juntas.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in juntas][-lines:]
