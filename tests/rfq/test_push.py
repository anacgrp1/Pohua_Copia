"""Los avisos en el teléfono (app/notifications/push.py).

Sin base ni red: se simulan la lista de suscripciones y `pywebpush.webpush`,
y se prueban las reglas: qué se manda, a quién, y qué pasa con un dispositivo
que ya no existe.
"""
from __future__ import annotations

import json
import unittest
from unittest import mock

import app.notifications.push as push


def _sub(i=1):
    return {"id": i, "usuario_id": 7, "usuario_correo": "pm@x", "endpoint": f"https://push.example/{i}",
            "p256dh": "BP-clave", "auth": "auth", "navegador": "Chrome", "creada_en": None,
            "ultimo_envio": None, "fallos": 0}


class _Config:
    VAPID_PUBLIC_KEY = "pub"
    VAPID_PRIVATE_KEY = "priv"
    VAPID_SUBJECT = ""
    IMAP_USER = "buzon@x"
    GRAPH_USER = None
    SMTP_USER = None


class TestPush(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(push, "_config", return_value=_Config()),
                  mock.patch.object(push, "_anotar_resultado")):
            p.start(); self.addCleanup(p.stop)

    def test_sin_claves_no_hay_push(self):
        with mock.patch.object(push, "_config", return_value=type("C", (), {"VAPID_PUBLIC_KEY": "", "VAPID_PRIVATE_KEY": ""})()):
            self.assertFalse(push.habilitado())
            self.assertEqual(push.enviar_a_todos("t", "c", "RFQ-1"), 0)

    def test_valida_la_suscripcion(self):
        with self.assertRaises(ValueError):
            push._validar({"endpoint": "http://inseguro", "keys": {"p256dh": "a", "auth": "b"}})
        with self.assertRaises(ValueError):
            push._validar({"endpoint": "https://ok", "keys": {"p256dh": "a"}})
        s = push._validar({"endpoint": "https://ok", "keys": {"p256dh": "a", "auth": "b"}})
        self.assertEqual(s["endpoint"], "https://ok")

    def test_manda_a_cada_dispositivo_con_la_carga_del_rfq(self):
        llamadas = []
        def webpush_falso(**kw):
            llamadas.append(kw); return "ok"
        with mock.patch.object(push, "listar", return_value=[_sub(1), _sub(2)]), \
             mock.patch.dict("sys.modules", {"pywebpush": mock.Mock(webpush=webpush_falso, WebPushException=Exception)}):
            n = push.enviar_a_todos("RFQ-9: necesita tu dictamen", "PN 1060", "RFQ-9",
                                    nivel="warn", en_segundo_plano=False)
        self.assertEqual(n, 2)
        self.assertEqual(len(llamadas), 2)
        carga = json.loads(llamadas[0]["data"])
        self.assertEqual(carga["url"], "/#/rfq/RFQ-9")
        self.assertEqual(carga["tag"], "rfq-RFQ-9")
        self.assertEqual(carga["nivel"], "warn")
        self.assertEqual(llamadas[0]["vapid_claims"], {"sub": "mailto:buzon@x"})
        self.assertEqual(llamadas[0]["subscription_info"]["endpoint"], "https://push.example/1")

    def test_un_dispositivo_muerto_se_da_de_baja(self):
        class Excepcion(Exception):
            def __init__(self, codigo):
                super().__init__("gone"); self.response = mock.Mock(status_code=codigo)
        def webpush_falso(**kw):
            raise Excepcion(410)
        modulo = mock.Mock(webpush=webpush_falso, WebPushException=Excepcion)
        with mock.patch.object(push, "listar", return_value=[_sub(5)]), \
             mock.patch.dict("sys.modules", {"pywebpush": modulo}):
            push.enviar_a_todos("t", "c", "RFQ-1", en_segundo_plano=False)
        push._anotar_resultado.assert_called_once_with(5, ok=False, muerta=True)

    def test_un_fallo_transitorio_no_da_de_baja(self):
        class Excepcion(Exception):
            def __init__(self):
                super().__init__("503"); self.response = mock.Mock(status_code=503)
        def webpush_falso(**kw):
            raise Excepcion()
        with mock.patch.object(push, "listar", return_value=[_sub(5)]), \
             mock.patch.dict("sys.modules", {"pywebpush": mock.Mock(webpush=webpush_falso, WebPushException=Excepcion)}):
            push.enviar_a_todos("t", "c", "RFQ-1", en_segundo_plano=False)
        push._anotar_resultado.assert_called_once_with(5, ok=False, muerta=False)


if __name__ == "__main__":
    unittest.main()
