"""El recordatorio por correo de lo que lleva demasiado tiempo esperando.

Cómo se entera quien revisa
---------------------------
Primero, por donde debe: la campana de Pohua y el aviso en el teléfono, en
cuanto el caso entra. Eso no cambia.

Esto es el respaldo. Si un RFQ se queda esperando dictamen más de
``RECORDATORIO_HORAS`` y nadie lo ha tocado, sale UN correo a quien puede
dictaminar —los usuarios registrados de Pohua con permiso ``rfq:dictaminar``—
con el texto del machote y el enlace al caso. Uno, no uno por ciclo: la tabla
``recordatorios_revision`` (migración 020) guarda que ya se mandó.

Qué cuenta como "esperando":

  RequiresReview  la factibilidad necesita dictamen  → NOT FEASIBLE REVIEW
  New             está listo y espera aprobación     → VALIDATION EMAIL

Cuándo corre: al final de cada ciclo de detección (``app/main.py``), que sólo
corre en horario de atención (``app/rfq/horario.py``). Así el recordatorio de
un caso que entró el viernes por la tarde sale el lunes por la mañana, y no a
las tres de la madrugada.

Apagarlo: ``RECORDATORIO_HORAS=0``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("cotizador.recordatorios")

# Qué texto le toca a cada estado que espera a una persona.
_CORREO_DE_ESTADO = {
    "RequiresReview": "revision_factibilidad",
    "New": "validacion_pm",
}


def _config():
    import app.core.config as config
    return config.settings


def horas() -> int:
    """Cuántas horas se deja esperar antes de escribir. 0 = no se escribe."""
    try:
        return max(0, int(getattr(_config(), "RECORDATORIO_HORAS", 0) or 0))
    except (TypeError, ValueError):
        return 0


def _base_url() -> str:
    """Dónde vive Pohua, para el enlace del correo.

    ``APP_URL`` primero —es la que se pone en Render— y si no está, la del
    servidor web. Sin ninguna de las dos el enlace sería a localhost, que en
    un correo no sirve para nada: entonces no se manda y se dice por qué.
    """
    c = _config()
    for nombre in ("APP_URL", "WEB_SERVER_URL"):
        valor = (getattr(c, nombre, "") or "").strip().rstrip("/")
        if valor and "localhost" not in valor and "127.0.0.1" not in valor:
            return valor
    return ""


def enlace_de(rfq_id: str) -> str:
    """La dirección de la ventana de revisión de ese RFQ."""
    base = _base_url()
    return f"{base}/#/rfq/{rfq_id}" if base else ""


# --------------------------------------------------------------------------- #
# La base
# --------------------------------------------------------------------------- #

def _conexion(conexion=None):
    import app.persistence.duplicates as duplicates
    return duplicates.conexion_bd() if conexion is None else _Prestada(conexion)


class _Prestada:
    """Envuelve una conexión ajena para poder usar `with` sin cerrarla."""

    def __init__(self, conexion):
        self._conexion = conexion

    def __enter__(self):
        return self._conexion

    def __exit__(self, *_):
        return False


_SQL_PENDIENTES = """
    SELECT rfq_id, estado, cliente_id, nombre_proyecto, fecha_registro
      FROM (
           SELECT DISTINCT ON (r.rfq_id)
                  r.rfq_id, r.estado, r.cliente_id, r.nombre_proyecto,
                  r.fecha_registro
             FROM rfqs r
            ORDER BY r.rfq_id, r.version DESC
           ) ultima
     WHERE ultima.estado = ANY(%s)
       AND ultima.fecha_registro <= NOW() - (%s || ' hours')::interval
       AND NOT EXISTS (SELECT 1 FROM recordatorios_revision x
                        WHERE x.rfq_id = ultima.rfq_id)
     ORDER BY fecha_registro
     LIMIT 20;
"""


def pendientes(conexion=None) -> List[Dict[str, Any]]:
    """Los casos que llevan demasiado esperando y aún no se han recordado.

    Se mira la ÚLTIMA versión de cada RFQ: una versión vieja en
    ``RequiresReview`` no significa nada si la de ahora ya está aprobada.
    """
    espera = horas()
    if not espera:
        return []
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(_SQL_PENDIENTES, (list(_CORREO_DE_ESTADO), str(espera)))
            columnas = [c[0] for c in cur.description]
            return [dict(zip(columnas, fila)) for fila in cur.fetchall()]


def marcar(rfq_id: str, estado: str, destinatarios: str, conexion=None) -> None:
    """Deja constancia de que ya se escribió por este caso."""
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO recordatorios_revision (rfq_id, estado, destinatarios)
                        VALUES (%s, %s, %s)
                   ON CONFLICT (rfq_id) DO NOTHING;""",
                (rfq_id, estado, destinatarios))


