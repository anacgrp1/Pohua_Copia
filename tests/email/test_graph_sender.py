import base64
import os
import tempfile
import unittest

# config valida credenciales al importarse; valores dummy ANTES del import.
os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")
# Credenciales Azure dummy para la ruta de obtención de token (modo <Token>).
os.environ.setdefault("AZURE_TENANT_ID", "tenant-falso")
os.environ.setdefault("AZURE_CLIENT_ID", "client-falso")
os.environ.setdefault("AZURE_CLIENT_SECRET", "secret-falso")

import requests

import app.core.config as config

# Fijar los atributos directamente en config: es robusto ante el orden de
# importación (config "fotografía" el entorno una sola vez al importarse, y
# otro test puede haberlo importado antes que este módulo).
config.AZURE_TENANT_ID = config.AZURE_TENANT_ID or "tenant-falso"
config.AZURE_CLIENT_ID = config.AZURE_CLIENT_ID or "client-falso"
config.AZURE_CLIENT_SECRET = config.AZURE_CLIENT_SECRET or "secret-falso"

from app.email.graph_sender import (  # noqa: E402
    GraphSenderError,
    construir_payload,
    enviar_correo_graph,
)


class FakeResponse:
    def __init__(self, payload=None, status_ok=True):
        self._payload = payload or {}
        self._ok = status_ok

    def raise_for_status(self):
        if not self._ok:
            raise requests.HTTPError("500 Server Error")

    def json(self):
        return self._payload


class FakeHTTP:
    """Cliente HTTP falso: distingue la petición de token de la de sendMail."""

    def __init__(self, token_ok=True, sendmail_ok=True):
        self.token_ok = token_ok
        self.sendmail_ok = sendmail_ok
        self.llamadas = []

    def post(self, url, **kwargs):
        self.llamadas.append({"url": url, **kwargs})
        if "oauth2" in url or "token" in url:
            return FakeResponse({"access_token": "TOKEN-FALSO"}, self.token_ok)
        return FakeResponse({}, self.sendmail_ok)


def _correo_base(adjuntos=None):
    return {
        "destinatario": "cliente@empresa.com",
        "asunto": "RE: Solicitud de cotización",
        "cuerpo_html": "<html><body><p>Hola equipo</p></body></html>",
        "cuerpo_texto": "Hola equipo",
        "adjuntos": adjuntos or [],
    }


class TestConstruirPayload(unittest.TestCase):

    def test_payload_html_y_destinatario(self):
        payload = construir_payload(_correo_base())
        msg = payload["message"]
        self.assertEqual(msg["body"]["contentType"], "HTML")
        self.assertIn("Hola equipo", msg["body"]["content"])
        self.assertEqual(
            msg["toRecipients"][0]["emailAddress"]["address"],
            "cliente@empresa.com",
        )
        self.assertEqual(msg["attachments"], [])

    def test_payload_usa_texto_si_no_hay_html(self):
        correo = _correo_base()
        correo["cuerpo_html"] = ""
        payload = construir_payload(correo)
        self.assertEqual(payload["message"]["body"]["contentType"], "Text")
        self.assertEqual(payload["message"]["body"]["content"], "Hola equipo")

    def test_payload_con_adjunto_desde_disco(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, mode="wb") as fh:
            fh.write(b"%PDF-1.7 contenido")
            ruta = fh.name
        try:
            payload = construir_payload(_correo_base(adjuntos=[ruta]))
            att = payload["message"]["attachments"][0]
            self.assertEqual(att["@odata.type"], "#microsoft.graph.fileAttachment")
            self.assertEqual(att["name"], os.path.basename(ruta))
            # contentBytes es base64 del archivo
            self.assertEqual(
                base64.b64decode(att["contentBytes"]), b"%PDF-1.7 contenido"
            )
        finally:
            os.remove(ruta)

    def test_adjunto_inexistente_lanza_error(self):
        with self.assertRaises(GraphSenderError):
            construir_payload(_correo_base(adjuntos=["C:/no/existe/plano.pdf"]))


class TestEnviarCorreoGraph(unittest.TestCase):

    def test_envio_con_token_inyectado(self):
        """Con token dado: una sola llamada POST (sendMail) con Bearer."""
        fake = FakeHTTP()
        ok = enviar_correo_graph(
            _correo_base(), token="TOK", usuario="buzon@cgr.com", cliente_http=fake
        )
        self.assertTrue(ok)
        self.assertEqual(len(fake.llamadas), 1)
        llamada = fake.llamadas[0]
        self.assertIn("sendMail", llamada["url"])
        self.assertIn("buzon@cgr.com", llamada["url"])
        self.assertEqual(llamada["headers"]["Authorization"], "Bearer TOK")

    def test_envio_obtiene_token_si_no_se_da(self):
        """Sin token: primero pide token, luego envía (2 llamadas)."""
        fake = FakeHTTP()
        ok = enviar_correo_graph(
            _correo_base(), usuario="buzon@cgr.com", cliente_http=fake
        )
        self.assertTrue(ok)
        self.assertEqual(len(fake.llamadas), 2)
        self.assertIn("oauth2", fake.llamadas[0]["url"])
        self.assertIn("sendMail", fake.llamadas[1]["url"])
        # El token obtenido se usa en la segunda llamada
        self.assertEqual(
            fake.llamadas[1]["headers"]["Authorization"], "Bearer TOKEN-FALSO"
        )

    def test_sin_destinatario_lanza_error(self):
        correo = _correo_base()
        correo["destinatario"] = ""
        with self.assertRaises(GraphSenderError):
            enviar_correo_graph(correo, token="TOK", usuario="b@cgr.com", cliente_http=FakeHTTP())

    def test_error_http_se_envuelve(self):
        """Un fallo HTTP de Graph se traduce a GraphSenderError."""
        fake = FakeHTTP(sendmail_ok=False)
        with self.assertRaises(GraphSenderError):
            enviar_correo_graph(
                _correo_base(), token="TOK", usuario="b@cgr.com", cliente_http=fake
            )


if __name__ == "__main__":
    unittest.main()
