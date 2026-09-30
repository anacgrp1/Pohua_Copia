"""Una respuesta se lee con su conversación (INT-4C64CF50, 2026-09-30).

«3- Test - blank mail»: el primer correo traía el plano y la firma, pero no
el volumen, así que el RFQ se paró antes de leer el plano y se le pidió el
volumen al comprador. Contestó «Volume: 20000» y el RFQ se completó con sólo
eso: sin número de parte (estaba en el plano, que nunca se leyó) y con el
dominio como cliente (la respuesta traía el dominio y tapaba «CGR México»).
"""
import unittest
from unittest import mock

import app.extraction.email_extractor as ex
import app.rfq.flow as flow
from tests.rfq.test_flow import RESORTE_FACTIBLE, correo_base


class TestTextoConHilo(unittest.TestCase):

    HILO = [{"fecha": "2026-09-29", "remitente": "d@cgr.com", "asunto": "3- Test",
             "cuerpo": "Good afternoon, please quote PN SG0000142. Daniela, CGR México"}]

    def test_el_hilo_va_debajo_del_correo_nuevo(self):
        t = ex.texto_con_hilo("Volume: 20000", self.HILO)
        self.assertTrue(t.startswith("Volume: 20000"))
        self.assertIn("CORREOS ANTERIORES DEL MISMO HILO", t)
        self.assertIn("SG0000142", t)

    def test_lo_que_ya_viene_citado_no_se_repite(self):
        citado = "Volume: 20000\n\nFrom: Daniela\n" + self.HILO[0]["cuerpo"]
        self.assertEqual(ex.texto_con_hilo(citado, self.HILO), citado)

    def test_sin_hilo_es_el_correo_tal_cual(self):
        self.assertEqual(ex.texto_con_hilo("hola", []), "hola")

    def test_el_prompt_explica_la_conversacion(self):
        self.assertIn("MÁS RECIENTE", ex.PROMPT_COMERCIAL)
        self.assertIn("CORREOS ANTERIORES DEL MISMO HILO", ex.PROMPT_COMERCIAL)

    def test_extraer_manda_el_hilo_al_modelo(self):
        with mock.patch.object(ex, "analizar_cuerpo",
                               return_value={"texto": '{"volumen": 20000, "confianza": {"volumen": 1}}',
                                             "modelo": "m"}) as analizar:
            ex.extraer("Volume: 20000", asunto="RE: 3- Test", hilo=self.HILO)
        self.assertIn("SG0000142", analizar.call_args[0][0])


class TestRespuestaConSuHilo(unittest.TestCase):

    PREVIOS = {"customer": "CGR México", "dominio": "cgr-international.com",
               "tiene_adjunto": True, "motivo_incompleto": "gate_temprano"}

    def setUp(self):
        for p in [
            mock.patch("app.rfq.thread_validator.registrar_en_historial"),
            mock.patch.object(flow, "_envio_habilitado", return_value=False),
            mock.patch.object(flow, "_avisar", return_value=True),
            mock.patch.object(flow, "registrar_veredicto"),
            mock.patch("app.clients.mapper.mapear_cliente", return_value=None),
            mock.patch("app.rfq.repository.datos_anteriores", return_value=self.PREVIOS),
            mock.patch("app.persistence.blueprint_store.listar_de_base",
                       return_value=[{"nombre": "2594.pdf"}]),
        ]:
            p.start()
        self.guardar = mock.patch("app.persistence.spring_repository.guardar").start()
        self.addCleanup(mock.patch.stopall)

    def _respuesta(self, **parches):
        correo = correo_base(asunto="RE: 3- Test - blank mail [RFQ INT-4C64CF50]",
                             remitente="daniela.diaz@cgr-international.com",
                             cuerpo="Volume: 20000", adjuntos=[])
        hilo = [{"cuerpo": "Please quote. Daniela Diaz, CGR México"}]
        leer = mock.MagicMock(return_value=[dict(RESORTE_FACTIBLE, num_parte="SG0000142")])
        with mock.patch("app.rfq.repository.correos_del_hilo", return_value=hilo) as del_hilo, \
             mock.patch.object(flow, "extraer_datos_correo",
                               return_value={"campos": {"volumen": 20000}}) as extraer, \
             mock.patch.object(flow, "_planos_del_hilo",
                               return_value=[{"nombre": "2594.pdf", "contenido": b"%PDF"}]), \
             mock.patch.object(flow, "procesar_dibujos",
                               side_effect=lambda c, *a, **k: leer() if c.get("adjuntos") else []) as vision, \
             mock.patch.object(flow, "persistir", return_value={}) as persistir:
            resultado = flow.avanzar_a_parsing(correo, flow.RESPUESTA_RFQ, "INT-4C64CF50")
        return resultado, persistir.call_args[0][0], extraer, del_hilo, vision

    def test_la_extraccion_recibe_el_hilo(self):
        _, _, extraer, del_hilo, _ = self._respuesta()
        del_hilo.assert_called_once_with("INT-4C64CF50")
        self.assertEqual(extraer.call_args.kwargs["hilo"][0]["cuerpo"],
                         "Please quote. Daniela Diaz, CGR México")

    def test_se_lee_el_plano_que_se_guardo_con_el_primer_correo(self):
        resultado, datos, _, _, vision = self._respuesta()
        self.assertEqual(resultado["rfq_id"], "INT-4C64CF50")
        self.assertEqual(datos["part_number"], "SG0000142")
        self.assertEqual(datos["resorte"]["diametro_alambre_mm"], 1.2)
        # El plano del hilo se lee y se apunta en el MISMO RFQ.
        segunda = vision.call_args_list[-1]
        self.assertEqual(segunda.args[1], "INT-4C64CF50")
        self.assertTrue(segunda.kwargs.get("guardar"))

    def test_el_dominio_no_tapa_el_cliente_que_ya_se_conocia(self):
        _, datos, _, _, _ = self._respuesta()
        self.assertEqual(datos["customer"], "CGR México")


class TestHeredarCliente(unittest.TestCase):

    def test_un_nombre_de_cliente_dicho_en_la_respuesta_manda(self):
        datos = {"customer": "Neogen SA", "dominio": "neogen.com"}
        with mock.patch("app.rfq.repository.datos_anteriores",
                        return_value={"customer": "Otra"}):
            flow.heredar_del_hilo(datos, "RFQ-1")
        self.assertEqual(datos["customer"], "Neogen SA")


if __name__ == "__main__":
    unittest.main()
