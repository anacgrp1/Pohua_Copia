"""La comprobación previa al ensayo general.

Lo que se protege: que cuente bien lo que falta, que un fallo en una
comprobación no se lleve por delante el informe entero —es justo cuando más
falta hace verlo— y que `con_buzon=False` no toque la red.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

import app.core.config as config
import app.core.preflight as preflight


def _todo_bien(extra=None):
    """Parchea el mundo para que todo conteste que sí."""
    ajustes = {"APP_ENV": "prod", "DATABASE_URL": "postgresql://u:p@neon.tech/db",
               "JWT_SECRET": "x" * 40, "ANTHROPIC_API_KEY": "sk-x",
               "MAIL_MODE": "imap", "MAIL_FOLDER": "TEST",
               "IMAP_SERVER": "outlook.office365.com", "IMAP_USER": "a@b.com",
               "IMAP_PASSWORD": "x", "RECORDATORIO_HORAS": 4,
               "APP_URL": "https://pohua.example", "WORKER_SECRET_KEY": "s" * 20,
               "INTERVALO_MINUTOS": 5}
    ajustes.update(extra or {})
    parches = [mock.patch.object(config.settings, k, v) for k, v in ajustes.items()]
    parches += [
        mock.patch("app.persistence.migraciones.estado",
                   return_value={"disponible": True, "aplicadas": ["a", "b"], "pendientes": []}),
        mock.patch("app.email.outbound.envio_habilitado", return_value=False),
        mock.patch("app.notifications.push.habilitado", return_value=True),
        mock.patch("app.notifications.push.listar",
                   return_value=[{"correo": "rodea@isc.com"}]),
        mock.patch("app.auth.repository.usuarios_con_permiso",
                   return_value=[{"nombre": "Rodea", "correo": "rodea@isc.com"}]),
    ]
    return parches


class _Parcheado:
    def __init__(self, parches):
        self.parches = parches

    def __enter__(self):
        for p in self.parches:
            p.start()
        return self

    def __exit__(self, *_):
        mock.patch.stopall()
        return False


class _ServidorFalso:
    """Lo mínimo de `api.server` que mira el preflight: cuándo fue el latido."""

    def __init__(self, hace_segundos=None):
        import time
        self._last_heartbeat_time = 0.0 if hace_segundos is None else time.time() - hace_segundos


class TestAplicacionDeEscritorio(unittest.TestCase):
    """El respaldo: si lee la app de escritorio, el servidor no necesita buzón."""

    def _con_latido(self, hace_segundos):
        import sys
        return mock.patch.dict(sys.modules, {"api.server": _ServidorFalso(hace_segundos)})

    def test_leyendo_ella_no_falta_nada_en_el_servidor(self):
        with _Parcheado(_todo_bien({"IMAP_PASSWORD": "", "IMAP_USER": ""})), \
             self._con_latido(60):
            informe = preflight.revisar(con_buzon=True)

        self.assertTrue(informe["listo"], [p for p in informe["puntos"]
                                           if p["estado"] == "falta"])
        self.assertTrue(any("aplicación de escritorio está leyendo" in p["titulo"]
                            for p in informe["puntos"] if p["estado"] == "ok"))
        # Y las credenciales que faltan se dicen, pero como aviso, no como fallo.
        credenciales = [p for p in informe["puntos"]
                        if "credenciales del buzón" in p["titulo"]]
        self.assertEqual([p["estado"] for p in credenciales], ["ojo"])

    def test_un_latido_viejo_no_cuenta(self):
        """Si dejó de latir, el buzón se queda sin nadie: eso sí es un fallo."""
        with _Parcheado(_todo_bien({"IMAP_PASSWORD": ""})), \
             self._con_latido(3 * 3600):
            informe = preflight.revisar(con_buzon=True)
        self.assertFalse(informe["listo"])
        self.assertTrue(any("Faltan credenciales del buzón" in p["titulo"]
                            for p in informe["puntos"] if p["estado"] == "falta"))

    def test_sin_secreto_compartido_el_latido_no_puede_llegar(self):
        """Con el latido llegando, el secreto está bien por definición; el
        aviso es para cuando NO llega y encima no podría llegar."""
        with _Parcheado(_todo_bien({"WORKER_SECRET_KEY": ""})), self._con_latido(None):
            informe = preflight.revisar(con_buzon=False)
        self.assertTrue(any("WORKER_SECRET_KEY" in p["titulo"]
                            for p in informe["puntos"] if p["estado"] == "ojo"))


class TestInforme(unittest.TestCase):

    def test_con_todo_puesto_esta_listo(self):
        with _Parcheado(_todo_bien()):
            informe = preflight.revisar(con_buzon=False)
        self.assertTrue(informe["listo"])
        self.assertEqual(informe["bloqueantes"], 0)
        self.assertFalse(informe["buzon_comprobado"])
        # El informe se lee de arriba abajo: cada punto sabe de qué grupo es.
        self.assertTrue(all(p["grupo"] for p in informe["puntos"]))

    def test_lo_que_falta_se_cuenta_y_se_nombra(self):
        with _Parcheado(_todo_bien({"ANTHROPIC_API_KEY": "", "APP_URL": "",
                                    "WEB_SERVER_URL": "http://localhost:8000"})):
            informe = preflight.revisar(con_buzon=False)
        titulos = [p["titulo"] for p in informe["puntos"] if p["estado"] == "falta"]
        self.assertFalse(informe["listo"])
        self.assertIn("Falta ANTHROPIC_API_KEY", titulos)
        self.assertIn("Falta APP_URL", titulos)
        self.assertEqual(informe["bloqueantes"], len(titulos))

    def test_sin_credenciales_del_buzon_no_se_intenta_conectar(self):
        with _Parcheado(_todo_bien({"IMAP_PASSWORD": ""})), \
             mock.patch("app.email.factory.EmailProviderFactory.get_provider") as fabrica:
            informe = preflight.revisar(con_buzon=True)
        fabrica.assert_not_called()
        self.assertTrue(any("credenciales del buzón" in p["titulo"]
                            for p in informe["puntos"] if p["estado"] == "falta"))

    def test_con_buzon_apagado_no_se_toca_la_red(self):
        with _Parcheado(_todo_bien()), \
             mock.patch("app.email.factory.EmailProviderFactory.get_provider") as fabrica:
            preflight.revisar(con_buzon=False)
        fabrica.assert_not_called()

    def test_la_bandeja_de_entrada_se_avisa(self):
        """Probar contra INBOX no es un fallo, pero hay que decirlo."""
        with _Parcheado(_todo_bien({"MAIL_FOLDER": "INBOX"})):
            informe = preflight.revisar(con_buzon=False)
        self.assertTrue(any("BANDEJA DE ENTRADA" in p["titulo"]
                            for p in informe["puntos"] if p["estado"] == "ojo"))

    def test_una_comprobacion_que_revienta_no_tumba_el_informe(self):
        with _Parcheado(_todo_bien()), \
             mock.patch.object(preflight, "_avisos", side_effect=RuntimeError("boom")):
            informe = preflight.revisar(con_buzon=False)
        # Sigue habiendo informe, con el fallo dentro y contado.
        self.assertTrue(any(p["titulo"] == "Una comprobación falló"
                            for p in informe["puntos"]))
        self.assertTrue(any(p["grupo"] == "Lector y calculadoras"
                            for p in informe["puntos"]))
        self.assertFalse(informe["listo"])


if __name__ == "__main__":
    unittest.main()
