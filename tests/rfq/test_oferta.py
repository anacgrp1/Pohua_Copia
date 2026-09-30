"""La oferta al cliente (app/rfq/oferta.py) y el costeo por tramos (costeo.py).

Sin base ni motor: se simulan la carga del RFQ y el costeo, que es lo que
tienen de lento, y se prueban las reglas —qué bloquea, qué avisa, qué sale.
"""
from __future__ import annotations

import unittest
from unittest import mock

import app.rfq.costeo as costeo
import app.rfq.oferta as oferta


class TestCantidades(unittest.TestCase):
    def test_los_escalones_mandan_sobre_el_volumen(self):
        datos = {"escalones_cantidad": [50000, 10000, 25000], "volumen": "7000"}
        self.assertEqual(costeo.cantidades_del_rfq(datos), [10000.0, 25000.0, 50000.0])

    def test_los_escalones_pueden_venir_como_texto(self):
        datos = {"escalones_cantidad": "10,000, 25000 y 50.000"}
        self.assertEqual(costeo.cantidades_del_rfq(datos), [10000.0, 25000.0, 50000.0])

    def test_sin_escalones_queda_el_volumen(self):
        self.assertEqual(costeo.cantidades_del_rfq({"volumen": "12,500"}), [12500.0])

    def test_sin_nada_no_hay_tramos(self):
        self.assertEqual(costeo.cantidades_del_rfq({}), [])


def _rfq(estado="Approved", remitente="buyer@cliente.com"):
    return {"id": 1, "version": 1, "estado": estado, "cliente_id": None,
            "part_number": "1060-022", "volumen": "10000", "material": "SS",
            "datos": {"customer": "Fake Customer", "remitente": remitente,
                      "asunto": "Spring Quote", "escalones_cantidad": [10000, 25000]},
            "notas": None, "fecha_registro": None,
            "resorte": {"tipo_resorte": "compresion", "diametro_alambre_mm": 5.207}}


def _costeado(completo=True, tramos=True):
    return {
        "cantidades": [10000.0, 25000.0],
        "tramos": ([{"cantidad": 10000.0, "precio_pc": 0.8658},
                    {"cantidad": 25000.0, "precio_pc": 0.7427}] if tramos else []),
        "costeo": {"completo": completo, "faltantes": ([] if completo else ["SS sin precio"]),
                   "origen": {}, "banderas_motor": []},
        "comunes": {"material": "SS", "material_nombre": "Stainless Steel 302/304"},
        "error_costeo": None,
    }


class TestPreparar(unittest.TestCase):
    def test_lista_cuando_esta_aprobado_y_el_costeo_es_completo(self):
        with mock.patch.object(oferta, "_cargar", return_value=_rfq()), \
             mock.patch.object(costeo, "costear", return_value=_costeado()):
            prep = oferta.preparar("RFQ-1")
        self.assertTrue(prep["listo"])
        linea = prep["pdf"]["lines"][0]
        self.assertEqual(linea["partNo"], "1060-022")
        self.assertEqual(linea["description"], "Compression spring")
        self.assertEqual([t["qty"] for t in linea["tiers"]], [10000.0, 25000.0])
        self.assertEqual(prep["correo"]["destinatario"], "buyer@cliente.com")
        self.assertEqual(prep["correo"]["nombre_proyecto"], "1060-022")

    def test_sin_aprobar_no_esta_lista(self):
        with mock.patch.object(oferta, "_cargar", return_value=_rfq("RequiresReview")), \
             mock.patch.object(costeo, "costear", return_value=_costeado()):
            prep = oferta.preparar("RFQ-1")
        self.assertFalse(prep["listo"])
        self.assertTrue(any("aprobado" in m for m in prep["motivos"]))

    def test_costeo_orientativo_avisa(self):
        with mock.patch.object(oferta, "_cargar", return_value=_rfq()), \
             mock.patch.object(costeo, "costear", return_value=_costeado(completo=False)):
            prep = oferta.preparar("RFQ-1")
        self.assertFalse(prep["listo"])
        self.assertTrue(any("orientativo" in m for m in prep["motivos"]))


