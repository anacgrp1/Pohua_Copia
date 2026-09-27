"""COT-36 — Tests de la orquestación del RFQ (cableado de los 8 módulos).

Se verifica que ``flow`` llame a cada módulo en el orden correcto y que
cada bifurcación termine donde debe. Las dependencias externas (visión, BD,
SMTP/Graph) se sustituyen por dobles: estos tests no tocan red ni PostgreSQL.
"""
import os
import unittest
from unittest import mock

# config valida credenciales al importarse; valores dummy ANTES del import.
os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

import app.core.config as config
import app.rfq.flow as flow

PDF ={"nombre": "plano.pdf", "contenido": b"%PDF-fake"}

# Resorte que pasa las directrices provisionales de reglas/factibilidad.json
# (COT-74): sirve para ejercitar la rama de alta de punta a punta, motor real
# incluido. Si alguien cambia esos rangos y este resorte deja de ser factible,
# los tests de la rama "alta" lo avisan.
RESORTE_FACTIBLE = {
    "tipo_resorte": "compresion",
    "material": "Acero inoxidable AISI 302",
    "num_parte": "RS-9",
    "cantidad": 5000,
    "diametro_alambre_mm": 1.2,
    "diametro_exterior_mm": 12.0,
    "longitud_libre_mm": 40.0,
    "confianza": 0.95,
}

# Mismo resorte, con un alambre que la planta no puede enrollar.
RESORTE_NO_FACTIBLE = dict(RESORTE_FACTIBLE, diametro_alambre_mm=25.0)


def correo_base(**extra):
    """Correo de RFQ nuevo con un plano adjunto."""
    datos = {
        "message_id": "<abc@cliente.com>",
        "remitente": "roberto.perez@neogen.com",
        "asunto": "RFQ 4500 - resorte de compresión",
        "cuerpo": "Please quote the attached spring drawing.",
        "adjuntos": [dict(PDF)],
    }
    datos.update(extra)
    return datos


class TestLimpiarCuerpo(unittest.TestCase):
    """Etapa 1 — html_cleaner (COT-53)."""

    def test_cuerpo_html_se_limpia(self):
        correo = correo_base(cuerpo="<p>Hola <b>mundo</b></p><script>x()</script>")
        texto = flow.limpiar_cuerpo(correo)
        self.assertIn("Hola", texto)
        self.assertNotIn("<p>", texto)
        self.assertNotIn("x()", texto)

    def test_texto_plano_pasa_intacto(self):
        correo = correo_base(cuerpo="Necesito cotización de 5000 piezas")
        self.assertEqual(
            flow.limpiar_cuerpo(correo),
            "Necesito cotización de 5000 piezas",
        )

    def test_fallo_del_limpiador_devuelve_el_original(self):
        crudo = "<p>algo</p>"
        with mock.patch("app.shared.html_cleaner.limpiar_html", side_effect=RuntimeError("boom")):
            self.assertEqual(flow.limpiar_cuerpo(correo_base(cuerpo=crudo)), crudo)


class TestPrepararDatosCorreo(unittest.TestCase):
    """Etapa 2 — mapper (COT-55)."""

    def test_cliente_conocido_llena_customer_y_cliente_id(self):
        cliente = {"cliente_id": "C-001", "razon_social": "Neogen SA"}
        with mock.patch("app.clients.mapper.mapear_cliente", return_value=cliente):
            datos = flow.preparar_datos_correo(correo_base(), "RFQ-1")
        self.assertEqual(datos["customer"], "Neogen SA")
        self.assertEqual(datos["cliente_id"], "C-001")
        self.assertTrue(datos["tiene_adjunto"])

    def test_dominio_sin_alta_cae_al_dominio_como_customer(self):
        with mock.patch("app.clients.mapper.mapear_cliente", return_value=None):
            datos = flow.preparar_datos_correo(correo_base(), "RFQ-1")
        self.assertEqual(datos["customer"], "neogen.com")
        self.assertIsNone(datos["cliente_id"])

    def test_fallo_de_bd_no_propaga(self):
        with mock.patch("app.clients.mapper.mapear_cliente", side_effect=Exception("sin BD")):
            datos = flow.preparar_datos_correo(correo_base(), "RFQ-1")
        self.assertIsNone(datos["customer"])
        self.assertIsNone(datos["cliente_id"])


class TestFusionar(unittest.TestCase):
    """Etapa 4 — fusión correo + dibujo (regla de COT-36)."""

    def test_el_dibujo_rellena_lo_que_el_correo_no_trae(self):
        datos = {"material": None, "volumen": None, "part_number": None}
        resorte = {"material": "SAE 1070", "cantidad": 5000, "num_parte": "RS-9"}
        fusionado = flow.fusionar(datos, [resorte])
        self.assertEqual(fusionado["material"], "SAE 1070")
        self.assertEqual(fusionado["volumen"], 5000)
        self.assertEqual(fusionado["part_number"], "RS-9")

    def test_el_correo_manda_sobre_el_dibujo(self):
        datos = {"material": "Inox 302", "volumen": 100, "part_number": "DEL-CORREO"}
        resorte = {"material": "SAE 1070", "cantidad": 5000, "num_parte": "RS-9"}
        fusionado = flow.fusionar(datos, [resorte])
        self.assertEqual(fusionado["material"], "Inox 302")
        self.assertEqual(fusionado["volumen"], 100)
        self.assertEqual(fusionado["part_number"], "DEL-CORREO")

    def test_sin_dibujo_no_altera_los_datos(self):
        datos = {"material": None}
        self.assertEqual(flow.fusionar(datos, []), datos)


