# -*- coding: utf-8 -*-
"""La ventana «A program is trying to send an email message on your behalf».

Outlook la saca en CADA `Send()` cuando no confía en el programa, y no tiene
«permitir durante un rato». Eso se quita en Outlook (antivirus válido en el
Centro de confianza), no desde aquí. Lo que sí es de Pohua es que no se
amontonen: después de un «Deny» no se vuelve a llamar a `Send()` durante un
rato, la cola se para en vez de sacar una ventana por correo, y ningún correo
se pierde por eso.
"""

import os

import pytest

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

from app.email import outlook_provider as op  # noqa: E402


class ComError(Exception):
    """Como pywintypes.com_error: (hresult, texto, excepinfo, argerr)."""


@pytest.fixture(autouse=True)
def sin_pausa(monkeypatch):
    monkeypatch.setattr(op, "_denegado_en", None)


class _CorreoQueNiegan:
    def __init__(self, error):
        self.error = error
        self.Attachments = self

    def Add(self, ruta):
        return None

    def Send(self):
        raise self.error


class _Outlook:
    def __init__(self, error):
        self.error = error
        self.creados = 0

    def CreateItem(self, _):
        self.creados += 1
        return _CorreoQueNiegan(self.error)


def _proveedor(error, monkeypatch):
    p = op.OutlookEmailProvider()
    p._outlook = _Outlook(error)
    monkeypatch.setattr(p, "_fijar_remitente", lambda correo: None)
    return p


class TestReconoceElDeny:

    def test_por_el_hresult(self):
        assert op._es_denegado(ComError(op.E_ABORT, "Operation aborted", None, None))

    def test_por_el_excepinfo(self):
        info = (0, "Outlook", "Operation aborted", None, 0, op.E_ABORT)
        assert op._es_denegado(ComError(-2147352567, "Exception occurred.", info, None))

    def test_otro_error_no_es_un_deny(self):
        assert not op._es_denegado(ComError(-2147221005, "Invalid class string", None, None))


class TestTrasUnDeny:

    def test_se_avisa_y_no_se_vuelve_a_preguntar(self, monkeypatch):
        p = _proveedor(ComError(op.E_ABORT, "Operation aborted", None, None), monkeypatch)
        with pytest.raises(op.EnvioDenegado):
            p.send_email("a@b.com", "Oferta", "hola")
        assert p._outlook.creados == 1
        # El siguiente ni siquiera llega a Outlook: sería otra ventana.
        with pytest.raises(op.EnvioDenegado):
            p.send_email("c@d.com", "Oferta", "hola")
        assert p._outlook.creados == 1
        assert op.envio_en_pausa()

    def test_un_error_cualquiera_no_pausa(self, monkeypatch):
        p = _proveedor(ComError(-1, "otro", None, None), monkeypatch)
        assert p.send_email("a@b.com", "Oferta", "hola") is False
        assert not op.envio_en_pausa()