class TestEnviar(unittest.TestCase):
    def _parches(self, rfq, costeado, habilitado=True):
        return [
            mock.patch.object(oferta, "_cargar", return_value=rfq),
            mock.patch.object(costeo, "costear", return_value=costeado),
            mock.patch.object(oferta, "generar_pdf", return_value=__import__("pathlib").Path("/tmp/Fake Customer - RFQ-1.pdf")),
            mock.patch("app.email.outbound.envio_habilitado", return_value=habilitado),
            mock.patch("app.email.outbound.enviar", return_value=True),
            mock.patch("app.rfq.repository.anotar_oferta", return_value={}),
        ]

    def _con(self, parches):
        for p in parches:
            p.start(); self.addCleanup(p.stop)
        return parches

    def test_sin_aprobar_se_niega(self):
        self._con(self._parches(_rfq("New"), _costeado()))
        with self.assertRaises(ValueError):
            oferta.enviar("RFQ-1", usuario="pm@x")

    def test_orientativo_exige_forzar(self):
        self._con(self._parches(_rfq(), _costeado(completo=False)))
        with self.assertRaises(ValueError):
            oferta.enviar("RFQ-1", usuario="pm@x")
        salida = oferta.enviar("RFQ-1", usuario="pm@x", forzar=True)
        self.assertTrue(salida["enviado"])

    def test_sin_tramos_se_niega_aunque_se_fuerce(self):
        self._con(self._parches(_rfq(), _costeado(tramos=False)))
        with self.assertRaises(ValueError):
            oferta.enviar("RFQ-1", usuario="pm@x", forzar=True)

    def test_con_envio_apagado_se_genera_pero_no_sale(self):
        self._con(self._parches(_rfq(), _costeado(), habilitado=False))
        salida = oferta.enviar("RFQ-1", usuario="pm@x")
        self.assertFalse(salida["enviado"])
        self.assertFalse(salida["envio_habilitado"])
        import app.email.outbound as outbound
        outbound.enviar.assert_not_called()
        # La constancia se deja igual, y dice que NO salió.
        import app.rfq.repository as repository
        repository.anotar_oferta.assert_called_once()
        oferta_guardada = repository.anotar_oferta.call_args.args[1]
        self.assertFalse(oferta_guardada["enviada"])
        self.assertIn("GENERADA", repository.anotar_oferta.call_args.kwargs["nota"])

    def test_el_correo_lleva_el_pdf_y_va_al_remitente(self):
        self._con(self._parches(_rfq(), _costeado()))
        import app.email.outbound as outbound
        salida = oferta.enviar("RFQ-1", usuario="pm@x", opciones={"lead_time": "4 weeks"})
        self.assertTrue(salida["enviado"])
        contenido = outbound.enviar.call_args.args[0]
        self.assertEqual(contenido["destinatario"], "buyer@cliente.com")
        self.assertTrue(contenido["adjuntos"][0].endswith("RFQ-1.pdf"))
        self.assertIn("4 weeks", contenido["cuerpo_texto"])

    def test_la_nota_del_pm_va_en_el_correo_y_en_las_notas(self):
        self._con(self._parches(_rfq(), _costeado()))
        import app.email.outbound as outbound
        import app.rfq.repository as repository
        oferta.enviar("RFQ-1", usuario="pm@x",
                      opciones={"nota_correo": "Prices assume annual release.\nTooling included."})
        texto = outbound.enviar.call_args.args[0]["cuerpo_texto"]
        self.assertIn("Additional notes:", texto)
        self.assertIn("Prices assume annual release.", texto)
        self.assertIn("Tooling included.", texto)
        self.assertLess(texto.index("Offer Validity"), texto.index("Additional notes:"))
        self.assertLess(texto.index("Additional notes:"), texto.index("Do not hesitate"))
        nota = repository.anotar_oferta.call_args.kwargs["nota"]
        self.assertIn("Prices assume annual release.", nota)
        self.assertEqual(repository.anotar_oferta.call_args.args[1]["nota_correo"],
                         "Prices assume annual release.\nTooling included.")

    def test_sin_nota_el_correo_de_oferta_es_el_de_siempre(self):
        self._con(self._parches(_rfq(), _costeado()))
        import app.email.outbound as outbound
        oferta.enviar("RFQ-1", usuario="pm@x", opciones={"nota_correo": "   "})
        self.assertNotIn("Additional notes", outbound.enviar.call_args.args[0]["cuerpo_texto"])


if __name__ == "__main__":
    unittest.main()
