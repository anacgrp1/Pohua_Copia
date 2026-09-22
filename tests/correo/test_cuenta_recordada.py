# -*- coding: utf-8 -*-
"""La cuenta de envío se busca una vez, no en cada correo.

Por qué existe
--------------
Recorrer `Session.Accounts` y leer su `SmtpAddress` es, palabra por palabra,
lo que el guardián de Outlook llama «email address information stored in
Outlook»: cada recorrido puede levantar el cuadro de «A program is trying to
access…».

Y se hacía en CADA envío. La bandeja de salida se vacía en cada ciclo del
lector, así que el cuadro salía una y otra vez. Eso no es sólo molesto: darle
a Permitir muchas veces al día es exactamente la costumbre que hace que un día
alguien se lo dé a algo que no era esto.
"""

from app.email.outlook_provider import OutlookEmailProvider


class TestSoloSePreguntaUnaVez:

    def _proveedor(self, encontrada="CUENTA"):
        p = OutlookEmailProvider()
        p._veces = 0

        def buscar(buzon):
            p._veces += 1
            return encontrada if buzon == "ventas@ejemplo.com" else None

        p._buscar_cuenta = buscar
        return p

    def test_veinte_correos_un_solo_recorrido(self):
        p = self._proveedor()
        for _ in range(20):
            p._cuenta("ventas@ejemplo.com")
        assert p._veces == 1

    def test_tambien_se_recuerda_que_no_estaba(self):
        # Un buzón que no está en el perfil tampoco va a aparecer solo.
        # Sin recordar el "no", cada envío pagaría otro cuadro de permiso para
        # volver a no encontrarlo — el caso peor, porque es el que además
        # manda el correo "en nombre de" y ya va con una pega.
        p = self._proveedor()
        for _ in range(20):
            assert p._cuenta("nadie@ejemplo.com") is None
        assert p._veces == 1

    def test_da_igual_como_se_escriba_el_buzon(self):
        p = self._proveedor()
        p._cuenta("ventas@ejemplo.com")
        assert p._cuenta("VENTAS@Ejemplo.COM") == "CUENTA"
        assert p._veces == 1

    def test_dos_buzones_distintos_se_buscan_cada_uno(self):
        # El recuerdo es por buzón, no uno global: si alguien cambia
        # OUTLOOK_BUZON en caliente, el nuevo se busca.
        p = self._proveedor()
        p._cuenta("ventas@ejemplo.com")
        p._cuenta("otro@ejemplo.com")
        assert p._veces == 2

    def test_lo_que_devuelve_no_cambia_por_recordarlo(self):
        p = self._proveedor()
        primera = p._cuenta("ventas@ejemplo.com")
        assert primera == "CUENTA"
        assert p._cuenta("ventas@ejemplo.com") is primera

    def test_cada_proveedor_tiene_su_recuerdo(self):
        # Si el diccionario fuera de la clase y no de la instancia, una
        # prueba contaminaría a la siguiente y, peor, reconectar a Outlook no
        # volvería a mirar las cuentas.
        a, b = self._proveedor(), self._proveedor()
        a._cuenta("ventas@ejemplo.com")
        b._cuenta("ventas@ejemplo.com")
        assert a._veces == 1 and b._veces == 1
