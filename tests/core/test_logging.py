
import imaplib
import smtplib
import socket
import unittest

from app.core.exceptions import EmailAuthError, EmailNetworkError, EmailProviderError
from app.core.logging import track_email_errors


class DummyService:
    """Clase dummy para simular métodos de proveedores de correo y verificar el decorador."""

    @track_email_errors()
    def fail_with_socket(self):
        raise socket.timeout("Connection timed out")

    @track_email_errors()
    def fail_with_imap(self):
        raise imaplib.IMAP4.error("Invalid credentials")

    @track_email_errors()
    def fail_with_smtp(self):
        raise smtplib.SMTPException("SMTP Server down")

    @track_email_errors()
    def fail_with_generic(self):
        raise ValueError("Some random error")

    @track_email_errors(default_fallback=False)
    def fail_with_fallback_bool(self):
        raise ConnectionError("No internet connection")

    @track_email_errors(default_fallback=[])
    def fail_with_fallback_list(self):
        raise imaplib.IMAP4.error("Login failed")

    @track_email_errors()
    def success_method(self):
        return "SUCCESS"


class TestLoggerControl(unittest.TestCase):

    def setUp(self):
        self.service = DummyService()

    def test_success_flow(self):
        """Verifica que el decorador no altere el valor de retorno en ejecuciones exitosas."""
        self.assertEqual(self.service.success_method(), "SUCCESS")

    def test_socket_error_mapping(self):
        """Verifica que los fallos de red se mapeen a EmailNetworkError."""
        with self.assertRaises(EmailNetworkError) as ctx:
            self.service.fail_with_socket()
        self.assertIn("Fallo de conexión o timeout de red detectado", str(ctx.exception))

    def test_auth_error_mapping(self):
        """Verifica que los fallos de credenciales IMAP se mapeen a EmailAuthError."""
        with self.assertRaises(EmailAuthError) as ctx:
            self.service.fail_with_imap()
        self.assertIn("Error crítico de credenciales o autenticación", str(ctx.exception))

    def test_smtp_error_mapping(self):
        """Verifica que los errores de SMTP se mapeen a la excepción base del negocio."""
        with self.assertRaises(EmailProviderError) as ctx:
            self.service.fail_with_smtp()
        self.assertIn("Fallo en el protocolo SMTP", str(ctx.exception))

    def test_generic_error_mapping(self):
        """Verifica que excepciones genéricas no esperadas se envuelvan en EmailProviderError."""
        with self.assertRaises(EmailProviderError) as ctx:
            self.service.fail_with_generic()
        self.assertIn("Error inesperado no controlado", str(ctx.exception))

    def test_fallback_bool_handling(self):
        ("""Verifica que si se define un default_fallback de booleano, se """
         """devuelva en lugar de lanzar la excepción.""")
        result = self.service.fail_with_fallback_bool()
        self.assertFalse(result)

    def test_fallback_list_handling(self):
        ("""Verifica que si se define un default_fallback de lista, se """
         """devuelva en lugar de lanzar la excepción.""")
        result = self.service.fail_with_fallback_list()
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
