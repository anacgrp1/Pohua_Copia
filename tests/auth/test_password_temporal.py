"""Contraseñas temporales: alta sin contraseña, restablecimiento y primer acceso.

Sin base: se simula `app.auth.repository` debajo de las rutas de usuarios y
de sesión, y se comprueba lo que promete la pantalla:

  - el alta devuelve la temporal UNA vez y deja la marca de "cámbiala";
  - restablecer genera otra, la devuelve y (si se pide) la manda al teléfono;
  - mandarla al teléfono sólo funciona con la temporal vigente;
  - nadie se restablece a sí mismo;
  - la generada cumple la política y se lee sin ambigüedad.
"""
from __future__ import annotations

import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.routes.auth as auth_router
import api.routes.users as users_router
from api.security import usuario_actual
from app.auth import passwords, repository
from app.auth.tokens import UsuarioSesion

ADMIN = UsuarioSesion(id=1, correo="admin@x", nombre="Admin", rol="admin", permisos=["admin"])


def _fila(uid=5, **extra):
    base = {"id": uid, "correo": "nic@x", "nombre": "Nic Scherer", "rol": "pm", "externo": False,
            "activo": True, "ultimo_acceso": None, "creado_en": None, "tiene_foto": False,
            "foto_actualizada": None, "debe_cambiar_password": True,
            "password_hash": passwords.hashear("Temp-Kf7m-Qw3p")}
    base.update(extra)
    return base


class TestGenerarTemporal(unittest.TestCase):
    def test_cumple_la_politica_y_es_legible(self):
        for _ in range(50):
            t = passwords.generar_temporal()
            passwords.validar_politica(t)          # no lanza
            self.assertRegex(t, r"^[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}$")
            for confusa in "0O1lI5S":
                self.assertNotIn(confusa, t)

    def test_no_se_repite(self):
        self.assertNotEqual(passwords.generar_temporal(), passwords.generar_temporal())