class TestGateTemprano(unittest.TestCase):
    """Etapa 2 — la optimización de dos etapas definida en COT-36."""

    def test_sin_extraccion_del_correo_el_gate_omite_volumen(self):
        # Si el modelo no entregó nada, exigir volumen rechazaría todo.
        campos = flow.campos_gate_temprano({})
        self.assertCountEqual(campos, ["tiene_adjunto", "customer"])

    def test_si_el_modelo_corrio_y_no_hallo_cantidades_el_volumen_se_exige(self):
        # «Hola, test»: el modelo corrió y no había volúmenes. Se piden.
        campos = flow.campos_gate_temprano({"campos": {}, "en_revision": {}})
        self.assertIn("volumen", campos)

    def test_con_extraccion_el_gate_usa_campos_solo_correo_completo(self):
        import app.shared.field_validator as field_validator
        campos = flow.campos_gate_temprano({"volumen": 5000})
        self.assertEqual(campos, field_validator.CAMPOS_SOLO_CORREO)
        self.assertIn("volumen", campos)

    def test_cuerpo_vacio_no_llama_al_modelo(self):
        with mock.patch("app.extraction.email_extractor.extraer") as extraer:
            self.assertEqual(flow.extraer_datos_correo({"cuerpo": "  "}), {})
        extraer.assert_not_called()

    def test_fallo_del_modelo_no_rompe_el_rfq(self):
        # Sin API key, sin red o con JSON irrecuperable, el flujo sigue con el
        # dibujo como única fuente, igual que antes de COT-61.
        with mock.patch("app.extraction.email_extractor.extraer",
                        side_effect=RuntimeError("sin API key")):
            self.assertEqual(
                flow.extraer_datos_correo({"cuerpo": "5000 pzs"}), {})


class TestRespuestaDatosFaltantes(unittest.TestCase):
    """Etapa 7 — templates (COT-59) + senders (COT-57/58)."""

    def setUp(self):
        self.datos = {
            "remitente": "roberto.perez@neogen.com",
            "asunto": "RFQ 4500",
        }

    def test_con_envio_apagado_construye_pero_no_despacha(self):
        with mock.patch.object(flow, "_envio_habilitado", return_value=False), \
             mock.patch.object(flow, "_despachar") as despachar:
            enviado = flow.responder_datos_faltantes(
                self.datos, ["volumen"], "RFQ-1")
        self.assertFalse(enviado)
        despachar.assert_not_called()

    def test_con_envio_encendido_despacha_el_dict_de_construir_correo(self):
        with mock.patch.object(flow, "_envio_habilitado", return_value=True), \
             mock.patch.object(flow, "_despachar", return_value=True) as despachar:
            enviado = flow.responder_datos_faltantes(
                self.datos, ["volumen", "material"], "RFQ-1")

        self.assertTrue(enviado)
        contenido = despachar.call_args[0][0]
        self.assertEqual(contenido["destinatario"], "roberto.perez@neogen.com")
        # El asunto lleva la etiqueta del RFQ: es lo que deja reconocer la
        # respuesta del comprador como parte de esta misma conversación.
        self.assertEqual(contenido["asunto"], "RFQ 4500 [RFQ RFQ-1]")
        self.assertIn("Roberto Perez", contenido["cuerpo_texto"])
        # Lo que falta se dice como en el machote, no con el nombre del campo:
        # "volumen" no significa nada para quien recibe el correo.
        self.assertIn("Volume / EAU", contenido["cuerpo_texto"])
        self.assertIn("Material Specification", contenido["cuerpo_texto"])

    def test_fallo_del_envio_no_propaga(self):
        with mock.patch.object(flow, "_envio_habilitado", return_value=True), \
             mock.patch.object(flow, "_despachar", side_effect=Exception("SMTP")):
            self.assertFalse(
                flow.responder_datos_faltantes(self.datos, ["volumen"], "RFQ-1"))

    def test_sin_remitente_no_intenta_responder(self):
        with mock.patch.object(flow, "_despachar") as despachar:
            self.assertFalse(
                flow.responder_datos_faltantes({}, ["volumen"], "RFQ-1"))
        despachar.assert_not_called()


