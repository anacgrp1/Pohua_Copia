"""Shared dependencies for API routes.

Provides database connection helpers and simple configuration accessors
so that routes don't import ``app.persistence`` directly.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

log = logging.getLogger("cotizador.api")


@contextmanager
def get_db():
    """Yields a psycopg2 connection from the same pool the backend uses."""
    import app.persistence.duplicates as duplicates
    conn = duplicates.conectar_bd()
    try:
        yield conn
    finally:
        conn.close()


def get_config():
    """Returns the singleton Settings object."""
    import app.core.config as config
    return config.settings
