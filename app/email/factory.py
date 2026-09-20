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

    # Cómo se entra al buzón, por nombre. `local`/`token` son los nombres
    # viejos de `imap`/`graph`, que la configuración sigue aceptando.
    _MODOS = {
        "imap": "imap", "local": "imap",
        "graph": "graph", "token": "graph", "prod": "graph",
        "outlook": "outlook", "com": "outlook", "escritorio": "outlook",
    }

    @staticmethod
    def get_provider() -> BaseEmailProvider:
        """El proveedor de correo que toca, según ``MAIL_MODE``.

        Antes se elegía por ``APP_ENV``: dev → IMAP, prod → Graph. Eso ataba
        dos cosas que no tienen por qué ir juntas —dónde corre y por dónde lee
        el correo— y llevaba a la contradicción de tener ``AUTH_METHOD=local``
        configurado y estar usando Graph por haber puesto ``APP_ENV=prod``.
        Ahora manda ``MAIL_MODE`` (``AUTH_METHOD`` es su nombre viejo y la
        configuración los sincroniza), y ``APP_ENV`` sólo decide si no hay
        ninguno puesto.

        Tres puertas:

          imap     usuario y contraseña. En Microsoft 365 ya no vale: la
                   autenticación básica está retirada.
          graph    aplicación registrada en Entra ID (AZURE_* + GRAPH_USER).
          outlook  el Outlook de escritorio que ya tiene el buzón abierto.
                   Sin credenciales propias; es el de ``desktop_app/``.
        """
        modo = (getattr(settings, "MAIL_MODE", "") or "").strip().lower()
        origen = "MAIL_MODE"

        if modo not in EmailProviderFactory._MODOS:
            env = (settings.APP_ENV or "").lower()
            modo, origen = ("graph" if env == "prod" else "imap"), f"APP_ENV={env}"

        elegido = EmailProviderFactory._MODOS[modo]
        logger.info("Fábrica: modo de correo '%s' (por %s).", elegido, origen)

        if elegido == "imap":
            return ImapEmailProvider()
        if elegido == "graph":
            return GraphEmailProvider()
        if elegido == "outlook":
            from app.email.outlook_provider import OutlookEmailProvider
            return OutlookEmailProvider()

        error_message = (
            f"Modo de correo '{modo}' no soportado. Usa imap, graph u outlook.")
        logger.critical(error_message)
        raise FactoryConfigurationError(error_message)