class TestOrquestacion(unittest.TestCase):
    """avanzar_a_parsing — la cadena completa y sus tres desenlaces."""

    def setUp(self):
        parches = [
            mock.patch("app.rfq.thread_validator.registrar_en_historial"),
            mock.patch.object(flow, "_envio_habilitado", return_value=False),
            # El veredicto se escribe en PostgreSQL; aquí sólo interesa que la
            # etapa lo intente. Su contenido se prueba en TestFactibilidad.
            mock.patch.object(flow, "registrar_veredicto"),
            # Los avisos al PM también van a la base (y al teléfono): fuera.
            mock.patch.object(flow, "_avisar", return_value=True),
            # Y el alta del RFQ y sus planos también. Sin esto, la batería
            # dejaba un «RFQ-1» de neogen.com en la base a la que apuntara
            # el .env de quien la corría.
            mock.patch.object(flow, "persistir", return_value=None),
            # Lo que mira el hilo para saber si la respuesta es del mismo
            # resorte, y dónde apunta el resorte leído: todo va a la base.
            mock.patch("app.rfq.repository.datos_anteriores", return_value={}),
            mock.patch("app.persistence.blueprint_store.listar_de_base", return_value=[]),
            mock.patch("app.persistence.spring_repository.guardar"),
            mock.patch("app.rfq.thread_validator.reasociar_en_historial"),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)

    def test_sin_adjunto_se_detiene_en_el_gate_temprano(self):
        correo = correo_base(adjuntos=[])
        with mock.patch("app.clients.mapper.mapear_cliente", return_value=None), \
             mock.patch.object(flow, "procesar_dibujos") as vision, \
             mock.patch.object(flow, "responder_datos_faltantes") as responder:
            resultado = flow.avanzar_a_parsing(
                correo, flow.RFQ_NUEVO, "RFQ-1")

        self.assertEqual(resultado["etapa"], "gate_temprano")
        self.assertIn("tiene_adjunto", resultado["campos_faltantes"])
        vision.assert_not_called()          # no se gasta la llamada de visión
        responder.assert_called_once()

    def test_con_cot61_activo_el_gate_frena_por_volumen_sin_gastar_vision(self):
        # Simula COT-61 entregando datos pero sin volumen: el gate completo
        # debe rechazar ANTES de llamar al modelo de visión.
        with mock.patch("app.clients.mapper.mapear_cliente", return_value=None), \
             mock.patch.object(flow, "extraer_datos_correo",
                               return_value={"campos": {"part_number": "RS-9"}}), \
             mock.patch.object(flow, "procesar_dibujos") as vision, \
             mock.patch.object(flow, "responder_datos_faltantes"):
            resultado = flow.avanzar_a_parsing(
                correo_base(), flow.RFQ_NUEVO, "RFQ-1")

        self.assertEqual(resultado["etapa"], "gate_temprano")
        self.assertEqual(resultado["campos_faltantes"], ["volumen"])
        vision.assert_not_called()

    def test_una_respuesta_sin_cantidades_espera_al_cliente(self):
        """Regla de ISC: sin volumen en ESTE correo no se cotiza.

        El hilo ya tenía cantidades (el correo anterior las trajo), pero la
        respuesta no. Antes se heredaban y se costeaba con las viejas; ahora
        el RFQ se da de alta como incompleto y se le piden por correo, sin
        gastar la lectura del plano.
        """
        previos = {"volumen": 50000, "escalones_cantidad": [10000, 22000, 50000],
                   "part_number": "1060-022", "tiene_adjunto": True,
                   "customer": "neogen.com"}
        with mock.patch("app.clients.mapper.mapear_cliente", return_value=None), \
             mock.patch("app.rfq.repository.datos_anteriores", return_value=previos), \
             mock.patch.object(flow, "extraer_datos_correo",
                               return_value={"campos": {"material": "Music wire"}}), \
             mock.patch.object(flow, "procesar_dibujos") as vision, \
             mock.patch.object(flow, "persistir", return_value=None) as persistir, \
             mock.patch.object(flow, "responder_datos_faltantes") as responder:
            resultado = flow.avanzar_a_parsing(
                correo_base(asunto="RE: RFQ 4500 [RFQ RFQ-1]"), flow.RESPUESTA_RFQ, "RFQ-1")

        self.assertEqual(resultado["etapa"], "gate_temprano")
        self.assertEqual(resultado["campos_faltantes"], ["volumen"])
        vision.assert_not_called()
        # A «esperando al cliente», y se le escribe pidiendo las cantidades.
        self.assertEqual(persistir.call_args.kwargs["estado"], flow._estado_incompleto())
        responder.assert_called_once()
        self.assertEqual(responder.call_args[0][1], ["volumen"])

    def test_los_datos_del_correo_entran_al_dict_del_rfq(self):
        with mock.patch("app.clients.mapper.mapear_cliente", return_value=None), \
             mock.patch.object(flow, "extraer_datos_correo",
                               return_value={"campos": {"volumen": 5000,
                                                        "material": "Inox 302"}}), \
             mock.patch.object(flow, "procesar_dibujos", return_value=[]), \
             mock.patch.object(flow, "responder_datos_faltantes") as responder:
            resultado = flow.avanzar_a_parsing(
                correo_base(), flow.RFQ_NUEVO, "RFQ-1")

        # Pasó el gate completo y sólo quedó faltando lo que nadie extrae aún.
        self.assertEqual(resultado["etapa"], "datos_faltantes")
        self.assertEqual(resultado["campos_faltantes"], ["part_number"])

        datos_finales = responder.call_args[0][0]
        self.assertEqual(datos_finales["volumen"], 5000)
        self.assertEqual(datos_finales["material"], "Inox 302")

    def test_confianza_baja_manda_a_revision_del_pm_y_da_de_alta(self):
        # El dato existe pero no es de fiar: se registra marcado, y NO se le
        # pide nada al comprador (podria estar mandandolo ya).
        extraccion = {
            "campos": {"volumen": 5000},
            "en_revision": {"material": {"valor": "acero?", "confianza": 0.4}},
            "requiere_revision": True,
        }
        resorte = {"material": "SAE 1070", "cantidad": 5000, "num_parte": "RS-9"}
        with mock.patch("app.clients.mapper.mapear_cliente", return_value=None), \
             mock.patch.object(flow, "extraer_datos_correo", return_value=extraccion), \
             mock.patch.object(flow, "procesar_dibujos", return_value=[resorte]), \
             mock.patch.object(flow, "persistir", return_value={"version": 1}) as persistir, \
             mock.patch.object(flow, "responder_datos_faltantes") as responder, \
             mock.patch.object(flow, "notificar_revision_pm") as notificar:
            resultado = flow.avanzar_a_parsing(
                correo_base(), flow.RFQ_NUEVO, "RFQ-1")

        self.assertEqual(resultado["etapa"], "requiere_revision")
        self.assertIn("material", resultado["en_revision"])
        responder.assert_not_called()                   # no se molesta al cliente
        notificar.assert_called_once()                  # lo ve el PM
        self.assertEqual(persistir.call_args.kwargs["estado"], "RequiresReview")

    def test_datos_faltantes_ganan_sobre_la_revision(self):
        # Regla de ISC (2026-09-26): si falta algo, sólo sale el correo al
        # comprador y el RFQ espera al cliente; no se abre la revisión del PM
        # hasta que esté completo. La duda de confianza se queda apuntada.
        extraccion = {
            "campos": {"volumen": 5000, "material": "Inox 302"},
            "en_revision": {"customer": {"valor": "Neo?", "confianza": 0.3}},
            "requiere_revision": True,
        }
        with mock.patch("app.clients.mapper.mapear_cliente", return_value=None), \
             mock.patch.object(flow, "extraer_datos_correo", return_value=extraccion), \
             mock.patch.object(flow, "procesar_dibujos", return_value=[]), \
             mock.patch.object(flow, "persistir", return_value={}) as persistir, \
             mock.patch.object(flow, "responder_datos_faltantes") as responder, \
             mock.patch.object(flow, "notificar_revision_pm") as notificar:
            resultado = flow.avanzar_a_parsing(
                correo_base(), flow.RFQ_NUEVO, "RFQ-1")

        self.assertEqual(resultado["etapa"], "datos_faltantes")
        self.assertIn("part_number", resultado["campos_faltantes"])
        self.assertEqual(persistir.call_args.kwargs["estado"], "Incomplete")
        responder.assert_called_once()                  # se le piden al comprador
        pedidos = responder.call_args[0][1]
        self.assertNotIn("customer", pedidos)           # lo dudoso no se pide
        notificar.assert_not_called()                   # el PM no lo ve todavía
        self.assertIn("customer", persistir.call_args[0][0]["en_revision"])

    def test_incompleto_tras_el_dibujo_pide_los_datos_y_lo_da_de_alta_incompleto(self):
        # COT-76: un RFQ al que le faltan datos tras el plano ya no se pierde:
        # se da de alta en Incomplete (con qué faltó) y se le pide al comprador.
        resorte = {"material": "SAE 1070", "cantidad": None, "num_parte": None}
        with mock.patch("app.clients.mapper.mapear_cliente", return_value=None), \
             mock.patch.object(flow, "procesar_dibujos", return_value=[resorte]), \
             mock.patch.object(flow, "persistir") as persistir, \
             mock.patch.object(flow, "responder_datos_faltantes") as responder:
            resultado = flow.avanzar_a_parsing(
                correo_base(), flow.RFQ_NUEVO, "RFQ-1")

        self.assertEqual(resultado["etapa"], "datos_faltantes")
        self.assertFalse(resultado["es_valido"])
        self.assertCountEqual(
            resultado["campos_faltantes"], ["part_number", "volumen"])
        persistir.assert_called_once()
        self.assertEqual(persistir.call_args.kwargs.get("estado"), "Incomplete")
        responder.assert_called_once()

    def test_rfq_completo_se_da_de_alta_y_no_responde(self):
        resorte = dict(RESORTE_FACTIBLE)
        with mock.patch("app.clients.mapper.mapear_cliente", return_value=None), \
             mock.patch.object(flow, "procesar_dibujos", return_value=[resorte]), \
             mock.patch.object(flow, "persistir", return_value={"version": 1}) as persistir, \
             mock.patch.object(flow, "responder_datos_faltantes") as responder:
            resultado = flow.avanzar_a_parsing(
                correo_base(), flow.RFQ_NUEVO, "RFQ-1")

        self.assertEqual(resultado["etapa"], "alta")
        self.assertTrue(resultado["es_valido"])
        self.assertEqual(resultado["registro"], {"version": 1})
        responder.assert_not_called()
        persistir.assert_called_once()
        self.assertFalse(persistir.call_args.kwargs["es_seguimiento"])

    def test_respuesta_de_hilo_se_marca_como_seguimiento(self):
        resorte = dict(RESORTE_FACTIBLE)
        with mock.patch("app.clients.mapper.mapear_cliente", return_value=None), \
             mock.patch.object(flow, "procesar_dibujos", return_value=[resorte]), \
             mock.patch.object(flow, "persistir", return_value={}) as persistir:
            flow.avanzar_a_parsing(
                correo_base(), flow.RESPUESTA_RFQ, "RFQ-1")

        self.assertTrue(persistir.call_args.kwargs["es_seguimiento"])


