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

    def _cuentas(self, *direcciones):
        """Las cuentas del perfil de Outlook, como las ve COM."""
        cuentas = []
        for direccion in direcciones:
            cuenta = mock.MagicMock()
            cuenta.SmtpAddress = direccion
            cuentas.append(cuenta)
        return _Coleccion(cuentas)

    def test_sale_como_ventas_si_ese_buzon_es_una_cuenta(self):
        """Lo que quiere el cliente: que conteste ventas, no un desconocido.

        Con la cuenta en el perfil se manda CON ella. Es la diferencia entre
        que el correo llegue de sales.isc y que llegue de "System
        Administrator" con la ruta interna de Exchange, sin poder contestar.
        """
        proveedor = self._proveedor([])
        proveedor.connect()
        proveedor._outlook.Session.Accounts = self._cuentas(
            "ana.ramirez@cgr-international.com", "sales.isc@cgr-international.com")
        nuevo = mock.MagicMock()
        proveedor._outlook.CreateItem.return_value = nuevo

        self.assertTrue(proveedor.send_email("comprador@neogen.com", "Re: RFQ", "hola"))
        self.assertEqual(nuevo.SendUsingAccount.SmtpAddress,
                         "sales.isc@cgr-international.com")

    def test_si_la_asignacion_no_agarra_se_pone_por_el_camino_largo(self):
        """El fallo silencioso que mandaba los correos desde la cuenta personal.

        `SendUsingAccount` guarda un objeto, y esa clase de asignación en COM
        unas veces se aplica y otras se ignora sin avisar. Si se ignora y nadie
        lo comprueba, el correo sale desde la cuenta de quien tenga Outlook
        abierto —el cliente recibe una respuesta de una dirección personal— y
        en el registro no aparece ni un error.
        """
        class _CorreoTerco:
            """No hace caso a la asignación normal; sólo a propertyputref."""

            def __init__(self):
                self.SendUsingAccount = None
                self._oleobj_ = mock.MagicMock()
                self._oleobj_.Invoke.side_effect = self._invocado

            def _invocado(self, *args):
                if args[0] == 64209:
                    object.__setattr__(self, "SendUsingAccount", args[-1])

            def __setattr__(self, nombre, valor):
                if nombre == "SendUsingAccount" and valor is not None:
                    return          # se lo traga, como hace COM a veces
                object.__setattr__(self, nombre, valor)

        proveedor = self._proveedor([])
        proveedor.connect()
        proveedor._outlook.Session.Accounts = self._cuentas(
            "sales.isc@cgr-international.com")

        correo = _CorreoTerco()
        proveedor._fijar_remitente(correo)

        self.assertIsNotNone(correo.SendUsingAccount)
        self.assertEqual(correo.SendUsingAccount.SmtpAddress,
                         "sales.isc@cgr-international.com")
        correo._oleobj_.Invoke.assert_called()

    def test_si_no_es_una_cuenta_se_manda_en_su_nombre(self):
        proveedor = self._proveedor([])
        proveedor.connect()
        proveedor._outlook.Session.Accounts = self._cuentas(
            "ana.ramirez@cgr-international.com")
        nuevo = mock.MagicMock()
        proveedor._outlook.CreateItem.return_value = nuevo

        self.assertTrue(proveedor.send_email("comprador@neogen.com", "Re: RFQ", "hola"))
        self.assertEqual(nuevo.SentOnBehalfOfName, "sales.isc@cgr-international.com")

    def test_la_firma_se_incrusta_y_no_sale_como_adjunto(self):
        """El logo tiene que pintarse dentro del correo, no colgar como archivo."""
        proveedor = self._proveedor([])
        proveedor.connect()
        nuevo = mock.MagicMock()
        puesto = mock.MagicMock()
        nuevo.Attachments.Add.return_value = puesto
        proveedor._outlook.CreateItem.return_value = nuevo

        from app.email.base_provider import EmailAttachment
        from app.email.outlook_provider import (PR_ATTACH_CONTENT_ID,
                                                PR_ATTACHMENT_HIDDEN)
        proveedor.send_email(
            "comprador@neogen.com", "Re: RFQ", "<p>hola</p>",
            [EmailAttachment("firma.png", b"\x89PNG", content_id="firma-cgr-isc")])

        puestas = {c.args[0]: c.args[1]
                   for c in puesto.PropertyAccessor.SetProperty.call_args_list}
        self.assertEqual(puestas.get(PR_ATTACH_CONTENT_ID), "firma-cgr-isc")
        self.assertIs(puestas.get(PR_ATTACHMENT_HIDDEN), True)

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


