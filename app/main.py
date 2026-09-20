"""
COTIZADOR - Detección de nuevos correos (Outlook)
Integra los 3 componentes:
  1. Filtro de no leídos (imaplib UNSEEN / Graph isRead eq false)
  2. Control de duplicados por message-id en PostgreSQL
  3. Ejecución periódica con la librería schedule
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parseaddr
from typing import List

import schedule

import app.clients.mapper as mapper
import app.core.config as config
import app.persistence.duplicates as duplicates
import app.persistence.spring_repository as spring_repository
import app.rfq.flow as flow
import app.rfq.horario as horario
import app.rfq.repository as repository
import app.rfq.thread_validator as thread_validator
from app.core.logging import configure_logging
from app.email.factory import EmailProviderFactory

log = logging.getLogger("cotizador")


@dataclass
class ResultadoCiclo:
    """Lo que devuelve un ciclo de detección.

    Existe para que la API no tenga que reimplementar el ciclo sólo para poder
    contar qué pasó: antes ``api/routes/status.py`` llevaba una copia literal
    de ``ciclo_deteccion()`` con los contadores metidos a mano, y las dos
    versiones ya habían empezado a separarse.
    """

    encontrados: int = 0
    procesados: int = 0
    rfqs: int = 0
    errores: int = 0
    detalles: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    # Un ciclo que no se ejecutó por estar fuera de horario no es un ciclo con
    # cero correos: la diferencia importa para no leer "no llega nada" cuando
    # lo que pasa es que todavía no ha abierto.
    en_horario: bool = True


def procesar_correo(correo):
    """
    Punto de entrada para la lógica del cotizador.
    Aplica la bifurcación RFQ/trash (flujo_rfq).
    """
    log.info("Correo NUEVO: %s | %s", correo["remitente"], correo["asunto"])
    clasificacion = flow.procesar(correo)
    return clasificacion


def map_email_message(msg):
    """Mapea un objeto EmailMessage al formato de diccionario requerido por el cotizador."""
    headers = {k.lower(): v for k, v in msg.raw_headers.items()}
    remitente_limpio = parseaddr(msg.sender)[1] if msg.sender else ""
    if not remitente_limpio and msg.sender:
        remitente_limpio = msg.sender

    return {
        "message_id": str(headers.get("message-id") or getattr(msg, "id", "") or "").strip(),
        "remitente": remitente_limpio,
        "asunto": msg.subject or "",
        "fecha": msg.date or "",
        "cuerpo": msg.body or "",
        # `cuerpo_html` sólo cuando el proveedor dice que lo es. `flow.limpiar_cuerpo`
        # lo leía desde el principio, pero nadie lo producía: el limpiador de HTML
        # quedaba desconectado y el modelo de lenguaje recibía el correo con sus
        # etiquetas, sus estilos y la cadena de respuestas citada.
        "cuerpo_html": (msg.body or "") if getattr(msg, "body_is_html", False) else "",
        "in_reply_to": str(headers.get("in-reply-to") or "").strip(),
        "references": str(headers.get("references") or "").strip(),
        "uid_local": msg.id,  # Para compatibilidad con IMAP
        "graph_id": msg.id,   # Para compatibilidad con Graph
        "adjuntos": [
            {
                "nombre": att.filename,
                "contenido": att.content,
                "content_type": att.content_type
            }
            for att in msg.attachments
        ]
    }


def ciclo_deteccion(*, forzar: bool = False) -> ResultadoCiclo:
    """Un ciclo completo: buscar no leídos -> filtrar duplicados -> procesar -> marcar como leído.

    Devuelve un ``ResultadoCiclo`` con el recuento de lo ocurrido, para que
    quien lo llame (el worker del servidor, la app de escritorio o el endpoint
    manual) pueda informar sin volver a implementar el ciclo.

    Fuera del horario de atención no se abre el buzón: se devuelve un
    resultado vacío con ``en_horario=False``. El correo se queda sin leer
    donde está y entra en el primer ciclo de la apertura siguiente, que es
    justo lo que se quiere —nada se pierde, no se gasta el modelo de
    madrugada y no sale una oferta a las 2 a.m.

    ``forzar`` se salta el horario. Lo usa el botón de "Ejecutar ciclo": si
    alguien lo pulsa un domingo es porque quiere que se lea ahora, y negárselo
    sería una puerta cerrada sin motivo.
    """
    resultado = ResultadoCiclo()

    if not forzar and not horario.abierto():
        motivo = horario.motivo_cerrado()
        log.info("Ciclo omitido. %s", motivo)
        resultado.en_horario = False
        resultado.detalles.append(motivo)
        return resultado

    log.info("Buscando correos no leídos (modo=%s)...", config.settings.MAIL_MODE)
    try:
        provider = EmailProviderFactory.get_provider()
        provider.connect()
        mensajes = provider.fetch_unread_messages()
    except Exception as error:
        log.error("Error al consultar el buzón: %s", error)
        resultado.errores = 1
        resultado.detalles.append(f"Error al consultar el buzón: {error}")
        return resultado

    resultado.encontrados = len(mensajes)

    for msg in mensajes:
        # Un correo que truena no debe tumbar el ciclo: se registra, se deja
        # SIN marcar como leído (para reintentarlo) y se sigue con el resto
        # del lote.
        try:
            correo = map_email_message(msg)

            # Conteo rápido por message-id ANTES de evaluar contenido
            if duplicates.es_duplicado(correo["message_id"]):
                log.debug("Duplicado ignorado: %s", correo["message_id"])
                resultado.detalles.append(f"Duplicado omitido: {correo['message_id']}")
                continue

            clasificacion = procesar_correo(correo)
            duplicates.registrar_correo(correo)
            if clasificacion and str(clasificacion).upper().startswith("RFQ"):
                resultado.rfqs += 1
            resultado.detalles.append(f"{clasificacion}: {correo.get('asunto', '?')}")
        except Exception as error:
            log.exception("Fallo al procesar el correo ID %s; queda sin leer "
                          "para reintentarlo: %s", getattr(msg, "id", "?"), error)
            resultado.errores += 1
            resultado.detalles.append(f"Error: {error}")
            continue

        # Marcar como leído en el servidor de correo después de procesar
        try:
            provider.mark_as_read(msg.id)
        except Exception as error:
            log.error("Error al marcar correo ID %s como leído: %s", msg.id, error)

        resultado.procesados += 1

    # Desconectar el proveedor de forma limpia
    if hasattr(provider, "disconnect"):
        try:
            provider.disconnect()
        except Exception:
            log.debug("Fallo al desconectar el proveedor; se ignora.", exc_info=True)

    # El respaldo por correo de lo que lleva demasiado tiempo esperando
    # dictamen. Va aquí y no en un hilo aparte porque el ciclo ya corre sólo
    # en horario de atención: así el recordatorio de un caso que entró el
    # viernes por la tarde sale el lunes por la mañana, no de madrugada.
    try:
        import app.rfq.recordatorios as recordatorios
        recordado = recordatorios.revisar()
        if recordado.get("avisados"):
            resultado.detalles.append(
                f"Recordatorio de dictamen enviado por {recordado['avisados']} "
                f"caso(s) ({recordado['correos']} correo/s).")
    except Exception as error:
        log.warning("No se pudo revisar lo pendiente de dictamen: %s", error)

    log.info("Ciclo terminado: %d no leídos, %d nuevos procesados, %d RFQ, %d con error.",
             resultado.encontrados, resultado.procesados, resultado.rfqs, resultado.errores)
    return resultado


def main():
    # El logging se configura aquí, en el punto de entrada, no como efecto
    # secundario de importar un módulo.
    configure_logging(app_env=config.settings.APP_ENV)

    # Inicialización centralizada de todos los dominios
    duplicates.inicializar_bd()
    thread_validator.inicializar_historial()
    spring_repository.inicializar_bd()
    repository.inicializar_bd()
    mapper.inicializar_bd()

    log.info("Cotizador iniciado. Intervalo: %d min.", config.settings.INTERVALO_MINUTOS)

    # Primera ejecución inmediata
    ciclo_deteccion()

    # Ejecución periódica con schedule
    schedule.every(config.settings.INTERVALO_MINUTOS).minutes.do(ciclo_deteccion)

    # Bucle de control con retraso
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
