"""COT-72 [Flujo] Dictamen del plant manager sobre un RFQ no factible.

Propósito
---------
Cerrar el circuito de factibilidad. El motor (COT-75) nunca declina: cuando
detecta que un RFQ no cumple las directrices, lo deja en ``RequiresReview``
con sus motivos y el que dictamina es el **plant manager**. Este módulo es lo
que la pantalla del PM (COT-31/COT-77, CGRmx) llama cuando esa persona
resuelve:

* ``aprobar(rfq_id)``  → el RFQ sigue su curso hacia cotización.
* ``declinar(rfq_id)`` → se registra el dictamen **y se le avisa al cliente**
  con la plantilla ``declinar_rfq`` (COT-59).

Ése es el único punto del sistema desde el que sale un correo diciéndole a un
cliente que su RFQ no es factible: nunca lo dispara el motor por su cuenta.

Alcance
-------
* **Sí hace:** registrar ``veredicto_final`` + estado, y despachar el correo
  de declinación.
* **NO hace:** decidir (eso es de la persona), ni dibujar la pantalla, ni
  volver a evaluar las directrices.

Orden de las dos operaciones
----------------------------
Primero se registra el dictamen, después se manda el correo. Si el envío
falla, el veredicto queda escrito igual y el correo se puede reintentar; al
revés, un cliente podría recibir la declinación de un RFQ que en la base
sigue abierto.

Funciones públicas
------------------
``aprobar(rfq_id, ...) -> dict``
``declinar(rfq_id, ...) -> dict``
``resolver(rfq_id, veredicto, ...) -> dict``
"""

from __future__ import annotations

import logging
from typing import Optional

import app.feasibility.engine as engine

log = logging.getLogger("cotizador.decision_pm")

# Vocabulario del veredicto final; lo define el motor para que sistema y
# pantalla del PM escriban lo mismo en `rfqs.veredicto_final`.
FACTIBLE = engine.FINAL_FACTIBLE
NO_FACTIBLE = engine.FINAL_NO_FACTIBLE
VEREDICTOS = (FACTIBLE, NO_FACTIBLE)


def aprobar(rfq_id, version=None, nota=None, usuario=None, conexion=None) -> dict:
    """El PM confirma que el RFQ sí es factible. No se le escribe al cliente."""
    return resolver(rfq_id, FACTIBLE, version=version, nota=nota,
                    usuario=usuario, conexion=conexion)


def declinar(rfq_id, version=None, nota=None, usuario=None, destinatario=None,
             enviar_correo=True, conexion=None) -> dict:
    """El PM resuelve que el RFQ no es factible: se registra y se declina.

    ``enviar_correo=False`` registra el dictamen sin avisarle al cliente, para
    cuando la pantalla re-guarda una decisión ya tomada o el comercial
    prefiere dar la noticia por su cuenta. El módulo no lleva registro de si
    ya se envió: esa decisión es de quien llama.
    """
    return resolver(rfq_id, NO_FACTIBLE, version=version, nota=nota,
                    usuario=usuario, destinatario=destinatario,
                    enviar_correo=enviar_correo, conexion=conexion)


def resolver(rfq_id, veredicto, version=None, nota=None, usuario=None,
             destinatario=None, enviar_correo=True, conexion=None) -> dict:
    """Registra el dictamen del PM y, si declina, avisa al cliente.

    Args:
        rfq_id: identificador del RFQ.
        veredicto: ``FACTIBLE`` o ``NO_FACTIBLE``.
        version: versión del RFQ. Por defecto, la última.
        nota: comentario del PM; se anexa a ``rfqs.notas``, debajo de los
            motivos que dejó el motor.
        usuario: quién dictaminó; queda en la nota, porque hoy ``rfqs`` no
            tiene columna para el responsable.
        destinatario: a quién escribirle. Por defecto, el remitente del correo
            original que quedó en ``datos_json``.
        enviar_correo: sólo aplica al declinar.
        conexion: conexión psycopg2 abierta (inyección para pruebas).

    Returns:
        ``{id, rfq_id, version, veredicto_final, estado, correo_enviado}``.

    Raises:
        ValueError: si el veredicto no es uno de los dos admitidos, o si el
            RFQ no existe. El correo no se manda si el registro falla.
    """
    if veredicto not in VEREDICTOS:
        raise ValueError(
            f"Veredicto final no admitido: {veredicto!r}. "
            f"El PM sólo resuelve {' o '.join(VEREDICTOS)}.")

    import app.rfq.repository as repository
    estado = (repository.ESTADO_DECLINADO if veredicto == NO_FACTIBLE
              else repository.ESTADO_APROBADO)

    # Sin nota, la constancia dice al menos QUÉ se dictaminó: una línea
    # "[PM: fulano]" a secas no le cuenta nada a quien lea las notas después.
    texto = nota or ("APROBADO" if veredicto == FACTIBLE else "DECLINADO")
    registro = repository.guardar_veredicto_final(
        rfq_id, veredicto, version=version, nota=_nota_con_autor(texto, usuario),
        estado=estado, conexion=conexion)

    correo_enviado = False
    if veredicto == NO_FACTIBLE and enviar_correo:
        correo_enviado = notificar_declinacion(
            rfq_id, registro.get("datos") or {}, destinatario=destinatario)

    return {
        "id": registro["id"],
        "rfq_id": rfq_id,
        "version": registro["version"],
        "veredicto_final": veredicto,
        "estado": registro["estado"],
        "correo_enviado": correo_enviado,
    }


