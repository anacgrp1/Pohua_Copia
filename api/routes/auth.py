"""Rutas de sesión.

POST /api/auth/login     → intercambia correo+contraseña por un token
GET  /api/auth/me        → devuelve la sesión actual (la PWA la usa al arrancar)
POST /api/auth/password  → el usuario cambia su propia contraseña

El alta de usuarios no está aquí a propósito: se hace con
``scripts/crear_usuario.py``, desde el servidor.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from api.models.schemas import (
    CambioPasswordRequest,
    LoginRequest,
    LoginResponse,
    UsuarioPublico,
)
from api.security import usuario_actual
from app.auth import passwords, repository
from app.auth.tokens import UsuarioSesion, emitir

log = logging.getLogger("cotizador.api.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

_CREDENCIALES_INVALIDAS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Correo o contraseña incorrectos.",
    headers={"WWW-Authenticate": "Bearer"},
)


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest):
    """Valida credenciales y emite el token de sesión.

    El mismo error para correo inexistente, contraseña mala y cuenta
    desactivada: si se distinguieran, la pantalla de login se convertiría en
    un buscador de qué correos tienen cuenta.
    """
    try:
        usuario = repository.autenticar(body.correo, body.password)
    except Exception as err:
        log.exception("Fallo consultando la base durante el login.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo validar la sesión contra la base de datos.",
        ) from err

    if usuario is None:
        raise _CREDENCIALES_INVALIDAS

    log.info("Sesión iniciada: %s (rol=%s).", usuario.correo, usuario.rol)

    # El cuerpo del login lleva TAMBIÉN el estado de la foto.
    #
    # Sin esto, el usuario que la PWA guarda al entrar no tenía `tiene_foto`, y
    # la barra de la esquina se pintaba con las iniciales aunque la persona
    # tuviera foto: sólo aparecía al recargar, cuando el arranque vuelve a
    # pedir /me y ese sí la traía. Dos respuestas describiendo al mismo usuario
    # de dos maneras distintas; la de después contradecía a la de antes.
    respuesta = emitir(usuario)
    respuesta["usuario"].update(_estado_foto(usuario.id))
    return respuesta


def _estado_foto(usuario_id: int) -> dict:
    """``{tiene_foto, foto_actualizada}`` para las respuestas de sesión.

    La foto NO viaja en ellas: sólo si la hay y de cuándo es. Con esas dos
    cosas el navegador arma la dirección de la imagen —el sello va dentro— y
    la pide una vez, en lugar de arrastrar los bytes en cada arranque.

    Vive aquí y lo usan login y /me para que no puedan volver a discrepar. Si
    la consulta falla, se contesta "sin foto": una cara que falta no puede
    impedir entrar.
    """
    try:
        fila = repository.datos_foto(usuario_id)
        if fila:
            return {"tiene_foto": bool(fila[0]), "foto_actualizada": fila[1]}
    except Exception:
        log.debug("No se pudo leer el estado de la foto.", exc_info=True)
    return {"tiene_foto": False, "foto_actualizada": None}


@router.get("/me", response_model=UsuarioPublico)
def yo(usuario: UsuarioSesion = Depends(usuario_actual)):
    """Sesión actual. La PWA la llama al cargar para saber si sigue vigente."""
    return UsuarioPublico(
        id=usuario.id, correo=usuario.correo, nombre=usuario.nombre,
        rol=usuario.rol, permisos=usuario.permisos,
        **_estado_foto(usuario.id),
    )


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def cambiar_password(
    body: CambioPasswordRequest,
    usuario: UsuarioSesion = Depends(usuario_actual),
):
    """Cambia la contraseña del propio usuario.

    Se re-verifica la contraseña actual aunque la sesión sea válida: un token
    robado no debe bastar para dejar al dueño fuera de su cuenta.
    """
    if repository.autenticar(usuario.correo, body.password_actual) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La contraseña actual no es correcta.",
        )

    try:
        repository.cambiar_password(usuario.id, body.password_nueva)
    except passwords.PasswordInvalida as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err)
        ) from err

    log.info("Contraseña cambiada por el propio usuario %s.", usuario.correo)
