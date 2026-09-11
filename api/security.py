"""Dependencias de seguridad de la API.

Aquí vive la única forma en que un endpoint queda protegido:

    @router.post("/algo")
    def algo(usuario: UsuarioSesion = Depends(exige("rfq:dictaminar"))):
        ...

``exige`` devuelve una dependencia que (1) verifica el token de sesión y (2)
comprueba el permiso.  Si algún endpoint futuro se olvida de declararla, el
test ``tests/api/test_seguridad.py::test_todo_endpoint_mutante_pide_sesion``
lo caza: recorre las rutas registradas y falla si alguna que escribe no exige
sesión.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.tokens import TokenInvalido, UsuarioSesion, leer

log = logging.getLogger("cotizador.api.security")

# auto_error=False para poder responder 401 con nuestro propio mensaje y con
# la cabecera WWW-Authenticate que el frontend usa para saber que debe volver
# a la pantalla de login.
_bearer = HTTPBearer(auto_error=False, description="Token de sesión (POST /api/auth/login)")

_NO_AUTORIZADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Sesión requerida o expirada.",
    headers={"WWW-Authenticate": "Bearer"},
)


def usuario_actual(
    credenciales: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> UsuarioSesion:
    """Devuelve el usuario de la sesión. 401 si no hay token válido."""
    if credenciales is None or not credenciales.credentials:
        raise _NO_AUTORIZADO
    try:
        return leer(credenciales.credentials)
    except TokenInvalido as err:
        log.debug("Acceso rechazado: %s", err)
        raise _NO_AUTORIZADO from err


def exige(permiso: str) -> Callable[..., UsuarioSesion]:
    """Dependencia que exige sesión válida **y** un permiso concreto.

    Se devuelve 403 (no 404) cuando la sesión es válida pero le falta el
    permiso: el usuario existe y sabe que el recurso está ahí, ocultarlo no
    aporta nada y complica el diagnóstico.
    """

    def _dependencia(usuario: UsuarioSesion = Depends(usuario_actual)) -> UsuarioSesion:
        if not usuario.puede(permiso):
            log.warning("Usuario %s (rol=%s) intentó una acción que requiere '%s'.",
                        usuario.correo, usuario.rol, permiso)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Tu rol ({usuario.rol or 'sin rol'}) no tiene el permiso '{permiso}'.",
            )
        return usuario

    return _dependencia