class TestLaColaSeParaSinPerderNada:

    def test_un_deny_para_la_cola_y_no_gasta_intentos(self, monkeypatch):
        import app.email.bandeja_salida as bandeja
        cola = [{"id": i, "destinatario": f"c{i}@x.com", "rfq_id": None} for i in (1, 2, 3)]
        fallos = []
        monkeypatch.setattr(bandeja, "pendientes", lambda limite=20: list(cola))
        monkeypatch.setattr(bandeja, "hay_pendientes", lambda: 3)
        monkeypatch.setattr(bandeja, "marcar_fallo", lambda i, e: fallos.append(i))
        llamadas = []

        def niega(correo):
            llamadas.append(correo["id"])
            raise op.EnvioDenegado("Outlook no dejó mandar el correo.")

        resumen = bandeja.drenar(enviar=niega)
        assert llamadas == [1]              # una sola ventana, no tres
        assert fallos == []                 # no cuenta como intento fallido
        assert resumen["denegados"] == 1 and resumen["pendientes"] == 3

    def test_un_correo_directo_denegado_queda_en_la_bandeja(self, monkeypatch):
        import app.core.config as config
        import app.email.bandeja_salida as bandeja
        import app.email.factory as factory
        import app.email.outbound as outbound

        class Niega:
            def send_email(self, **kw):
                raise op.EnvioDenegado("Outlook no dejó mandar el correo.")

        monkeypatch.setattr(config.settings, "MAIL_MODE", "outlook", raising=False)
        monkeypatch.setattr(outbound, "diagnostico_envio",
                            lambda: {"puede": True, "modo": "outlook", "faltan": []})
        monkeypatch.setattr(factory.EmailProviderFactory, "get_provider",
                            staticmethod(lambda: Niega()))
        encolados = []
        monkeypatch.setattr(bandeja, "encolar",
                            lambda contenido, **kw: encolados.append(contenido) or 99)
        ok = outbound.enviar({"destinatario": "c@x.com", "asunto": "Oferta",
                              "cuerpo_texto": "hola"}, rfq_id="RFQ-1", clase="oferta")
        assert ok is True and len(encolados) == 1


class TestNoSeReleeLoYaAtendido:
    """Cada lectura de un correo toca propiedades vigiladas (cuerpo,
    PropertyAccessor): releer el mismo cada cinco minutos era la ventana de
    «access email address information» cada cinco minutos."""

    def test_marcar_como_leido_usa_la_tienda_del_buzon(self, monkeypatch):
        visto: dict[str, object] = {}

        class Item:
            UnRead = True

            def Save(self):
                visto["guardado"] = True

        class Mapi:
            def GetItemFromID(self, entry, tienda=None):
                visto["tienda"] = tienda
                return Item()

        p = op.OutlookEmailProvider()
        p._mapi = Mapi()
        p._carpeta = type("Carpeta", (), {"StoreID": "STORE-VENTAS"})()
        monkeypatch.setattr(op, "_YA_VISTOS", set())
        assert p.mark_as_read("ENTRY-1") is True
        assert visto == {"tienda": "STORE-VENTAS", "guardado": True}
        assert "ENTRY-1" in op._YA_VISTOS

    def test_lo_ya_atendido_se_salta_sin_leer_su_cuerpo(self, monkeypatch):
        class Correo:
            Class = 43
            EntryID = "ENTRY-1"
            UnRead = True

            def Save(self):
                pass

            @property
            def Body(self):
                raise AssertionError("no debía leerse: es una propiedad vigilada")

        class Coleccion:
            Count = 1

            def Item(self, i):
                return Correo()

            def Sort(self, *a):
                pass

            def Restrict(self, _):
                return self

        p = op.OutlookEmailProvider()
        p._carpeta = type("Carpeta", (), {"Items": Coleccion()})()
        monkeypatch.setattr(op, "_YA_VISTOS", {"ENTRY-1"})
        assert p.fetch_unread_messages() == []



class TestElLector:

    def test_el_lector_ejecuta_el_ciclo(self):
        import inspect

        import desktop_app.main as escritorio
        fuente = inspect.getsource(escritorio.Lector.run)
        assert "ciclo_deteccion(forzar=forzado)" in fuente


