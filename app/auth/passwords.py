"""Hash y verificación de contraseñas.

Usa PBKDF2-HMAC-SHA256 de la librería estándar: no añade dependencias nuevas
y es una función de derivación aceptable para este caso (usuarios internos de
la planta, no un servicio público masivo).

Formato almacenado en ``usuarios.password_hash``::

    pbkdf2_sha256$<iteraciones>$<salt_b64>$<hash_b64>

El formato lleva las iteraciones dentro, así que se pueden subir en el futuro
sin invalidar los hashes viejos: ``verificar()`` lee las que traiga cada hash y
``necesita_rehash()`` avisa cuándo conviene regenerarlo.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

ALGORITMO = "pbkdf2_sha256"
ITERACIONES = 480_000
TAM_SALT = 16
TAM_HASH = 32

LONGITUD_MINIMA = 12


class PasswordInvalida(ValueError):
    """La contraseña propuesta no cumple la política mínima."""


def validar_politica(password: str) -> None:
    """Rechaza contraseñas triviales. Lanza ``PasswordInvalida``.

    La política es corta a propósito: longitud por encima de todo, que es lo
    que de verdad importa, más un puñado de valores obvios en la lista negra.
    """
    if not password or len(password) < LONGITUD_MINIMA:
        raise PasswordInvalida(
            f"La contraseña debe tener al menos {LONGITUD_MINIMA} caracteres."
        )
    if password.lower() in {
        "contrasena123", "contraseña123", "password123", "cotizador123",
        "administrador", "12345678901234", "qwertyuiop123",
    }:
        raise PasswordInvalida("La contraseña es demasiado común.")
    if len(set(password)) < 5:
        raise PasswordInvalida("La contraseña tiene muy poca variedad de caracteres.")


def _derivar(password: str, salt: bytes, iteraciones: int) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iteraciones, dklen=TAM_HASH
    )


def hashear(password: str, *, iteraciones: int = ITERACIONES) -> str:
    """Devuelve el hash listo para guardar en ``usuarios.password_hash``."""
    salt = secrets.token_bytes(TAM_SALT)
    dk = _derivar(password, salt, iteraciones)
    return "{}${}${}${}".format(
        ALGORITMO,
        iteraciones,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(dk).decode("ascii"),
    )


def verificar(password: str, hash_guardado: str | None) -> bool:
    """Compara en tiempo constante. Nunca lanza: un hash corrupto es un `False`.

    Si el usuario no tiene ``password_hash`` (columna nullable en la migración
    005) se devuelve False, de modo que un usuario sembrado sin contraseña no
    puede entrar hasta que se le asigne una.
    """
    if not password or not hash_guardado:
        return False
    try:
        algoritmo, iteraciones_txt, salt_b64, hash_b64 = hash_guardado.split("$")
        if algoritmo != ALGORITMO:
            return False
        salt = base64.b64decode(salt_b64)
        esperado = base64.b64decode(hash_b64)
        calculado = _derivar(password, salt, int(iteraciones_txt))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculado, esperado)


def necesita_rehash(hash_guardado: str | None) -> bool:
    """True si el hash usa menos iteraciones que las actuales."""
    if not hash_guardado:
        return True
    try:
        algoritmo, iteraciones_txt, _, _ = hash_guardado.split("$")
    except ValueError:
        return True
    return algoritmo != ALGORITMO or int(iteraciones_txt) < ITERACIONES
