"""Persistencia de usuarios y permisos.

Se apoya en las tablas que ya crea la migración 005 (``usuarios``, ``roles``,
``permisos``, ``rol_permisos``); no inventa un esquema paralelo.

Sigue el mismo contrato que el resto de repositorios del proyecto: todas las
funciones aceptan ``conexion=None`` para poder reusar una conexión existente
(y para poder pasar un doble en los tests); si no se pasa ninguna, abren y
cierran la suya.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import psycopg2

import app.persistence.duplicates as duplicates
from app.auth import passwords
from app.auth.tokens import UsuarioSesion

log = logging.getLogger("cotizador.auth.repository")


@contextmanager
def _conexion(conexion=None):
    """Reusa la conexión recibida, o abre una propia y la cierra al salir."""
    if conexion is not None:
        yield conexion
        return
    with duplicates.conexion_bd() as conn:
        yield conn


_SELECT_USUARIO = """
    SELECT u.id, u.correo, u.nombre, u.password_hash, u.activo,
           COALESCE(r.codigo, '') AS rol, COALESCE(u.externo, false)
    FROM usuarios u
    LEFT JOIN roles r ON r.id = u.rol_id
    WHERE {filtro}
    LIMIT 1;
"""

_SELECT_PERMISOS = """
    SELECT p.codigo
    FROM usuarios u
    JOIN rol_permisos rp ON rp.rol_id = u.rol_id
    JOIN permisos p      ON p.id = rp.permiso_id
    WHERE u.id = %s
    ORDER BY p.codigo;
