import functools
import imaplib
import logging
import re
import smtplib
import socket
from logging.handlers import RotatingFileHandler
from typing import Any, Callable, TypeVar, cast

from app.core.exceptions import EmailAuthError, EmailNetworkError, EmailProviderError

# --- Configuración del Logging ---

def configure_logging(log_file_name: str = "app.log", app_env: str | None = None) -> None:
    """Configura el sistema de logs con salida a consola y archivo rotativo.

    Idempotente: se puede llamar varias veces (limpia los handlers previos).
    Debe llamarla el punto de entrada, no un import.
    """
    if app_env is None:
        try:
            from app.core.config import settings
            app_env = settings.APP_ENV
        except Exception:
            app_env = "dev"

    # Los correos de clientes no se quedan en el registro (ver tachar_correos).
    _instalar_tachado()

    # Crear formateador de logs
    log_format = "%(asctime)s [%(levelname)s] [%(name)s] [%(filename)s:%(lineno)d]: %(message)s"
    formatter = logging.Formatter(log_format)

    # Logger raíz
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Limpiar manejadores previos si existen
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Handler 1: Consola (Siempre activo, ideal para desarrollo y contenedores)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)

    # Handler 2: Archivo Rotativo (Ideal para persistencia y auditoría en producción)
    try:
        # 5 MB por archivo, máximo 5 archivos de respaldo
        file_handler = RotatingFileHandler(
            log_file_name,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)
        root_logger.addHandler(file_handler)
        logging.getLogger("LoggerControl").info(
            f"Manejador de archivos rotativos inicializado: '{log_file_name}'"
        )
    except Exception as e:
        logging.getLogger("LoggerControl").error(
            f"No se pudo crear el archivo de logs '{log_file_name}': {e}"
        )


# --- Correos tachados en el registro ---
#
# El registro (app.log en cada computadora, la consola de Render, el Monitor)
# se guarda en texto plano y no se borra con el RFQ. Hasta 2026-10 llevaba la
# dirección completa de cada comprador. Los datos del cliente viven en Neon;
# en el registro basta con saber de qué dominio era: «r***@neogen.com».
#
# Se hace al CREAR cada línea (setLogRecordFactory) y no con un filtro, porque
# un filtro de logger no se aplica a lo que llega propagado de los demás y
# cada punto de entrada añade sus propios manejadores.

_CORREO = re.compile(r"(?<![\w.%+-])([A-Za-z0-9])[A-Za-z0-9._%+-]*@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")


def tachar_correos(texto: str) -> str:
    """``roberto.perez@neogen.com`` -> ``r***@neogen.com``."""
    return _CORREO.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", texto)


def _instalar_tachado() -> None:
    fabrica = logging.getLogRecordFactory()
    if getattr(fabrica, "_tacha_correos", False):
        return

    def _fabrica(*args, **kwargs):
        registro = fabrica(*args, **kwargs)
        try:
            mensaje = registro.getMessage()
        except Exception:
            return registro          # un mensaje mal formado lo cuenta logging
        limpio = tachar_correos(mensaje)
        if limpio != mensaje:
            registro.msg = limpio
            registro.args = ()
        return registro

    _fabrica._tacha_correos = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(_fabrica)


# NOTA: este módulo ya NO configura el logging al importarse.
#
# Antes lo hacía, y como `configure_logging()` limpia los handlers del logger
# raíz, el simple hecho de importar cualquier módulo que dependiera de este
# (por ejemplo app.email.imap_provider) reconfiguraba los logs de todo el
# proceso, pisando lo que hubiera montado el punto de entrada. Además convivía
# con dos `logging.basicConfig()` en app/main.py y app/core/config.py, así que
# el formato final dependía del orden de los imports.
#
# Ahora la configuración la aplica explícitamente cada punto de entrada:
#   * app/main.py         (worker de consola)
#   * api/server.py       (servidor web)
#   * desktop_app/main.py (aplicación de escritorio)
#   * scripts/*.py        (utilidades de consola)

# Logger específico de este módulo
logger = logging.getLogger("EmailExceptionTracker")


# --- Decorador de Control de Errores ---

F = TypeVar('F', bound=Callable[..., Any])

def track_email_errors(default_fallback: Any = None) -> Callable[[F], F]:
    """Decorador parametrizado para interceptar, registrar y normalizar excepciones
    lanzadas en los métodos de los proveedores de correo electrónico.

    Args:
        default_fallback (Any): Valor que se retornará si ocurre una excepción
            y se prefiere evitar la propagación (evitando romper el loop principal).
            Si es None (y no se indica un fallback explícito), se propagará una
            excepción limpia del negocio (`EmailProviderError` o derivadas).
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            method_name = f"{args[0].__class__.__name__}.{func.__name__}" if args else func.__name__

            try:
                logger.debug(f"Ejecutando método controlado: {method_name}")
                return func(*args, **kwargs)

            # 1. Errores de Autenticación IMAP/SMTP específicos
            except (imaplib.IMAP4.error, smtplib.SMTPAuthenticationError) as auth_err:
                error_msg = (
                    "Error crítico de credenciales o autenticación en "
                    f"'{method_name}': {auth_err}"
                )
                logger.exception(error_msg)

                if default_fallback is not None:
                    logger.warning(
                        f"Retornando fallback controlado '{default_fallback}' "
                        "debido a fallo de autenticación."
                    )
                    return default_fallback
                raise EmailAuthError(error_msg) from auth_err

            # 2. Otros Errores SMTP o de Protocolo (subclase de OSError en algunas versiones)
            except smtplib.SMTPException as smtp_err:
                error_msg = (
                    "Fallo en el protocolo SMTP durante la ejecución de "
                    f"'{method_name}': {smtp_err}"
                )
                logger.exception(error_msg)

                if default_fallback is not None:
                    logger.warning(
                        f"Retornando fallback controlado '{default_fallback}' "
                        "debido al error SMTP."
                    )
                    return default_fallback
                raise EmailProviderError(error_msg) from smtp_err

            # 3. Errores de Red y Timeouts (incluye socket.error/OSError)
            except (socket.error, TimeoutError, ConnectionError) as net_err:
                error_msg = (
                    "Fallo de conexión o timeout de red detectado en "
                    f"'{method_name}': {net_err}"
                )
                logger.exception(error_msg)

                if default_fallback is not None:
                    logger.warning(
                        f"Retornando fallback controlado '{default_fallback}' "
                        "debido al error de red."
                    )
                    return default_fallback
                raise EmailNetworkError(error_msg) from net_err

            # 4. Cualquier otra excepción no controlada
            except Exception as raw_err:
                # Evitar envolver dos veces si ya es una excepción del negocio
                if isinstance(raw_err, EmailProviderError):
                    raise raw_err

                error_msg = (
                    "Error inesperado no controlado durante la ejecución de "
                    f"'{method_name}': {raw_err}"
                )
                logger.exception(error_msg)

                if default_fallback is not None:
                    logger.warning(
                        f"Retornando fallback controlado '{default_fallback}' "
                        "debido a error no controlado."
                    )
                    return default_fallback
                raise EmailProviderError(error_msg) from raw_err

        return cast(F, wrapper)
    return decorator
