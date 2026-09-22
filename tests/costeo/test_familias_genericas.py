# -*- coding: utf-8 -*-
"""Regla 2: "spring wire" a secas se cotiza como Music Wire.

Por qué existe
--------------
"Spring wire" nombra la familia entera, no un material. No resolvía a ningún
código ISC, y sin código no hay módulo de cortante —así que el lector no puede
deducir las espiras desde la rigidez ni comprobar las del plano— ni precio por
libra. La oferta se iba a revisión por un material que en la planta ya está
decidido.

Lo delicado no es la regla, es su SITIO. Tiene que ser el último recurso: si
entrara en el índice de alias normal, "spring wire" (once letras) le ganaría
por longitud a "hard drawn" (diez), y un plano que dice "hard drawn spring
wire" se cotizaría como Music Wire —material equivocado, precio equivocado,
y nada que lo delate—. Eso es lo que vigilan estas pruebas.
"""

import copy
import io
import json

import pytest

from app.feasibility.rules import Reglas, ReglasInvalidasError, cargar_reglas


@pytest.fixture(scope="module")
def reglas():
    return cargar_reglas(refrescar=True)


@pytest.fixture(scope="module")
def crudo():
    return json.load(io.open("reglas/factibilidad.json", encoding="utf-8"))


class TestLoConcretoGanaALoGeneral:
    """La tabla del núcleo, tal cual."""

    @pytest.mark.parametrize("texto, codigo", [
        ("hard drawn spring wire", "HD"),
        ("stainless spring wire", "SS"),
        ("oil tempered spring wire", "OT"),
        ("chrome silicon spring wire", "CSI"),
        ("spring wire", "MW"),
        ("spring steel wire", "MW"),
        ("alambre de muelle", "MW"),
    ])
    def test_cada_familia_a_su_codigo(self, reglas, texto, codigo):
        assert reglas.codigo_material(texto) == codigo

    def test_da_igual_como_venga_escrito(self, reglas):
        for t in ("SPRING WIRE", "Spring Wire", "  spring   wire  "):
            assert reglas.codigo_material(t) == "MW"


class TestNoPisaALosMaterialesDeVerdad:
    """Lo que ya funcionaba tiene que seguir dando lo mismo."""

    @pytest.mark.parametrize("texto, codigo", [
        ("ASTM A228 music wire, zinc plated finish", "MW"),
        ("MUSIC WIRE", "MW"),
        ("acero inoxidable 302", "SS"),
        ("stainless 316", "316"),
        ("17-7 PH", "SS177"),
        ("chrome silicon", "CSI"),
        ("hard drawn", "HD"),
    ])
    def test_los_concretos_no_se_mueven(self, reglas, texto, codigo):
        assert reglas.codigo_material(texto) == codigo

    def test_lo_que_no_se_sabe_sigue_sin_saberse(self, reglas):
        # La regla resuelve familias conocidas, no todo lo que lleve "wire".
        # Convertir cualquier desconocido en Music Wire sería peor que no
        # resolverlo: el dictamen dejaría de avisar.
        for t in ("titanio", "aluminio 6061", "", None, "acero"):
            assert reglas.codigo_material(t) is None

    def test_inconel_sigue_resolviendo_por_su_alias(self, reglas):
        # No es de esta regla: "inconel" es alias de HAST desde antes. Queda
        # escrito para que no se confunda con un efecto de las familias.
        assert reglas.codigo_material("inconel 600") == "HAST"

    def test_el_generico_solo_actua_si_no_hay_concreto(self, reglas):
        # Consultado directamente sí resuelve; el orden lo pone
        # `codigo_material`, que prueba primero el índice de materiales.
        assert reglas.material_generico("hard drawn spring wire") == "HD"
        assert reglas.material_soportado("hard drawn spring wire") is not None


class TestElArchivoSeValida:

    def _con(self, crudo, familias):
        d = copy.deepcopy(crudo)
        d["familias_genericas"] = familias
        return d

    def test_un_codigo_inexistente_no_pasa(self, crudo):
        # Es el fallo peor: resuelve —nadie ve un material faltante— y luego el
        # catálogo no encuentra la fila. El precio sale sin materia prima.
        with pytest.raises(ReglasInvalidasError, match="materiales_soportados"):
            Reglas(self._con(crudo, [{"alias": "x wire", "codigo": "NOEXISTE"}]))

    def test_un_alias_repetido_no_pasa(self, crudo):
        with pytest.raises(ReglasInvalidasError, match="dos veces"):
            Reglas(self._con(crudo, [{"alias": "spring wire", "codigo": "MW"},
                                     {"alias": "spring wire", "codigo": "HD"}]))

    def test_una_clave_de_mas_no_pasa(self, crudo):
        with pytest.raises(ReglasInvalidasError):
            Reglas(self._con(crudo, [{"alias": "x wire", "codigo": "MW",
                                      "color": "rojo"}]))

    def test_el_bloque_es_opcional(self, crudo):
        d = copy.deepcopy(crudo)
        d.pop("familias_genericas", None)
        Reglas(d)          # no lanza: un archivo sin familias es válido

    def test_el_orden_del_archivo_se_respeta(self, crudo):
        # No se ordena por longitud: manda el archivo. Aquí lo general va
        # primero a propósito, y tiene que ganar.
        r = Reglas(self._con(crudo, [{"alias": "spring wire", "codigo": "MW"},
                                     {"alias": "hard drawn spring wire",
                                      "codigo": "HD"}]))
        assert r.material_generico("hard drawn spring wire") == "MW"


class TestElCosteoRecibeElCodigo:

    def test_el_adaptador_lo_resuelve_igual(self):
        # `pricing` entra por `repository.codigo_de_material`, que delega en
        # las mismas reglas.
        # Si esa puerta se quedara sin la escalera, el dictamen resolvería y el
        # precio no, que es justo la incoherencia que esto viene a evitar.
        from pricing.repository import codigo_de_material
        assert codigo_de_material("spring wire") == "MW"
        assert codigo_de_material("hard drawn spring wire") == "HD"
        assert codigo_de_material("") is None
