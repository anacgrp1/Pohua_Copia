"""El material del correo tiene que llegar al catálogo de costeo.

El comprador escribe "ASTM A228 music wire, zinc plated finish"; el catálogo
guarda "MW". Antes se buscaba en `materiales` una fila cuyo código fuera la
frase entera, no aparecía, y la ventana de revisión declaraba faltante un
material que la planta tiene en existencia.
"""

import pytest

import app.feasibility.rules as reglas_mod
import pricing.repository as repository


# --------------------------------------------------------------------------- #
# Traducción texto libre -> código de catálogo
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("texto, esperado", [
    ("ASTM A228 music wire, zinc plated finish", "MW"),
    ("MUSIC WIRE ASTM A228", "MW"),
    ("music wire", "MW"),
    ("MW", "MW"),
    ("ac. inox 302", "SS"),
    ("AISI 316", "316"),
    ("chrome silicon A401", "CSI"),
    ("oil tempered", "OT"),
    ("Hard Drawn (ASTM A227)", "HD"),
])
def test_codigo_material_traduce_el_texto_del_rfq(texto, esperado):
    assert reglas_mod.cargar_reglas().codigo_material(texto) == esperado


@pytest.mark.parametrize("texto", ["", "   ", None, "titanio grado 5"])
def test_codigo_material_sin_equivalencia_es_none(texto):
    assert reglas_mod.cargar_reglas().codigo_material(texto) is None


def test_todos_los_materiales_declaran_codigo():
    """Un material sin código no se puede costear aunque el dictamen lo acepte."""
    reglas = reglas_mod.cargar_reglas()
    sin_codigo = [n for n in reglas.materiales if not reglas.codigo_material(n)]
    assert sin_codigo == []


# --------------------------------------------------------------------------- #
# La consulta: qué candidatos se prueban y en qué orden
# --------------------------------------------------------------------------- #

class _Cursor:
    """Cursor de mentira: responde con la fila que tenga para ese código."""

    def __init__(self, filas_por_codigo, por_texto=None):
        self.filas = filas_por_codigo
        self.por_texto = por_texto or {}
        self.consultados = []
        self._ultima = None

    def execute(self, sql, params):
        if "upper(m.nombre)" in sql:
            self.consultados.append(("texto", params["texto"]))
            self._ultima = self.por_texto.get(params["texto"].upper())
        elif "aleacion_surcharges" in sql:
            self._ultima = None
        else:
            self.consultados.append(("codigo", params["codigo"]))
            self._ultima = self.filas.get(params["codigo"].upper())

    def fetchone(self):
        return self._ultima

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _Conexion:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


_FILA_MW = (7, "MW", "Music Wire (ASTM A228)", False, 2.5, 0.08, None)


def test_el_texto_del_correo_encuentra_el_material():
    cur = _Cursor({"MW": _FILA_MW})
    datos = repository.precio_material(
        "ASTM A228 music wire, zinc plated finish", 0.08,
        conexion=_Conexion(cur))

    assert datos is not None
    assert datos["codigo"] == "MW"
    assert datos["precio_lb"] == 2.5
    # Primero tal cual vino, y sólo después el código traducido.
    assert cur.consultados == [
        ("codigo", "ASTM A228 music wire, zinc plated finish"),
        ("codigo", "MW"),
    ]


def test_un_codigo_de_catalogo_se_resuelve_a_la_primera():
    cur = _Cursor({"MW": _FILA_MW})
    datos = repository.precio_material("MW", 0.08, conexion=_Conexion(cur))

    assert datos["codigo"] == "MW"
    assert cur.consultados == [("codigo", "MW")]


def test_el_nombre_completo_del_catalogo_tambien_sirve():
    """Sin alias que casen, queda el nombre o la norma tal cual."""
    cur = _Cursor({}, por_texto={"ALGÚN MATERIAL RARO": _FILA_MW})
    datos = repository.precio_material("Algún material raro", 0.08,
                                       conexion=_Conexion(cur))

    assert datos is not None
    assert cur.consultados[-1] == ("texto", "Algún material raro")


def test_material_desconocido_sigue_siendo_none():
    cur = _Cursor({})
    assert repository.precio_material("titanio grado 5", 0.08,
                                      conexion=_Conexion(cur)) is None
