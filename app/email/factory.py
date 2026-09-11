import logging

from app.core.config import settings
from app.core.exceptions import FactoryConfigurationError
from app.email.base_provider import BaseEmailProvider
from app.email.graph_provider import GraphEmailProvider
from app.email.imap_provider import ImapEmailProvider

logger = logging.getLogger("EmailProviderFactory")

class EmailProviderFactory:
    """Clase fábrica encargada de orquestar la arquitectura dual de correo en la aplicación.

    Inicializa y retorna la instancia del proveedor de correo concreto adecuado
    según el entorno de ejecución configurado centralizadamente.
    """

    @staticmethod
    def get_provider() -> BaseEmailProvider:
        """Determina, inicializa y retorna el proveedor de correo correspondiente
        según el valor de settings.APP_ENV.

        Returns:
            BaseEmailProvider: Instancia del proveedor concreta que implementa la interfaz base.

        Raises:
            FactoryConfigurationError: Si el valor del entorno no está soportado.
        """
        env = settings.APP_ENV.lower() if settings.APP_ENV else ""

        logger.info(f"Fábrica evaluando el entorno del sistema (APP_ENV: '{env}')...")

        if env == "dev":
            logger.info("Resolución de fábrica: Entorno de desarrollo local detectado (@Local@).")
            provider = ImapEmailProvider()
            logger.info("Instancia de ImapEmailProvider creada y lista.")
            return provider

        elif env == "prod":
            logger.info("Resolución de fábrica: Entorno de producción seguro detectado (@Token@).")
            provider = GraphEmailProvider()
            logger.info("Instancia de GraphEmailProvider creada y lista.")
            return provider

        else:
            error_message = (
                f"El entorno configurado '{settings.APP_ENV}' no es válido para la fábrica. "
                "Debe ser 'dev' (desarrollo) o 'prod' (producción)."
            )
            logger.critical(error_message)
            raise FactoryConfigurationError(error_message)