def notificar_declinacion(rfq_id, datos, destinatario=None) -> bool:
    """
    Construye (COT-59) y despacha (COT-57/58) el correo de declinación.

    Devuelve ``True`` si el correo salió; ``False`` si sólo se construyó
    (``ENVIO_AUTOMATICO`` apagado), si no había a quién escribirle o si falló
    el despacho. Ningún fallo aquí propaga: el dictamen del PM ya está
    registrado y lo que queda pendiente es sólo el aviso.
    """
    import app.email.outbound as outbound

    destino = destinatario or datos.get("remitente")
    if not destino:
        log.warning("RFQ=%s: no hay destinatario para la declinación "
                    "(datos_json sin remitente).", rfq_id)
        return False

    try:
        import app.email.templates as templates
        contenido = templates.construir_correo("declinar_rfq", {
            "destinatario": destino,
            "asunto_original": datos.get("asunto") or f"RFQ {rfq_id}",
            "nombre_comprador": outbound.nombre_comprador(
                {"remitente": destino}),
        })
    except Exception as error:
        log.error("RFQ=%s: no se pudo construir la declinación: %s", rfq_id, error)
        return False

    if not outbound.envio_habilitado():
        log.info("RFQ=%s: correo de declinación LISTO pero no enviado "
                 "(ENVIO_AUTOMATICO apagado). Para: %s", rfq_id, destino)
        return False

    try:
        enviado = outbound.enviar(contenido)
        log.info("RFQ=%s: declinación enviada a %s.", rfq_id, destino)
        return bool(enviado)
    except Exception as error:
        log.error("RFQ=%s: fallo al enviar la declinación: %s", rfq_id, error)
        return False


def _nota_con_autor(nota: Optional[str], usuario: Optional[str]) -> Optional[str]:
    """Deja constancia de quién dictaminó dentro del texto de la nota."""
    if not nota and not usuario:
        return None
    if not usuario:
        return nota
    return f"[PM: {usuario}] {nota}" if nota else f"[PM: {usuario}]"


def devolver(rfq_id, nota=None, usuario=None, conexion=None) -> dict:
    """El PM DEVUELVE el RFQ: no lo aprueba ni lo declina, pide que se corrija.

    Es la tercera salida de la ventana de revisión, y la única que no cierra
    nada: el RFQ sigue en ``RequiresReview`` con la nota del PM debajo, y se
    deja un aviso en el buzón para que quien cotiza vea qué hay que cambiar.

    No manda correo al comprador. Devolver es una conversación interna; lo que
    sale hacia fuera es aprobar (la oferta) o declinar (el correo de
    declinación), y ésos siguen siendo los dos únicos con consecuencias
    externas.
    """
    if not nota or not str(nota).strip():
        raise ValueError("Para devolver un RFQ hace falta decir qué hay que corregir.")

    import app.rfq.repository as repository
    texto = _nota_con_autor(f"DEVUELTO — {str(nota).strip()}", usuario)
    registro = repository.agregar_nota(
        rfq_id, texto, estado=repository.ESTADO_REVISION, conexion=conexion)

    try:
        import app.notifications.repository as notificaciones
        notificaciones.crear(
            tipo="dictamen_pm", rfq_id=rfq_id,
            titulo=f"{rfq_id}: devuelto por el PM",
            detalle=str(nota).strip(),
            datos={"usuario": usuario, "accion": "devolver"},
            nivel="warn")
    except Exception as error:   # el aviso no puede impedir la devolución
        log.warning("RFQ=%s: devuelto, pero sin aviso en el buzón: %s", rfq_id, error)

    log.info("RFQ %s devuelto por %s.", rfq_id, usuario or "-")
    return {"id": registro["id"], "rfq_id": rfq_id, "version": registro["version"],
            "veredicto_final": None, "estado": registro["estado"],
            "notas": registro["notas"], "correo_enviado": False}