class TestFactibilidad(unittest.TestCase):
    """Etapa 5c — engine (COT-74/75) dentro del flujo."""

    def setUp(self):
        parches = [
            mock.patch("app.rfq.thread_validator.registrar_en_historial"),
            mock.patch.object(flow, "_envio_habilitado", return_value=False),
            mock.patch.object(flow, "_avisar", return_value=True),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)

    def _correr(self, resorte, **extra):
        parches = {
            "procesar_dibujos": mock.patch.object(
                flow, "procesar_dibujos", return_value=[resorte]),
            "persistir": mock.patch.object(
                flow, "persistir", return_value={"id": 7, "version": 1}),
            "registrar_veredicto": mock.patch.object(flow, "registrar_veredicto"),
            "notificar_factibilidad_pm": mock.patch.object(
                flow, "notificar_factibilidad_pm"),
            "responder_datos_faltantes": mock.patch.object(
                flow, "responder_datos_faltantes"),
        }
        parches.update(extra)
        with mock.patch("app.clients.mapper.mapear_cliente", return_value=None):
            dobles = {nombre: parche.start() for nombre, parche in parches.items()}
            try:
                resultado = flow.avanzar_a_parsing(
                    correo_base(), flow.RFQ_NUEVO, "RFQ-1")
            finally:
                for parche in parches.values():
                    parche.stop()
        return resultado, dobles

    def test_resorte_factible_se_da_de_alta(self):
        resultado, dobles = self._correr(dict(RESORTE_FACTIBLE))
        self.assertEqual(resultado["etapa"], "alta")
        self.assertEqual(resultado["factibilidad"]["veredicto"], "feasible")
        self.assertEqual(resultado["factibilidad"]["motivos"], [])
        dobles["notificar_factibilidad_pm"].assert_not_called()
        self.assertIsNone(dobles["persistir"].call_args.kwargs["estado"])

    def test_resorte_no_factible_va_al_plant_manager(self):
        resultado, dobles = self._correr(dict(RESORTE_NO_FACTIBLE))
        self.assertEqual(resultado["etapa"], "revision_factibilidad")
        self.assertEqual(resultado["factibilidad"]["veredicto"], "requires review")
        self.assertEqual(
            dobles["persistir"].call_args.kwargs["estado"], "RequiresReview")
        dobles["notificar_factibilidad_pm"].assert_called_once()

    def test_no_factible_no_le_escribe_al_cliente(self):
        # El correo de declinación lo dispara el veredicto del PM, no el motor.
        _, dobles = self._correr(dict(RESORTE_NO_FACTIBLE))
        dobles["responder_datos_faltantes"].assert_not_called()

    def test_el_veredicto_se_registra_con_la_version_del_alta(self):
        _, dobles = self._correr(dict(RESORTE_NO_FACTIBLE))
        rfq_id, factibilidad, registro = dobles["registrar_veredicto"].call_args[0]
        self.assertEqual(rfq_id, "RFQ-1")
        self.assertEqual(factibilidad["veredicto"], "requires review")
        self.assertEqual(registro, {"id": 7, "version": 1})

    def test_fallo_del_motor_no_frena_el_alta(self):
        # Directrices ilegibles: el RFQ entra igual, sin veredicto.
        with mock.patch("app.feasibility.engine.evaluar_factibilidad",
                        side_effect=RuntimeError("reglas rotas")):
            resultado, dobles = self._correr(dict(RESORTE_NO_FACTIBLE))
        self.assertEqual(resultado["etapa"], "alta")
        self.assertIsNone(resultado["factibilidad"])
        dobles["notificar_factibilidad_pm"].assert_not_called()

    def test_fallo_al_guardar_el_veredicto_no_rompe_el_flujo(self):
        with mock.patch("app.rfq.repository.guardar_veredicto",
                        side_effect=Exception("sin BD")):
            resultado = flow.registrar_veredicto(
                "RFQ-1", {"veredicto": "requires review", "motivos": []},
                {"version": 1})
        self.assertIsNone(resultado)

    def test_sin_registro_no_intenta_guardar_el_veredicto(self):
        # Si el alta falló, no hay fila que marcar.
        with mock.patch("app.rfq.repository.guardar_veredicto") as guardar:
            flow.registrar_veredicto("RFQ-1", {"veredicto": "feasible"}, None)
        guardar.assert_not_called()

    def test_la_confianza_baja_no_dictamina_factibilidad(self):
        # Dictaminar sobre medidas dudosas daría motivos indefendibles.
        extraccion = {
            "campos": {"volumen": 5000},
            "en_revision": {"material": {"valor": "acero?", "confianza": 0.4}},
        }
        with mock.patch("app.clients.mapper.mapear_cliente", return_value=None), \
             mock.patch.object(flow, "extraer_datos_correo", return_value=extraccion), \
             mock.patch.object(flow, "procesar_dibujos",
                               return_value=[dict(RESORTE_NO_FACTIBLE)]), \
             mock.patch.object(flow, "persistir", return_value={"version": 1}), \
             mock.patch.object(flow, "notificar_revision_pm"), \
             mock.patch.object(flow, "dictaminar_factibilidad") as motor:
            resultado = flow.avanzar_a_parsing(
                correo_base(), flow.RFQ_NUEVO, "RFQ-1")

        self.assertEqual(resultado["etapa"], "requiere_revision")
        motor.assert_not_called()

    def test_datos_incompletos_no_llegan_al_motor(self):
        # Sin part_number no hay qué dictaminar: primero se piden los datos.
        resorte = {"material": "SAE 1070", "cantidad": None, "num_parte": None}
        with mock.patch("app.clients.mapper.mapear_cliente", return_value=None), \
             mock.patch.object(flow, "procesar_dibujos", return_value=[resorte]), \
             mock.patch.object(flow, "responder_datos_faltantes"), \
             mock.patch.object(flow, "dictaminar_factibilidad") as motor:
            resultado = flow.avanzar_a_parsing(
                correo_base(), flow.RFQ_NUEVO, "RFQ-1")

        self.assertEqual(resultado["etapa"], "datos_faltantes")
        motor.assert_not_called()


