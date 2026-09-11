
import email as email_parser
import imaplib
import unittest
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.email.base_provider import EmailAttachment
from app.email.imap_provider import ImapEmailProvider


class TestDevEmailProvider(unittest.TestCase):

    def setUp(self):
        # Asegurarse de que settings tenga configuraciones para el test
        settings.APP_ENV = "dev"
        settings.AUTH_METHOD = "local"
        settings.IMAP_SERVER = "imap.test.com"
        settings.IMAP_PORT = 993
        settings.IMAP_USER = "test@test.com"
        settings.IMAP_PASSWORD = "test-password"
        settings.SMTP_SERVER = "smtp.test.com"
        settings.SMTP_PORT = 587
        settings.SMTP_USE_TLS = True

    @patch("imaplib.IMAP4_SSL")
    def test_connect_success(self, mock_imap_ssl):
        """Verifica que connect() cree la sesión e inicie sesión con éxito."""
        mock_instance = MagicMock()
        mock_imap_ssl.return_value = mock_instance

        provider = ImapEmailProvider()
        result = provider.connect()

        self.assertTrue(result)
        mock_imap_ssl.assert_called_once_with("imap.test.com", 993)
        mock_instance.login.assert_called_once_with("test@test.com", "test-password")

    @patch("imaplib.IMAP4_SSL")
    def test_connect_failure(self, mock_imap_ssl):
        """Verifica que si falla el login, connect() retorne False de forma segura."""
        mock_instance = MagicMock()
        mock_instance.login.side_effect = imaplib.IMAP4.error("Login failed")
        mock_imap_ssl.return_value = mock_instance

        provider = ImapEmailProvider()
        result = provider.connect()

        self.assertFalse(result)
        self.assertIsNone(provider.imap_client)

    @patch("imaplib.IMAP4_SSL")
    def test_fetch_unread_messages_no_mails(self, mock_imap_ssl):
        """Prueba fetch_unread_messages cuando no hay correos no leídos."""
        mock_instance = MagicMock()
        mock_instance.select.return_value = ("OK", [b"123"])
        # Retornar una lista vacía de IDs de búsqueda
        mock_instance.search.return_value = ("OK", [b""])
        mock_imap_ssl.return_value = mock_instance

        provider = ImapEmailProvider()
        provider.connect()

        emails = provider.fetch_unread_messages()
        self.assertEqual(len(emails), 0)
        mock_instance.select.assert_called_with("INBOX")
        mock_instance.search.assert_called_with(None, "UNSEEN")

    @patch("imaplib.IMAP4_SSL")
    def test_fetch_unread_messages_with_data(self, mock_imap_ssl):
        """Prueba el parseo completo de un correo descargado por IMAP."""
        mock_instance = MagicMock()
        mock_instance.select.return_value = ("OK", [b"123"])
        mock_instance.search.return_value = ("OK", [b"1 2"])

        # Simular los bytes RFC822 de un correo simple
        raw_email_bytes = (
            b"From: sender@domain.com\r\n"
            b"To: test@test.com\r\n"
            b"Subject: Request spring quota\r\n"
            b"Date: Mon, 8 Jun 2026 12:00:00 -0600\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"Hello, this is the body of the spring request."
        )

        # fetch(mail_id, "(BODY.PEEK[])") retorna
        # [ ( b"1 (BODY.PEEK[] {120}", raw_email_bytes ), b")" ]
        mock_instance.fetch.return_value = (
            "OK",
            [(b"1 (BODY.PEEK[] {120}", raw_email_bytes), b")"]
        )
        mock_imap_ssl.return_value = mock_instance

        provider = ImapEmailProvider()
        provider.connect()

        emails = provider.fetch_unread_messages()

        # Deben haberse procesado los dos IDs mapeados con los mismos bytes
        self.assertEqual(len(emails), 2)
        self.assertEqual(emails[0].id, "1")
        self.assertEqual(emails[0].sender, "sender@domain.com")
        self.assertEqual(emails[0].subject, "Request spring quota")
        self.assertEqual(emails[0].body, "Hello, this is the body of the spring request.")
        self.assertEqual(emails[0].date, "Mon, 8 Jun 2026 12:00:00 -0600")

    @patch("smtplib.SMTP")
    def test_send_email_no_attachments(self, mock_smtp_class):
        """Verifica el flujo correcto de envío SMTP de correos sin adjuntos."""
        mock_smtp_inst = MagicMock()
        mock_smtp_class.return_value = mock_smtp_inst

        provider = ImapEmailProvider()
        result = provider.send_email(
            to="recipient@example.com",
            subject="Test Subject",
            body="Test body context"
        )

        self.assertTrue(result)
        mock_smtp_class.assert_called_once_with("smtp.test.com", 587, timeout=15)
        mock_smtp_inst.starttls.assert_called_once()
        mock_smtp_inst.login.assert_called_once_with("test@test.com", "test-password")

        # Verificar que se mandó llamar sendmail con el cuerpo correcto
        args, kwargs = mock_smtp_inst.sendmail.call_args
        self.assertEqual(args[0], "test@test.com")
        self.assertEqual(args[1], ["recipient@example.com"])

        # Parsear el correo enviado para validar cabeceras y payload
        sent_msg = email_parser.message_from_string(args[2])
        self.assertEqual(sent_msg["Subject"], "Test Subject")
        self.assertEqual(sent_msg["From"], "test@test.com")
        self.assertEqual(sent_msg["To"], "recipient@example.com")
        self.assertEqual(sent_msg.get_payload(decode=True).decode("utf-8"), "Test body context")

    @patch("smtplib.SMTP")
    def test_send_email_with_attachments(self, mock_smtp_class):
        """Verifica que los archivos adjuntos se empaqueten adecuadamente en el MIME del correo."""
        mock_smtp_inst = MagicMock()
        mock_smtp_class.return_value = mock_smtp_inst

        attachment = EmailAttachment(
            filename="resorte.pdf",
            content=b"%PDF-1.4 mock data",
            content_type="application/pdf"
        )

        provider = ImapEmailProvider()
        result = provider.send_email(
            to="recipient@example.com",
            subject="Drawing Attached",
            body="Please see the attachment.",
            attachments=[attachment]
        )

        self.assertTrue(result)
        mock_smtp_inst.sendmail.assert_called_once()
        args, kwargs = mock_smtp_inst.sendmail.call_args

        # El cuerpo MIME multipart debe contener codificación base64 y el adjunto
        raw_msg_str = args[2]
        self.assertIn("Content-Type: multipart/mixed;", raw_msg_str)
        self.assertIn("filename=resorte.pdf", raw_msg_str)

    @patch("imaplib.IMAP4_SSL")
    def test_mark_as_read_success(self, mock_imap_ssl):
        """Verifica que mark_as_read marque el correo como leido en IMAP."""
        mock_instance = MagicMock()
        mock_instance.store.return_value = ("OK", [b"\\Seen"])
        mock_imap_ssl.return_value = mock_instance

        provider = ImapEmailProvider()
        provider.connect()

        result = provider.mark_as_read("123")
        self.assertTrue(result)
        mock_instance.store.assert_called_once_with(b"123", "+FLAGS", "\\Seen")


if __name__ == "__main__":
    unittest.main()