class TestElCuerpoSeLeeSinDespertarAlGuardian:
    """`HTMLBody` y `Body` eran lo único de la lectura que aún sacaba el cuadro
    de Outlook. Se leen por sus etiquetas MAPI (PR_HTML / PR_BODY), como hace
    Ixtli, y las vigiladas quedan sólo de respaldo."""

    class _Item:
        def __init__(self, props):
            self._props = props
            self.PropertyAccessor = self

        def GetProperty(self, esquema):
            if esquema not in self._props:
                raise RuntimeError("no existe")
            return self._props[esquema]

        @property
        def HTMLBody(self):
            raise AssertionError("HTMLBody es vigilada: no debía leerse")

        @property
        def Body(self):
            raise AssertionError("Body es vigilada: no debía leerse")

    def test_html_por_etiqueta_mapi_en_bytes(self):
        item = self._Item({op.PR_HTML: "<p>Cotizar 5,000 pzas · Ñ</p>".encode("utf-8"),
                           op.PR_INTERNET_CPID: 65001})
        html, texto = op.OutlookEmailProvider()._cuerpo(item)
        assert "5,000 pzas · Ñ" in html and texto == ""

    def test_html_como_tupla_de_enteros_y_cp1252(self):
        crudo = tuple("<b>Señor</b>".encode("cp1252"))
        item = self._Item({op.PR_HTML: crudo, op.PR_INTERNET_CPID: 1252})
        html, _ = op.OutlookEmailProvider()._cuerpo(item)
        assert html == "<b>Señor</b>"

    def test_sin_html_se_usa_el_texto_mapi(self):
        item = self._Item({op.PR_BODY_W: "Please quote 10,000 pcs"})
        html, texto = op.OutlookEmailProvider()._cuerpo(item)
        assert (html, texto) == ("", "Please quote 10,000 pcs")

    def test_solo_sin_etiquetas_mapi_se_tocan_las_vigiladas(self):
        class Raro(self._Item):
            @property
            def HTMLBody(self):
                return "<p>viejo</p>"
        html, _ = op.OutlookEmailProvider()._cuerpo(Raro({}))
        assert html == "<p>viejo</p>"

    def test_ya_no_se_provoca_el_cuadro_al_arrancar(self):
        # Sin lecturas vigiladas no hay nada que pedir al arrancar: provocarlo
        # sería sacar el cuadro que se acaba de quitar.
        assert not hasattr(op, "pedir_permiso_ahora")
        import desktop_app.main as escritorio
        assert not hasattr(escritorio.Lector, "_pedir_permiso_a_outlook")



class TestVueltoAMarcarComoNoLeido:
    """«2- Test - editing» (2026-09-30): se saltó una vez como repetido y, al
    volver a marcarlo como no leído, el lector lo seguía saltando en silencio
    («0 sin leer») hasta reiniciarse."""

    class _Coleccion:
        def __init__(self, correo):
            self.correo = correo
            self.Count = 1

        def Item(self, i):
            return self.correo

        def Sort(self, *a):
            pass

        def Restrict(self, _):
            return self

    def _proveedor(self, correo):
        p = op.OutlookEmailProvider()
        p._carpeta = type("Carpeta", (), {"Items": self._Coleccion(correo)})()
        return p

    def test_si_lo_dejamos_leido_y_vuelve_sin_leer_se_lee_otra_vez(self, monkeypatch):
        correo = type("Correo", (), {"Class": 43, "EntryID": "ENTRY-2", "UnRead": True,
                                     "Save": lambda self: None})()
        p = self._proveedor(correo)
        monkeypatch.setattr(op, "_YA_VISTOS", {"ENTRY-2"})
        monkeypatch.setattr(op, "_MARCADOS", {"ENTRY-2"})
        monkeypatch.setattr(p, "_a_mensaje", lambda item: "MENSAJE")
        assert p.fetch_unread_messages() == ["MENSAJE"]
        assert "ENTRY-2" not in op._YA_VISTOS

    def test_marcar_como_leido_lo_apunta(self, monkeypatch):
        class Item:
            UnRead = True
            def Save(self):
                pass
        p = op.OutlookEmailProvider()
        p._mapi = type("Mapi", (), {"GetItemFromID": lambda self, e, t=None: Item()})()
        p._carpeta = type("Carpeta", (), {"StoreID": "S"})()
        monkeypatch.setattr(op, "_YA_VISTOS", set())
        monkeypatch.setattr(op, "_MARCADOS", set())
        assert p.mark_as_read("ENTRY-3") is True
        assert "ENTRY-3" in op._MARCADOS
