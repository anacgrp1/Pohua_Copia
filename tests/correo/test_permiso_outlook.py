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


class TestElPermisoSePideAlArrancar:
    """El aviso de direcciones, nada más arrancar y no con el primer correo."""

    def _con_outlook(self, monkeypatch, sesion):
        import sys
        import types

        class _App:
            def GetNamespace(self, _):
                return sesion
        win32 = types.SimpleNamespace(client=types.SimpleNamespace(
            Dispatch=lambda nombre: _App()))
        monkeypatch.setitem(sys.modules, "pythoncom",
                            types.SimpleNamespace(CoInitialize=lambda: None))
        monkeypatch.setitem(sys.modules, "win32com", win32)
        monkeypatch.setitem(sys.modules, "win32com.client", win32.client)

    def test_lee_la_direccion_del_usuario_a_proposito(self, monkeypatch):
        class Sesion:
            class CurrentUser:
                Address = "sales.isc@cgr-international.com"
        self._con_outlook(monkeypatch, Sesion())
        assert op.pedir_permiso_ahora() is True

    def test_un_deny_se_reconoce(self, monkeypatch):
        class Sesion:
            @property
            def CurrentUser(self):
                raise ComError(op.E_ABORT, "Denied", None, None)
        self._con_outlook(monkeypatch, Sesion())
        assert op.pedir_permiso_ahora() is False

    def test_sin_outlook_no_se_sabe(self, monkeypatch):
        class Sesion:
            @property
            def CurrentUser(self):
                raise RuntimeError("no hay Outlook")
        self._con_outlook(monkeypatch, Sesion())
        assert op.pedir_permiso_ahora() is None

    def test_el_lector_lo_pide_antes_del_primer_ciclo(self):
        # La llamada va en `run`, antes del bucle de ciclos.
        import inspect

        import desktop_app.main as escritorio
        fuente = inspect.getsource(escritorio.Lector.run)
        assert fuente.index("_pedir_permiso_a_outlook") < fuente.index("while self._corriendo")
