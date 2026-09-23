# -*- coding: utf-8 -*-
"""Un correo sin cuenta emisora se encola; no se pierde.

Por qué existe
--------------
Render no tiene buzón: el de ventas se abre por el Outlook de una computadora
concreta. Eso ya estaba resuelto para la OFERTA, que se encola en
``correos_salida`` y la aplicación de escritorio despacha en su ciclo.

La declinación, la petición de datos faltantes y los recordatorios no. Llamaban
a ``outbound.enviar`` directamente, que en Render levanta ``SinCuentaEmisora``;
quien llamaba se lo tragaba, anotaba un error, y el correo no salía ni quedaba
guardado en ninguna parte.

Un RFQ declinado cuyo comprador nunca se entera es PEOR que uno sin declinar,
porque en la pantalla pone Declined y nadie vuelve a mirarlo.

Encolar en vez de fallar convierte «se perdió» en «está esperando», y lo manda
la misma computadora que ya manda las ofertas.
"""

import pytest

import app.email.outbound as outbound


@pytest.fixture
def sin_cuenta(monkeypatch):
    monkeypatch.setattr(outbound, "diagnostico_envio",
                        lambda: {"modo": "ninguno", "puede": False,
                                 "faltan": ["cuenta emisora"],
                                 "nota": "este proceso no manda"})


@pytest.fixture
def bandeja(monkeypatch):
    """La bandeja, sustituida por una lista.

    Se parchea la FUNCIÓN del módulo de verdad, no la entrada de
    ``sys.modules``. Motivo: ``import app.email.bandeja_salida as bandeja``
    resuelve primero el atributo del paquete ``app.email``, y en cuanto otra
    prueba importa el módulo ese atributo existe y el parche de ``sys.modules``
    se queda sin efecto. Suelta pasaba; dentro de la suite no, y entonces la
    prueba intentaba encolar en Neon de verdad.
    """
    encolados = []
    import app.email.bandeja_salida as real

    def encolar(contenido, rfq_id=None, clase="oferta", por=None):
        encolados.append({"contenido": contenido, "rfq_id": rfq_id,
                          "clase": clase, "por": por})
        return len(encolados)

    monkeypatch.setattr(real, "encolar", encolar)
    return encolados


CORREO = {"destinatario": "cliente@ejemplo.com", "asunto": "RFQ 1060-022",
          "cuerpo_texto": "...", "adjuntos": []}


class TestSinCuentaEmisora:

    def test_se_encola_en_vez_de_reventar(self, sin_cuenta, bandeja):
        assert outbound.enviar(CORREO) is True
        assert len(bandeja) == 1

    def test_devuelve_true_porque_el_correo_va_a_salir(self, sin_cuenta, bandeja):
        # El que llama necesita distinguir "esto tarda" de "esto se perdió".
        # False haría que la pantalla dijera que no se avisó al cliente cuando
        # sí se le va a avisar.
        assert outbound.enviar(CORREO, rfq_id="INT-097CBB6A",
                               clase="declinacion") is True

    def test_viaja_de_qué_rfq_es_y_de_qué_clase(self, sin_cuenta, bandeja):
        outbound.enviar(CORREO, rfq_id="INT-097CBB6A", clase="declinacion")
        assert bandeja[0]["rfq_id"] == "INT-097CBB6A"
        assert bandeja[0]["clase"] == "declinacion"

    def test_por_defecto_es_un_aviso_no_una_oferta(self, sin_cuenta, bandeja):
        # Si entrara como "oferta", al despacharse marcaría el RFQ como
        # ofertado y el embudo lo contaría en "Quote sent". Una declinación no
        # es una oferta.
        outbound.enviar(CORREO)
        assert bandeja[0]["clase"] == "aviso"

    def test_si_tampoco_hay_bandeja_entonces_sí_falla(self, sin_cuenta, monkeypatch):
        # Aquí el correo no queda en ningún sitio: callarlo sería perderlo en
        # silencio.
        import app.email.bandeja_salida as real

        def revienta(*a, **k):
            raise RuntimeError("la base no contesta")

        monkeypatch.setattr(real, "encolar", revienta)
        with pytest.raises(outbound.SinCuentaEmisora):
            outbound.enviar(CORREO)


class TestConCuentaEmisoraNoCambiaNada:

    def test_se_manda_por_el_canal_de_siempre(self, monkeypatch, bandeja):
        monkeypatch.setattr(outbound, "diagnostico_envio",
                            lambda: {"modo": "outlook", "puede": True,
                                     "faltan": [], "nota": ""})
        monkeypatch.setattr(outbound, "_adjuntos", lambda c: [])

        import app.core.config as config
        monkeypatch.setattr(config.settings, "MAIL_MODE", "outlook")

        mandados = []

        class Proveedor:
            def send_email(self, **kw):
                mandados.append(kw)
                return True

        import app.email.factory as factory
        monkeypatch.setattr(factory.EmailProviderFactory, "get_provider",
                            staticmethod(lambda: Proveedor()))

        assert outbound.enviar(CORREO) is True
        assert len(mandados) == 1
        assert not bandeja          # no se encoló: salió de verdad


class TestElMachoteDeDeclinación:
    """El texto que recibe el cliente, contra el machote de RODEA."""

    def _correo(self):
        from app.email import templates
        return templates.construir_correo("declinar_rfq", {
            "destinatario": "comprador@ejemplo.com",
            "asunto_original": "RFQ 1060-022",
            "nombre_comprador": "Ana", "rfq_id": "INT-097CBB6A"})

    @pytest.mark.parametrize("frase", [
        "Thank you for reaching out and sharing your request with us.",
        "we regret to inform you that we are unable to quote this project",
        "fall outside our current manufacturing capabilities",
        "please let us know if we can assist with future projects",
    ])
    def test_el_cuerpo_es_el_del_machote(self, frase):
        assert frase in self._correo()["cuerpo_texto"]

    @pytest.mark.parametrize("linea", [
        "Best regards,",
        "INDUSTRIAL SPRING CORPORATION",
        "1801 Bedford Ave",
        "North Kansas City, MO 64116",
        "www.cgr-international.com",
        "www.isckc.com",
    ])
    def test_la_firma_entera(self, linea):
        assert linea in self._correo()["cuerpo_texto"]

    def test_el_asunto_conserva_el_del_cliente_y_añade_el_rfq(self):
        # Contestar en el mismo hilo es lo que hace que el comprador lo
        # reconozca; el RFQ entre corchetes es para nosotros.
        asunto = self._correo()["asunto"]
        assert "RFQ 1060-022" in asunto and "INT-097CBB6A" in asunto

    def test_no_lleva_adjuntos(self):
        assert self._correo()["adjuntos"] == []
