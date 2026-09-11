import os
import tempfile
import unittest

# config valida credenciales al importarse; fijamos valores dummy ANTES de
# importar smtp_sender (que hace `import config`).
os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

from app.email.smtp_sender import (
    SmtpSenderError,
    construir_mensaje,
    enviar_correo_smtp,
)


class FakeSMTP:
    """Cliente SMTP falso que captura la llamada a sendmail."""

    def __init__(self):
        self.enviado = None

    def sendmail(self, remitente, destinatarios, mensaje):
        self.enviado = {
            "remitente": remitente,
            "destinatarios": destinatarios,
            "mensaje": mensaje,
        }


def _correo_base(adjuntos=None):
    return {
        "destinatario": "cliente@empresa.com",
        "asunto": "RE: Solicitud de cotización",
        "cuerpo_html": "<html><body><p>Hola equipo</p></body></html>",
        "cuerpo_texto": "Hola equipo",
        "adjuntos": adjuntos or [],
    }


class TestConstruirMensaje(unittest.TestCase):

    def test_multipart_alternative_sin_adjuntos(self):
        """Sin adjuntos: multipart/alternative con parte texto y parte HTML."""
        mensaje = construir_mensaje(_correo_base(), "remitente@cgr.com")
        self.assertEqual(mensaje.get_content_type(), "multipart/alternative")
        subtipos = [p.get_content_type() for p in mensaje.get_payload()]
        self.assertIn("text/plain", subtipos)
        self.assertIn("text/html", subtipos)

    def test_cabeceras_correctas(self):
        """From, To y Subject se colocan en el mensaje."""
        mensaje = construir_mensaje(_correo_base(), "remitente@cgr.com")
        self.assertEqual(mensaje["To"], "cliente@empresa.com")
        self.assertEqual(mensaje["From"], "remitente@cgr.com")
        self.assertEqual(mensaje["Subject"], "RE: Solicitud de cotización")

    def test_con_adjunto_desde_disco(self):
        """Con adjuntos: multipart/mixed que incluye el archivo del disco."""
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False, mode="wb"
        ) as fh:
            fh.write(b"%PDF-1.7 contenido de prueba")
            ruta = fh.name
        try:
            mensaje = construir_mensaje(
                _correo_base(adjuntos=[ruta]), "remitente@cgr.com"
            )
            self.assertEqual(mensaje.get_content_type(), "multipart/mixed")
            # Debe haber una parte con Content-Disposition attachment
            nombres = [
                p.get_filename()
                for p in mensaje.walk()
                if p.get_content_disposition() == "attachment"
            ]
            self.assertIn(os.path.basename(ruta), nombres)
        finally:
            os.remove(ruta)

    def test_adjunto_inexistente_lanza_error(self):
        """Una ruta de adjunto que no existe aborta el envío."""
        with self.assertRaises(SmtpSenderError):
            construir_mensaje(
                _correo_base(adjuntos=["C:/no/existe/plano.pdf"]),
                "remitente@cgr.com",
            )


class TestEnviarCorreoSmtp(unittest.TestCase):

    def test_envio_con_cliente_inyectado(self):
        """Con cliente inyectado despacha por sendmail y devuelve True."""
        fake = FakeSMTP()
        ok = enviar_correo_smtp(
            _correo_base(),
            remitente="remitente@cgr.com",
            cliente_smtp=fake,
        )
        self.assertTrue(ok)
        self.assertIsNotNone(fake.enviado)
        self.assertEqual(fake.enviado["remitente"], "remitente@cgr.com")
        self.assertEqual(fake.enviado["destinatarios"], ["cliente@empresa.com"])
        # El asunto con acentos viaja codificado en RFC 2047; verificamos el
        # destinatario (ASCII) y que haya cabecera de asunto en el mensaje.
        self.assertIn("To: cliente@empresa.com", fake.enviado["mensaje"])
        self.assertIn("Subject:", fake.enviado["mensaje"])

    def test_sin_destinatario_lanza_error(self):
        """Un correo sin destinatario no se envía."""
        correo = _correo_base()
        correo["destinatario"] = ""
        with self.assertRaises(SmtpSenderError):
            enviar_correo_smtp(
                correo, remitente="remitente@cgr.com", cliente_smtp=FakeSMTP()
            )

    def test_sin_cuerpo_lanza_error(self):
        """Un correo sin texto ni HTML no se envía."""
        correo = _correo_base()
        correo["cuerpo_texto"] = ""
        correo["cuerpo_html"] = ""
        with self.assertRaises(SmtpSenderError):
            enviar_correo_smtp(
                correo, remitente="remitente@cgr.com", cliente_smtp=FakeSMTP()
            )


if __name__ == "__main__":
    unittest.main()
