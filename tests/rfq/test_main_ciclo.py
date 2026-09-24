"""Resiliencia del ciclo de detección (src/main.py).

Un correo que truena no debe tumbar el lote completo: se registra, se deja sin
marcar como leído para reintentarlo, y el ciclo sigue con los demás.
"""
import importlib.util
import os
import sys
import unittest
from unittest import mock

import app.core.config as config

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
            # El ciclo respeta el horario de atención; estas pruebas son sobre
            # lo que pasa DENTRO de él, así que se deja abierto a propósito
            # (si no, el lote entero se saltaría al correr de madrugada).
            mock.patch("app.rfq.horario.abierto", return_value=True),
            mock.patch("app.email.factory.EmailProviderFactory.get_provider",
                       return_value=self.provider),
            # El buzón es falso: que no dependa de las variables IMAP del
            # entorno (según el orden de las pruebas, estaban o no).
            mock.patch("app.email.entrada.diagnostico_lectura",
                       return_value={"puede": True}),
            mock.patch("app.persistence.duplicates.es_duplicado", return_value=False),
            mock.patch("app.persistence.duplicates.registrar_correo", return_value=True),
            mock.patch("app.persistence.duplicates.hay_rfq_del_correo", return_value=False),
            mock.patch("app.persistence.duplicates.olvidar_correo"),
            # Al final del ciclo va el recordatorio de lo que lleva demasiado
            # tiempo esperando dictamen, y eso abre la base de datos por su
            # cuenta. Estas pruebas son sobre el lote de correos, así que se
            # tapa: si no, dependerían de que haya una base de datos delante.
            mock.patch("app.rfq.recordatorios.revisar",
                       return_value={"avisados": 0, "correos": 0}),
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

    def test_el_repetido_se_salta(self):
        """Lo normal: el mismo correo no se procesa dos veces."""
        with mock.patch("app.persistence.duplicates.es_duplicado", return_value=True), \
             mock.patch.object(main, "procesar_correo") as procesar:
            resultado = main.ciclo_deteccion()
        procesar.assert_not_called()
        self.assertEqual(resultado.procesados, 0)
        self.assertTrue(any("Duplicado omitido" in d for d in resultado.detalles))

    def test_en_modo_prueba_el_repetido_se_vuelve_a_procesar(self):
        """Con REPROCESAR_REPETIDOS se repite el MISMO correo a propósito.

        Es lo que hace falta para ensayar el recorrido entero sin tener que
        mandar un correo nuevo en cada intento. Y se anuncia en el resultado,
        para que nadie se lo encuentre encendido sin querer.
        """
        with mock.patch.object(config.settings, "REPROCESAR_REPETIDOS", True), \
             mock.patch("app.persistence.duplicates.es_duplicado", return_value=True), \
             mock.patch.object(main, "procesar_correo", return_value="RFQ_NUEVO"):
            resultado = main.ciclo_deteccion()
        self.assertEqual(resultado.procesados, 3)
        self.assertTrue(any("repetidos" in d for d in resultado.detalles))

    def test_no_se_contesta_a_si_mismo(self):
        """Una respuesta del propio buzón no es un RFQ del cliente.

        El buzón de ventas manda las respuestas; si una acaba en la carpeta
        vigilada —una regla de Outlook, un reenvío, alguien que la movió—, sin
        este filtro el sistema la trataría como correo entrante y se pondría a
        contestarse a sí mismo.
        """
        propio = FakeMensaje("PROPIO")
        propio.sender = "sales.isc@cgr-international.com"
        self.provider._mensajes = [propio, FakeMensaje("A")]

        with mock.patch.object(config.settings, "OUTLOOK_BUZON",
                               "sales.isc@cgr-international.com"), \
             mock.patch.object(main, "procesar_correo", return_value="RFQ_NUEVO") as procesar:
            resultado = main.ciclo_deteccion()

        procesados = [c.args[0]["remitente"] for c in procesar.call_args_list]
        self.assertEqual(procesados, ["comprador+A@neogen.com"])
        # Y se marca como leído: si no, volvería a mirarse en cada ciclo.
        self.assertIn("PROPIO", self.provider.leidos)
        self.assertTrue(any("propio buzón" in d for d in resultado.detalles))

    def test_el_duplicado_se_busca_tambien_por_entry_id(self):
        """El EntryID de Outlook también cuenta como clave del correo.

        Si una vez el guardián de Outlook dejó leer la cabecera y otra no, el
        mismo correo llega con dos claves distintas. Se consulta y se apunta
        con las dos, para reconocerlo con cualquiera.
        """
        with mock.patch("app.persistence.duplicates.es_duplicado",
                        return_value=False) as es_dup, \
             mock.patch("app.persistence.duplicates.registrar_correo",
                        return_value=True) as registrar, \
             mock.patch.object(main, "procesar_correo", return_value="RFQ_NUEVO"):
            main.ciclo_deteccion()
        self.assertEqual(es_dup.call_args_list[0].kwargs["otras_claves"], ["A"])
        self.assertEqual(registrar.call_args_list[0].kwargs["otras_claves"], ["A"])

    def test_se_apunta_antes_de_procesar(self):
        """Si se apuntara después, un fallo tras crear el RFQ lo repetiría."""
        orden = []
        with mock.patch("app.persistence.duplicates.registrar_correo",
                        side_effect=lambda *a, **k: orden.append("apuntar") or True), \
             mock.patch.object(main, "procesar_correo",
                               side_effect=lambda c: orden.append("procesar") or "RFQ"):
            main.ciclo_deteccion()
        self.assertEqual(orden[:2], ["apuntar", "procesar"])

    def test_si_otra_ejecucion_ya_lo_apunto_no_se_procesa(self):
        with mock.patch("app.persistence.duplicates.registrar_correo", return_value=False), \
             mock.patch.object(main, "procesar_correo") as procesar:
            main.ciclo_deteccion()
        procesar.assert_not_called()

    def test_falla_sin_rfq_se_desapunta_para_reintentarlo(self):
        with mock.patch("app.persistence.duplicates.hay_rfq_del_correo",
                        return_value=False), \
             mock.patch("app.persistence.duplicates.olvidar_correo") as olvidar, \
             mock.patch.object(main, "procesar_correo", side_effect=RuntimeError("x")):
            main.ciclo_deteccion()
        self.assertEqual(olvidar.call_count, 3)
        self.assertEqual(self.provider.leidos, [])

    def test_falla_con_rfq_ya_creado_no_se_vuelve_a_cotizar(self):
        """El caso real: el RFQ ya existía y el correo seguía sin leer.

        Falló algo DESPUÉS de dar de alta el RFQ. El correo se queda apuntado
        y se marca leído: volver a procesarlo daba un segundo RFQ, cotizado de
        nuevo, de un pedido que ya tenía dictamen.
        """
        with mock.patch("app.persistence.duplicates.hay_rfq_del_correo",
                        return_value=True), \
             mock.patch("app.persistence.duplicates.olvidar_correo") as olvidar, \
             mock.patch.object(main, "procesar_correo", side_effect=RuntimeError("x")):
            resultado = main.ciclo_deteccion()
        olvidar.assert_not_called()
        self.assertEqual(self.provider.leidos, ["A", "B", "C"])
        self.assertEqual(resultado.errores, 3)

    def test_lote_sano_marca_todo_como_leido(self):
        with mock.patch.object(main, "procesar_correo", return_value="RFQ_NUEVO"):
            main.ciclo_deteccion()

        self.assertEqual(self.provider.leidos, ["A", "B", "C"])


if __name__ == "__main__":
    unittest.main()
