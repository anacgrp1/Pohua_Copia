"""La foto de perfil viaja igual en el login que en /me.

EL FALLO QUE ESTO GUARDA: el cuerpo del login no incluía `tiene_foto` ni
`foto_actualizada`. La PWA guarda ese usuario tal cual al entrar, así que la
barra de la esquina se pintaba con las iniciales aunque la persona tuviera
foto; sólo aparecía al RECARGAR, cuando el arranque vuelve a pedir /me y esa
respuesta sí las traía.

Eran dos respuestas describiendo al mismo usuario de dos maneras distintas.
Estos tests las comparan campo por campo para que no puedan volver a
discrepar.
"""

import os
import unittest
from unittest import mock

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")
os.environ.setdefault("JWT_SECRET", "clave-de-pruebas-suficientemente-larga-1234567890")

from fastapi.testclient import TestClient  # noqa: E402

import api.server as server  # noqa: E402
from app.auth.tokens import UsuarioSesion, emitir  # noqa: E402

USUARIO = UsuarioSesion(id=7, correo="pm@cgr.com", nombre="MiguelAngel Rodea",
                        rol="pm", permisos=["rfq:leer"])
SELLO = "2026-09-08 11:30:00"


def _cabecera():
    return {"Authorization": f"Bearer {emitir(USUARIO)['access_token']}"}


class TestFotoEnLasRespuestasDeSesion(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(server.app)

    def _login(self, con_foto):
        """Login real, con la base y el hash simulados."""
        with mock.patch("api.routes.auth.repository.autenticar", return_value=USUARIO), \
             mock.patch("api.routes.auth.repository.datos_foto",
                        return_value=(con_foto, SELLO if con_foto else None)):
            respuesta = self.cliente.post(
                "/api/auth/login",
                json={"correo": USUARIO.correo, "password": "lo-que-sea-12345"})
        self.assertEqual(respuesta.status_code, 200, respuesta.text)
        return respuesta.json()["usuario"]

    def _me(self, con_foto):
        with mock.patch("api.routes.auth.repository.datos_foto",
                        return_value=(con_foto, SELLO if con_foto else None)):
            respuesta = self.cliente.get("/api/auth/me", headers=_cabecera())
        self.assertEqual(respuesta.status_code, 200, respuesta.text)
        return respuesta.json()

    def test_login_trae_la_foto(self):
        """Sin esto, la esquina enseña iniciales hasta que se recarga."""
        usuario = self._login(con_foto=True)
        self.assertTrue(usuario["tiene_foto"])
        self.assertEqual(usuario["foto_actualizada"], SELLO)

    def test_login_sin_foto_lo_dice_explicitamente(self):
        usuario = self._login(con_foto=False)
        self.assertFalse(usuario["tiene_foto"])
        self.assertIsNone(usuario["foto_actualizada"])

    def test_login_y_me_describen_al_usuario_igual(self):
        """El corazón del asunto: las dos respuestas, campo por campo."""
        for con_foto in (True, False):
            with self.subTest(con_foto=con_foto):
                self.assertEqual(self._login(con_foto), self._me(con_foto))

    def test_una_base_caida_no_impide_entrar(self):
        """La cara es un adorno; la sesión no puede depender de ella."""
        with mock.patch("api.routes.auth.repository.autenticar", return_value=USUARIO), \
             mock.patch("api.routes.auth.repository.datos_foto",
                        side_effect=RuntimeError("la base se cayó")):
            respuesta = self.cliente.post(
                "/api/auth/login",
                json={"correo": USUARIO.correo, "password": "lo-que-sea-12345"})
        self.assertEqual(respuesta.status_code, 200, respuesta.text)
        self.assertFalse(respuesta.json()["usuario"]["tiene_foto"])


if __name__ == "__main__":
    unittest.main()
