import os
import shutil
import tempfile
import unittest

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

from app.persistence.blueprint_store import AlmacenPlanosError, guardar_planos


def _adjuntos():
    return [
        {"nombre": "plano-1.pdf", "contenido": b"%PDF-1.7 uno"},
        {"nombre": "plano-2.png", "contenido": b"\x89PNG dos"},
    ]


class FakeContenedorBlob:
    """Container de Blob falso: captura las subidas."""

    def __init__(self):
        self.subidas = []

    def upload_blob(self, name, data, overwrite=False):
        self.subidas.append({"name": name, "data": data, "overwrite": overwrite})


class TestGuardarPlanosDisco(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="planos_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_guarda_en_disco_local(self):
        rutas = guardar_planos(
            "RFQ-2026-001", _adjuntos(), modo="local", base_dir=self.tmp
        )
        self.assertEqual(len(rutas), 2)
        for ruta in rutas:
            self.assertTrue(os.path.isfile(ruta))
        # Contenido correcto del primero
        with open(rutas[0], "rb") as fh:
            self.assertEqual(fh.read(), b"%PDF-1.7 uno")
        # Se agrupan bajo la carpeta del rfq_id
        self.assertIn("RFQ-2026-001", rutas[0])

    def test_el_lector_de_outlook_guarda_en_disco(self):
        """MAIL_MODE=outlook es el lector de escritorio: disco, como imap.

        Antes daba «Modo de almacenamiento desconocido: 'outlook'» en cada RFQ.
        """
        from unittest import mock
        with mock.patch("app.persistence.blueprint_store.guardar_en_base"):
            rutas = guardar_planos(
                "RFQ-2026-002", [{"nombre": "plano.pdf", "contenido": b"%PDF-1.7"}],
                modo="outlook", base_dir=self.tmp)
        self.assertEqual(len(rutas), 1)
        self.assertTrue(os.path.isfile(rutas[0]))

    def test_sin_adjuntos_devuelve_lista_vacia(self):
        self.assertEqual(
            guardar_planos("RFQ-2026-001", [], modo="local", base_dir=self.tmp), []
        )

    def test_rfq_id_se_sanea_para_carpeta(self):
        # Un rfq_id con caracteres problemáticos no debe romper la ruta.
        rutas = guardar_planos(
            "RFQ/2026:001", _adjuntos(), modo="local", base_dir=self.tmp
        )
        self.assertEqual(len(rutas), 2)
        self.assertTrue(os.path.isfile(rutas[0]))


class TestGuardarPlanosBlob(unittest.TestCase):

    def test_sube_a_blob_token(self):
        fake = FakeContenedorBlob()
        nombres = guardar_planos(
            "RFQ-2026-001", _adjuntos(), modo="token", cliente_blob=fake
        )
        self.assertEqual(len(nombres), 2)
        self.assertEqual(len(fake.subidas), 2)
        # Nombres de blob con prefijo del rfq_id
        self.assertEqual(fake.subidas[0]["name"], "RFQ-2026-001/plano-1.pdf")
        self.assertTrue(fake.subidas[0]["overwrite"])
        self.assertEqual(fake.subidas[0]["data"], b"%PDF-1.7 uno")


class TestModoDesconocido(unittest.TestCase):

    def test_modo_invalido_lanza_error(self):
        with self.assertRaises(AlmacenPlanosError):
            guardar_planos("RFQ-1", _adjuntos(), modo="ftp")


if __name__ == "__main__":
    unittest.main()
