"""Verificación del esquema: una sola fuente de verdad para el DDL.

Por qué existe
--------------
Los módulos de acceso a datos creaban sus tablas con ``CREATE TABLE IF NOT
EXISTS`` embebido, en paralelo a ``sql/schema.sql`` y las migraciones. Ese
DDL quedó congelado en la forma **anterior** a la migración ``004``: sin
``resorte_id``, sin los veredictos, sin el score. Y como usa ``IF NOT
EXISTS``, el conflicto era silencioso — la tabla ya existía, la migración no
se aplicaba, y el problema sólo aparecía cuando una query pedía una columna
ausente.

Desde COT-93 el esquema lo aplica ``make db-up`` (``schema.sql`` + todas las
migraciones, 43 tablas) y el smoke test lo verifica contra PostgreSQL real.
Este módulo sustituye la creación por una **verificación**: si las tablas no
están, se falla de inmediato con un mensaje que dice qué correr, en vez de
crear en silencio un esquema viejo.

Uso
---
``verificar_tablas(("correos_procesados",))`` → lanza ``EsquemaIncompletoError``
si falta alguna.
"""
import logging

log = logging.getLogger("cotizador.esquema")

_SQL_TABLAS_PRESENTES = """
SELECT table_name
FROM information_schema.tables
WHERE table_schema = current_schema()
  AND table_name = ANY(%s);
"""

_AYUDA = (
    "El esquema lo aplica 'make db-up' (schema.sql + migraciones). "
    "Los módulos ya no crean tablas: ver src/schema.py."
)


class EsquemaIncompletoError(RuntimeError):
    """Faltan tablas que el código necesita para operar."""


def tablas_faltantes(tablas, conexion=None):
    """Devuelve la lista de ``tablas`` que no existen en la base."""
    esperadas = list(tablas)
    if not esperadas:
        return []

    import app.persistence.duplicates as duplicates

    propia = conexion is None
    conn = conexion or duplicates.conectar_bd()
    try:
        with conn.cursor() as cursor:
            cursor.execute(_SQL_TABLAS_PRESENTES, (esperadas,))
            presentes = {fila[0] for fila in cursor.fetchall()}
    finally:
        if propia and hasattr(conn, "close"):
            conn.close()

    return [t for t in esperadas if t not in presentes]


def verificar_tablas(tablas, conexion=None):
    """Verifica que existan las ``tablas``; si falta alguna, falla claro.

    Raises:
        EsquemaIncompletoError: con el nombre de las tablas ausentes y la
            instrucción para crearlas.
    """
    faltantes = tablas_faltantes(tablas, conexion=conexion)
    if faltantes:
        raise EsquemaIncompletoError(
            f"Faltan tablas en la base de datos: {', '.join(faltantes)}. {_AYUDA}"
        )
    log.debug("Esquema verificado: %s", ", ".join(tablas))
