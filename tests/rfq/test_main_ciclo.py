"""Resiliencia del ciclo de detección (src/main.py).

Un correo que truena no debe tumbar el lote completo: se registra, se deja sin
marcar como leído para reintentarlo, y el ciclo sigue con los demás.
"""
import importlib.util
import os
import sys
import unittest
from unittest import mock

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

# El ciclo no usa el scheduler, pero src/main.py lo importa al cargarse. Se
# sustituye si no está instalado, para que el test corra en cualquier máquina.
try:
    import schedule  # noqa: F401
except ImportError:
    sys.modules["schedule"] = mock.MagicMock()

# Hay dos main.py: el de la raíz (lanzador) y el de src/ (el ciclo real).
# Un `import main` resolvería al de la raíz, así que se carga por ruta.
_spec = importlib.util.spec_from_file_location(
    "cotizador_main", os.path.join(RAIZ, "app", "main.py"))
main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(main)


class FakeMensaje:
    """EmailMessage mínimo, con lo que map_email_message necesita leer."""

    def __init__(self, id_):
        self.id = id_
        self.raw_headers = {"Message-ID": f"<{id_}@cliente.com>"}
        self.sender = f"comprador+{id_}@neogen.com"
        self.subject = f"RFQ {id_}"
        self.date = "Tue, 19 Aug 2026 10:00:00 -0600"
        self.body = "Please quote."
        self.attachments = []


class FakeProvider:
    def __init__(self, mensajes):
        self._mensajes = mensajes
        self.leidos = []

    def connect(self):
        return True

    def fetch_unread_messages(self):
        return self._mensajes

    def mark_as_read(self, msg_id):
        self.leidos.append(msg_id)


class TestCicloDeteccion(unittest.TestCase):

    def setUp(self):
        self.provider = FakeProvider([FakeMensaje("A"), FakeMensaje("B"), FakeMensaje("C")])
        parches = [
            mock.patch("app.email.factory.EmailProviderFactory.get_provider",
                       return_value=self.provider),
            mock.patch("app.persistence.duplicates.es_duplicado", return_value=False),
            mock.patch("app.persistence.duplicates.registrar_correo"),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)

    def test_un_correo_que_truena_no_detiene_el_lote(self):
        def procesar(correo):
            if "+B@" in correo["remitente"]:
                raise RuntimeError("dibujo corrupto")
            return "RFQ_NUEVO"

        with mock.patch.object(main, "procesar_correo", side_effect=procesar):
            main.ciclo_deteccion()

        # A y C se procesaron y se marcaron como leídos; B no.
        self.assertEqual(self.provider.leidos, ["A", "C"])

    def test_el_correo_fallido_queda_sin_marcar_para_reintentarlo(self):
        with mock.patch.object(main, "procesar_correo",
                               side_effect=RuntimeError("BD caída")):
            main.ciclo_deteccion()

        self.assertEqual(self.provider.leidos, [])

    def test_lote_sano_marca_todo_como_leido(self):
        with mock.patch.object(main, "procesar_correo", return_value="RFQ_NUEVO"):
            main.ciclo_deteccion()

        self.assertEqual(self.provider.leidos, ["A", "B", "C"])


if __name__ == "__main__":
    unittest.main()
