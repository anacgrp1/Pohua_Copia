import os
import tempfile
import unittest

from app.core.config import Settings
from app.core.exceptions import ConfigurationError


class TestConfigSystem(unittest.TestCase):

    def setUp(self):
        # Limpiar variables clave de entorno del sistema antes de cada prueba
        self.original_env = dict(os.environ)

        # Lista de variables a limpiar
        self.keys_to_clear = [
            "APP_ENV", "AUTH_METHOD", "MAIL_MODE",
            "IMAP_SERVER", "IMAP_HOST", "IMAP_PORT", "IMAP_USER", "IMAP_PASSWORD", "IMAP_FOLDER",
            "SMTP_SERVER", "SMTP_PORT", "SMTP_USE_TLS",
            "AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_CLIENT_SECRET",
            "GRAPH_CLIENT_ID", "GRAPH_TENANT_ID", "GRAPH_CLIENT_SECRET", "GRAPH_USER",
            "PG_HOST", "PG_PORT", "PG_DATABASE", "PG_USER", "PG_PASSWORD",
            "INTERVALO_MINUTOS", "ANTHROPIC_API_KEY", "VISION_MODEL",
            "VISION_MAX_TOKENS", "VISION_TEMPERATURE"
        ]
        for key in self.keys_to_clear:
            if key in os.environ:
                del os.environ[key]

    def tearDown(self):
        # Restaurar variables originales de entorno
        os.environ.clear()
        os.environ.update(self.original_env)

    def create_temp_env_file(self, content: str) -> str:
        """Crea un archivo temporal con el contenido env dado y retorna su ruta."""
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, "temp_config.env")
        with open(temp_file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return temp_file_path

    def test_default_env_loading(self):
        """Verifica que se lea correctamente un .env con la plantilla del proyecto.

        Antes apuntaba al ``../.env`` real de la máquina, así que el resultado
        dependía de cómo tuviera cada quien configurado su entorno: en una
        máquina con credenciales reales fallaba por valor distinto, y en una
        sin .env fallaba por variable crítica ausente. Ahora el archivo se
        construye aquí, con el mismo contenido de la plantilla.
        """
        content = """
        APP_ENV=dev
        AUTH_METHOD=local
        IMAP_SERVER=imap.example.com
        IMAP_PORT=993
        IMAP_USER=usuario@example.com
        IMAP_PASSWORD=secreto
        SMTP_USE_TLS=True
        """
        temp_env = self.create_temp_env_file(content)

        settings = Settings(env_file_path=temp_env)

        # Validar valores según nuestra plantilla .env
        self.assertEqual(settings.APP_ENV, "dev")
        self.assertEqual(settings.AUTH_METHOD, "local")
        self.assertEqual(settings.IMAP_SERVER, "imap.example.com")
        self.assertEqual(settings.IMAP_PORT, 993)
        self.assertEqual(settings.SMTP_USE_TLS, True)

        # Limpieza
        try:
            os.remove(temp_env)
        except OSError:
            pass

    def test_type_conversion(self):
        """Prueba que los tipos sean convertidos de forma correcta (int, bool, str)."""
        content = """
        APP_ENV=dev
        AUTH_METHOD=local
        IMAP_SERVER=imap.test.com
        IMAP_PORT=143
        IMAP_USER=test@test.com
        IMAP_PASSWORD=pass
        SMTP_PORT=25
        SMTP_USE_TLS=False
        """
        temp_env = self.create_temp_env_file(content)

        settings = Settings(env_file_path=temp_env)
        self.assertIsInstance(settings.IMAP_PORT, int)
        self.assertEqual(settings.IMAP_PORT, 143)

        self.assertIsInstance(settings.SMTP_PORT, int)
        self.assertEqual(settings.SMTP_PORT, 25)

        self.assertIsInstance(settings.SMTP_USE_TLS, bool)
        self.assertFalse(settings.SMTP_USE_TLS)

        # Limpieza
        try:
            os.remove(temp_env)
        except OSError:
            pass

    def test_missing_critical_var_local(self):
        """Prueba que falten variables críticas en el modo local y arroje error."""
        content = """
        APP_ENV=dev
        AUTH_METHOD=local
        # Falta IMAP_SERVER o IMAP_USER
        """
        temp_env = self.create_temp_env_file(content)

        with self.assertRaises(ConfigurationError) as ctx:
            Settings(env_file_path=temp_env)

        self.assertIn("Falta variable crítica para AUTH_METHOD='local'", str(ctx.exception))

        # Limpieza
        try:
            os.remove(temp_env)
        except OSError:
            pass

    def test_missing_critical_var_token(self):
        """Prueba que falten variables críticas en el modo token y arroje error."""
        content = """
        APP_ENV=dev
        AUTH_METHOD=token
        # Falta AZURE_CLIENT_ID
        AZURE_TENANT_ID=some-tenant-id
        AZURE_CLIENT_SECRET=some-secret
        """
        temp_env = self.create_temp_env_file(content)

        with self.assertRaises(ConfigurationError) as ctx:
            Settings(env_file_path=temp_env)

        self.assertIn("Falta variable crítica para AUTH_METHOD='token'", str(ctx.exception))

        # Limpieza
        try:
            os.remove(temp_env)
        except OSError:
            pass

    def test_token_auth_success(self):
        """Prueba una carga exitosa usando la autenticación de Azure."""
        content = """
        APP_ENV=dev
        AUTH_METHOD=token
        AZURE_CLIENT_ID=client-id-123
        AZURE_TENANT_ID=tenant-id-456
        AZURE_CLIENT_SECRET=secret-789
        """
        temp_env = self.create_temp_env_file(content)

        settings = Settings(env_file_path=temp_env)
        self.assertEqual(settings.AUTH_METHOD, "token")
        self.assertEqual(settings.AZURE_CLIENT_ID, "client-id-123")
        self.assertEqual(settings.AZURE_TENANT_ID, "tenant-id-456")
        self.assertEqual(settings.AZURE_CLIENT_SECRET, "secret-789")

        # Limpieza
        try:
            os.remove(temp_env)
        except OSError:
            pass

    def test_production_safety_check_local(self):
        ("""Prueba que en producción no se permitan contraseñas o usuarios """
         """por defecto en modo local.""")
        content = """
        APP_ENV=prod
        AUTH_METHOD=local
        IMAP_SERVER=imap.realcompany.com
        IMAP_USER=usuario@example.com
        IMAP_PASSWORD=tu_contraseña_segura
        """
        temp_env = self.create_temp_env_file(content)

        with self.assertRaises(ConfigurationError) as ctx:
            Settings(env_file_path=temp_env)

        self.assertIn("SEGURIDAD", str(ctx.exception))

        # Limpieza
        try:
            os.remove(temp_env)
        except OSError:
            pass

    def test_production_safety_check_token(self):
        """Prueba que en producción no se permitan secrets por defecto en modo token."""
        content = """
        APP_ENV=prod
        AUTH_METHOD=token
        AZURE_CLIENT_ID=00000000-0000-0000-0000-000000000000
        AZURE_TENANT_ID=00000000-0000-0000-0000-000000000000
        AZURE_CLIENT_SECRET=tu_client_secret_seguro_de_azure
        """
        temp_env = self.create_temp_env_file(content)

        with self.assertRaises(ConfigurationError) as ctx:
            Settings(env_file_path=temp_env)

        self.assertIn("SEGURIDAD", str(ctx.exception))

        # Limpieza
        try:
            os.remove(temp_env)
        except OSError:
            pass


if __name__ == "__main__":
    unittest.main()
