"""Reconocer que un correo es respuesta de un RFQ que ya existe.

Sin esto, la conversación no avanza: el comprador contesta con el dato que le
faltaba, el sistema no reconoce el hilo, lo trata como un RFQ nuevo —sin plano
y sin cantidades— y le vuelve a pedir lo mismo. Es el bucle que se veía en las
pruebas.

El caso que más duele es el normal: el comprador le da a "Responder" a NUESTRO
correo. La cabecera que encadena los mensajes apunta entonces a un correo que
el sistema mandó y nunca leyó, así que por ahí no hay hilo que seguir.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

import app.email.templates as templates
import app.rfq.detector as detector
import app.rfq.thread_validator as hilo


class TestEtiquetaDelAsunto(unittest.TestCase):
    """La etiqueta [RFQ ...] es lo que viaja de ida y vuelta."""

    def test_el_correo_al_cliente_la_lleva(self):
        correo = templates.construir_correo("datos_faltantes", {
            "destinatario": "ana.ramirez@cgr-international.com",
            "asunto_original": "test rfq",
            "rfq_id": "INT-AABD575F",
            "nombre_comprador": "Ana",
            "campos_faltantes": ["material"],
        })
        self.assertEqual(correo["asunto"], "test rfq [RFQ INT-AABD575F]")

    def test_no_se_repite_en_la_segunda_vuelta(self):
        self.assertEqual(
            templates.asunto_con_rfq("test rfq [RFQ INT-1A2B]", "INT-1A2B"),
            "test rfq [RFQ INT-1A2B]")

    def test_el_identificador_se_lee_entero_aunque_acabe_en_letra(self):
        """Antes se cortaba en el último dígito y no encontraba nada."""
        self.assertEqual(
            detector.extraer_id_rfq("RE: test rfq [RFQ INT-AABD575F]"),
            "INT-AABD575F")

    def test_una_palabra_suelta_no_es_un_identificador(self):
        self.assertIsNone(detector.extraer_id_rfq("Re: your RFQ request"))


class TestAsuntoBase(unittest.TestCase):

    def test_quita_prefijos_y_etiqueta(self):
        self.assertEqual(hilo.asunto_base("RE: RV: test rfq [RFQ INT-1A2B]"),
                         "test rfq")

    def test_el_mismo_asunto_se_reconoce_venga_como_venga(self):
        self.assertEqual(hilo.asunto_base("Fwd:  Test   RFQ "),
                         hilo.asunto_base("test rfq"))


class TestPorRemitenteYAsunto(unittest.TestCase):
    """La red de seguridad: mismo remitente, mismo asunto, mismo RFQ."""

    def _con_filas(self, filas, existe_id=0):
        cursor = mock.MagicMock()
        cursor.fetchall.return_value = filas
        # Lo que contesta la regla 3 (¿existe ese id en el historial?).
        cursor.fetchone.return_value = (existe_id,)
        conexion = mock.MagicMock()
        conexion.cursor.return_value.__enter__.return_value = cursor
        gestor = mock.MagicMock()
        gestor.__enter__.return_value = conexion
        return mock.patch.object(hilo.duplicates, "conexion_bd", return_value=gestor)

    def test_reconoce_la_respuesta_por_la_etiqueta_del_asunto(self):
        """Lo normal cuando el comprador contesta a nuestro correo."""
        correo = {"remitente": "ana.ramirez@cgr-international.com",
                  "asunto": "RE: test rfq [RFQ INT-AABD575F]",
                  "in_reply_to": "<nuestro-correo@cgr>", "references": ""}
        with self._con_filas([], existe_id=1), \
             mock.patch.object(hilo, "buscar_rfq_por_message_id", return_value=None):
            self.assertEqual(hilo.validar_respuesta(correo), "INT-AABD575F")

    def test_reconoce_la_respuesta_aunque_borren_la_etiqueta(self):
        """Y si el comprador la quita, queda el par remitente + asunto."""
        correo = {"remitente": "ana.ramirez@cgr-international.com",
                  "asunto": "RE: test rfq",
                  "in_reply_to": "<nuestro-correo@cgr>", "references": ""}
        with self._con_filas([("INT-AABD575F", "test rfq")]), \
             mock.patch.object(hilo, "buscar_rfq_por_message_id", return_value=None):
            self.assertEqual(hilo.validar_respuesta(correo), "INT-AABD575F")

    def test_otro_comprador_con_el_mismo_asunto_no_se_mezcla(self):
        correo = {"remitente": "otro@neogen.com", "asunto": "RE: test rfq",
                  "in_reply_to": "", "references": ""}
        with self._con_filas([]), \
             mock.patch.object(hilo, "buscar_rfq_por_message_id", return_value=None):
            self.assertIsNone(hilo.validar_respuesta(correo))

    def test_sin_asunto_no_adivina(self):
        correo = {"remitente": "ana@cgr.com", "asunto": "", "in_reply_to": "",
                  "references": ""}
        with mock.patch.object(hilo, "buscar_rfq_por_message_id", return_value=None):
            self.assertIsNone(hilo.validar_respuesta(correo))
