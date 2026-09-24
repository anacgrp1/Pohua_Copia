"""COT-72 — Tests del dictamen del plant manager (aprobar / declinar).

Sin BD, sin red: la persistencia y el transporte del correo se sustituyen por
dobles. Lo que se verifica es el circuito — qué se registra, cuándo sale el
correo al cliente y cuándo no.
"""
import os
import unittest
from unittest import mock

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

import app.feasibility.pm_decision as pm_decision


# Lo que devuelve repository.guardar_veredicto_final: incluye el
# datos_json del RFQ, de donde sale a quién contestarle.
def registro_falso(**extra):
    datos = {
        "id": 7,
        "rfq_id": "RFQ-1",
        "version": 1,
        "veredicto_final": None,
        "estado": "Declined",
        "datos": {
            "remitente": "roberto.perez@neogen.com",
            "asunto": "RFQ 4500 - resorte de compresión",
            "customer": "Neogen SA",
        },
    }
    datos.update(extra)
    return datos


class BaseDecision(unittest.TestCase):
    """Dobles comunes: persistencia, plantilla y canal de salida."""

    def setUp(self):
        self.guardar = self.patch("app.rfq.repository.guardar_veredicto_final",
                                  return_value=registro_falso())
        self.construir = self.patch("app.email.templates.construir_correo",
                                    return_value={"destinatario": "x@y.com"})
        self.habilitado = self.patch("app.email.outbound.envio_habilitado",
                                     return_value=False)
        self.enviar = self.patch("app.email.outbound.enviar", return_value=True)
        self.cerrar_avisos = self.patch("app.notifications.repository.cerrar_del_rfq",
                                        return_value=1)

    def patch(self, objetivo, **kwargs):
        parche = mock.patch(objetivo, **kwargs)
        doble = parche.start()
        self.addCleanup(parche.stop)
        return doble


class TestDeclinar(BaseDecision):

    def test_registra_el_veredicto_y_el_estado(self):
        resultado = pm_decision.declinar("RFQ-1")
        self.assertEqual(resultado["veredicto_final"], "not feasible")
        self.assertEqual(self.guardar.call_args[0][1], "not feasible")
        self.assertEqual(self.guardar.call_args.kwargs["estado"], "Declined")

    def test_con_envio_apagado_construye_pero_no_manda(self):
        resultado = pm_decision.declinar("RFQ-1")
        self.construir.assert_called_once()
        self.enviar.assert_not_called()
        self.assertFalse(resultado["correo_enviado"])

    def test_con_envio_encendido_le_escribe_al_cliente(self):
        self.habilitado.return_value = True
        resultado = pm_decision.declinar("RFQ-1")
        self.enviar.assert_called_once()
        self.assertTrue(resultado["correo_enviado"])

    def test_usa_la_plantilla_de_declinacion(self):
        pm_decision.declinar("RFQ-1")
        tipo, params = self.construir.call_args[0]
        self.assertEqual(tipo, "declinar_rfq")
        self.assertEqual(params["destinatario"], "roberto.perez@neogen.com")
        self.assertEqual(params["asunto_original"],
                         "RFQ 4500 - resorte de compresión")
        self.assertEqual(params["nombre_comprador"], "Roberto Perez")

    def test_destinatario_explicito_manda(self):
        pm_decision.declinar("RFQ-1", destinatario="compras@neogen.com")
        self.assertEqual(self.construir.call_args[0][1]["destinatario"],
                         "compras@neogen.com")

    def test_sin_remitente_no_hay_a_quien_escribirle(self):
        self.guardar.return_value = registro_falso(datos={})
        resultado = pm_decision.declinar("RFQ-1")
        self.construir.assert_not_called()
        # El dictamen queda registrado igual: lo que falta es sólo el aviso.
        self.assertFalse(resultado["correo_enviado"])
        self.guardar.assert_called_once()

    def test_enviar_correo_false_solo_registra(self):
        self.habilitado.return_value = True
        resultado = pm_decision.declinar("RFQ-1", enviar_correo=False)
        self.construir.assert_not_called()
        self.enviar.assert_not_called()
        self.assertFalse(resultado["correo_enviado"])
        self.guardar.assert_called_once()

    def test_fallo_del_envio_no_propaga(self):
        self.habilitado.return_value = True
        self.enviar.side_effect = Exception("SMTP caído")
        resultado = pm_decision.declinar("RFQ-1")
        self.assertFalse(resultado["correo_enviado"])

    def test_fallo_de_la_plantilla_no_propaga(self):
        self.construir.side_effect = Exception("plantilla rota")
        self.assertFalse(pm_decision.declinar("RFQ-1")["correo_enviado"])

    def test_si_no_se_pudo_registrar_no_se_escribe_al_cliente(self):
        # Al revés, el cliente recibiría la declinación de un RFQ que en la
        # base sigue abierto.
        self.guardar.side_effect = ValueError("no existe el RFQ")
        with self.assertRaises(ValueError):
            pm_decision.declinar("RFQ-FANTASMA")
        self.construir.assert_not_called()


