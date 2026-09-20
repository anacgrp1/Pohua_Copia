"""El horario de atención: cuándo contesta Pohua y cuándo espera.

La ventana es una sola —la de la planta, Kansas City— porque el ciclo es un
proceso y no puede tener tres horarios a la vez. Lo que cambia de un sitio a
otro es cómo se LEE: por eso ``estado()`` devuelve instantes con su huso, para
que el navegador los pinte en la ciudad del reloj.

Todas las horas de aquí son de Kansas City salvo donde se diga.
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

import app.core.config as config
import app.rfq.horario as horario

KC = ZoneInfo("America/Chicago")
QRO = ZoneInfo("America/Mexico_City")
SEV = ZoneInfo("Europe/Paris")


def kc(dia, hora, minuto=0):
    """Un instante de septiembre de 2026 en Kansas City. El 14 es lunes."""
    return datetime(2026, 9, dia, hora, minuto, tzinfo=KC)


class TestVentana(unittest.TestCase):

    def test_dentro_de_horario(self):
        self.assertTrue(horario.abierto(kc(14, 6)))      # lunes al abrir
        self.assertTrue(horario.abierto(kc(16, 12)))     # miércoles a mediodía
        self.assertTrue(horario.abierto(kc(18, 17, 59)))  # viernes, el último minuto

    def test_fuera_de_horario(self):
        self.assertFalse(horario.abierto(kc(14, 5, 59)))  # lunes, un minuto antes
        self.assertFalse(horario.abierto(kc(14, 18)))     # a las 18:00 en punto, cerrado
        self.assertFalse(horario.abierto(kc(14, 3)))      # madrugada
        self.assertFalse(horario.abierto(kc(19, 10)))     # sábado
        self.assertFalse(horario.abierto(kc(20, 10)))     # domingo

    def test_la_hora_que_cuenta_es_la_de_la_planta(self):
        """Las 7:00 de Querétaro son las 6:00 de Kansas: abierto.

        Y las 12:00 de Sevran son las 5:00 de Kansas: todavía cerrado. El
        mismo instante, dos lecturas, una sola respuesta.
        """
        self.assertTrue(horario.abierto(datetime(2026, 9, 14, 7, 0, tzinfo=QRO)))
        self.assertFalse(horario.abierto(datetime(2026, 9, 14, 12, 0, tzinfo=SEV)))

    def test_se_puede_apagar(self):
        with mock.patch.object(config.settings, "HORARIO_ACTIVO", False):
            self.assertTrue(horario.abierto(kc(20, 3)))   # domingo de madrugada
            self.assertIsNone(horario.proxima_apertura(kc(20, 3)))

    def test_una_ventana_imposible_no_apaga_el_sistema(self):
        """HASTA <= DESDE dejaría el buzón cerrado para siempre y en silencio."""
        with mock.patch.object(config.settings, "HORARIO_DESDE", 18), \
             mock.patch.object(config.settings, "HORARIO_HASTA", 6):
            self.assertTrue(horario.abierto(kc(20, 3)))


class TestDias(unittest.TestCase):

    def test_formatos(self):
        self.assertEqual(horario.dias_laborables("1-5"), [1, 2, 3, 4, 5])
        self.assertEqual(horario.dias_laborables("1,3,5"), [1, 3, 5])
        self.assertEqual(horario.dias_laborables("6,7"), [6, 7])

    def test_basura_cae_en_lunes_a_viernes(self):
        for texto in ("", "   ", "lunes", None, "0,9"):
            self.assertEqual(horario.dias_laborables(texto), [1, 2, 3, 4, 5])

    def test_sabado_incluido(self):
        with mock.patch.object(config.settings, "HORARIO_DIAS", "1-6"):
            self.assertTrue(horario.abierto(kc(19, 10)))   # sábado
            self.assertFalse(horario.abierto(kc(20, 10)))  # domingo


class TestProximaApertura(unittest.TestCase):

    def test_hoy_si_aun_no_ha_abierto(self):
        self.assertEqual(horario.proxima_apertura(kc(14, 4)), kc(14, 6))

    def test_manana_si_ya_cerro(self):
        self.assertEqual(horario.proxima_apertura(kc(14, 19)), kc(15, 6))

    def test_el_viernes_por_la_noche_apunta_al_lunes(self):
        """El caso que importa: lo que llega el sábado espera al lunes."""
        self.assertEqual(horario.proxima_apertura(kc(18, 20)), kc(21, 6))
        self.assertEqual(horario.proxima_apertura(kc(19, 11)), kc(21, 6))
        self.assertEqual(horario.proxima_apertura(kc(20, 23)), kc(21, 6))

    def test_abierto_no_tiene_proxima_apertura(self):
        self.assertIsNone(horario.proxima_apertura(kc(16, 9)))

    def test_cierre(self):
        self.assertEqual(horario.proximo_cierre(kc(16, 9)), kc(16, 18))
        self.assertIsNone(horario.proximo_cierre(kc(16, 20)))


class TestEstado(unittest.TestCase):

    def test_lo_que_ve_la_pantalla(self):
        e = horario.estado(kc(19, 11))          # sábado
        self.assertFalse(e["abierto"])
        self.assertTrue(e["activo"])
        self.assertEqual(e["ciudad"], "Kansas City")
        self.assertEqual((e["desde"], e["hasta"]), (6, 18))
        self.assertEqual(e["dias"], [1, 2, 3, 4, 5])
        # El instante lleva su huso: el navegador lo pinta en su ciudad.
        self.assertTrue(e["proxima_apertura"].startswith("2026-09-21T06:00:00-05"))
        self.assertIsNone(e["proximo_cierre"])

    def test_abierto(self):
        e = horario.estado(kc(16, 9))
        self.assertTrue(e["abierto"])
        self.assertIsNone(e["proxima_apertura"])
        self.assertTrue(e["proximo_cierre"].startswith("2026-09-16T18:00:00-05"))

    def test_la_ciudad_sale_de_la_zona(self):
        with mock.patch.object(config.settings, "HORARIO_ZONA", "America/Mexico_City"):
            self.assertEqual(horario.estado(kc(16, 9))["ciudad"], "Querétaro")
        with mock.patch.object(config.settings, "HORARIO_ZONA", "Europe/Paris"):
            self.assertEqual(horario.estado(kc(16, 9))["ciudad"], "Sevran")

    def test_motivo_cerrado_dice_hasta_cuando(self):
        motivo = horario.motivo_cerrado(kc(19, 11))
        self.assertIn("Kansas City", motivo)
        self.assertIn("2026-09-21T06:00:00", motivo)


class TestCicloRespetaElHorario(unittest.TestCase):
    """Fuera de hora el buzón NI SE ABRE: el correo espera donde está."""

    def _main(self):
        import importlib.util
        import sys
        raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        sys.modules.setdefault("schedule", mock.MagicMock())
        spec = importlib.util.spec_from_file_location(
            "cotizador_main_horario", os.path.join(raiz, "app", "main.py"))
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo

    def test_cerrado_no_toca_el_buzon(self):
        main = self._main()
        with mock.patch("app.rfq.horario.abierto", return_value=False), \
             mock.patch("app.email.factory.EmailProviderFactory.get_provider") as proveedor:
            resultado = main.ciclo_deteccion()
        proveedor.assert_not_called()
        self.assertFalse(resultado.en_horario)
        self.assertEqual(resultado.encontrados, 0)
        self.assertEqual(resultado.errores, 0)
        self.assertTrue(resultado.detalles and "horario" in resultado.detalles[0].lower())

    def test_a_mano_se_salta_el_horario(self):
        """Quien pulsa "Ejecutar ciclo" un domingo quiere leer el buzón."""
        main = self._main()
        proveedor = mock.MagicMock()
        proveedor.fetch_unread_messages.return_value = []
        # El recordatorio de dictamen va al final del ciclo y habla con la base
        # de datos. Aquí no se está probando eso: sin taparlo, esta prueba
        # acabaría esperando a un servidor que en la máquina de pruebas no
        # tiene por qué existir.
        with mock.patch("app.rfq.horario.abierto", return_value=False), \
             mock.patch("app.rfq.recordatorios.revisar",
                        return_value={"avisados": 0, "correos": 0}), \
             mock.patch("app.email.factory.EmailProviderFactory.get_provider",
                        return_value=proveedor):
            resultado = main.ciclo_deteccion(forzar=True)
        proveedor.connect.assert_called_once()
        self.assertTrue(resultado.en_horario)


class TestEstadoNoCuentaCiclosOmitidos(unittest.TestCase):
    """Un ciclo que no se ejecutó no es el "último ciclo" del servicio."""

    def test_omitido_no_mueve_el_contador(self):
        import api.routes.status as status

        class Omitido:
            timestamp = "2026-09-20T03:00:00"
            procesados, rfqs, errores, en_horario = 0, 0, 0, False

        antes = status._snapshot()["last_cycle"]
        status.registrar_ciclo(Omitido())
        self.assertEqual(status._snapshot()["last_cycle"], antes)


if __name__ == "__main__":
    unittest.main()