"""


def _fila_a_dict(fila) -> Dict[str, Any]:
    return {
        "id": fila[0],
        "correo": fila[1],
        "nombre": fila[2],
        "password_hash": fila[3],
        "activo": fila[4],
        "rol": fila[5] or "",
        # Marca informativa: quién es de fuera de ISC. No concede ni quita
        # permisos —eso lo decide el rol—, pero sí cambia cómo se lee la lista
        # de usuarios.
        "externo": bool(fila[6]),
    }


def obtener_por_correo(correo: str, conexion=None) -> Optional[Dict[str, Any]]:
    """Busca un usuario por correo (sin distinguir mayúsculas). None si no existe."""
    if not correo:
        return None
    sql = _SELECT_USUARIO.format(filtro="lower(u.correo) = lower(%s)")
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (correo.strip(),))
            fila = cur.fetchone()
            return _fila_a_dict(fila) if fila else None


def obtener_por_id(usuario_id: int, conexion=None) -> Optional[Dict[str, Any]]:
    """Busca un usuario por id. None si no existe."""
    sql = _SELECT_USUARIO.format(filtro="u.id = %s")
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (usuario_id,))
            fila = cur.fetchone()
            return _fila_a_dict(fila) if fila else None


def permisos_de(usuario_id: int, conexion=None) -> List[str]:
    """Códigos de permiso del rol del usuario."""
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_PERMISOS, (usuario_id,))
            return [f[0] for f in cur.fetchall()]


def registrar_acceso(usuario_id: int, conexion=None) -> None:
    """Sella ``ultimo_acceso``. Un fallo aquí no debe impedir el login."""
    try:
        with _conexion(conexion) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE usuarios SET ultimo_acceso = now() WHERE id = %s;",
                    (usuario_id,),
                )
    except Exception:
        log.warning("No se pudo sellar ultimo_acceso del usuario %s.", usuario_id,
                    exc_info=True)


def autenticar(correo: str, password: str, conexion=None) -> Optional[UsuarioSesion]:
    """Valida credenciales y devuelve el usuario de sesión, o None.

    Devuelve None indistintamente si el correo no existe, si la contraseña no
    coincide o si la cuenta está desactivada: la capa HTTP responde el mismo
    error en los tres casos para no revelar qué correos están dados de alta.
    """
    with _conexion(conexion) as conn:
        usuario = obtener_por_correo(correo, conexion=conn)
        if usuario is None:
            # Se verifica igualmente contra un hash ficticio para que el tiempo
            # de respuesta no delate si el correo existe o no.
            passwords.verificar(password, passwords.hashear("usuario-inexistente"))
            return None

        if not passwords.verificar(password, usuario["password_hash"]):
            log.info("Login fallido para %s (contraseña incorrecta).", correo)
            return None

        if not usuario["activo"]:
            log.info("Login rechazado para %s (cuenta desactivada).", correo)
            return None

        permisos = permisos_de(usuario["id"], conexion=conn)
        registrar_acceso(usuario["id"], conexion=conn)

        return UsuarioSesion(
            id=usuario["id"],
            correo=usuario["correo"],
            nombre=usuario["nombre"],
            rol=usuario["rol"],
            permisos=permisos,
        )


def cambiar_password(usuario_id: int, password_nueva: str, conexion=None) -> None:
    """Cambia la contraseña. Valida la política antes de escribir."""
    passwords.validar_politica(password_nueva)
    nuevo_hash = passwords.hashear(password_nueva)
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE usuarios SET password_hash = %s WHERE id = %s;",
                (nuevo_hash, usuario_id),
            )
    log.info("Contraseña actualizada para el usuario %s.", usuario_id)


def crear_usuario(correo: str, nombre: str, password: str, rol_codigo: str,
                  conexion=None) -> int:
    """Da de alta un usuario y devuelve su id.

    La usa ``scripts/crear_usuario.py``; no se expone por HTTP para no
    convertir el alta en algo que pueda hacer cualquiera con una sesión.
    """
    passwords.validar_politica(password)
    hash_pw = passwords.hashear(password)

    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM roles WHERE codigo = %s;", (rol_codigo,))
            fila = cur.fetchone()
            if not fila:
                raise ValueError(
                    f"El rol '{rol_codigo}' no existe. "
                    "Aplica sql/migrations/006_auth_roles.sql primero."
                )
            rol_id = fila[0]

            cur.execute(
                """
                INSERT INTO usuarios (correo, nombre, rol_id, password_hash, activo)
                VALUES (%s, %s, %s, %s, true)
                ON CONFLICT (correo) DO UPDATE
                    SET nombre = EXCLUDED.nombre,
                        rol_id = EXCLUDED.rol_id,
                        password_hash = EXCLUDED.password_hash,
                        activo = true
                RETURNING id;
                """,
                (correo.strip().lower(), nombre.strip(), rol_id, hash_pw),
            )
            return cur.fetchone()[0]


# --------------------------------------------------------------------------- #
# Gestión de usuarios (perfil y administración)
# --------------------------------------------------------------------------- #

# Tamaño máximo de una foto ya recortada por el navegador. 256x256 en PNG rara
# vez pasa de 80 KB; el tope está para que una petición manipulada no meta un
# megabyte por usuario en la base.
MAX_BYTES_FOTO = 400 * 1024


def listar_usuarios(conexion=None) -> List[Dict[str, Any]]:
    """Todos los usuarios con su rol. Sin el hash de la contraseña.

    `foto IS NOT NULL` en vez de la foto misma: traer los bytes de todas las
    fotos para pintar una lista sería mover megabytes por una columna que sólo
    se usa para saber si hay que pedir la imagen.
    """
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.id, u.correo, u.nombre, COALESCE(r.codigo, '') AS rol,
                       COALESCE(u.externo, false) AS externo,
                       u.activo, u.ultimo_acceso::text, u.creado_en::text,
                       u.foto IS NOT NULL AS tiene_foto,
                       u.foto_actualizada::text
                FROM usuarios u
                LEFT JOIN roles r ON r.id = u.rol_id
                ORDER BY u.activo DESC, lower(u.nombre);
            """)
            columnas = ("id", "correo", "nombre", "rol", "externo", "activo", "ultimo_acceso",
                        "creado_en", "tiene_foto", "foto_actualizada")
            return [dict(zip(columnas, f)) for f in cur.fetchall()]


def listar_roles(conexion=None) -> List[Dict[str, Any]]:
    """Los roles que existen en la base, para el desplegable del formulario.

    Se leen, no se codifican en el frontend: si mañana se añade un rol con una
    migración, aparece solo.
    """
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT codigo, nombre, COALESCE(descripcion, '') "
                "FROM roles ORDER BY codigo;")
            return [{"codigo": c, "nombre": n, "descripcion": d}
                    for c, n, d in cur.fetchall()]


