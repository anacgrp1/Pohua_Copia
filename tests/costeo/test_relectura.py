"""Volver a leer el plano que el RFQ ya tiene guardado.

Un plano se lee una sola vez, cuando el correo entra. Si aquel día falló
—formato no soportado, la firma colada como dibujo, un JSON a medias— el RFQ
se queda sin cotas para siempre y el costeo sale orientativo aunque el correo
viniera completo. Estas pruebas cubren que releer no dependa del correo, que
nunca lance, y que sólo se gaste la llamada al modelo cuando hace falta.

Nada aquí llama a la API: el cliente de visión se inyecta.
"""

import pytest

import app.rfq.relectura as relectura


# --------------------------------------------------------------------------- #
# Dobles
# --------------------------------------------------------------------------- #

_JSON_BUENO = """
{"num_parte": "SPR-100", "tipo_resorte": "compresion",
 "material": "ASTM A228 music wire", "diametro_alambre_mm": 1.6,
 "diametro_exterior_mm": 12.0, "longitud_libre_mm": 40.0,
 "numero_espiras_totales": 9, "confianza": 0.9, "advertencias": []}
"""


class _Parte:
    type = "text"

    def __init__(self, texto):
        self.text = texto


class _Respuesta:
    def __init__(self, texto):
        self.content = [_Parte(texto)]
        self.usage = None


class _Mensajes:
    def __init__(self, texto, registro):
        self._texto = texto
        self._registro = registro

    def create(self, **kwargs):
        self._registro.append(kwargs)
        return _Respuesta(self._texto)


class _ClienteFalso:
    """Cliente de Anthropic de mentira. `llamadas` cuenta lo que se gastó."""

    def __init__(self, texto=_JSON_BUENO):
        self.llamadas = []
        self.messages = _Mensajes(texto, self.llamadas)


class _ClienteQueRevienta:
    class _M:
        def create(self, **kwargs):
            raise RuntimeError("Error code: 400 - el modelo dijo que no")

    def __init__(self):
        self.messages = self._M()


_PDF = b"%PDF-1.7 un plano de mentira"
_PNG = b"\x89PNG\r\n\x1a\n" + b"pixeles"


@pytest.fixture
def almacen_falso(monkeypatch):
    """Sustituye el almacén de planos y el guardado del resorte."""
    estado = {"planos": {}, "guardados": []}

    import app.persistence.blueprint_store as almacen
    import app.persistence.spring_repository as spring_repository

    monkeypatch.setattr(
        almacen, "listar_de_base",
        lambda rfq_id: [{"nombre": n} for n in sorted(estado["planos"])])
    monkeypatch.setattr(almacen, "carpeta_de", lambda rfq_id: None)
    monkeypatch.setattr(
        almacen, "leer_plano",
        lambda rfq_id, nombre: ((estado["planos"][nombre], "application/pdf")
                                if nombre in estado["planos"] else None))
    monkeypatch.setattr(
        spring_repository, "guardar",
        lambda rfq_id, mid, origen, datos: estado["guardados"].append(
            (rfq_id, origen, datos)) or 1)
    return estado


# --------------------------------------------------------------------------- #
# releer()
# --------------------------------------------------------------------------- #

def test_sin_plano_guardado_lo_dice_y_no_gasta_el_modelo(almacen_falso):
    cliente = _ClienteFalso()
    r = relectura.releer("RFQ-1", cliente=cliente)

    assert r["estado"] == "sin_adjunto"
    assert r["resorte"] is None
    assert cliente.llamadas == []


def test_un_formato_que_el_lector_no_abre_no_llega_al_modelo(almacen_falso):
    almacen_falso["planos"]["pedido.docx"] = b"PK\x03\x04 algo"
    cliente = _ClienteFalso()
    r = relectura.releer("RFQ-1", cliente=cliente)

    assert r["estado"] == "formato_no_leido"
    assert r["ficheros"] == ["pedido.docx"]
    assert ".pdf" in r["soportados"]
    assert cliente.llamadas == []


