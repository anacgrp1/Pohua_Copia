"""La aceptación del aviso de privacidad y los términos de uso.

Los documentos viven en ``frontend/legal/`` (públicos: se leen sin sesión).
Aquí sólo se lleva la constancia de quién aceptó qué versión y cuándo, en la
tabla ``aceptaciones_legales`` (migración 027).

``VERSION_LEGAL`` tiene que ser la misma que ``VERSION`` en
``frontend/legal/responsable.js``: si se cambian los textos y no la versión,
nadie vuelve a aceptarlos; si se cambia la versión en un solo sitio, Pohua
pide aceptar una versión que la página no enseña. Una prueba lo vigila.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Optional

from app.persistence import duplicates

log = logging.getLogger("cotizador.legal")

VERSION_LEGAL = "2026-09-24"


@contextmanager
def _conexion(conexion=None):
    """Reusa la conexión recibida, o abre una propia (en autocommit) y la cierra."""
    if conexion is not None:
        yield conexion
        return
    with duplicates.conexion_bd() as conn:
        yield conn


def pendiente(usuario_id: int, conexion=None) -> Optional[str]:
    """La versión que ese usuario tiene que aceptar, o None si ya lo hizo.

    Si la base no contesta —o la migración aún no corrió— no se bloquea a
    nadie: se devuelve None y se vuelve a preguntar en el siguiente arranque.
    Dejar a toda la empresa fuera por una tabla que falta sería peor que
    pedir la aceptación un día más tarde.
    """
    try:
        with _conexion(conexion) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM aceptaciones_legales "
                    "WHERE usuario_id = %s AND version = %s LIMIT 1;",
                    (usuario_id, VERSION_LEGAL))
                return None if cur.fetchone() else VERSION_LEGAL
    except Exception:
        log.warning("No se pudo leer la aceptación legal del usuario %s.",
                    usuario_id, exc_info=True)
        return None


def aceptar(usuario_id: int, version: str, conexion=None) -> None:
    """Deja constancia. Sólo se acepta la versión vigente: aceptar otra no
    prueba que la persona leyera lo que hoy está publicado."""
    if version != VERSION_LEGAL:
        raise ValueError(
            "La versión aceptada (%s) no es la vigente (%s)." % (version, VERSION_LEGAL))
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO aceptaciones_legales (usuario_id, version) "
                "VALUES (%s, %s) ON CONFLICT (usuario_id, version) DO NOTHING;",
                (usuario_id, version))
        if not getattr(conn, "autocommit", True):
            conn.commit()
    log.info("Usuario %s aceptó el aviso de privacidad y los términos v%s.",
             usuario_id, version)