class TestRutas(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(users_router.router)
        app.include_router(auth_router.router)
        app.dependency_overrides[usuario_actual] = lambda: ADMIN
        self.c = TestClient(app)
        self.repo = mock.patch.multiple(
            repository,
            obtener_por_correo=mock.DEFAULT, obtener_por_id=mock.DEFAULT,
            crear_usuario_temporal=mock.DEFAULT, listar_usuarios=mock.DEFAULT,
            restablecer_password=mock.DEFAULT, cambiar_password=mock.DEFAULT,
            debe_cambiar_password=mock.DEFAULT, datos_foto=mock.DEFAULT,
        ).start()
        self.addCleanup(mock.patch.stopall)
        self.repo["datos_foto"].return_value = (False, None)

    # ---- alta -----------------------------------------------------------

    def test_alta_devuelve_la_temporal_una_vez(self):
        self.repo["obtener_por_correo"].return_value = None
        self.repo["crear_usuario_temporal"].return_value = (5, "Kf7m-Qw3p-Zt9h")
        self.repo["listar_usuarios"].return_value = [_fila()]

        r = self.c.post("/api/users", json={"correo": "Nic@X", "nombre": "Nic", "apellido": "Scherer",
                                            "rol": "pm", "externo": True})
        self.assertEqual(r.status_code, 201, r.text)
        cuerpo = r.json()
        self.assertEqual(cuerpo["password_temporal"], "Kf7m-Qw3p-Zt9h")
        self.assertTrue(cuerpo["debe_cambiar_password"])
        # nombre y apellido juntos, correo en minúsculas, externo respetado
        self.repo["crear_usuario_temporal"].assert_called_once_with(
            "nic@x", "Nic Scherer", "pm", externo=True)

    def test_alta_sin_contrasena_en_el_cuerpo_no_la_acepta(self):
        """El campo `password` ya no existe: si alguien lo manda, se ignora."""
        self.repo["obtener_por_correo"].return_value = None
        self.repo["crear_usuario_temporal"].return_value = (5, "Kf7m-Qw3p-Zt9h")
        self.repo["listar_usuarios"].return_value = [_fila()]
        r = self.c.post("/api/users", json={"correo": "nic@x", "nombre": "Nic", "rol": "pm",
                                            "password": "LaQueYoQuiera-2026"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["password_temporal"], "Kf7m-Qw3p-Zt9h")

    def test_alta_con_correo_repetido(self):
        self.repo["obtener_por_correo"].return_value = _fila()
        r = self.c.post("/api/users", json={"correo": "nic@x", "nombre": "Nic", "rol": "pm"})
        self.assertEqual(r.status_code, 409)

    # ---- restablecer ----------------------------------------------------

    def test_restablecer_genera_y_devuelve(self):
        self.repo["obtener_por_id"].return_value = _fila()
        self.repo["restablecer_password"].return_value = "Abcd-Efgh-Jkmn"
        r = self.c.post("/api/users/5/password/reset", json={})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {"password_temporal": "Abcd-Efgh-Jkmn", "notificada": False,
                                    "dispositivos": 0, "entregados": 0})

    def test_restablecer_y_mandar_al_telefono(self):
        self.repo["obtener_por_id"].return_value = _fila()
        self.repo["restablecer_password"].return_value = "Abcd-Efgh-Jkmn"
        with mock.patch("app.notifications.push.enviar_a_persona",
                        return_value={"dispositivos": 2, "entregados": 1}) as envio:
            r = self.c.post("/api/users/5/password/reset", json={"notificar": True})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["entregados"], 1)
        self.assertTrue(r.json()["notificada"])
        args, kwargs = envio.call_args
        self.assertEqual(args[0], 5)
        self.assertIn("Abcd-Efgh-Jkmn", args[2])   # la temporal va en el cuerpo
        self.assertEqual(kwargs["tag"], "pohua-password")

    def test_nadie_se_restablece_a_si_mismo(self):
        r = self.c.post("/api/users/1/password/reset", json={})
        self.assertEqual(r.status_code, 400)
        self.repo["restablecer_password"].assert_not_called()

    def test_restablecer_a_quien_no_existe(self):
        self.repo["obtener_por_id"].return_value = None
        r = self.c.post("/api/users/99/password/reset", json={})
        self.assertEqual(r.status_code, 404)

    # ---- mandar la vigente ---------------------------------------------

    def test_notificar_solo_la_temporal_vigente(self):
        self.repo["obtener_por_id"].return_value = _fila()
        with mock.patch("app.notifications.push.enviar_a_persona",
                        return_value={"dispositivos": 1, "entregados": 1}) as envio:
            ok = self.c.post("/api/users/5/password/notificar",
                             json={"password_temporal": "Temp-Kf7m-Qw3p"})
            mal = self.c.post("/api/users/5/password/notificar",
                              json={"password_temporal": "Otra-Cosa-1234"})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()["entregados"], 1)
        self.assertEqual(mal.status_code, 409)
        self.assertEqual(envio.call_count, 1)

    def test_notificar_no_vale_si_ya_puso_la_suya(self):
        self.repo["obtener_por_id"].return_value = _fila(debe_cambiar_password=False)
        with mock.patch("app.notifications.push.enviar_a_persona") as envio:
            r = self.c.post("/api/users/5/password/notificar",
                            json={"password_temporal": "Temp-Kf7m-Qw3p"})
        self.assertEqual(r.status_code, 409)
        envio.assert_not_called()

    # ---- la sesión dice si debe cambiarla --------------------------------

    def test_me_lleva_la_marca(self):
        self.repo["debe_cambiar_password"].return_value = True
        r = self.c.get("/api/auth/me")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["debe_cambiar_password"])

    def test_login_con_temporal_avisa_y_recuerda(self):
        sesion = UsuarioSesion(id=5, correo="nic@x", nombre="Nic", rol="pm", permisos=["rfq:leer"])
        self.repo["debe_cambiar_password"].return_value = True
        respuesta = {"access_token": "t", "token_type": "bearer", "expires_in": 1,
                     "usuario": {"id": 5, "correo": "nic@x", "nombre": "Nic",
                                 "rol": "pm", "permisos": ["rfq:leer"]}}
        with mock.patch.object(repository, "autenticar", return_value=sesion), \
             mock.patch.object(auth_router, "emitir", return_value=respuesta), \
             mock.patch("app.notifications.push.enviar_a_todos", return_value=1) as push:
            r = self.c.post("/api/auth/login", json={"correo": "nic@x", "password": "Temp-Kf7m-Qw3p"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["usuario"]["debe_cambiar_password"])
        self.assertEqual(push.call_args.kwargs["usuario_id"], 5)


class TestRepositorio(unittest.TestCase):
    """`cambiar_password` apaga la marca; `temporal=True` la enciende."""

    def test_marca(self):
        cur = mock.MagicMock()
        conn = mock.MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        repository.cambiar_password(5, "Mi-Propia-Clave-2026", conexion=conn)
        self.assertIs(cur.execute.call_args.args[1][1], False)
        repository.cambiar_password(5, "Kf7m-Qw3p-Zt9h", temporal=True, conexion=conn)
        self.assertIs(cur.execute.call_args.args[1][1], True)

    def test_restablecer_devuelve_lo_que_guarda(self):
        with mock.patch.object(repository, "cambiar_password") as cp:
            t = repository.restablecer_password(5)
        passwords.validar_politica(t)
        cp.assert_called_once_with(5, t, temporal=True, conexion=None)


if __name__ == "__main__":
    unittest.main()