class TestPersistir(unittest.TestCase):
    """Etapa 6 — repository + blueprint_store (COT-56)."""

    def test_alta_y_planos_en_el_mismo_paso(self):
        datos = {"rfq_id": "RFQ-1"}
        with mock.patch("app.rfq.repository.guardar_rfq", return_value={"version": 1}) as alta, \
             mock.patch("app.persistence.blueprint_store.guardar_planos",
                        return_value=["planos/RFQ-1/plano.pdf"]):
            registro = flow.persistir(
                datos, correo_base(), "RFQ-1", es_seguimiento=False)

        alta.assert_called_once()
        self.assertEqual(registro["planos"], ["planos/RFQ-1/plano.pdf"])

    def test_fallo_de_bd_no_impide_guardar_los_planos(self):
        with mock.patch("app.rfq.repository.guardar_rfq", side_effect=Exception("sin BD")), \
             mock.patch("app.persistence.blueprint_store.guardar_planos",
                        return_value=["ruta"]) as planos:
            registro = flow.persistir(
                {}, correo_base(), "RFQ-1", es_seguimiento=False)

        self.assertIsNone(registro)
        planos.assert_called_once()


if __name__ == "__main__":
    unittest.main()


class TestEscaleraComoVolumen(unittest.TestCase):
    """Unas cantidades escalonadas SON el volumen; no un dato que falte.

    "The volumes are: 10000, 22000, 50000" es un RFQ de manual en resortes. El
    modelo las lee como `escalones_cantidad`, y antes el validador pedía
    además un `volumen` suelto: el sistema le escribía al comprador para
    pedirle lo que acababa de mandar.
    """

    def test_se_toma_el_escalon_mayor(self):
        campos = {"escalones_cantidad": [10000, 22000, 50000]}
        self.assertEqual(flow.volumen_de_escalones(campos), 50000)

    def test_si_ya_hay_volumen_no_se_toca(self):
        campos = {"volumen": 8000, "escalones_cantidad": [10000, 50000]}
        self.assertIsNone(flow.volumen_de_escalones(campos))

    def test_aguanta_la_escalera_escrita_a_mano(self):
        campos = {"escalones_cantidad": "10,000, 25000 y 50.000"}
        self.assertEqual(flow.volumen_de_escalones(campos), 50000)

    def test_sin_escalera_no_inventa_nada(self):
        self.assertIsNone(flow.volumen_de_escalones({"notas": "urge"}))
        self.assertIsNone(flow.volumen_de_escalones({}))

    def test_con_la_escalera_el_filtro_temprano_deja_pasar(self):
        """La prueba de verdad: ese correo ya no rebota al cliente."""
        campos = {"part_number": "1060-022",
                  "escalones_cantidad": [10000, 22000, 50000]}
        datos = {"tiene_adjunto": True, "customer": "neogen.com"}
        datos.update(campos)
        datos["volumen"] = flow.volumen_de_escalones(datos)

        veredicto = flow.validar(datos, flow.campos_gate_temprano(campos))
        self.assertTrue(veredicto["es_valido"], veredicto["campos_faltantes"])