class TestAprobar(BaseDecision):

    def test_registra_factible_y_no_escribe_al_cliente(self):
        self.habilitado.return_value = True
        resultado = pm_decision.aprobar("RFQ-1", usuario="ing.lopez")
        self.assertEqual(resultado["veredicto_final"], "feasible")
        self.assertEqual(self.guardar.call_args.kwargs["estado"], "Approved")
        self.construir.assert_not_called()
        self.enviar.assert_not_called()


class TestLaCampanaSeVacia(BaseDecision):
    """Aprobado o declinado, sus avisos ya no piden nada a nadie."""

    def test_aprobar_cierra_los_avisos_del_rfq(self):
        pm_decision.aprobar("RFQ-1", usuario="rodea@isc.com")
        self.cerrar_avisos.assert_called_once()
        self.assertEqual(self.cerrar_avisos.call_args.args[0], "RFQ-1")
        self.assertEqual(self.cerrar_avisos.call_args.kwargs["correo"], "rodea@isc.com")

    def test_declinar_tambien(self):
        pm_decision.declinar("RFQ-1", usuario="rodea@isc.com", enviar_correo=False)
        self.cerrar_avisos.assert_called_once()

    def test_devolver_no_los_cierra(self):
        # Devuelto sigue esperando: el aviso tiene que quedarse.
        self.patch("app.rfq.repository.agregar_nota",
                   return_value={"id": 1, "version": 1, "estado": "RequiresReview",
                                 "notas": ""})
        self.patch("app.notifications.repository.crear", return_value=1)
        pm_decision.devolver("RFQ-1", nota="Falta el material", usuario="rodea@isc.com")
        self.cerrar_avisos.assert_not_called()

    def test_si_falla_el_dictamen_queda_igual(self):
        self.cerrar_avisos.side_effect = RuntimeError("sin base")
        resultado = pm_decision.aprobar("RFQ-1", usuario="rodea@isc.com")
        self.assertEqual(resultado["veredicto_final"], "feasible")
        self.guardar.assert_called_once()


class TestNotaYAutor(BaseDecision):

    def test_nota_con_usuario(self):
        pm_decision.declinar("RFQ-1", nota="Fuera de capacidad", usuario="ing.lopez")
        self.assertEqual(self.guardar.call_args.kwargs["nota"],
                         "[PM: ing.lopez] Fuera de capacidad")

    def test_solo_usuario(self):
        pm_decision.aprobar("RFQ-1", usuario="ing.lopez")
        self.assertEqual(self.guardar.call_args.kwargs["nota"], "[PM: ing.lopez]")

    def test_solo_nota(self):
        pm_decision.aprobar("RFQ-1", nota="Se puede con herramental nuevo")
        self.assertEqual(self.guardar.call_args.kwargs["nota"],
                         "Se puede con herramental nuevo")

    def test_sin_nota_ni_usuario(self):
        pm_decision.aprobar("RFQ-1")
        self.assertIsNone(self.guardar.call_args.kwargs["nota"])


class TestVeredictosAdmitidos(BaseDecision):

    def test_veredicto_inventado_no_toca_la_bd(self):
        with self.assertRaises(ValueError):
            pm_decision.resolver("RFQ-1", "requires review")
        self.guardar.assert_not_called()

    def test_el_vocabulario_es_el_del_motor(self):
        import app.feasibility.engine as engine
        self.assertEqual(pm_decision.FACTIBLE, engine.FINAL_FACTIBLE)
        self.assertEqual(pm_decision.NO_FACTIBLE, engine.FINAL_NO_FACTIBLE)
        # El veredicto del sistema no es un dictamen del PM.
        self.assertNotIn(engine.VEREDICTO_REVISION, pm_decision.VEREDICTOS)

    def test_version_explicita_llega_al_repositorio(self):
        pm_decision.declinar("RFQ-1", version=3)
        self.assertEqual(self.guardar.call_args.kwargs["version"], 3)


if __name__ == "__main__":
    unittest.main()