class TestElGuardianDeOutlook(unittest.TestCase):
    """«A program is trying to access email address information».

    Outlook saca ese cuadro cuando se tocan propiedades de LIBRETA DE
    DIRECCIONES —`SenderEmailType`, `Sender`, `GetExchangeUser()`,
    `SenderEmailAddress`—, y hay que aprobarlo a mano en cada correo.
    `PropertyAccessor` sobre las MAPI del mensaje lee lo mismo sin pasar por
    ahí, así que va primero.
    """

    class _ItemVigilado:
        """Un correo que grita si le tocan la libreta de direcciones."""

        def __init__(self, mapi=None):
            self._mapi = mapi or {}
            self.libreta_tocada = []
            self.PropertyAccessor = self._Accesor(self._mapi)

        class _Accesor:
            def __init__(self, mapi):
                self._mapi = mapi

            def GetProperty(self, esquema):
                if esquema in self._mapi:
                    return self._mapi[esquema]
                raise RuntimeError("propiedad no encontrada")

        def __getattr__(self, nombre):
            if nombre in ("SenderEmailType", "Sender", "SenderEmailAddress"):
                self.__dict__.setdefault("libreta_tocada", []).append(nombre)
                raise RuntimeError("El guardián de Outlook pidió permiso")
            raise AttributeError(nombre)

    def _proveedor(self):
        from app.email.outlook_provider import OutlookEmailProvider
        return OutlookEmailProvider.__new__(OutlookEmailProvider)

    def test_la_direccion_sale_sin_tocar_la_libreta(self):
        from app.email.outlook_provider import PR_SENDER_SMTP_ADDRESS
        item = self._ItemVigilado({PR_SENDER_SMTP_ADDRESS: "cliente@acme.com"})

        direccion = self._proveedor()._remitente(item)

        self.assertEqual(direccion, "cliente@acme.com")
        self.assertEqual(item.libreta_tocada, [],
                         "se tocó la libreta habiendo MAPI: saldría el cuadro")

    def test_tambien_vale_la_de_en_nombre_de(self):
        from app.email.outlook_provider import PR_SENT_REPRESENTING_SMTP_ADDRESS
        item = self._ItemVigilado(
            {PR_SENT_REPRESENTING_SMTP_ADDRESS: "ventas@acme.com"})

        self.assertEqual(self._proveedor()._remitente(item), "ventas@acme.com")
        self.assertEqual(item.libreta_tocada, [])

    def test_una_mapi_sin_arroba_no_se_da_por_buena(self):
        """La ruta interna de Exchange (/O=EXCHANGELABS/...) no es una
        dirección: darla por buena dejaría sin respuesta al cliente."""
        from app.email.outlook_provider import PR_SENDER_SMTP_ADDRESS
        item = self._ItemVigilado(
            {PR_SENDER_SMTP_ADDRESS: "/O=EXCHANGELABS/OU=EXCHANGE/CN=RECIPIENTS"})

        from app.email.outlook_provider import AccesoBloqueado
        with self.assertRaises(AccesoBloqueado):
            self._proveedor()._remitente(item)
        # Sin dirección utilizable, sí se cae al respaldo.
        self.assertTrue(item.libreta_tocada)

    def test_sin_mapi_se_cae_al_respaldo(self):
        """Un correo importado de otro sistema puede no traerlas. Entonces sí
        sale el cuadro, pero por uno de cada mil y no por todos."""
        from app.email.outlook_provider import AccesoBloqueado
        item = self._ItemVigilado({})
        # Con el guardián cortando TODO, el correo se queda sin leer y se
        # reintenta: eso ya estaba, y con este cambio pasa mucho menos.
        with self.assertRaises(AccesoBloqueado):
            self._proveedor()._remitente(item)
        self.assertIn("SenderEmailType", item.libreta_tocada)
