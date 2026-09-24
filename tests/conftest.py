"""Fixtures compartidos de pytest.

LA BASE DE DATOS DE VERDAD NO SE TOCA DESDE LAS PRUEBAS. La configuración
lee `.env`, y en la máquina de quien desarrolla ese `.env` apunta a Neon: la
batería completa dejó allí un RFQ ficticio («RFQ-1», neogen.com, un plano que
no era un PDF) que apareció en la ventana de revisión como si fuera real.

Así que antes de que se cargue nada, la conexión se fija a un servidor que
no existe. Una prueba que llegue a la base falla al conectar en vez de
escribir en producción, que es lo que se quiere: esa prueba le falta un
mock. Para las pruebas que SÍ necesitan una base (make db-smoke), se pasa
`POHUA_TEST_DATABASE_URL` a propósito.
"""

import os

_PRUEBAS = os.environ.get("POHUA_TEST_DATABASE_URL")
os.environ["DATABASE_URL"] = (
    _PRUEBAS or "postgresql://pruebas:pruebas@pohua-pruebas.invalid:5432/pohua_pruebas")
for _clave in ("PG_HOST", "PG_PORT", "PG_DATABASE", "PG_USER", "PG_PASSWORD"):
    os.environ.pop(_clave, None)
