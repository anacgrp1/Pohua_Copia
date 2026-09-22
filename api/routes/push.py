"""API routes — los avisos en el teléfono (Web Push).

GET    /api/push/clave        → la clave pública VAPID (o si está apagado)
GET    /api/push/dispositivos → los dispositivos suscritos de quien pregunta
POST   /api/push/suscribir    → guarda la suscripción de este dispositivo
DELETE /api/push/suscribir    → la borra (body: {endpoint})
POST   /api/push/probar       → manda un aviso de prueba a mis dispositivos

Quien puede ver la campana (``notificaciones:ver``) puede recibirla en el
teléfono; es el mismo permiso a propósito.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.security import exige
from app.auth.tokens import UsuarioSesion

log = logging.getLogger("cotizador.api.push")

router = APIRouter(prefix="/api/push", tags=["push"])


class Suscripcion(BaseModel):
    suscripcion: Dict[str, Any]     # PushSubscription.toJSON()
    # El idioma de Pohua en este aparato. Opcional a propósito: una versión
    # anterior de la web no lo manda, y quedarse sin avisos por eso sería peor
    # que recibirlos en inglés.
    idioma: Optional[str] = None


class Baja(BaseModel):
    endpoint: str


@router.get("/clave")
def clave(usuario: UsuarioSesion = Depends(exige("notificaciones:ver"))):
    import app.notifications.push as push
    return {"habilitado": push.habilitado(), "clave_publica": push.clave_publica()}


@router.get("/dispositivos")
def dispositivos(usuario: UsuarioSesion = Depends(exige("notificaciones:ver"))):
    import app.notifications.push as push
    filas = push.listar(usuario.id)
    return {"dispositivos": [
        {"id": f["id"], "endpoint": f["endpoint"], "navegador": f["navegador"],
         "creada_en": f["creada_en"], "ultimo_envio": f["ultimo_envio"], "fallos": f["fallos"]}
        for f in filas]}


@router.post("/suscribir")
def suscribir(body: Suscripcion, request: Request,
              usuario: UsuarioSesion = Depends(exige("notificaciones:ver"))):
    import app.notifications.push as push
    if not push.habilitado():
        raise HTTPException(status_code=503, detail="Los avisos push no están configurados "
                            "en el servidor (faltan las claves VAPID).")
    try:
        sub_id = push.suscribir(usuario.id, usuario.correo, body.suscripcion,
                                navegador=request.headers.get("user-agent"),
                                # El idioma de Pohua en ESTE aparato: es lo que
                                # decide en qué idioma le llegan los avisos, y
                                # sólo el navegador lo sabe.
                                idioma=body.idioma)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        log.exception("No se pudo guardar la suscripción push de %s", usuario.correo)
        raise HTTPException(status_code=500, detail=str(e))
    return {"id": sub_id}


@router.delete("/suscribir")
def desuscribir(body: Baja, usuario: UsuarioSesion = Depends(exige("notificaciones:ver"))):
    import app.notifications.push as push
    return {"borrada": push.desuscribir(body.endpoint, usuario_id=usuario.id)}


@router.post("/probar")
def probar(usuario: UsuarioSesion = Depends(exige("notificaciones:ver"))):
    """Un aviso de prueba a los dispositivos de quien lo pide, en el momento."""
    import app.notifications.push as push
    if not push.habilitado():
        raise HTTPException(status_code=503, detail="Los avisos push no están configurados.")
    n = push.enviar_a_todos(titulo="Pohua: avisos activados",
                            cuerpo="Así se verá cada RFQ que necesite tu dictamen.",
                            nivel="ok", usuario_id=usuario.id, en_segundo_plano=False)
    return {"dispositivos": n}