class TestLaRespuestaHeredaElHilo(unittest.TestCase):
    """Un RFQ es una conversación: la respuesta no llega desnuda.

    El comprador mandó el plano y las cantidades el primer día; al contestar
    con el material, su cliente de correo no reenvía el adjunto. Sin memoria
    del hilo, esa respuesta se juzgaba sola —sin plano, sin volumen— y el
    sistema volvía a pedir lo que ya tenía. Era el bucle que dejaba la
    conversación parada.
    """

    PREVIOS = {
        "tiene_adjunto": True,
        "customer": "neogen.com",
        "part_number": "1060-022",
        "volumen": 50000,
        "escalones_cantidad": [10000, 22000, 50000],
        "asunto": "test rfq",          # de esto NO se hereda nada
        "cuerpo": "el correo viejo",
        "message_id": "<viejo@cliente.com>",
    }

    def test_hereda_lo_que_falta_y_nada_mas(self):
        datos = {"material": "music wire ASTM A228", "asunto": "RE: test rfq"}
        with mock.patch("app.rfq.repository.datos_anteriores",
                        return_value=self.PREVIOS):
            heredados = flow.heredar_del_hilo(datos, "COT-75")

        self.assertEqual(datos["part_number"], "1060-022")
        self.assertTrue(datos["tiene_adjunto"])
        # Las cantidades NO se heredan: cada petición trae las suyas.
        self.assertNotIn("volumen", datos)
        self.assertNotIn("escalones_cantidad", datos)
        # Lo de este correo se respeta, y lo que es de cada correo no viaja.
        self.assertEqual(datos["material"], "music wire ASTM A228")
        self.assertEqual(datos["asunto"], "RE: test rfq")
        self.assertNotIn("cuerpo", datos)
        self.assertNotIn("message_id", datos)
        self.assertIn("part_number", heredados)

    def test_lo_que_corrige_el_comprador_no_se_pisa(self):
        datos = {"part_number": "1060-023", "material": "SAE 1070"}
        with mock.patch("app.rfq.repository.datos_anteriores",
                        return_value=self.PREVIOS):
            flow.heredar_del_hilo(datos, "COT-75")
        self.assertEqual(datos["part_number"], "1060-023")

    def test_con_lo_heredado_la_respuesta_ya_completa_el_rfq(self):
        """Deja de pedir lo que ya le dieron… salvo las cantidades."""
        datos = {"material": "music wire ASTM A228", "volumen": 12000}
        with mock.patch("app.rfq.repository.datos_anteriores",
                        return_value=self.PREVIOS):
            flow.heredar_del_hilo(datos, "COT-75")

        self.assertTrue(flow.validar(datos)["es_valido"],
                        flow.validar(datos)["campos_faltantes"])

    def test_sin_cantidades_en_este_correo_se_piden_aunque_el_hilo_las_tuviera(self):
        """Regla de ISC: el volumen viene en el correo o no se cotiza.

        Con la herencia, una respuesta sin cantidades se costeaba con las del
        correo anterior. Ahora falta «volumen» y el RFQ va a esperar al
        cliente.
        """
        datos = {"material": "music wire ASTM A228"}
        with mock.patch("app.rfq.repository.datos_anteriores",
                        return_value=self.PREVIOS):
            flow.heredar_del_hilo(datos, "COT-75")
        self.assertIn("volumen", flow.validar(datos)["campos_faltantes"])

    def test_sin_rfq_previo_no_se_inventa_nada(self):
        datos = {"material": "SAE 1070"}
        with mock.patch("app.rfq.repository.datos_anteriores", return_value={}):
            self.assertEqual(flow.heredar_del_hilo(datos, "COT-99"), [])
        self.assertEqual(datos, {"material": "SAE 1070"})


