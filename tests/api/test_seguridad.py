"""Regresiones de seguridad de la capa HTTP.

Cada test de aquí corresponde a un agujero que existió de verdad. Si alguno
vuelve a fallar, es que el agujero volvió.
"""

import os
import unittest

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")
os.environ.setdefault("JWT_SECRET", "clave-de-pruebas-suficientemente-larga-1234567890")

from fastapi.testclient import TestClient  # noqa: E402

import api.server as server  # noqa: E402
from app.auth.tokens import UsuarioSesion, emitir  # noqa: E402


def _cabecera(permisos, correo="pm@cgr.com", rol="pm"):
    token = emitir(UsuarioSesion(id=1, correo=correo, nombre="Prueba",
                                 rol=rol, permisos=list(permisos)))["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestPathTraversal(unittest.TestCase):
    """El catch-all de la SPA servía cualquier archivo del servidor.

    ``GET /%2e%2e/.env`` devolvía el .env entero, con el DSN de Neon, la
    ANTHROPIC_API_KEY y la contraseña de IMAP dentro. Starlette no normaliza la
    ruta, así que el ``..`` codificado llegaba tal cual a ``FRONTEND_DIR / ruta``.
    """

    def setUp(self):
        self.cliente = TestClient(server.app)

    def test_no_sirve_archivos_fuera_de_frontend(self):
        rutas = [
            "/../.env",
            "/%2e%2e/.env",
            "/..%2f.env",
            "/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "/css/../../.env",
            "/%2e%2e/%2e%2e/%2e%2e/etc/passwd",
            "/....//.env",
        ]
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                respuesta = self.cliente.get(ruta)
                cuerpo = respuesta.text
                # Se devuelve el index.html de la SPA, nunca el archivo pedido.
                self.assertNotIn("DATABASE_URL", cuerpo)
                self.assertNotIn("ANTHROPIC_API_KEY", cuerpo)
                self.assertNotIn("JWT_SECRET", cuerpo)
                self.assertNotIn("root:x:", cuerpo)

    def test_ruta_de_api_inexistente_devuelve_404(self):
        """Antes el catch-all devolvía el index.html con 200 para /api/loquesea,
        así que un endpoint mal escrito parecía funcionar."""
        respuesta = self.cliente.get("/api/endpoint-que-no-existe")
        self.assertEqual(respuesta.status_code, 404)


class TestEndpointsProtegidos(unittest.TestCase):
    """La API entera estaba abierta: cualquiera con la URL podía declinar un
    RFQ, lo que dispara un correo al comprador."""

    def setUp(self):
        self.cliente = TestClient(server.app)

    def test_sin_sesion_todo_responde_401(self):
        peticiones = [
            ("GET", "/api/status"),
            ("GET", "/api/rfqs"),
            ("GET", "/api/rfqs/RFQ-1"),
            ("POST", "/api/rfqs/RFQ-1/approve"),
            ("POST", "/api/rfqs/RFQ-1/decline"),
            ("POST", "/api/price"),
            ("POST", "/api/pipeline/run"),
            ("POST", "/api/worker/start"),
            ("POST", "/api/worker/stop"),
            ("GET", "/api/auth/me"),
        ]
        for metodo, ruta in peticiones:
            with self.subTest(ruta=f"{metodo} {ruta}"):
                respuesta = self.cliente.request(metodo, ruta, json={})
                self.assertEqual(respuesta.status_code, 401, f"{metodo} {ruta} quedó abierto")

    def test_health_y_login_siguen_abiertos(self):
        """Render necesita la sonda, y al login hay que poder llegar sin sesión."""
        self.assertEqual(self.cliente.get("/api/health").status_code, 200)
        # 401 (credenciales malas) o 503 (sin base) — lo que no puede es ser 401
        # por falta de token: la ruta tiene que ser alcanzable.
        respuesta = self.cliente.post("/api/auth/login",
                                      json={"correo": "x@y.z", "password": "nope"})
        self.assertIn(respuesta.status_code, (401, 503))

    def test_token_firmado_con_otro_secreto_se_rechaza(self):
        import jwt
        falso = jwt.encode(
            {"iss": "cgr-cotizador", "sub": "1", "permisos": ["admin"], "exp": 9_999_999_999},
            "un-secreto-que-no-es-el-nuestro-pero-igual-de-largo", algorithm="HS256")
        respuesta = self.cliente.get("/api/status",
                                     headers={"Authorization": f"Bearer {falso}"})
        self.assertEqual(respuesta.status_code, 401)

    def test_token_expirado_se_rechaza(self):
        token = emitir(UsuarioSesion(id=1, correo="a@b.c", nombre="A", rol="admin",
                                     permisos=["admin"]), minutos=-1)["access_token"]
        respuesta = self.cliente.get("/api/status",
                                     headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(respuesta.status_code, 401)

    def test_sesion_sin_el_permiso_recibe_403_no_401(self):
        """Distinguirlos importa: 401 manda al login, 403 no.

        El rol es un dato de prueba: lo que se ejercita es la comprobación del
        permiso, no un rol concreto del catálogo.
        """
        cabecera = _cabecera(["rfq:leer"], rol="rol-solo-lectura")
        respuesta = self.cliente.post("/api/rfqs/RFQ-1/decline", json={}, headers=cabecera)
        self.assertEqual(respuesta.status_code, 403)
        self.assertIn("rfq:dictaminar", respuesta.json()["detail"])

    def test_admin_puede_con_todo(self):
        cabecera = _cabecera(["admin"], rol="admin")
        self.assertEqual(self.cliente.get("/api/status", headers=cabecera).status_code, 200)


class TestSuperficieDeLaApi(unittest.TestCase):
    """Red de seguridad: si mañana se añade un endpoint que escribe y se olvida
    la dependencia de sesión, este test lo caza."""

    #: Rutas que pueden vivir sin sesión, con el motivo.
    PUBLICAS = {
        "/api/auth/login": "hay que poder llegar al login sin sesión",
        "/api/health": "sonda de vida de Render",
        "/api/worker/heartbeat": "la app de escritorio se autentica con secreto compartido",
    }

    def test_todo_endpoint_de_api_exige_sesion(self):
        cliente = TestClient(server.app)
        esquema = server.app.openapi()

        for ruta, metodos in esquema.get("paths", {}).items():
            if not ruta.startswith("/api/"):
                continue
            if ruta in self.PUBLICAS:
                continue
            for metodo in metodos:
                if metodo.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                    continue
                # Se sustituyen los parámetros de ruta por un valor cualquiera.
                concreta = ruta.replace("{rfq_id}", "RFQ-1")
                with self.subTest(endpoint=f"{metodo.upper()} {ruta}"):
                    respuesta = cliente.request(metodo.upper(), concreta, json={})
                    self.assertEqual(
                        respuesta.status_code, 401,
                        f"{metodo.upper()} {ruta} responde {respuesta.status_code} "
                        "sin sesión: le falta Depends(exige(...)) o hay que "
                        "declararla en PUBLICAS con su motivo.")


class TestHeartbeat(unittest.TestCase):
    """El heartbeat tenía el secreto 'default_secret_for_dev' por omisión: quien
    lo supiera podía dejar el worker del servidor en espera indefinida, y las
    RFQ dejaban de procesarse sin que nada fallara a la vista."""

    def setUp(self):
        self.cliente = TestClient(server.app)
        import app.core.config as config
        self.config = config
        self.original = config.settings.WORKER_SECRET_KEY

    def tearDown(self):
        self.config.settings.WORKER_SECRET_KEY = self.original

    def test_sin_secreto_configurado_el_endpoint_se_apaga(self):
        self.config.settings.WORKER_SECRET_KEY = ""
        respuesta = self.cliente.post("/api/worker/heartbeat",
                                      json={"secret_key": "default_secret_for_dev"})
        self.assertEqual(respuesta.status_code, 503)

    def test_secreto_incorrecto_se_rechaza(self):
        self.config.settings.WORKER_SECRET_KEY = "el-secreto-bueno"
        respuesta = self.cliente.post("/api/worker/heartbeat",
                                      json={"secret_key": "el-secreto-malo"})
        self.assertEqual(respuesta.status_code, 403)

    def test_secreto_correcto_se_acepta(self):
        self.config.settings.WORKER_SECRET_KEY = "el-secreto-bueno"
        respuesta = self.cliente.post("/api/worker/heartbeat",
                                      json={"secret_key": "el-secreto-bueno"})
        self.assertEqual(respuesta.status_code, 200)


class TestCors(unittest.TestCase):
    """Estaba en allow_origins=['*'] junto con allow_credentials=True."""

    def test_no_se_permite_cualquier_origen(self):
        import app.core.config as config
        self.assertNotIn("*", config.settings.cors_origins)


if __name__ == "__main__":
    unittest.main()
