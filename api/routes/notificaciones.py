"""
El buzón de avisos del Plant Manager (COT-77).

La campana de la aplicación ya enseñaba la cola de revisión
(`/api/assistant/attention`), que es "qué espera AHORA" deducido del estado de
cada RFQ. Esto es lo otro: los avisos como hechos con fecha, que se leen y se
marcan, y que siguen existiendo después de que el RFQ se dictamine.

Los dos conviven a propósito. La cola no se puede marcar como leída —un RFQ
sale de ella cuando se resuelve, no cuando lo miras— y un aviso no se puede
deducir del estado —el estado de hoy no dice qué se avisó ayer—.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.security import exige
from app.auth.tokens import UsuarioSesion

log = logging.getLogger("cotizador.api.notificaciones")

router = APIRouter(prefix="/api/notificaciones", tags=["notificaciones"])

PERMISO = "notificaciones:ver"


class Notificacion(BaseModel):
    id: int
    tipo: str
    rfq_id: str
    titulo: str
    detalle: str = ""
    datos: Dict[str, Any] = Field(default_factory=dict)
    nivel: str
    creada_en: Optional[str] = None
    leida_en: Optional[str] = None


class BuzonAvisos(BaseModel):
    total: int = Field(..., description="Avisos sin leer.")
    criticas: int = Field(..., description="De ésos, cuántos son críticos.")
    avisos: List[Notificacion] = Field(default_factory=list)


class Marcadas(BaseModel):
    marcadas: int


def _repo():
    import app.notifications.repository as repo
    return repo


@router.get("", response_model=BuzonAvisos)
def listar_avisos(
    sin_leer: bool = Query(True, description="Sólo los pendientes."),
    limite: int = Query(50, ge=1, le=200),
    usuario: UsuarioSesion = Depends(exige(PERMISO)),
) -> BuzonAvisos:
    """Los avisos del buzón, los más nuevos primero.

    El recuento es SIEMPRE de los pendientes, mire lo que mire la lista: el
    globo de la campana cuenta lo que falta por atender, y eso no cambia
    porque alguien despliegue el histórico.
    """
    repo = _repo()
    try:
        cuenta = repo.contar_sin_leer()
        avisos = repo.listar(solo_sin_leer=sin_leer, limite=limite)
    except Exception as error:
        log.exception("No se pudo leer el buzón de avisos: %s", error)
        raise HTTPException(status_code=503,
                            detail="El buzón de avisos no está disponible.")

    return BuzonAvisos(total=cuenta["total"], criticas=cuenta["criticas"],
                       avisos=[Notificacion(**a) for a in avisos])


@router.post("/{notificacion_id}/leer", response_model=Marcadas)
def marcar_leida(
    notificacion_id: int,
    usuario: UsuarioSesion = Depends(exige(PERMISO)),
) -> Marcadas:
    """Marca un aviso como leído.

    Devuelve 0 si ya lo estaba, y eso NO es un error: dos pestañas abiertas
    marcan lo mismo dos veces, y la segunda no tiene nada de anómalo.
    """
    try:
        cambio = _repo().marcar_leida(notificacion_id, usuario_id=usuario.id,
                                     correo=usuario.correo)
    except Exception as error:
        log.exception("No se pudo marcar el aviso %s: %s", notificacion_id, error)
        raise HTTPException(status_code=503,
                            detail="El buzón de avisos no está disponible.")
    return Marcadas(marcadas=1 if cambio else 0)


@router.post("/leer-todo", response_model=Marcadas)
def marcar_todas(
    usuario: UsuarioSesion = Depends(exige(PERMISO)),
) -> Marcadas:
    """Vacía el buzón de pendientes."""
    try:
        cuantas = _repo().marcar_todas(usuario_id=usuario.id, correo=usuario.correo)
    except Exception as error:
        log.exception("No se pudieron marcar los avisos: %s", error)
        raise HTTPException(status_code=503,
                            detail="El buzón de avisos no está disponible.")
    log.info("%s marcó %s aviso(s) como leídos.", usuario.correo, cuantas)
    return Marcadas(marcadas=cuantas)
