"""La aceptación del aviso de privacidad y los términos de uso.

POST /api/legal/aceptar  {version}  → deja constancia de que el usuario de la
                                      sesión aceptó esa versión.

Los documentos no pasan por aquí: son páginas públicas en ``/legal/``, porque
tienen que poder leerse antes de entrar.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.security import usuario_actual
from app import legal
from app.auth.tokens import UsuarioSesion

router = APIRouter(prefix="/api/legal", tags=["legal"])


class AceptacionRequest(BaseModel):
    version: str = Field(..., max_length=20)


@router.post("/aceptar", status_code=status.HTTP_204_NO_CONTENT)
def aceptar(body: AceptacionRequest, usuario: UsuarioSesion = Depends(usuario_actual)):
    try:
        legal.aceptar(usuario.id, body.version)
    except ValueError as err:
        # La página se quedó con una versión vieja: que recargue y lea la nueva.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo registrar la aceptación. Inténtalo de nuevo.",
        ) from err