class TestElMismoCompradorPideVariosResortes(unittest.TestCase):
    """Un comprador pide varios números de parte en correos seguidos.

    El hilo (mismo remitente, mismo asunto, o contestando al anterior) los
    tomaba todos por respuestas del primero, y el segundo resorte quedaba
    como una versión del primero con su plano y su número de parte
    heredados. Ahora, si el correo pide OTRO resorte, abre su propio RFQ.
    """

    PREVIOS = {"part_number": "1060-022", "tiene_adjunto": True,
               "customer": "neogen.com", "material": "Music wire"}

    def setUp(self):
        parches = [
            mock.patch("app.rfq.thread_validator.registrar_en_historial"),
            mock.patch.object(flow, "_envio_habilitado", return_value=False),
            mock.patch.object(flow, "_avisar", return_value=True),
            mock.patch.object(flow, "registrar_veredicto"),
            mock.patch("app.clients.mapper.mapear_cliente", return_value=None),
            mock.patch("app.rfq.repository.datos_anteriores", return_value=self.PREVIOS),
            mock.patch("app.persistence.blueprint_store.listar_de_base",
                       return_value=[{"nombre": "plano-022.pdf", "tipo": "pdf", "bytes": 9}]),
        ]
        self.guardar = mock.patch("app.persistence.spring_repository.guardar").start()
        self.reasociar = mock.patch("app.rfq.thread_validator.reasociar_en_historial").start()
        self.addCleanup(mock.patch.stopall)
        for parche in parches:
            parche.start()

    # --- la regla, sola ---

    def test_otro_numero_de_parte_es_otro_resorte(self):
        motivo = flow.pide_otro_resorte({"part_number": "1060-023"}, correo_base(), "RFQ-1")
        self.assertIn("1060-023", motivo)

    def test_el_mismo_numero_de_parte_es_el_mismo_aunque_traiga_otro_archivo(self):
        correo = correo_base(adjuntos=[{"nombre": "plano-022-rev-B.pdf", "contenido": b"%PDF"}])
        self.assertEqual(flow.pide_otro_resorte({"part_number": "1060 022"}, correo, "RFQ-1"), "")

    def test_sin_numero_de_parte_decide_el_plano(self):
        # El RFQ ya tenía plano y llega otro con otro nombre: otro resorte.
        correo = correo_base(adjuntos=[{"nombre": "plano-023.pdf", "contenido": b"%PDF"}])
        self.assertIn("otro plano", flow.pide_otro_resorte({}, correo, "RFQ-1"))
        # El mismo archivo, o ninguno: respuesta.
        correo = correo_base(adjuntos=[{"nombre": "plano-022.pdf", "contenido": b"%PDF"}])
        self.assertEqual(flow.pide_otro_resorte({}, correo, "RFQ-1"), "")
        self.assertEqual(flow.pide_otro_resorte({}, correo_base(adjuntos=[]), "RFQ-1"), "")

    def test_si_el_rfq_no_tenia_plano_el_que_llega_es_el_que_faltaba(self):
        with mock.patch("app.persistence.blueprint_store.listar_de_base", return_value=[]):
            self.assertEqual(flow.pide_otro_resorte({}, correo_base(), "RFQ-1"), "")

    def test_el_numero_de_parte_del_plano_tambien_cuenta(self):
        motivo = flow.pide_otro_resorte({}, correo_base(adjuntos=[]), "RFQ-1",
                                        resorte={"num_parte": "1060-023"})
        self.assertIn("1060-023", motivo)

    # --- en el flujo ---

    def test_la_respuesta_con_otro_pn_abre_su_propio_rfq(self):
        resorte = dict(RESORTE_FACTIBLE, num_parte="1060-023")
        with mock.patch.object(flow, "extraer_datos_correo",
                               return_value={"campos": {"part_number": "1060-023",
                                                        "volumen": 5000}}), \
             mock.patch.object(flow, "procesar_dibujos", return_value=[resorte]) as vision, \
             mock.patch.object(flow, "persistir", return_value={}) as persistir:
            resultado = flow.avanzar_a_parsing(
                correo_base(asunto="RE: RFQ 4500"), flow.RESPUESTA_RFQ, "RFQ-1")

        self.assertEqual(resultado["clasificacion"], flow.RFQ_NUEVO)
        self.assertNotEqual(resultado["rfq_id"], "RFQ-1")
        self.assertTrue(resultado["rfq_id"].startswith("INT-"))
        self.assertEqual(resultado["hilo_anterior"], "RFQ-1")
        # Se da de alta como RFQ nuevo, no como versión del viejo, y el
        # correo pasa al historial del nuevo.
        self.assertFalse(persistir.call_args.kwargs["es_seguimiento"])
        self.assertEqual(persistir.call_args[0][2], resultado["rfq_id"])
        self.reasociar.assert_called_once_with(resultado["rfq_id"], "<abc@cliente.com>")
        # Y el plano se lee (y se apunta) ya con el RFQ nuevo, no con el viejo.
        self.assertEqual(vision.call_args[0][1], resultado["rfq_id"])
        self.assertTrue(vision.call_args.kwargs.get("guardar", True))

    def test_si_el_pn_solo_esta_en_el_plano_se_decide_tras_leerlo(self):
        """El correo no dice el número de parte; el plano sí, y es otro."""
        resorte = dict(RESORTE_FACTIBLE, num_parte="1060-023")
        with mock.patch.object(flow, "extraer_datos_correo",
                               return_value={"campos": {"volumen": 5000}}), \
             mock.patch("app.persistence.blueprint_store.listar_de_base", return_value=[]), \
             mock.patch.object(flow, "procesar_dibujos", return_value=[resorte]), \
             mock.patch.object(flow, "persistir", return_value={}) as persistir:
            resultado = flow.avanzar_a_parsing(correo_base(), flow.RESPUESTA_RFQ, "RFQ-1")

        self.assertEqual(resultado["clasificacion"], flow.RFQ_NUEVO)
        datos = persistir.call_args[0][0]
        # Lo heredado del hilo se soltó: el número de parte es el del plano nuevo.
        self.assertEqual(datos["part_number"], "1060-023")
        self.assertEqual(datos["hilo_anterior"], "RFQ-1")
        self.assertEqual(self.guardar.call_args[0][0], resultado["rfq_id"])

    def test_la_respuesta_de_verdad_sigue_siendo_seguimiento(self):
        resorte = dict(RESORTE_FACTIBLE, num_parte="1060-022")
        with mock.patch.object(flow, "extraer_datos_correo",
                               return_value={"campos": {"volumen": 5000}}), \
             mock.patch.object(flow, "procesar_dibujos", return_value=[resorte]), \
             mock.patch.object(flow, "persistir", return_value={}) as persistir:
            resultado = flow.avanzar_a_parsing(
                correo_base(adjuntos=[]), flow.RESPUESTA_RFQ, "RFQ-1")

        self.assertEqual(resultado["rfq_id"], "RFQ-1")
        self.assertTrue(persistir.call_args.kwargs["es_seguimiento"])
        self.reasociar.assert_not_called()
        self.assertEqual(self.guardar.call_args[0][0], "RFQ-1")


