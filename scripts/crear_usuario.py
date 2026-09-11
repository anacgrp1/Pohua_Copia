#!/usr/bin/env python
"""Alta de usuarios del cotizador desde la consola.

El alta NO se expone por HTTP a propósito: crear cuentas es algo que se hace
con acceso al servidor, no con una sesión del navegador.

Uso::

    python scripts/crear_usuario.py --correo ana@cgr-international.com \\
        --nombre "Ana Ramírez" --rol admin

La contraseña se pide de forma interactiva (no se escribe en la línea de
comandos, para que no quede en el historial del shell).  Para automatizarlo en
un despliegue se puede pasar por la variable de entorno ``COTIZADOR_PASSWORD``.

Roles disponibles: admin, pm, quoter (ver sql/migrations/006, que explica
cómo añadir otros si en ISC hacen falta).
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import passwords, repository  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402

# Los que siembra sql/migrations/006. Si añades un rol en la base, añádelo
# también aquí para poder asignarlo desde la consola.
ROLES = ("admin", "pm", "quoter")


def pedir_password() -> str:
    """Pide la contraseña dos veces y valida la política antes de devolverla."""
    desde_entorno = os.environ.get("COTIZADOR_PASSWORD")
    if desde_entorno:
        passwords.validar_politica(desde_entorno)
        return desde_entorno

    while True:
        pw = getpass.getpass("Contraseña (mínimo 12 caracteres): ")
        try:
            passwords.validar_politica(pw)
        except passwords.PasswordInvalida as err:
            print(f"  ✗ {err}")
            continue
        if pw != getpass.getpass("Repetir contraseña: "):
            print("  ✗ Las contraseñas no coinciden.")
            continue
        return pw


def main() -> int:
    parser = argparse.ArgumentParser(description="Alta de usuarios del cotizador")
    parser.add_argument("--correo", required=True)
    parser.add_argument("--nombre", required=True)
    parser.add_argument("--rol", required=True, choices=ROLES)
    args = parser.parse_args()

    configure_logging()

    try:
        password = pedir_password()
    except KeyboardInterrupt:
        print("\nCancelado.")
        return 130

    try:
        usuario_id = repository.crear_usuario(
            correo=args.correo, nombre=args.nombre,
            password=password, rol_codigo=args.rol,
        )
    except ValueError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2
    except Exception as err:  # conexión, permisos de base, etc.
        print(f"ERROR al escribir en la base de datos: {err}", file=sys.stderr)
        return 1

    print(f"Usuario '{args.correo}' listo (id={usuario_id}, rol={args.rol}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
