
import unittest

from app.core.config import settings
from app.email.factory import EmailProviderFactory, FactoryConfigurationError
from app.email.graph_provider import GraphEmailProvider
from app.email.imap_provider import ImapEmailProvider


class TestEmailProviderFactory(unittest.TestCase):

    def setUp(self):
        # Guardar el entorno original
        self.original_env = settings.APP_ENV

    def tearDown(self):
        # Restaurar el entorno original
        settings.APP_ENV = self.original_env

    def test_factory_resolves_dev_provider(self):
        """Verifica que si APP_ENV es 'dev', la fábrica devuelva un ImapEmailProvider."""
        settings.APP_ENV = "dev"
        factory = EmailProviderFactory()
        provider = factory.get_provider()
        self.assertIsInstance(provider, ImapEmailProvider)

    def test_factory_resolves_prod_provider(self):
        """Verifica que si APP_ENV es 'prod', la fábrica devuelva un GraphEmailProvider."""
        settings.APP_ENV = "prod"
        factory = EmailProviderFactory()
        provider = factory.get_provider()
        self.assertIsInstance(provider, GraphEmailProvider)

    def test_factory_raises_error_for_invalid_env(self):
        """Verifica que un valor inesperado de entorno dispare FactoryConfigurationError."""
        settings.APP_ENV = "staging"
        with self.assertRaises(FactoryConfigurationError) as ctx:
            EmailProviderFactory.get_provider()

        self.assertIn("no es válido para la fábrica", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