def test_el_plano_guardado_se_lee_y_se_persiste(almacen_falso):
    almacen_falso["planos"]["plano.pdf"] = _PDF
    cliente = _ClienteFalso()
    r = relectura.releer("RFQ-1", message_id="<m@1>", cliente=cliente)

    assert r["estado"] == "leido"
    assert r["resorte"]["diametro_alambre_mm"] == 1.6
    assert r["ficheros"] == ["plano.pdf"]
    # Se gastó exactamente una llamada, y quedó guardado.
    assert len(cliente.llamadas) == 1
    assert len(almacen_falso["guardados"]) == 1
    rfq_id, origen, datos = almacen_falso["guardados"][0]
    assert rfq_id == "RFQ-1"
    assert origen == "plano.pdf"
    assert datos["diametro_alambre_mm"] == 1.6


def test_varios_planos_van_en_una_sola_llamada(almacen_falso):
    almacen_falso["planos"]["hoja1.pdf"] = _PDF
    almacen_falso["planos"]["hoja2.png"] = _PNG
    cliente = _ClienteFalso()
    r = relectura.releer("RFQ-1", cliente=cliente)

    assert r["estado"] == "leido"
    assert r["ficheros"] == ["hoja1.pdf", "hoja2.png"]
    assert len(cliente.llamadas) == 1


def test_un_fallo_del_modelo_no_lanza(almacen_falso):
    almacen_falso["planos"]["plano.pdf"] = _PDF
    r = relectura.releer("RFQ-1", cliente=_ClienteQueRevienta())

    assert r["estado"] == "fallo"
    assert r["resorte"] is None
    assert almacen_falso["guardados"] == []
    # El motivo ya no es el volcado de la librería, sino algo que se puede
    # leer y sobre lo que se puede actuar (app/core/modelo_errores.py).
    import app.core.modelo_errores as modelo_errores
    assert r["codigo"] == modelo_errores.PETICION_MALA
    assert "400" not in r["motivo"]
    assert r["reintentar"] is False


def test_un_plano_listado_pero_ilegible_se_omite(almacen_falso, monkeypatch):
    """Un bloque de cero bytes gasta la llamada y no enseña nada."""
    import app.persistence.blueprint_store as almacen
    monkeypatch.setattr(almacen, "listar_de_base",
                        lambda rfq_id: [{"nombre": "fantasma.pdf"}])
    monkeypatch.setattr(almacen, "leer_plano", lambda rfq_id, nombre: None)

    cliente = _ClienteFalso()
    r = relectura.releer("RFQ-1", cliente=cliente)

    assert r["estado"] == "sin_adjunto"
    assert cliente.llamadas == []


# --------------------------------------------------------------------------- #
# falta_geometria() / asegurar_resorte()
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("resorte", [
    None, {}, {"tipo_resorte": "compresion"},
    {"diametro_alambre_mm": None}, {"diametro_alambre_mm": 0},
    {"diametro_alambre_mm": "no es un número"},
])
def test_falta_geometria_cuando_no_hay_calibre(resorte):
    assert relectura.falta_geometria(resorte) is True


def test_con_calibre_no_falta_geometria():
    assert relectura.falta_geometria({"diametro_alambre_mm": 1.6}) is False


def test_asegurar_no_gasta_el_modelo_si_el_resorte_ya_esta(almacen_falso):
    almacen_falso["planos"]["plano.pdf"] = _PDF
    cliente = _ClienteFalso()
    r = relectura.asegurar_resorte(
        "RFQ-1", {"diametro_alambre_mm": 1.6}, cliente=cliente)

    assert r["resorte"]["diametro_alambre_mm"] == 1.6
    # `None` distingue "no se intentó" de "se intentó y no salió".
    assert r["lectura"] is None
    assert cliente.llamadas == []


def test_asegurar_lee_el_plano_cuando_falta_el_calibre(almacen_falso):
    almacen_falso["planos"]["plano.pdf"] = _PDF
    cliente = _ClienteFalso()
    r = relectura.asegurar_resorte("RFQ-1", {}, cliente=cliente)

    assert r["resorte"]["diametro_alambre_mm"] == 1.6
    assert r["lectura"]["estado"] == "leido"
    assert len(cliente.llamadas) == 1


def test_asegurar_conserva_el_resorte_viejo_si_la_lectura_falla(almacen_falso):
    almacen_falso["planos"]["plano.pdf"] = _PDF
    viejo = {"tipo_resorte": "compresion"}
    r = relectura.asegurar_resorte("RFQ-1", viejo, cliente=_ClienteQueRevienta())

    assert r["resorte"] is viejo
    assert r["lectura"]["estado"] == "fallo"
