"""
SUBTAREA 2 [Lógica]
Control de duplicados: conteo rápido en PostgreSQL usando el
message-id del correo entrante ANTES de evaluar el contenido.

Conexión directa vía psycopg2 — no depende de PostgREST en producción.
"""
import logging
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

import app.core.config as config

log = logging.getLogger("cotizador.duplicados")


def conectar_bd(max_retries=3, delay=1.0):
    """Abre y devuelve una conexión psycopg2 a PostgreSQL.

    Usa ``settings.database_dsn`` que resuelve automáticamente
    ``DATABASE_URL`` (Neon/Railway/Render) o las variables ``PG_*``
    individuales, con ``sslmode=require`` para hosts remotos.

    La conexión se devuelve con ``autocommit=True`` para que los
    INSERT/UPDATE se confirmen inmediatamente sin necesidad de un
    ``commit()`` explícito.  Los módulos que necesiten transacciones
    pueden desactivar autocommit manualmente.

    Returns:
        psycopg2.connection: conexión abierta lista para usar.
    """
    import time
    dsn = config.settings.database_dsn
    
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(dsn)
            conn.autocommit = True
            return conn
        except psycopg2.OperationalError as e:
            if attempt < max_retries - 1:
                log.warning("Fallo al conectar a la BD (intento %d/%d): %s. Reintentando en %ss...", attempt + 1, max_retries, e, delay)
                time.sleep(delay)
            else:
                log.error("No se pudo conectar a la BD tras %d intentos.", max_retries)
                raise e


@contextmanager
def conexion_bd():
    """Context manager que abre y **cierra** una conexión.

    Existe porque usar la conexión de psycopg2 directamente como context
    manager NO la cierra: ese context manager gestiona la transacción (commit
    o rollback) y deja la conexión abierta a propósito, para reutilizarla.
    El código la usaba como si cerrara, así que cada correo procesado dejaba
    varias conexiones colgando contra Neon hasta que pasara el recolector de
    basura — y Neon tiene un tope de conexiones simultáneas.

    Uso::

        with conexion_bd() as conn:
            with conn.cursor() as cur:
                ...
    """
    conn = conectar_bd()
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:  # pragma: no cover - cerrar nunca debe tumbar al que llama
            log.debug("Fallo al cerrar la conexión; se ignora.", exc_info=True)


def inicializar_bd():
    """Verifica que exista la tabla del control de duplicados.

    Ya no crea nada: el esquema lo aplica ``make db-up`` (COT-93). El porqué
    está en ``src/schema.py``.
    """
    import app.persistence.schema as schema
    schema.verificar_tablas(("correos_procesados",))


def es_duplicado(message_id):
    """
    Conteo rápido por message-id. Retorna True si el correo ya fue
    procesado. Se llama ANTES de evaluar el contenido del correo.
    """
    if not message_id:
        # Sin message-id no se puede garantizar unicidad: tratar como nuevo
        return False

    sql = "SELECT COUNT(1) FROM correos_procesados WHERE message_id = %s;"
    with conexion_bd() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (message_id,))
            return cur.fetchone()[0] > 0


def registrar_correo(correo):
    """
    Registra el message-id tras procesar el correo.
    ON CONFLICT DO NOTHING evita errores si dos ejecuciones se cruzan.
    Retorna True si se insertó (correo nuevo), False si ya existía.
    """
    sql = """
    INSERT INTO correos_procesados (message_id, remitente, asunto, fecha_correo)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (message_id) DO NOTHING
    RETURNING id;
    """
    valores = (
        correo["message_id"],
        correo.get("remitente", ""),
        correo.get("asunto", ""),
        correo.get("fecha", ""),
    )

    with conexion_bd() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, valores)
            fila = cur.fetchone()
            return fila is not None


if __name__ == "__main__":
    inicializar_bd()
    print("Tabla 'correos_procesados' lista.")