class TestTodoCorreoDeLaCarpetaEsUnaPeticion(unittest.TestCase):
    """La carpeta vigilada es la de peticiones de cotización.

    Un «Hola, test» sin plano y sin cantidades no lleva «RFQ» ni «quote», y
    antes iba a la basura sin más. Regla de ISC (2026-09-25): es una petición
    igual; se da de alta como incompleta y se le contesta pidiendo el plano y
    los volúmenes. Sólo lo automático se descarta.
    """

    def _correo(self, **extra):
        datos = {"message_id": "<hola@cgr.com>", "remitente": "daniela.diaz@cgr-international.com",
                 "asunto": "TEST", "cuerpo": "Hola,\n\nTest\n\nSaludos", "adjuntos": []}
        datos.update(extra)
        return datos

    def test_sin_palabras_clave_sigue_siendo_una_peticion(self):
        with mock.patch("app.rfq.thread_validator.validar_respuesta", return_value=None):
            clasificacion, rfq_id = flow.clasificar(self._correo())
        self.assertEqual(clasificacion, flow.RFQ_NUEVO)
        self.assertTrue(rfq_id.startswith("INT-"))

    def test_y_se_le_piden_el_plano_y_las_cantidades(self):
        with mock.patch("app.rfq.thread_validator.validar_respuesta", return_value=None), \
             mock.patch("app.rfq.thread_validator.registrar_en_historial"), \
             mock.patch.object(flow, "_envio_habilitado", return_value=False), \
             mock.patch.object(flow, "_avisar", return_value=True), \
             mock.patch("app.clients.mapper.mapear_cliente", return_value=None), \
             mock.patch.object(flow, "extraer_datos_correo", return_value={"campos": {}}), \
             mock.patch.object(flow, "procesar_dibujos") as vision, \
             mock.patch.object(flow, "persistir", return_value=None) as persistir, \
             mock.patch.object(flow, "responder_datos_faltantes") as responder:
            resultado = flow.avanzar_a_parsing(self._correo(), flow.RFQ_NUEVO, "INT-1")
        self.assertEqual(resultado["etapa"], "gate_temprano")
        self.assertEqual(set(resultado["campos_faltantes"]), {"tiene_adjunto", "volumen"})
        vision.assert_not_called()
        self.assertEqual(persistir.call_args.kwargs["estado"], flow._estado_incompleto())
        self.assertEqual(set(responder.call_args[0][1]), {"tiene_adjunto", "volumen"})

    def test_lo_automatico_va_a_la_basura(self):
        with mock.patch("app.rfq.thread_validator.validar_respuesta", return_value=None):
            for correo in (self._correo(remitente="no-reply@proveedor.com"),
                           self._correo(asunto="Automatic reply: TEST"),
                           self._correo(remitente="MAILER-DAEMON@outlook.com")):
                self.assertEqual(flow.clasificar(correo)[0], flow.TRASH, correo)

    def test_con_el_interruptor_apagado_vuelve_el_filtro_de_palabras(self):
        with mock.patch("app.rfq.thread_validator.validar_respuesta", return_value=None), \
             mock.patch.object(config.settings, "CARPETA_SOLO_RFQ", False):
            self.assertEqual(flow.clasificar(self._correo())[0], flow.TRASH)
            self.assertEqual(flow.clasificar(self._correo(asunto="Spring quote"))[0],
                             flow.RFQ_NUEVO)
