# -*- coding: utf-8 -*-
"""El resorte 004-222 (GRAVERMAX HAMMER SPRING), que salió mal dos veces.

El mismo plano dio dos dictámenes distintos en dos días:

    bien (22/9)          mal (23/9)
    Nt 12.25             Nt 10.25      <- las ACTIVAS puestas como totales
    Na 10.25             Na  8.25      <- y otra vez menos dos
    FEASIBLE, 100        REQUIRES REVIEW, 94

Eran dos fallos distintos que se juntaron en la misma pantalla.

1. El material. El plano dice "SPRING WIRE", que no es un material sino la
   familia entera. El costeo ya lo resolvía —`codigo_material` consulta las
   familias— pero el dictamen no, así que la misma pantalla enseñaba "Music
   Wire" en el desplegable y "no mapea a ningún código de ISC" en los motivos.
   Dos caminos mirando la misma tabla y contestando cosas distintas.

2. Las espiras. El plano acota las ACTIVAS (10.25) y no las totales. El
   endpoint que alimenta la hoja mandaba el campo crudo —null— y tiraba las
   activas. La casilla "Total Coils" quedaba vacía, parecía que faltaba un
   dato que ya estaba resuelto, y quien cotizaba escribía lo único que veía en
   el plano: 10.25. La hoja hace `Na = Nt - muertas` con lo que le llegue, así
   que se comió dos espiras y las arrastró hasta el precio.

Lo que hace que el segundo sea peligroso es que NO se ve: la hoja enseña
números perfectamente coherentes entre sí. Altura sólida, paso, rigidez,
carga, esfuerzo, peso y precio: todo cuadra, y todo está mal.
"""

import pytest

from app.feasibility.rules import cargar_reglas
import app.feasibility.engine as engine
import api.routes.rfqs as rutas


# Las cotas del plano, tal como las lee el lector: las ACTIVAS acotadas, las
# totales no, extremos escuadrados y esmerilados.
PLANO = {
    "tipo_resorte": "compresion",
    "tipo_extremos": "squared and ground",
    "material": "SPRING WIRE",
    "numero_espiras_activas": 10.25,
    "numero_espiras_totales": None,
    "diametro_alambre_mm": 0.991,
    "diametro_exterior_mm": 12.129,
    "longitud_libre_mm": 38.1,
}

MUERTAS = 2          # escuadrado y esmerilado


@pytest.fixture(scope="module")
def reglas():
    return cargar_reglas()


class TestElMaterial:
    """"SPRING WIRE" es la familia, no el material. No puede bloquear."""

    def test_no_bloquea(self, reglas):
        motivos = engine._evaluar_material(dict(PLANO), reglas)
        assert not any(m["nivel"] == engine.NIVEL_CRIT for m in motivos)

    def test_queda_dicho_que_lo_puso_el_sistema(self, reglas):
        # Que no bloquee no es lo mismo que que se calle: quien aprueba tiene
        # derecho a saber que ese material no venía en el plano.
        motivos = engine._evaluar_material(dict(PLANO), reglas)
        codigos = [m["codigo"] for m in motivos]
        assert engine.MATERIAL_GENERICO in codigos

    def test_no_resta_puntos(self, reglas):
        # La planta ya tiene decidido qué alambre es. El score de este resorte
        # era 100 cuando salía bien y tiene que seguir siéndolo.
        motivos = [m for m in engine._evaluar_material(dict(PLANO), reglas)
                   if m["codigo"] == engine.MATERIAL_GENERICO]
        assert motivos[0]["penalizacion"] == 0

    def test_resuelve_a_music_wire(self, reglas):
        motivos = engine._evaluar_material(dict(PLANO), reglas)
        dicho = [m for m in motivos if m["codigo"] == engine.MATERIAL_GENERICO][0]
        assert "Music Wire" in str(dicho["limite"])

    def test_el_dictamen_y_el_costeo_coinciden(self, reglas):
        # Ésta es la prueba que importa: los dos caminos, la misma respuesta.
        # Que discreparan es lo que puso "Music Wire" en el desplegable y "no
        # mapea a ningún código" en los motivos, en la misma pantalla.
        del reglas  # se recarga dentro para no compartir estado
        r = cargar_reglas()
        motivos = engine._evaluar_material(dict(PLANO), r)
        dicho = [m for m in motivos if m["codigo"] == engine.MATERIAL_GENERICO][0]
        assert r.nombre_por_codigo(r.codigo_material("SPRING WIRE")) == dicho["limite"]

    def test_un_material_de_verdad_sigue_sin_avisos(self, reglas):
        # El respaldo es el ÚLTIMO recurso: no puede dispararse cuando el
        # plano sí nombra el material.
        motivos = engine._evaluar_material(
            dict(PLANO, material="MUSIC WIRE ASTM A228"), reglas)
        assert not any(m["codigo"] == engine.MATERIAL_GENERICO for m in motivos)

    def test_hard_drawn_spring_wire_no_acaba_en_music_wire(self, reglas):
        # El alias concreto gana a la familia. Si esto se rompe, un plano de
        # Hard Drawn se cotiza con el precio del Music Wire.
        motivos = engine._evaluar_material(
            dict(PLANO, material="hard drawn spring wire"), reglas)
        assert not any(m["codigo"] == engine.MATERIAL_GENERICO for m in motivos)

    def test_un_material_inventado_sigue_bloqueando(self, reglas):
        motivos = engine._evaluar_material(
            dict(PLANO, material="unobtanium"), reglas)
        assert any(m["nivel"] == engine.NIVEL_CRIT for m in motivos)


