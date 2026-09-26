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
import re
from pathlib import Path

# TAMPOCO SE LEE EL `.env` DE QUIEN CORRE LAS PRUEBAS. Con el de una máquina de
# desarrollo (MAIL_MODE=outlook, MAIL_FOLDER=INBOX,TEST, el buzón de ventas,
# APP_ENV=prod…) las pruebas heredaban esa configuración y fallaban unas u
# otras según lo que tuviera cada `.env`: en una máquina limpia pasaban todas y
# en la de desarrollo quedaban 4 o 15 rojas sin que el código tuviera nada.
# Se quita del entorno todo lo que el proyecto configura —las claves de
# `.env.example` y las de un `.env` presente— y se le dice a la configuración
# que no cargue el fichero. Cada prueba pone lo que necesita.
_RAIZ = Path(__file__).resolve().parent.parent


def _claves(fichero: Path) -> set:
    try:
        lineas = fichero.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    # También las comentadas («# IMAP_SERVER=»): existen, sólo que apagadas.
    return {m.group(1) for m in (re.match(r"\s*#?\s*([A-Z][A-Z0-9_]*)\s*=", linea)
                                 for linea in lineas) if m}


for _clave in (_claves(_RAIZ / ".env.example") | _claves(_RAIZ / ".env")
               | _claves(Path.cwd() / ".env")):
    if _clave and _clave != "POHUA_TEST_DATABASE_URL":
        os.environ.pop(_clave, None)
os.environ["POHUA_SIN_DOTENV"] = "1"

_PRUEBAS = os.environ.get("POHUA_TEST_DATABASE_URL")
os.environ["DATABASE_URL"] = (
    _PRUEBAS or "postgresql://pruebas:pruebas@pohua-pruebas.invalid:5432/pohua_pruebas")
for _clave in ("PG_HOST", "PG_PORT", "PG_DATABASE", "PG_USER", "PG_PASSWORD"):
    os.environ.pop(_clave, None)
