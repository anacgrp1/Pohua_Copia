
import unittest

from app.shared.html_cleaner import limpiar_html


class TestLimpiarHtml(unittest.TestCase):
    def test_extrae_texto_y_elimina_tags(self):
        """Caso típico: quita tags y conserva el texto legible."""
        html = "<p>Hola <b>equipo</b>, necesito cotizar resortes.</p>"
        self.assertEqual(
            limpiar_html(html),
            "Hola equipo, necesito cotizar resortes.",
        )

    def test_elimina_estilos_y_scripts(self):
        """El contenido de <style> y <script> no debe aparecer en la salida."""
        html = """
        <html>
          <head>
            <style>.x { color: red; }</style>
            <title>No mostrar</title>
          </head>
          <body>
            <script>console.log('oculto');</script>
            <p>Solicito 500 resortes de compresión.</p>
          </body>
        </html>
        """
        resultado = limpiar_html(html)
        self.assertIn("Solicito 500 resortes de compresión.", resultado)
        self.assertNotIn("color: red", resultado)
        self.assertNotIn("console.log", resultado)
        self.assertNotIn("No mostrar", resultado)

    def test_colapsa_lineas_vacias_duplicadas(self):
        """Múltiples bloques vacíos se reducen a una sola línea en blanco."""
        html = "<div>Primera línea</div><br><br><br><div>Segunda línea</div>"
        resultado = limpiar_html(html)
        self.assertNotIn("\n\n\n", resultado)
        self.assertEqual(resultado, "Primera línea\n\nSegunda línea")

    def test_html_vacio_o_nulo(self):
        """Entradas vacías, en blanco o None devuelven cadena vacía."""
        self.assertEqual(limpiar_html(""), "")
        self.assertEqual(limpiar_html("   "), "")
        self.assertEqual(limpiar_html(None), "")

    def test_html_malformado_no_lanza_excepcion(self):
        """HTML mal formado se procesa de forma tolerante sin fallar."""
        html = "<p>Cotización <b>urgente <i>sin cerrar tags"
        resultado = limpiar_html(html)
        self.assertIn("Cotización", resultado)
        self.assertIn("urgente", resultado)


if __name__ == "__main__":
    unittest.main()
