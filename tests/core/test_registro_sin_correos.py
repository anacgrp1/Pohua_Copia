"""El registro no guarda la dirección completa de los compradores (app/core/logging.py)."""
import io
import logging
import unittest

from app.core.logging import _instalar_tachado, tachar_correos


class TestTacharCorreos(unittest.TestCase):

    def test_deja_inicial_y_dominio(self):
        self.assertEqual(tachar_correos("de roberto.perez@neogen.com."), "de r***@neogen.com.")
        self.assertEqual(tachar_correos("a@b.co y sales.isc@cgr-international.com"),
                         "a***@b.co y s***@cgr-international.com")

    def test_no_toca_lo_que_no_es_un_correo(self):
        for texto in ("RFQ INT-59C34202 aprobado", "x@localhost", "precio 3@4"):
            self.assertEqual(tachar_correos(texto), texto)


class TestTachadoEnElRegistro(unittest.TestCase):

    def setUp(self):
        self.fabrica = logging.getLogRecordFactory()

    def tearDown(self):
        logging.setLogRecordFactory(self.fabrica)

    def test_lo_tacha_al_crear_la_linea_y_vale_para_cualquier_manejador(self):
        _instalar_tachado()
        _instalar_tachado()                      # dos veces no lo envuelve dos veces
        salida = io.StringIO()
        manejador = logging.StreamHandler(salida)
        hijo = logging.getLogger("prueba.tachado.hijo")
        hijo.setLevel(logging.INFO)
        hijo.addHandler(manejador)
        try:
            hijo.info("Oferta enviada a %s (%d pz)", "comprador.uno@cliente.mx", 500)
        finally:
            hijo.removeHandler(manejador)
        self.assertEqual(salida.getvalue().strip(), "Oferta enviada a c***@cliente.mx (500 pz)")


if __name__ == "__main__":
    unittest.main()
