"""Canal de salida del correo, compartido por todo lo que le escribe al cliente.

Propósito
---------
Un solo lugar que decida **si** se manda un correo y **por dónde** sale. Lo
usan hoy dos flujos distintos:

* ``flujo_rfq`` — la petición de datos faltantes al comprador (COT-36/59).
* ``decision_pm`` — la declinación cuando el plant manager resuelve que el
  RFQ no es factible (COT-72).

Tener el interruptor duplicado sería peor que la duplicación normal: quien
apagara ``ENVIO_AUTOMATICO`` esperando silencio total podría seguir mandando
declinaciones a clientes reales por la otra rama.

Alcance
-------
* **Sí hace:** resolver el interruptor de envío y elegir el transporte
  (``smtp_sender`` en ``<Local>``, ``graph_sender`` en ``<Token>``).
* **NO hace:** redactar el correo (eso es ``email_templates``, COT-59) ni
  decidir a quién escribirle (eso es de cada flujo).

Funciones públicas
------------------
``envio_habilitado() -> bool``
``enviar(contenido) -> bool``
``nombre_comprador(datos) -> str``
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("cotizador.correo_saliente")

_MODOS_TOKEN = ("graph", "token", "prod")


def envio_habilitado() -> bool:
    """
    Interruptor del envío real de correo.

    Por defecto está **apagado**: el correo se construye y se registra en el
    log, pero no sale. Para habilitarlo, ``ENVIO_AUTOMATICO=true`` en el .env.
    Es un buzón de clientes reales; el envío automático se enciende a
    propósito, no por arrastre del cableado.

    ``config`` ya lo entrega convertido a bool (COT-56); el resto del cuerpo
    cubre que se inyecte a mano en pruebas o por variable de entorno.
    """
    import app.core.config as config
    valor = getattr(config, "ENVIO_AUTOMATICO", None)
    if isinstance(valor, bool):
        return valor
    if valor is None:
        valor = os.environ.get("ENVIO_AUTOMATICO", "false")
    return str(valor).strip().lower() in ("1", "true", "yes", "on")


def enviar(contenido) -> bool:
    """Envía el correo por el canal del modo activo: SMTP o Graph."""
    import app.core.config as config
    modo = str(getattr(config, "MAIL_MODE", "imap")).lower()
    if modo in _MODOS_TOKEN:
        import app.email.graph_sender as graph_sender
        return graph_sender.enviar_correo_graph(contenido)
    import app.email.smtp_sender as smtp_sender
    return smtp_sender.enviar_correo_smtp(contenido)


def nombre_comprador(datos) -> str:
    """Nombre de cortesía para el saludo, derivado del correo del remitente."""
    remitente = (datos or {}).get("remitente") or ""
    local = remitente.split("@")[0]
    nombre = local.replace(".", " ").replace("_", " ").strip()
    return nombre.title() or "Customer"
