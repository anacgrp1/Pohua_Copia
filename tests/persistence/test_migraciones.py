"""El aplicador de migraciones del arranque.

Lo que hay que proteger aquí no es "que aplique SQL" —eso lo hace psycopg2—
sino las tres decisiones que evitan un desastre en producción:

  1. Que NO repita un archivo ya aplicado. Repetirlos sería inofensivo hoy
     (todos son idempotentes) pero deja de serlo en cuanto alguien escriba una
     migración con un INSERT sin ON CONFLICT.
  2. Que al fallar uno se PARE ahí. Aplicar la 009 sin la 008 deja la base en
     un estado que nadie ha probado.
  3. Que un fallo NO tumbe la aplicación. La web ya estaba en pie con el
     esquema viejo; dejar a todo el mundo sin cotizador porque una migración no
     pasó es peor que seguir con las pantallas que sí funcionan.

Se prueba con una conexión de mentira: lo que importa es el orden de las
llamadas y qué se registra, no que PostgreSQL sepa ejecutar un CREATE TABLE.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import pytest

# La configuración se valida al importar y exige los datos del correo. Es el
# mismo apaño que usan los demás módulos de tests/persistence.
os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

import app.persistence.migraciones as migraciones


class CursorFalso:
    def __init__(self, conexion):
        self.conexion = conexion

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, args=None):
        self.conexion.ejecutados.append((sql, args))
        if sql in self.conexion.revientan:
            raise RuntimeError(self.conexion.revientan[sql])

    def fetchall(self):
        return [(nombre,) for nombre in sorted(self.conexion.registradas)]


class ConexionFalsa:
    def __init__(self, registradas=(), revientan=None):
        self.registradas = set(registradas)
        self.revientan = revientan or {}
        self.ejecutados = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return CursorFalso(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


@pytest.fixture
def conectar(monkeypatch):
    """Sustituye la conexión real y devuelve la falsa que se usó."""
    def _conectar(**kwargs):
        falsa = ConexionFalsa(**kwargs)

        @contextmanager
        def fabrica():
            yield falsa

        monkeypatch.setattr(migraciones.duplicates, "conexion_bd", fabrica)
        return falsa

    return _conectar


def _sql_de(conexion):
    return [sql for sql, _ in conexion.ejecutados]


def test_aplica_todo_en_una_base_sin_registro(conectar, monkeypatch):
    monkeypatch.delenv("AUTO_MIGRAR", raising=False)
    conectar()

    resumen = migraciones.aplicar_pendientes()

    esperados = [f.name for f in migraciones.archivos()]
    assert resumen["aplicadas"] == esperados
    assert resumen["error"] is None
    # El esquema base va primero: las migraciones cuentan con sus tablas.
    assert esperados[0] == "schema.sql"


def test_no_repite_lo_ya_aplicado(conectar, monkeypatch):
    monkeypatch.delenv("AUTO_MIGRAR", raising=False)
    todos = [f.name for f in migraciones.archivos()]
    conectar(registradas=todos[:-1])

    resumen = migraciones.aplicar_pendientes()

    assert resumen["aplicadas"] == [todos[-1]]
    assert resumen["ya_estaban"] == todos[:-1]


def test_se_detiene_en_el_primer_fallo(conectar, monkeypatch):
    monkeypatch.delenv("AUTO_MIGRAR", raising=False)
    todos = migraciones.archivos()
    assert len(todos) >= 3, "el proyecto debe tener varias migraciones"

    # Revienta la segunda: ni ella ni las siguientes deben quedar aplicadas.
    contenido = todos[1].read_text(encoding="utf-8")
    falsa = conectar(revientan={contenido: "relation ... does not exist"})

    resumen = migraciones.aplicar_pendientes()

    assert resumen["aplicadas"] == [todos[0].name]
    assert todos[1].name in resumen["error"]
    assert falsa.rollbacks == 1
    # Ninguna posterior llegó a ejecutarse.
    for posterior in todos[2:]:
        assert posterior.read_text(encoding="utf-8") not in _sql_de(falsa)


def test_un_fallo_no_lanza_excepcion(conectar, monkeypatch):
    """El arranque de la API nunca puede caerse por esto."""
    monkeypatch.delenv("AUTO_MIGRAR", raising=False)

    @contextmanager
    def fabrica():
        raise RuntimeError("no hay base")
        yield  # pragma: no cover

    monkeypatch.setattr(migraciones.duplicates, "conexion_bd", fabrica)

    resumen = migraciones.aplicar_pendientes()   # no lanza
    assert resumen["error"] == "no hay base"
    assert resumen["aplicadas"] == []


def test_se_puede_apagar(conectar, monkeypatch):
    monkeypatch.setenv("AUTO_MIGRAR", "false")
    falsa = conectar()

    resumen = migraciones.aplicar_pendientes()

    assert resumen["habilitado"] is False
    assert resumen["aplicadas"] == []
    assert falsa.ejecutados == []


def test_toma_y_suelta_el_cerrojo(conectar, monkeypatch):
    """Dos instancias de Render no pueden migrar a la vez."""
    monkeypatch.delenv("AUTO_MIGRAR", raising=False)
    falsa = conectar()

    migraciones.aplicar_pendientes()

    sql = _sql_de(falsa)
    assert any("pg_advisory_lock" in s for s in sql)
    assert any("pg_advisory_unlock" in s for s in sql)
    assert sql.index([s for s in sql if "pg_advisory_lock" in s][0]) < \
           sql.index([s for s in sql if "pg_advisory_unlock" in s][0])


def test_los_down_no_se_aplican():
    """Un `_down` es marcha atrás manual, no parte del camino de ida."""
    nombres = [f.name for f in migraciones.archivos()]
    assert nombres, "debe haber archivos SQL"
    assert not any(n.endswith("_down.sql") for n in nombres)
    # Y existe alguno en el repositorio, para que la prueba tenga sentido.
    carpeta = Path(migraciones.SQL) / "migrations"
    assert list(carpeta.glob("*_down.sql")), "no hay ningún _down que descartar"


def test_estado_separa_aplicadas_de_pendientes(conectar, monkeypatch):
    todos = [f.name for f in migraciones.archivos()]
    conectar(registradas=todos[:2])

    estado = migraciones.estado()

    assert estado["disponible"] is True
    assert estado["aplicadas"] == [n for n in todos if n in todos[:2]]
    assert estado["pendientes"] == [n for n in todos if n not in todos[:2]]


def test_estado_sin_base_no_lanza(monkeypatch):
    @contextmanager
    def fabrica():
        raise RuntimeError("sin conexión")
        yield  # pragma: no cover

    monkeypatch.setattr(migraciones.duplicates, "conexion_bd", fabrica)

    estado = migraciones.estado()
    assert estado["disponible"] is False
    assert estado["pendientes"] == [f.name for f in migraciones.archivos()]
