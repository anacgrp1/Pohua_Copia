"""Pone una contraseña PROVISIONAL conocida a usuarios ya dados de alta.

    python scripts/contrasena_temporal.py --todos
    python scripts/contrasena_temporal.py john@isc.com sales@isc.com
    python scripts/contrasena_temporal.py --todos --password "Otra-Provisional-2026"

Se conecta con el ``DATABASE_URL`` del entorno o del ``.env`` (el mismo que
usa el servidor), así que se ejecuta desde la carpeta del proyecto.

Para qué es: arrancar con el equipo. A todos se les pone la misma contraseña
provisional (``password123`` si no se dice otra) y se les deja marcado
``debe_cambiar_password``: al entrar, Pohua les pide la suya antes de nada, y
la suya SÍ tiene que cumplir la política (12 caracteres, variedad, no común).

Se salta la política a propósito y sólo aquí: ``password123`` está en la lista
negra del servidor, y por la API no se puede poner. Es una llave de arranque,
no una contraseña; por eso queda la marca de "cámbiala".

Los usuarios dados de baja no se tocan salvo con ``--incluir-bajas``.
"""
from __future__ import annotations

import argparse
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("correos", nargs="*", help="Correos a los que ponérsela (o --todos).")
    parser.add_argument("--todos", action="store_true", help="Todos los usuarios activos.")
    parser.add_argument("--incluir-bajas", action="store_true",
                        help="También los dados de baja (con --todos).")
    parser.add_argument("--password", default="password123",
                        help="La provisional (por defecto: password123).")
    parser.add_argument("--si", action="store_true", help="No preguntar confirmación.")
    args = parser.parse_args()

    if not args.todos and not args.correos:
        parser.error("Di a quién: correos sueltos, o --todos.")

    import app.core.config  # noqa: F401  carga el .env como el servidor
    import app.persistence.duplicates as duplicates
    from app.auth import passwords

    hash_pw = passwords.hashear(args.password)

    with duplicates.conexion_bd() as conn:
        with conn.cursor() as cur:
            if args.todos:
                filtro = "" if args.incluir_bajas else "WHERE activo"
                cur.execute(f"SELECT id, correo, nombre, activo FROM usuarios {filtro} ORDER BY id;")
            else:
                cur.execute(
                    "SELECT id, correo, nombre, activo FROM usuarios "
                    "WHERE lower(correo) = ANY(%s) ORDER BY id;",
                    ([c.strip().lower() for c in args.correos],))
            filas = cur.fetchall()

        if not filas:
            print("No hay usuarios que coincidan.")
            return 1

        print("Se pondrá la contraseña provisional a:")
        for _, correo, nombre, activo in filas:
            print(f"  - {nombre} <{correo}>{'' if activo else '  (de baja)'}")
        print("Al entrar, Pohua les pedirá que pongan la suya.")
        if not args.si:
            respuesta = input("¿Seguir? [s/N] ").strip().lower()
            if respuesta not in ("s", "si", "sí", "y", "yes"):
                print("Nada cambiado.")
                return 1

        ids = [f[0] for f in filas]
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE usuarios SET password_hash = %s, debe_cambiar_password = true "
                "WHERE id = ANY(%s);",
                (hash_pw, ids))
            print(f"Listo: {cur.rowcount} usuario(s) con contraseña provisional.")

    if args.todos and not args.correos:
        faltan = [f[1] for f in filas]
        print("Correos:", ", ".join(faltan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
