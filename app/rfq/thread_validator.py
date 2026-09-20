"""
SUBTAREA 2 [Lógica - Hilos]
Validación de respuestas: analiza in-reply-to y references, o busca
el ID del RFQ en el asunto, para asociar el correo al historial.
"""
import logging
import re

import app.persistence.duplicates as duplicates
import app.rfq.detector as detector

log = logging.getLogger("cotizador.hilos")


def inicializar_historial():
    """Verifica que exista la tabla de historial (message-id → RFQ).

    Ya no crea nada: el esquema lo aplica ``make db-up`` (COT-93).
    """
    import app.persistence.schema as schema
    schema.verificar_tablas(("rfq_historial",))


def buscar_rfq_por_message_id(message_id):
    """Retorna el rfq_id asociado a un message-id del historial, o None."""
    if not message_id:
        return None
    sql = "SELECT rfq_id FROM rfq_historial WHERE message_id = %s LIMIT 1;"
    with duplicates.conexion_bd() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(sql, (message_id.strip(),))
            fila = cursor.fetchone()
            return fila[0] if fila else None


def registrar_en_historial(rfq_id, message_id, asunto=""):
    """Asocia un correo (message-id) al historial de un RFQ."""
    sql = """
    INSERT INTO rfq_historial (rfq_id, message_id, asunto)
    VALUES (%s, %s, %s)
    ON CONFLICT (message_id) DO NOTHING;
    """
    with duplicates.conexion_bd() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(sql, (rfq_id, message_id, asunto))


def validar_respuesta(correo):
    """
    Determina si el correo es RESPUESTA de un RFQ existente.
    Orden de validación:
      1. Cabecera In-Reply-To  -> buscar en historial
      2. Cabecera References   -> buscar cada message-id en historial
      3. ID del RFQ en asunto  -> ej. "RE: RFQ-2024-001"
    Retorna el rfq_id asociado, o None si no es respuesta.
    """
    # 1. In-Reply-To
    in_reply_to = (correo.get("in_reply_to") or "").strip()
    if in_reply_to:
        rfq_id = buscar_rfq_por_message_id(in_reply_to)
        if rfq_id:
            log.info("Respuesta asociada por In-Reply-To al RFQ %s", rfq_id)
            return rfq_id

    # 2. References (lista de message-ids separados por espacios)
    references = (correo.get("references") or "").split()
    for ref in references:
        rfq_id = buscar_rfq_por_message_id(ref)
        if rfq_id:
            log.info("Respuesta asociada por References al RFQ %s", rfq_id)
            return rfq_id

    # 3. ID del RFQ en el asunto
    id_en_asunto = detector.extraer_id_rfq(correo.get("asunto", ""))
    if id_en_asunto:
        sql = "SELECT COUNT(1) FROM rfq_historial WHERE rfq_id = %s;"
        with duplicates.conexion_bd() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(sql, (id_en_asunto,))
                if cursor.fetchone()[0] > 0:
                    log.info("Respuesta asociada por ID en asunto al RFQ %s",
                             id_en_asunto)
                    return id_en_asunto

    # 4. Mismo remitente y mismo asunto que un correo ya visto
    rfq_id = _por_remitente_y_asunto(correo)
    if rfq_id:
        log.info("Respuesta asociada por remitente y asunto al RFQ %s", rfq_id)
        return rfq_id

    return None


# Prefijos que los clientes de correo ponen delante al responder o reenviar.
_PREFIJOS = ("re:", "rv:", "fwd:", "fw:", "res:", "tr:", "aw:")


def asunto_base(asunto: str) -> str:
    """El asunto sin los "RE:" ni la etiqueta [RFQ ...], en minúsculas.

    Sirve para reconocer que "RE: test rfq [RFQ INT-1A2B]" y "test rfq" son la
    misma conversación.
    """
    texto = (asunto or "").strip()
    texto = re.sub(r"\[\s*RFQ[^\]]*\]", " ", texto, flags=re.IGNORECASE)
    cambiado = True
    while cambiado:
        cambiado = False
        for prefijo in _PREFIJOS:
            if texto.lower().startswith(prefijo):
                texto = texto[len(prefijo):].lstrip()
                cambiado = True
    return re.sub(r"\s+", " ", texto).strip().lower()


def _por_remitente_y_asunto(correo):
    """El RFQ de un correo anterior del MISMO remitente con el MISMO asunto.

    Es la red de seguridad del hilo. Cuando el comprador contesta a nuestra
    respuesta, la cabecera que encadena los mensajes apunta a un correo que el
    sistema mandó y nunca leyó, así que por ahí no hay nada; y si además borra
    o cambia la etiqueta del asunto, tampoco hay identificador. Lo que casi
    nunca cambia es el par remitente + asunto, y con eso basta para saber de
    qué conversación se trata.

    Se mira sólo lo que escribió ESA persona, y lo más reciente primero: dos
    compradores distintos con el mismo asunto no se mezclan.
    """
    remitente = (correo.get("remitente") or "").strip().lower()
    base = asunto_base(correo.get("asunto"))
    if not remitente or not base:
        return None

    sql = """
    SELECT h.rfq_id, c.asunto
    FROM rfq_historial h
    JOIN correos_procesados c ON c.message_id = h.message_id
    WHERE lower(c.remitente) = %s
    ORDER BY c.fecha_registro DESC
    LIMIT 20;
    """
    try:
        with duplicates.conexion_bd() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(sql, (remitente,))
                filas = cursor.fetchall()
    except Exception as error:
        log.warning("No se pudo buscar el hilo por remitente y asunto: %s", error)
        return None

    for rfq_id, asunto in filas:
        if asunto_base(asunto) == base:
            return rfq_id
    return None
