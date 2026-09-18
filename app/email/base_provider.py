from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class EmailAttachment:
    """Estructura de datos para modelar archivos adjuntos en un correo electrónico."""
    filename: str
    content: bytes
    content_type: Optional[str] = None


@dataclass
class EmailMessage:
    """Estructura de datos estandarizada para representar un correo electrónico
    dentro del sistema, independientemente de la tecnología del proveedor (IMAP o API/REST).
    """
    id: str
    sender: str
    subject: str
    body: str
    date: str
    attachments: List[EmailAttachment] = field(default_factory=list)
    raw_headers: Dict[str, str] = field(default_factory=dict)

    # ``body`` viene en HTML, no en texto plano.
    #
    # Lo dice el proveedor, que es el único que lo sabe de verdad: Graph
    # devuelve el ``contentType`` del cuerpo, e IMAP sabe si tuvo que caer a la
    # parte ``text/html`` por no haber ``text/plain``. Adivinarlo después
    # buscando un "<" funciona casi siempre, y "casi" no es criterio para
    # decidir si un correo pasa por el limpiador.
    body_is_html: bool = False


class BaseEmailProvider(ABC):
    """Clase abstracta que define el contrato obligatorio para cualquier proveedor
    de servicios de correo electrónico (email provider) en el sistema.

    Permite el soporte híbrido de protocolos tradicionales como IMAP/SMTP o
    modernos basados en tokens OAuth2 (ej. Azure Graph API).
    """

    @abstractmethod
    def connect(self) -> bool:
        """Inicializa, autentica y valida la sesión con el servidor de correo.

        Debe realizar el handshake inicial y verificar que las credenciales
        (ya sean tradicionales o tokens de Azure) sean válidas.

        Returns:
            bool: True si la conexión y autenticación fueron exitosas.

        Raises:
            Exception: Si ocurre un error de conexión, autenticación o configuración.
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Cierra la sesión y desconecta del servidor de correo.
        """
        pass

    @abstractmethod
    def fetch_unread_messages(self) -> List[EmailMessage]:
        """Busca y recupera los correos electrónicos no leídos de la bandeja de entrada.

        Independientemente del protocolo subyacente (IMAP o API Graph REST),
        este método debe mapear la información cruda a una lista estructurada
        de objetos `EmailMessage`.

        Returns:
            List[EmailMessage]: Lista de correos no leídos listos para procesar.
        """
        pass

    @abstractmethod
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        attachments: Optional[List[EmailAttachment]] = None
    ) -> bool:
        """Despacha un correo electrónico saliente (notificaciones o solicitudes).

        Debe procesar el envío hacia el destinatario y soportar opcionalmente
        el envío de archivos adjuntos estructurados.

        Args:
            to (str): Dirección de correo del destinatario.
            subject (str): Asunto del mensaje.
            body (str): Contenido (cuerpo) del mensaje.
            attachments (Optional[List[EmailAttachment]]): Lista opcional de archivos
                adjuntos formateados como instancias de `EmailAttachment`.

        Returns:
            bool: True si el mensaje se envió correctamente.

        Raises:
            Exception: Si ocurre algún error durante la construcción o el envío del correo.
        """
        pass

    @abstractmethod
    def mark_as_read(self, message_id: str) -> bool:
        """Marca un correo electrónico como leído en el servidor.

        Args:
            message_id (str): Identificador único del correo (ID de IMAP o Graph).

        Returns:
            bool: True si la operación fue exitosa.
        """
        pass

