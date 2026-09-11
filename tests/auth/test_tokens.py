"""Emisión y lectura de tokens de sesión."""

import os
import unittest

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

import app.core.config as config  # noqa: E402
from app.auth import tokens  # noqa: E402

_SECRETO = "clave-de-pruebas-suficientemente-larga-1234567890"


class BaseToken(unittest.TestCase):

    def setUp(self):
        self.original = config.settings.JWT_SECRET
        config.settings.JWT_SECRET = _SECRETO
        self.usuario = tokens.UsuarioSesion(
            id=7, correo="pm@cgr.com", nombre="Plant Manager",
            rol="pm", permisos=["rfq:leer", "rfq:dictaminar"])

    def tearDown(self):
        config.settings.JWT_SECRET = self.original


class TestIdaYVuelta(BaseToken):

    def test_lo_emitido_se_lee_igual(self):
        token = tokens.emitir(self.usuario)["access_token"]
        leido = tokens.leer(token)
        self.assertEqual(leido.id, 7)
        self.assertEqual(leido.correo, "pm@cgr.com")
        self.assertEqual(leido.rol, "pm")
        self.assertEqual(leido.permisos, ["rfq:leer", "rfq:dictaminar"])

    def test_la_respuesta_de_login_no_lleva_el_hash(self):
        respuesta = tokens.emitir(self.usuario)
        self.assertNotIn("password_hash", respuesta["usuario"])
        self.assertEqual(set(respuesta["usuario"]),
                         {"id", "correo", "nombre", "rol", "permisos"})


class TestRechazos(BaseToken):

    def test_token_vacio(self):
        with self.assertRaises(tokens.TokenInvalido):
            tokens.leer("")

    def test_token_manipulado(self):
        token = tokens.emitir(self.usuario)["access_token"]
        cabecera, cuerpo, firma = token.split(".")
        with self.assertRaises(tokens.TokenInvalido):
            tokens.leer(f"{cabecera}.{cuerpo}.{firma[:-4]}xxxx")

    def test_token_de_otro_emisor(self):
        """Un token válido de otro sistema que compartiera secreto no entra."""
        import jwt
        ajeno = jwt.encode({"iss": "otra-app", "sub": "1", "exp": 9_999_999_999},
                           _SECRETO, algorithm="HS256")
        with self.assertRaises(tokens.TokenInvalido):
            tokens.leer(ajeno)

    def test_token_expirado(self):
        token = tokens.emitir(self.usuario, minutos=-1)["access_token"]
        with self.assertRaises(tokens.TokenInvalido):
            tokens.leer(token)

    def test_sin_secreto_no_se_emite_ni_se_lee(self):
        """Sin JWT_SECRET se firmaría con cadena vacía y cualquiera podría
        fabricarse una sesión: mejor fallar ruidosamente."""
        token = tokens.emitir(self.usuario)["access_token"]
        config.settings.JWT_SECRET = ""
        with self.assertRaises(tokens.TokenInvalido):
            tokens.emitir(self.usuario)
        with self.assertRaises(tokens.TokenInvalido):
            tokens.leer(token)


class TestPermisos(BaseToken):

    def test_permiso_concreto(self):
        self.assertTrue(self.usuario.puede("rfq:dictaminar"))
        self.assertFalse(self.usuario.puede("usuario:gestionar"))

    def test_admin_concede_todo(self):
        admin = tokens.UsuarioSesion(id=1, correo="a@b.c", nombre="A",
                                     rol="admin", permisos=["admin"])
        self.assertTrue(admin.puede("lo-que-sea"))


if __name__ == "__main__":
    unittest.main()
