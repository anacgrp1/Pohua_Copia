"""
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


def es_duplicado(message_id, otras_claves=()):
    """
    ¿Este correo ya se atendió? Se llama ANTES de evaluar su contenido.

    Mira dos sitios y varias claves, porque un solo sitio con una sola clave
    dejó pasar el mismo correo dos veces —y salieron dos RFQ del mismo pedido—:

    * ``correos_procesados`` y también ``rfqs.message_id``: si el proceso se
      cayó DESPUÉS de dar de alta el RFQ y antes de apuntar el correo, el RFQ
      existe aunque el correo no conste como procesado.
    * El Message-ID y, en ``otras_claves``, el EntryID de Outlook: cuando el
      guardián de Outlook no deja leer la cabecera, el correo queda apuntado
      con su EntryID, y la siguiente vez —ya con permiso— llegaba con su
      Message-ID de verdad, que no constaba en ningún sitio.
    """
    claves = [c for c in [message_id, *(otras_claves or ())] if c]
    if not claves:
        # Sin ninguna clave no se puede garantizar unicidad: tratar como nuevo
        return False

    sql = """
        SELECT (SELECT COUNT(1) FROM correos_procesados
                 WHERE message_id = ANY(%(c)s) OR entry_id = ANY(%(c)s))
             + (SELECT COUNT(1) FROM rfqs WHERE message_id = ANY(%(c)s));
    """
    with conexion_bd() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"c": claves})
            return (cur.fetchone()[0] or 0) > 0


def se_puede_reintentar(message_id, otras_claves=(), minutos=5) -> bool:
    """¿Este correo, ya apuntado, se volvió a poner como no leído a propósito?

    El lector marca como leído todo lo que apunta —procesado, duplicado o en
    cuarentena—, así que un correo que está apuntado, **sin RFQ** y otra vez
    sin leer es que una persona lo volvió a marcar para que se lea de nuevo
    (pasó con cinco correos que la cuarentena paró por una comprobación de
    más: al corregirla seguían saltándose como «Duplicado omitido»).

    Sólo si la marca tiene más de ``minutos``: dos lectores a la vez (el del
    servidor y el de escritorio) se cruzan en segundos, y el que llega
    segundo ve la marca del primero ANTES de que exista el RFQ; con el
    margen, ese cruce sigue siendo un duplicado y no un reintento.
    """
    claves = [c for c in [message_id, *(otras_claves or ())] if c]
    if not claves:
        return False
    sql = """
        SELECT COUNT(1)
          FROM correos_procesados c
         WHERE (c.message_id = ANY(%(c)s) OR c.entry_id = ANY(%(c)s))
           AND c.fecha_registro < NOW() - (%(m)s * INTERVAL '1 minute')
           AND NOT EXISTS (SELECT 1 FROM rfqs r
                            WHERE r.message_id = ANY(%(c)s)
                               OR r.message_id = c.message_id);
    """
    with conexion_bd() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"c": claves, "m": int(minutos)})
            return (cur.fetchone()[0] or 0) > 0


def rfq_del_correo(message_id, otras_claves=()):
    """El RFQ (y su versión) que ya se dio de alta con este correo, o None."""
    claves = [c for c in [message_id, *(otras_claves or ())] if c]
    if not claves:
        return None
    with conexion_bd() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT rfq_id, version FROM rfqs WHERE message_id = ANY(%(c)s) "
                        "ORDER BY id DESC LIMIT 1;", {"c": claves})
            fila = cur.fetchone()
            return {"rfq_id": fila[0], "version": fila[1]} if fila else None


def hay_rfq_del_correo(message_id) -> bool:
    """¿Se llegó a dar de alta un RFQ con este correo?"""
    if not message_id:
        return False
    with conexion_bd() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(1) FROM rfqs WHERE message_id = %s;", (message_id,))
            return cur.fetchone()[0] > 0


def olvidar_correo(message_id, otras_claves=()) -> None:
    """Quita la marca de procesado: el correo se volverá a intentar."""
    claves = [c for c in [message_id, *(otras_claves or ())] if c]
    if not claves:
        return
    with conexion_bd() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM correos_procesados "
                        "WHERE message_id = ANY(%(c)s) OR entry_id = ANY(%(c)s);",
                        {"c": claves})


def registrar_correo(correo, otras_claves=()):
    """
    Apunta el correo como atendido. Se llama ANTES de procesarlo.
    ON CONFLICT DO NOTHING evita errores si dos ejecuciones se cruzan.
    Retorna True si se insertó (correo nuevo), False si ya existía.

    ``otras_claves`` (el EntryID de Outlook) va en la MISMA fila, en
    ``entry_id``: así el correo se reconoce tanto si la próxima vez llega con
    su Message-ID como si el guardián de Outlook sólo deja ver el EntryID, y
    sigue siendo un correo —el recorrido de la pantalla Mail cuenta filas—.
    """
    sql = """
    INSERT INTO correos_procesados (message_id, remitente, asunto, fecha_correo, entry_id)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (message_id) DO NOTHING
    RETURNING id;
    """
    extra = [c for c in (otras_claves or ()) if c and c != correo["message_id"]]
    valores = (
        correo["message_id"],
        correo.get("remitente", ""),
        correo.get("asunto", ""),
        correo.get("fecha", ""),
        extra[0] if extra else None,
    )

    with conexion_bd() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, valores)
            fila = cur.fetchone()
            return fila is not None


if __name__ == "__main__":
    inicializar_bd()
    print("Tabla 'correos_procesados' lista.")