# --------------------------------------------------------------------------- #
# El recordatorio
# --------------------------------------------------------------------------- #

def _quien_dictamina() -> List[Dict[str, Any]]:
    """Los usuarios registrados que pueden dictaminar, con su correo."""
    try:
        import app.auth.repository as auth
        return auth.usuarios_con_permiso("rfq:dictaminar")
    except Exception as error:
        log.warning("No se pudo leer a quién avisar: %s", error)
        return []


def _cliente_de(caso: Dict[str, Any]) -> str:
    return (caso.get("cliente_id") or caso.get("nombre_proyecto")
            or caso.get("rfq_id") or "—")


def revisar(conexion=None) -> Dict[str, Any]:
    """Escribe a quien dictamina por los casos que llevan demasiado esperando.

    Devuelve el recuento para el registro del ciclo. Nada de lo que pase aquí
    puede tumbar el ciclo: un correo que no sale se apunta y se sigue.
    """
    resultado = {"pendientes": 0, "avisados": 0, "correos": 0, "motivo": ""}

    if not horas():
        resultado["motivo"] = "recordatorios apagados (RECORDATORIO_HORAS=0)"
        return resultado

    try:
        casos = pendientes(conexion)
    except Exception as error:
        log.warning("No se pudieron buscar los casos pendientes: %s", error)
        resultado["motivo"] = f"no se pudo consultar: {error}"
        return resultado

    resultado["pendientes"] = len(casos)
    if not casos:
        return resultado

    if not _base_url():
        # Sin dirección pública, el correo llevaría un enlace a localhost.
        # Mejor no mandarlo y decirlo: el aviso de la campana sigue estando.
        log.warning("%d caso(s) llevan más de %d h esperando dictamen, pero no "
                    "hay APP_URL configurada: no se manda el recordatorio.",
                    len(casos), horas())
        resultado["motivo"] = "falta APP_URL"
        return resultado

    personas = _quien_dictamina()
    if not personas:
        log.warning("%d caso(s) esperando dictamen y nadie con permiso "
                    "'rfq:dictaminar' y correo al que escribir.", len(casos))
        resultado["motivo"] = "nadie a quien escribir"
        return resultado

    import app.email.outbound as outbound
    import app.email.templates as templates

    # El mismo interruptor que para todo lo que sale solo. El recordatorio va a
    # los de casa y no al cliente, pero sigue siendo correo que manda la
    # máquina sin que nadie lo pulse: durante una prueba controlada, con
    # ENVIO_AUTOMATICO apagado, no tiene por qué salir. No se apunta como
    # mandado, así que el día que se encienda el envío saldrá igual.
    if not outbound.envio_habilitado():
        log.info("%d caso(s) llevan más de %d h esperando dictamen. El "
                 "recordatorio queda preparado pero NO sale: ENVIO_AUTOMATICO "
                 "está apagado.", len(casos), horas())
        resultado["motivo"] = "envío automático apagado"
        return resultado

    for caso in casos:
        rfq_id = caso["rfq_id"]
        tipo = _CORREO_DE_ESTADO.get(caso.get("estado") or "")
        if not tipo:
            continue
        cliente = _cliente_de(caso)
        enviados = []
        for persona in personas:
            correo = (persona.get("correo") or "").strip()
            if not correo:
                continue
            try:
                contenido = templates.construir_correo(tipo, {
                    "destinatario": correo,
                    "nombre_pm": (persona.get("nombre") or correo.split("@")[0]),
                    "cliente": cliente,
                    "enlace": enlace_de(rfq_id),
                })
                outbound.enviar(contenido)
                enviados.append(correo)
            except Exception as error:
                log.warning("RFQ=%s: no se pudo mandar el recordatorio a %s: %s",
                            rfq_id, correo, error)

        if not enviados:
            continue
        try:
            marcar(rfq_id, caso.get("estado") or "", ", ".join(enviados), conexion)
        except Exception as error:
            # Si no se puede apuntar, se apaga para este caso: repetir el
            # correo cada ciclo sería peor que no mandarlo.
            log.error("RFQ=%s: recordatorio enviado pero NO apuntado (%s). "
                      "Se podría repetir en el siguiente ciclo.", rfq_id, error)
        resultado["avisados"] += 1
        resultado["correos"] += len(enviados)
        log.info("RFQ=%s: recordatorio de %s enviado a %s (llevaba más de %d h).",
                 rfq_id, tipo, ", ".join(enviados), horas())

    return resultado
