"""El recordatorio de lo que lleva demasiado esperando dictamen.

Lo que se protege aquí es que sea un RESPALDO y no una lluvia: que no salga
si está apagado, que no salga sin una dirección pública a la que enlazar, que
salga UNA vez por caso y que un fallo de correo no tumbe el ciclo.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

import app.core.config as config
import app.rfq.recordatorios as recordatorios

CASOS = [
    {"rfq_id": "COT-75", "estado": "RequiresReview", "cliente_id": "Neogen",
     "nombre_proyecto": "1060-022", "fecha_registro": None},
    {"rfq_id": "COT-76", "estado": "New", "cliente_id": "Wabtec",
     "nombre_proyecto": "2200-001", "fecha_registro": None},
]

PERSONAS = [{"id": 1, "correo": "rodea@isc.com", "nombre": "Miguel Rodea", "rol": "pm"},
            {"id": 2, "correo": "ana@cgr.com", "nombre": "Ana", "rol": "admin"}]


class TestInterruptores(unittest.TestCase):

    def test_apagado_no_consulta_nada(self):
        with mock.patch.object(config.settings, "RECORDATORIO_HORAS", 0), \
             mock.patch.object(recordatorios, "pendientes") as buscar:
            r = recordatorios.revisar()
        buscar.assert_not_called()
        self.assertIn("apagados", r["motivo"])

    def test_sin_direccion_publica_no_manda(self):
        """Un enlace a localhost en un correo no sirve para nada."""
        with mock.patch.object(config.settings, "RECORDATORIO_HORAS", 4), \
             mock.patch.object(config.settings, "APP_URL", ""), \
             mock.patch.object(config.settings, "WEB_SERVER_URL", "http://localhost:8000"), \
             mock.patch.object(recordatorios, "pendientes", return_value=CASOS), \
             mock.patch("app.email.outbound.enviar") as enviar:
            r = recordatorios.revisar()
        enviar.assert_not_called()
        self.assertEqual(r["motivo"], "falta APP_URL")
        self.assertEqual(r["pendientes"], 2)

    def test_sin_nadie_a_quien_escribir(self):
        with mock.patch.object(config.settings, "RECORDATORIO_HORAS", 4), \
             mock.patch.object(config.settings, "APP_URL", "https://pohua.example"), \
             mock.patch.object(recordatorios, "pendientes", return_value=CASOS), \
             mock.patch.object(recordatorios, "_quien_dictamina", return_value=[]), \
             mock.patch("app.email.outbound.enviar") as enviar:
            r = recordatorios.revisar()
        enviar.assert_not_called()
        self.assertEqual(r["motivo"], "nadie a quien escribir")


class TestEnvio(unittest.TestCase):

    def _revisar(self, enviar, marcar):
        with mock.patch.object(config.settings, "RECORDATORIO_HORAS", 4), \
             mock.patch.object(config.settings, "APP_URL", "https://pohua.example"), \
             mock.patch.object(recordatorios, "pendientes", return_value=CASOS), \
             mock.patch.object(recordatorios, "_quien_dictamina", return_value=PERSONAS), \
             mock.patch.object(recordatorios, "marcar", marcar), \
             mock.patch("app.email.outbound.enviar", enviar):
            return recordatorios.revisar()

    def test_uno_por_persona_y_el_texto_que_toca(self):
        enviar, marcar = mock.MagicMock(return_value=True), mock.MagicMock()
        r = self._revisar(enviar, marcar)

        self.assertEqual(r, {"pendientes": 2, "avisados": 2, "correos": 4, "motivo": ""})
        asuntos = [c.args[0]["asunto"] for c in enviar.call_args_list]
        self.assertEqual(asuntos, ["Feasibility review required – Neogen"] * 2
                                  + ["Quote validation required – Wabtec"] * 2)
        # A cada quien por su nombre, y con el enlace a SU caso.
        primero = enviar.call_args_list[0].args[0]
        self.assertEqual(primero["destinatario"], "rodea@isc.com")
        self.assertIn("Hi Miguel Rodea,", primero["cuerpo_texto"])
        self.assertIn("https://pohua.example/#/rfq/COT-75", primero["cuerpo_texto"])

    def test_queda_apuntado_para_no_repetirlo(self):
        enviar, marcar = mock.MagicMock(return_value=True), mock.MagicMock()
        self._revisar(enviar, marcar)
        apuntados = [c.args[0] for c in marcar.call_args_list]
        self.assertEqual(apuntados, ["COT-75", "COT-76"])
        self.assertIn("rodea@isc.com", marcar.call_args_list[0].args[2])

    def test_un_correo_que_falla_no_frena_el_resto(self):
        enviar = mock.MagicMock(side_effect=[Exception("SMTP"), True, True, True])
        marcar = mock.MagicMock()
        r = self._revisar(enviar, marcar)
        self.assertEqual(enviar.call_count, 4)
        self.assertEqual(r["correos"], 3)
        self.assertEqual(r["avisados"], 2)

    def test_si_no_sale_ninguno_no_se_apunta(self):
        """Si no se apuntara, el caso se quedaría sin recordatorio para siempre."""
        enviar = mock.MagicMock(side_effect=Exception("SMTP"))
        marcar = mock.MagicMock()
        r = self._revisar(enviar, marcar)
        marcar.assert_not_called()
        self.assertEqual(r["avisados"], 0)


class TestEnlace(unittest.TestCase):

    def test_prefiere_app_url(self):
        with mock.patch.object(config.settings, "APP_URL", "https://pohua.example/"), \
             mock.patch.object(config.settings, "WEB_SERVER_URL", "https://otra.example"):
            self.assertEqual(recordatorios.enlace_de("COT-1"),
                             "https://pohua.example/#/rfq/COT-1")

    def test_cae_en_el_servidor_web_si_es_publico(self):
        with mock.patch.object(config.settings, "APP_URL", ""), \
             mock.patch.object(config.settings, "WEB_SERVER_URL", "https://otra.example"):
            self.assertEqual(recordatorios.enlace_de("COT-1"),
                             "https://otra.example/#/rfq/COT-1")

    def test_localhost_no_cuenta(self):
        with mock.patch.object(config.settings, "APP_URL", "http://127.0.0.1:8000"), \
             mock.patch.object(config.settings, "WEB_SERVER_URL", "http://localhost:8000"):
            self.assertEqual(recordatorios.enlace_de("COT-1"), "")


if __name__ == "__main__":
    unittest.main()
