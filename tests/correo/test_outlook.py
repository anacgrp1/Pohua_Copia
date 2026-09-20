"""El proveedor que lee por el Outlook de escritorio.

No hay Outlook aquí, así que se le pone delante un Outlook de mentira con la
misma forma que el de verdad (Folders, Items, PropertyAccessor…). Lo que se
comprueba es lo que de verdad se puede equivocar al hablar con COM: encontrar
el buzón y la carpeta, sacar la dirección SMTP del remitente en vez del
galimatías de Exchange, sacar el Message-ID por su etiqueta MAPI —sin él, cada
relectura sería un correo nuevo— y no tragarse lo que no es un correo.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

import app.core.config as config


# --------------------------------------------------------------------------- #
# El Outlook de mentira
# --------------------------------------------------------------------------- #

class _Coleccion:
    """Se comporta como una colección de COM: 1-based, con .Count y .Item()."""

    def __init__(self, cosas):
        self._cosas = list(cosas)

    @property
    def Count(self):
        return len(self._cosas)

    def Item(self, i):
        return self._cosas[i - 1]

    def Sort(self, *_):
        return None

    def Restrict(self, consulta):
        if "Unread" in consulta:
            return _Coleccion([c for c in self._cosas if getattr(c, "UnRead", False)])
        return self


class _Propiedades:
    def __init__(self, valores):
        self._valores = valores

    def GetProperty(self, esquema):
        if esquema in self._valores:
            return self._valores[esquema]
        raise RuntimeError("propiedad ausente")


class _Adjunto:
    def __init__(self, nombre, datos):
        self.FileName = nombre
        self.Size = len(datos)
        self._datos = datos

    def SaveAsFile(self, ruta):
        with open(ruta, "wb") as fichero:
            fichero.write(self._datos)


class _Correo:
    Class = 43

    def __init__(self, **kw):
        self.EntryID = kw.get("entry", "ENTRY-1")
        self.Subject = kw.get("asunto", "Spring Quote - Fake Customer")
        self.Body = kw.get("texto", "Good afternoon")
        self.HTMLBody = kw.get("html", "<p>Good afternoon</p>")
        self.SenderEmailType = kw.get("tipo", "EX")
        self.SenderEmailAddress = kw.get("direccion", "/O=EXCHANGELABS/CN=DANIELA")
        self.UnRead = kw.get("sin_leer", True)
        self.Attachments = _Coleccion(kw.get("adjuntos", []))
        self.PropertyAccessor = _Propiedades(kw.get("propiedades", {}))
        self.guardado = False

        import datetime
        self.ReceivedTime = datetime.datetime(2026, 9, 11, 19, 50,
                                              tzinfo=datetime.timezone.utc)

        smtp = kw.get("smtp", "daniela.diaz@cgr-international.com")
        self.Sender = mock.MagicMock()
        self.Sender.GetExchangeUser.return_value.PrimarySmtpAddress = smtp

    def Save(self):
        self.guardado = True


class _CorreoRoto:
    """Un correo que truena al leerlo.

    Pasa de verdad: COM devuelve un error en una propiedad cuando el elemento
    está dañado o el servidor no lo tiene descargado. Es una clase aparte, y no
    un `_Correo` al que se le rompe una propiedad sobre la marcha, porque eso
    último se la rompería también a todos los `_Correo` de las demás pruebas.
    """
    Class = 43
    UnRead = True
    EntryID = "MALO"

    @property
    def Subject(self):
        raise RuntimeError("COM")


class _CorreoBloqueado:
    """Un correo al que el guardián de Outlook le tapa TODAS las direcciones.

    Es lo que se ve cuando salta el aviso "A program is trying to access
    e-mail address information" y nadie lo acepta: el correo está ahí y se le
    lee el asunto, pero ninguna de las tres vías da la dirección. No hereda de
    `_Correo` porque su constructor ASIGNA esas tres cosas, y aquí justamente
    no se pueden ni tocar.
    """
    Class = 43
    UnRead = True
    EntryID = "TAPADO"
    Subject = "Spring Quote - Fake Customer"
    Body = "Good afternoon"
    HTMLBody = "<p>Good afternoon</p>"

    def __init__(self):
        import datetime
        self.ReceivedTime = datetime.datetime(2026, 9, 11, 19, 50,
                                              tzinfo=datetime.timezone.utc)
        self.Attachments = _Coleccion([])
        self.PropertyAccessor = _Propiedades({})

    def _corta(self):
        raise RuntimeError("El guardián de Outlook denegó el acceso")

    SenderEmailType = property(_corta)
    Sender = property(_corta)
    SenderEmailAddress = property(_corta)


class _Cita:
    """Una cita de calendario: está en la carpeta, pero no es un correo."""
    Class = 26
    UnRead = True


class _Carpeta:
    def __init__(self, nombre, hijas=(), correos=()):
        self.Name = nombre
        self.Folders = _Coleccion(hijas)
        self.Items = _Coleccion(correos)


def _outlook_de_mentira(correos):
    bandeja = _Carpeta("Bandeja de entrada",
                       hijas=[_Carpeta("TEST", correos=correos)])
    buzon = _Carpeta("sales.isc@cgr-international.com", hijas=[bandeja])
    otro = _Carpeta("ana.ramirez@cgr-international.com")

    espacio = mock.MagicMock()
    espacio.Folders = _Coleccion([otro, buzon])
    espacio.Stores = _Coleccion([])

    aplicacion = mock.MagicMock()
    aplicacion.GetNamespace.return_value = espacio
    return aplicacion, espacio


class _Base(unittest.TestCase):

    def setUp(self):
        # win32com y pythoncom no existen fuera de Windows: se inventan.
        win32com = mock.MagicMock()
        self.cliente = win32com.client
        sys.modules["win32com"] = win32com
        sys.modules["win32com.client"] = self.cliente
        sys.modules["pythoncom"] = mock.MagicMock()
        self.addCleanup(lambda: [sys.modules.pop(m, None)
                                 for m in ("win32com", "win32com.client", "pythoncom")])

        for clave, valor in (("MAIL_MODE", "outlook"), ("MAIL_FOLDER", "TEST"),
                             ("OUTLOOK_BUZON", "sales.isc@cgr-international.com")):
            parche = mock.patch.object(config.settings, clave, valor)
            parche.start()
            self.addCleanup(parche.stop)

    def _proveedor(self, correos):
        aplicacion, espacio = _outlook_de_mentira(correos)
        self.cliente.Dispatch.return_value = aplicacion
        self.espacio = espacio
        from app.email.outlook_provider import OutlookEmailProvider
        return OutlookEmailProvider()


class TestEncontrarElBuzon(_Base):

    def test_el_buzon_y_la_carpeta_anidada(self):
        proveedor = self._proveedor([])
        self.assertTrue(proveedor.connect())
        self.assertEqual(proveedor._carpeta.Name, "TEST")

    def test_sin_esa_carpeta_no_arranca(self):
        with mock.patch.object(config.settings, "MAIL_FOLDER", "NO_EXISTE"):
            proveedor = self._proveedor([])
            self.assertFalse(proveedor.connect())

    def test_sin_ese_buzon_no_arranca(self):
        with mock.patch.object(config.settings, "OUTLOOK_BUZON", "otro@sitio.com"):
            proveedor = self._proveedor([])
            self.assertFalse(proveedor.connect())


class TestLeer(_Base):

    ID_INTERNET = "http://schemas.microsoft.com/mapi/proptag/0x1035001F"

    def test_un_correo_entero(self):
        correo = _Correo(
            adjuntos=[_Adjunto("2XX486152_1060-022.pdf", b"%PDF-1.4 falso")],
            propiedades={self.ID_INTERNET: "<abc123@cgr-international.com>"})
        proveedor = self._proveedor([correo])
        proveedor.connect()

        mensajes = proveedor.fetch_unread_messages()
        self.assertEqual(len(mensajes), 1)
        m = mensajes[0]

        self.assertEqual(m.id, "ENTRY-1")
        self.assertEqual(m.subject, "Spring Quote - Fake Customer")
        # La dirección de verdad, no la ruta interna de Exchange.
        self.assertEqual(m.sender, "daniela.diaz@cgr-international.com")
        # El Message-ID es lo que evita procesar dos veces el mismo correo.
        self.assertEqual(m.raw_headers["Message-ID"], "<abc123@cgr-international.com>")
        self.assertTrue(m.body_is_html)
        self.assertIn("Good afternoon", m.body)
        self.assertIn("11 Sep 2026", m.date)
        self.assertEqual(len(m.attachments), 1)
        self.assertEqual(m.attachments[0].filename, "2XX486152_1060-022.pdf")
        self.assertEqual(m.attachments[0].content, b"%PDF-1.4 falso")

    def test_lo_que_no_es_correo_se_ignora(self):
        proveedor = self._proveedor([_Cita(), _Correo(entry="ENTRY-2")])
        proveedor.connect()
        mensajes = proveedor.fetch_unread_messages()
        self.assertEqual([m.id for m in mensajes], ["ENTRY-2"])

    def test_los_leidos_no_vuelven(self):
        proveedor = self._proveedor([_Correo(entry="A", sin_leer=False),
                                     _Correo(entry="B")])
        proveedor.connect()
        self.assertEqual([m.id for m in proveedor.fetch_unread_messages()], ["B"])

    def test_un_correo_que_truena_no_para_a_los_demas(self):
        proveedor = self._proveedor([_CorreoRoto(), _Correo(entry="BUENO")])
        proveedor.connect()
        self.assertEqual([m.id for m in proveedor.fetch_unread_messages()], ["BUENO"])

    def test_si_outlook_tapa_la_direccion_el_correo_no_se_procesa(self):
        """Sin remitente no hay ni cliente ni a quién contestar.

        Así que ese correo no sale del lote a medias: se queda fuera y, como
        nadie lo marca como leído, vuelve a intentarse en el siguiente ciclo.
        Lo que no puede hacer es frenar a los demás.
        """
        proveedor = self._proveedor([_CorreoBloqueado(),
                                     _Correo(entry="BUENO")])
        proveedor.connect()
        mensajes = proveedor.fetch_unread_messages()
        self.assertEqual([m.id for m in mensajes], ["BUENO"])

    def test_sin_remitente_de_exchange_se_usa_la_direccion(self):
        correo = _Correo(tipo="SMTP", direccion="comprador@neogen.com")
        proveedor = self._proveedor([correo])
        proveedor.connect()
        self.assertEqual(proveedor.fetch_unread_messages()[0].sender,
                         "comprador@neogen.com")


class TestMarcarYEnviar(_Base):

    def test_marcar_como_leido(self):
        correo = _Correo(entry="ENTRY-9")
        proveedor = self._proveedor([correo])
        proveedor.connect()
        self.espacio.GetItemFromID.return_value = correo

        self.assertTrue(proveedor.mark_as_read("ENTRY-9"))
        self.espacio.GetItemFromID.assert_called_once_with("ENTRY-9")
        self.assertFalse(correo.UnRead)
        self.assertTrue(correo.guardado)

    def test_enviar_sale_por_outlook_desde_el_buzon(self):
        proveedor = self._proveedor([])
        proveedor.connect()
        nuevo = mock.MagicMock()
        proveedor._outlook.CreateItem.return_value = nuevo

        from app.email.base_provider import EmailAttachment
        ok = proveedor.send_email("comprador@neogen.com", "Re: RFQ",
                                  "<p>Attached</p>",
                                  [EmailAttachment("COT-75.pdf", b"%PDF")])

        self.assertTrue(ok)
        self.assertEqual(nuevo.To, "comprador@neogen.com")
        self.assertEqual(nuevo.SentOnBehalfOfName, "sales.isc@cgr-international.com")
        nuevo.Attachments.Add.assert_called_once()
        nuevo.Send.assert_called_once()


class TestLaFabrica(unittest.TestCase):
    """`MAIL_MODE` manda, no `APP_ENV`."""

    def test_outlook(self):
        sys.modules.setdefault("win32com", mock.MagicMock())
        sys.modules.setdefault("win32com.client", mock.MagicMock())
        from app.email.factory import EmailProviderFactory
        from app.email.outlook_provider import OutlookEmailProvider
        with mock.patch.object(config.settings, "MAIL_MODE", "outlook"), \
             mock.patch.object(config.settings, "APP_ENV", "prod"):
            self.assertIsInstance(EmailProviderFactory.get_provider(),
                                  OutlookEmailProvider)

    def test_imap_aunque_el_entorno_sea_prod(self):
        from app.email.factory import EmailProviderFactory
        from app.email.imap_provider import ImapEmailProvider
        with mock.patch.object(config.settings, "MAIL_MODE", "imap"), \
             mock.patch.object(config.settings, "APP_ENV", "prod"):
            self.assertIsInstance(EmailProviderFactory.get_provider(),
                                  ImapEmailProvider)

    def test_sin_modo_manda_el_entorno(self):
        from app.email.factory import EmailProviderFactory
        from app.email.graph_provider import GraphEmailProvider
        with mock.patch.object(config.settings, "MAIL_MODE", ""), \
             mock.patch.object(config.settings, "APP_ENV", "prod"):
            self.assertIsInstance(EmailProviderFactory.get_provider(),
                                  GraphEmailProvider)


if __name__ == "__main__":
    unittest.main()
