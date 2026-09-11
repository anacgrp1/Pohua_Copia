"""La política de contraseñas del navegador y la del servidor son la misma.

`frontend/js/components/password.js` enseña al usuario, mientras escribe, los
requisitos que tiene que cumplir la contraseña. Esa lista es una COPIA de la de
`app/auth/passwords.py`: el navegador no valida nada de verdad —el servidor
rechaza igual—, sólo cuenta de antemano lo que va a pasar.

Una copia se separa del original en cuanto alguien toca uno de los dos. Y si se
separa, el daño es peor que no haber avisado: la pantalla pone tres palomitas
verdes y el alta falla igual, sin que nadie entienda por qué.

Así que aquí se leen los dos archivos y se comparan los tres números y la lista
negra. Si alguien sube el mínimo a 14 en Python y se olvida del JS, esto falla y
dice exactamente qué quedó descolgado.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.auth import passwords

JS = Path(__file__).resolve().parents[2] / "frontend/js/components/password.js"


def _numero(nombre: str) -> int:
    texto = JS.read_text(encoding="utf-8")
    encontrado = re.search(rf"const {nombre}\s*=\s*(\d+);", texto)
    assert encontrado, f"No se encontró la constante {nombre} en {JS.name}."
    return int(encontrado.group(1))


def _comunes() -> set[str]:
    texto = JS.read_text(encoding="utf-8")
    encontrado = re.search(r"const COMUNES = \[(.*?)\];", texto, re.S)
    assert encontrado, f"No se encontró la lista COMUNES en {JS.name}."
    crudo = encontrado.group(1)
    return {
        json.loads(f'"{m}"') if "\\" in m else m
        for m in re.findall(r"'([^']*)'", crudo)
    }


def test_longitud_minima_coincide():
    assert _numero("LONGITUD_MINIMA") == passwords.LONGITUD_MINIMA


def test_variedad_minima_coincide():
    """El servidor exige 5 caracteres distintos; el aviso del navegador igual.

    En Python el número está escrito dentro de `validar_politica`, así que se
    lee de ahí en vez de duplicarlo en el test: si allí cambia, esto lo ve.
    """
    fuente = Path(passwords.__file__).read_text(encoding="utf-8")
    encontrado = re.search(r"len\(set\(password\)\) < (\d+)", fuente)
    assert encontrado, "Cambió la comprobación de variedad en passwords.py."
    assert _numero("VARIEDAD_MINIMA") == int(encontrado.group(1))


def test_lista_negra_coincide():
    fuente = Path(passwords.__file__).read_text(encoding="utf-8")
    bloque = re.search(r"if password\.lower\(\) in \{(.*?)\}:", fuente, re.S)
    assert bloque, "Cambió la lista negra en passwords.py."
    del_servidor = set(re.findall(r'"([^"]*)"', bloque.group(1)))
    assert _comunes() == del_servidor


@pytest.mark.parametrize(
    "password",
    ["corta", "contrasena123", "aaaaaaaaaaaaaaaa", ""],
)
def test_las_rechazadas_por_el_servidor_fallan_alguna_regla(password):
    """Nada de lo que el servidor rechaza debe cumplir las tres reglas del JS.

    Se comprueba del lado de Python reproduciendo las mismas tres condiciones
    que el JS evalúa, con los valores leídos de ese archivo: si el navegador se
    volviera más permisivo que el servidor, alguna de estas pasaría.
    """
    largo = len(password) >= _numero("LONGITUD_MINIMA")
    variedad = len(set(password)) >= _numero("VARIEDAD_MINIMA")
    comun = password.lower() not in _comunes()
    navegador_conforme = largo and variedad and comun

    with pytest.raises(passwords.PasswordInvalida):
        passwords.validar_politica(password)
    assert not navegador_conforme, (
        f"El navegador daría por buena {password!r} y el servidor la rechaza."
    )
