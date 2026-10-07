import os
import shutil
import tempfile
import unittest

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

from app.persistence.blueprint_store import AlmacenPlanosError, guardar_planos


def _adjuntos():
    # El PNG va con tamaño de plano: una imagen diminuta ahora se toma por el
    # logo de la firma (blueprint_store.es_plano) y no se guarda como plano.
    return [
        {"nombre": "plano-1.pdf", "contenido": b"%PDF-1.7 uno"},
        {"nombre": "plano-2.png", "contenido": b"\x89PNG dos" + b"\x00" * 200_000},
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


class TestPlanosSoloEnNeon(unittest.TestCase):
    """Desde 2026-10 el plano vive en Neon; fuera sólo va lo que la base no tomó."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="planos_neon_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _guardar(self, en_base, copia_externa=False, modo="outlook"):
        from unittest import mock
        with mock.patch("app.persistence.blueprint_store.guardar_en_base",
                        return_value=en_base) as base, \
             mock.patch("app.persistence.blueprint_store._copia_externa",
                        return_value=copia_externa):
            rutas = guardar_planos("INT-ABC", _adjuntos(), modo=modo, base_dir=self.tmp)
        base.assert_called_once()
        return rutas

    def _en_disco(self):
        return sorted(f for _, _, fs in os.walk(self.tmp) for f in fs)

    def test_si_la_base_los_guarda_no_queda_nada_en_disco(self):
        rutas = self._guardar(["plano-1.pdf", "plano-2.png"])
        self.assertEqual(self._en_disco(), [])
        self.assertEqual(rutas, ["neon:rfq_planos/INT-ABC/plano-1.pdf",
                                 "neon:rfq_planos/INT-ABC/plano-2.png"])

    def test_solo_lo_que_la_base_no_tomo_va_de_respaldo_al_disco(self):
        rutas = self._guardar(["plano-1.pdf"])
        self.assertEqual(self._en_disco(), ["plano-2.png"])
        self.assertEqual(len(rutas), 2)

    def test_sin_base_todo_va_de_respaldo(self):
        self._guardar([])
        self.assertEqual(self._en_disco(), ["plano-1.pdf", "plano-2.png"])

    def test_copia_externa_vuelve_a_guardar_siempre_fuera(self):
        self._guardar(["plano-1.pdf", "plano-2.png"], copia_externa=True)
        self.assertEqual(self._en_disco(), ["plano-1.pdf", "plano-2.png"])

    def test_en_modo_token_tampoco_sube_a_blob_si_la_base_los_tiene(self):
        fake = FakeContenedorBlob()
        from unittest import mock
        with mock.patch("app.persistence.blueprint_store.guardar_en_base",
                        return_value=["plano-1.pdf", "plano-2.png"]), \
             mock.patch("app.persistence.blueprint_store._copia_externa",
                        return_value=False):
            guardar_planos("INT-ABC", _adjuntos(), modo="token", cliente_blob=fake)
        self.assertEqual(fake.subidas, [])

    def test_el_modo_invalido_se_rechaza_antes_de_tocar_la_base(self):
        from unittest import mock
        with mock.patch("app.persistence.blueprint_store.guardar_en_base") as base:
            with self.assertRaises(AlmacenPlanosError):
                guardar_planos("RFQ-1", _adjuntos(), modo="ftp")
        base.assert_not_called()


if __name__ == "__main__":
    unittest.main()
