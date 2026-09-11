"""Excepciones centralizadas del dominio."""

class ConfigurationError(ValueError):
    """Excepción lanzada cuando ocurre un error al validar la configuración."""
    pass

class FactoryConfigurationError(ValueError):
    """Excepción lanzada cuando la fábrica no puede resolver un proveedor debido
    a una configuración de entorno no válida o desconocida.
    """
    pass

class EmailProviderError(Exception):
    """Excepción base para errores de los proveedores de correo electrónico."""
    pass

class EmailNetworkError(EmailProviderError):
    """Excepción lanzada cuando ocurre un error de red o timeout."""
    pass

class EmailAuthError(EmailProviderError):
    """Excepción lanzada cuando fallan las credenciales o la autenticación."""
    pass
