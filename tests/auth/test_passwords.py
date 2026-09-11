"""Hash y política de contraseñas."""

import unittest

from app.auth import passwords


class TestHashear(unittest.TestCase):

    def test_el_hash_no_contiene_la_contrasena(self):
        h = passwords.hashear("una-contrasena-larga")
        self.assertNotIn("una-contrasena-larga", h)

    def test_dos_hashes_de_la_misma_contrasena_son_distintos(self):
        """Salt aleatorio: dos usuarios con la misma contraseña no comparten hash."""
        a = passwords.hashear("una-contrasena-larga")
        b = passwords.hashear("una-contrasena-larga")
        self.assertNotEqual(a, b)
        self.assertTrue(passwords.verificar("una-contrasena-larga", a))
        self.assertTrue(passwords.verificar("una-contrasena-larga", b))

    def test_formato_esperado(self):
        algoritmo, iteraciones, salt, digest = passwords.hashear("otra-contrasena").split("$")
        self.assertEqual(algoritmo, "pbkdf2_sha256")
        self.assertGreaterEqual(int(iteraciones), 100_000)
        self.assertTrue(salt and digest)


class TestVerificar(unittest.TestCase):

    def setUp(self):
        self.hash = passwords.hashear("la-buena-de-verdad")

    def test_correcta(self):
        self.assertTrue(passwords.verificar("la-buena-de-verdad", self.hash))

    def test_incorrecta(self):
        self.assertFalse(passwords.verificar("la-mala", self.hash))

    def test_entradas_degeneradas_no_lanzan(self):
        """Un hash corrupto o ausente debe ser un False, nunca una excepción:
        la columna password_hash de la migración 005 admite NULL."""
        casos = [
            ("algo", None),
            ("algo", ""),
            ("algo", "no-tiene-formato"),
            ("algo", "pbkdf2_sha256$mal$mal$mal"),
            ("algo", "otro_algoritmo$1000$c2FsdA==$aGFzaA=="),
            ("", self.hash),
            (None, self.hash),
        ]
        for password, hash_guardado in casos:
            with self.subTest(hash=hash_guardado):
                self.assertFalse(passwords.verificar(password, hash_guardado))


class TestPolitica(unittest.TestCase):

    def test_acepta_una_contrasena_razonable(self):
        passwords.validar_politica("cotizador-planta-2026")  # no lanza

    def test_rechaza_las_malas(self):
        malas = ["", "corta", "12345678901", "password123", "aaaaaaaaaaaaaaa"]
        for mala in malas:
            with self.subTest(password=mala):
                with self.assertRaises(passwords.PasswordInvalida):
                    passwords.validar_politica(mala)


class TestRehash(unittest.TestCase):

    def test_hash_con_pocas_iteraciones_pide_rehash(self):
        viejo = passwords.hashear("una-contrasena-larga", iteraciones=1000)
        self.assertTrue(passwords.necesita_rehash(viejo))
        # Y sigue validando, para no dejar fuera a nadie al subir el coste.
        self.assertTrue(passwords.verificar("una-contrasena-larga", viejo))

    def test_hash_actual_no_pide_rehash(self):
        self.assertFalse(passwords.necesita_rehash(passwords.hashear("una-contrasena-larga")))


if __name__ == "__main__":
    unittest.main()