class TestLasEspirasQueLeLleganALaHoja:
    """La hoja resta las muertas a lo que reciba. Sólo vale el TOTAL."""

    def test_manda_el_total_no_las_activas(self):
        env = rutas._espiras_para_la_hoja(dict(PLANO))
        assert env["espiras_totales"] == 12.25

    def test_la_hoja_reconstruye_las_activas_del_plano(self):
        # El ciclo completo: 10.25 activas -> 12.25 totales -> la hoja resta
        # dos -> 10.25 activas otra vez. Si en vez de eso le llegan las
        # activas, la hoja enseña 8.25 y nadie lo nota.
        env = rutas._espiras_para_la_hoja(dict(PLANO))
        assert env["espiras_totales"] - MUERTAS == PLANO["numero_espiras_activas"]

    def test_dice_de_donde_sale(self):
        # Un total deducido y uno leído del plano no valen lo mismo.
        env = rutas._espiras_para_la_hoja(dict(PLANO))
        assert env["espiras_origen"]
        assert "dead coils" in env["espiras_origen"]

    def test_el_leido_del_plano_manda_y_no_se_explica(self):
        env = rutas._espiras_para_la_hoja(dict(PLANO, numero_espiras_totales=12.25))
        assert env["espiras_totales"] == 12.25
        assert env["espiras_origen"] is None

    def test_el_leido_no_se_recalcula_aunque_discrepe(self):
        # Si el plano dice 9 y las activas dicen otra cosa, manda el plano:
        # aquí no se corrige al dibujante.
        env = rutas._espiras_para_la_hoja(dict(PLANO, numero_espiras_totales=9))
        assert env["espiras_totales"] == 9

    def test_por_altura_solida_cuando_no_hay_activas(self):
        sin_activas = dict(PLANO, numero_espiras_activas=None,
                           altura_solida_mm=12.14)
        assert rutas._espiras_para_la_hoja(sin_activas)["espiras_totales"] == 12.25

    def test_por_paso_cuando_no_hay_ni_activas_ni_altura(self):
        solo_paso = dict(PLANO, numero_espiras_activas=None, paso_mm=3.524)
        assert rutas._espiras_para_la_hoja(solo_paso)["espiras_totales"] == 12.25

    def test_sin_nada_va_vacio_y_no_se_inventa(self):
        # Vacío es la respuesta correcta: es cuando hay que preguntarle al
        # cliente. Un número inventado aquí se convierte en un precio
        # inventado que nadie vuelve a mirar.
        pelado = {"tipo_resorte": "compresion", "tipo_extremos": "squared and ground"}
        assert rutas._espiras_para_la_hoja(pelado)["espiras_totales"] is None

    def test_no_revienta_sin_resorte(self):
        assert rutas._espiras_para_la_hoja({})["espiras_totales"] is None


class TestLasCuatroViasCoinciden:
    """Un resorte coherente da el mismo número por los cuatro caminos."""

    def test_004_222_da_12_25_por_todos(self):
        from pricing import espiras
        completo = dict(PLANO, altura_solida_mm=12.14, paso_mm=3.524)
        assert espiras.totales_por_altura_solida(completo)[0] == 12.25
        assert espiras.totales_por_paso(completo)[0] == 12.25
        assert espiras.espiras_totales(completo)[0] == 12.25
        assert completo["numero_espiras_activas"] + MUERTAS == 12.25