def actualizar_usuario(usuario_id: int, *, nombre: Optional[str] = None,
                       rol_codigo: Optional[str] = None,
                       activo: Optional[bool] = None,
                       externo: Optional[bool] = None,
                       conexion=None) -> bool:
    """Cambia nombre, rol y/o alta-baja. Devuelve False si el usuario no existe.

    El correo NO se puede cambiar: es la identidad con la que se inicia sesión
    y con la que quedan firmadas las decisiones sobre RFQs en la bitácora.
    Cambiarlo reescribiría la historia de quién aprobó qué.
    """
    campos = []
    valores: List[Any] = []

    if nombre is not None:
        limpio = nombre.strip()
        if not limpio:
            raise ValueError("El nombre no puede quedar vacío.")
        campos.append("nombre = %s")
        valores.append(limpio)

    if activo is not None:
        campos.append("activo = %s")
        valores.append(bool(activo))

    if externo is not None:
        campos.append("externo = %s")
        valores.append(bool(externo))

    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            if rol_codigo is not None:
                cur.execute("SELECT id FROM roles WHERE codigo = %s;", (rol_codigo,))
                fila = cur.fetchone()
                if not fila:
                    raise ValueError(f"El rol '{rol_codigo}' no existe.")
                campos.append("rol_id = %s")
                valores.append(fila[0])

            if not campos:
                return True   # nada que cambiar no es un error

            valores.append(usuario_id)
            cur.execute(
                f"UPDATE usuarios SET {', '.join(campos)} WHERE id = %s RETURNING id;",
                valores,
            )
            cambiado = cur.fetchone() is not None

    if cambiado:
        log.info("Usuario %s actualizado (%s).", usuario_id, ", ".join(campos))
    return cambiado


def guardar_foto(usuario_id: int, datos: bytes, tipo: str, conexion=None) -> None:
    """Guarda la foto de perfil ya recortada por el navegador."""
    if not datos:
        raise ValueError("La imagen está vacía.")
    if len(datos) > MAX_BYTES_FOTO:
        raise ValueError(
            f"La imagen pesa {len(datos) // 1024} KB; el máximo son "
            f"{MAX_BYTES_FOTO // 1024} KB.")
    if tipo not in ("image/png", "image/jpeg", "image/webp"):
        raise ValueError(f"Formato no admitido: {tipo}.")

    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE usuarios SET foto = %s, foto_tipo = %s, "
                "foto_actualizada = now() WHERE id = %s;",
                (psycopg2.Binary(datos), tipo, usuario_id),
            )
    log.info("Foto de perfil actualizada para el usuario %s (%d bytes).",
             usuario_id, len(datos))


def borrar_foto(usuario_id: int, conexion=None) -> None:
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE usuarios SET foto = NULL, foto_tipo = NULL, "
                "foto_actualizada = NULL WHERE id = %s;",
                (usuario_id,),
            )


def obtener_foto(usuario_id: int, conexion=None) -> Optional[tuple]:
    """Devuelve ``(bytes, tipo)`` o None si el usuario no tiene foto."""
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT foto, foto_tipo FROM usuarios WHERE id = %s;",
                (usuario_id,))
            fila = cur.fetchone()
    if not fila or fila[0] is None:
        return None
    return bytes(fila[0]), fila[1] or "image/png"


def datos_foto(usuario_id: int, conexion=None) -> Optional[tuple]:
    """``(tiene_foto, sello)`` sin traer los bytes de la imagen.

    Lo usa ``/api/auth/me``, que se llama en cada arranque de la aplicación:
    devolver ahí la foto entera cargaría de bytes la petición más frecuente.
    """
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT foto IS NOT NULL, foto_actualizada::text "
                "FROM usuarios WHERE id = %s;",
                (usuario_id,))
            fila = cur.fetchone()
    return (bool(fila[0]), fila[1]) if fila else None
