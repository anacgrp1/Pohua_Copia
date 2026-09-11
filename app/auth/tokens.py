"""Tokens de sesión (JWT HS256).

Se firman con ``settings.JWT_SECRET``.  En producción ``config._validate()``
exige que esa variable exista y tenga longitud razonable, así que aquí no hay
ningún valor por defecto: si falta, emitir o leer un token falla ruidosamente
en vez de firmar con cadena vacía.

El token lleva lo mínimo para autorizar sin ir a la base en cada petición:
``sub`` (id de usuario), ``correo``, ``nombre``, ``rol`` y ``permisos``.  Como
consecuencia, un cambio de rol no surte efecto hasta el siguiente login; con
sesiones de 8 h es un compromiso aceptable y evita una consulta por request.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import jwt

import app.core.config as config

log = logging.getLogger("cotizador.auth.tokens")

EMISOR = "cgr-cotizador"


class TokenInvalido(Exception):
    """El token no se pudo verificar (firma, expiración o formato)."""


@dataclass
class UsuarioSesion:
    """Usuario ya autenticado, tal y como viaja dentro del token."""

    id: int
    correo: str
    nombre: str
    rol: str
    permisos: List[str] = field(default_factory=list)

    def puede(self, permiso: str) -> bool:
        """True si el usuario tiene ese permiso (o es admin)."""
        return "admin" in self.permisos or permiso in self.permisos


def _secreto() -> str:
    secreto = config.settings.JWT_SECRET
    if not secreto:
        raise TokenInvalido(
            "JWT_SECRET no está configurada; la API no puede emitir ni validar sesiones."
        )
    return secreto


def emitir(usuario: UsuarioSesion, *, minutos: int | None = None) -> Dict[str, Any]:
    """Genera el token de sesión y devuelve el cuerpo de la respuesta de login."""
    duracion = minutos if minutos is not None else config.settings.JWT_EXPIRE_MINUTES
    ahora = datetime.now(timezone.utc)
    expira = ahora + timedelta(minutes=duracion)

    payload = {
        "iss": EMISOR,
        "sub": str(usuario.id),
        "correo": usuario.correo,
        "nombre": usuario.nombre,
        "rol": usuario.rol,
        "permisos": usuario.permisos,
        "iat": int(ahora.timestamp()),
        "exp": int(expira.timestamp()),
    }
    token = jwt.encode(payload, _secreto(), algorithm=config.settings.JWT_ALGORITHM)
    # PyJWT >= 2 devuelve str; en 1.x devolvía bytes.
    if isinstance(token, bytes):  # pragma: no cover - compatibilidad
        token = token.decode("utf-8")

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": duracion * 60,
        "usuario": {
            "id": usuario.id,
            "correo": usuario.correo,
            "nombre": usuario.nombre,
            "rol": usuario.rol,
            "permisos": usuario.permisos,
        },
    }


def leer(token: str) -> UsuarioSesion:
    """Verifica firma y expiración, y devuelve el usuario. Lanza ``TokenInvalido``."""
    if not token:
        raise TokenInvalido("Token vacío.")
    try:
        payload = jwt.decode(
            token,
            _secreto(),
            algorithms=[config.settings.JWT_ALGORITHM],
            issuer=EMISOR,
            options={"require": ["exp", "sub", "iss"]},
        )
    except jwt.ExpiredSignatureError as err:
        raise TokenInvalido("La sesión expiró.") from err
    except jwt.InvalidTokenError as err:
        # No se filtra el detalle al cliente: se registra y se responde genérico.
        log.warning("Token rechazado: %s", err)
        raise TokenInvalido("Token inválido.") from err

    try:
        return UsuarioSesion(
            id=int(payload["sub"]),
            correo=payload.get("correo", ""),
            nombre=payload.get("nombre", ""),
            rol=payload.get("rol", ""),
            permisos=list(payload.get("permisos") or []),
        )
    except (KeyError, TypeError, ValueError) as err:
        raise TokenInvalido("Token con contenido inesperado.") from err
