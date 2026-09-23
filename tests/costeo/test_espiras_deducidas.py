# -*- coding: utf-8 -*-
"""Cuando el plano no acota las espiras, pero las dice de otra forma.

Por qué existe
--------------
«O viene acotado o hay que preguntárselo al cliente» era demasiado tajante.
Las espiras no siempre están escritas, pero a menudo están IMPLÍCITAS en otras
cotas que sí lo están:

* la ALTURA SÓLIDA, que es la cota que limita el hueco donde va el resorte y
  por eso se acota mucho — y que el lector ni siquiera estaba pidiendo;
* el PASO entre espiras.

Sacarlas de ahí no es estimar. Es la misma aritmética que saca el calibre de
(OD - ID)/2: determinista, auditable, igual las mil veces.

Lo que estas pruebas fijan, además de las fórmulas, es la FRONTERA: qué se
deduce, qué no, y que un resultado imposible se descarta en vez de viajar
hasta el precio.
"""

import pytest

from pricing import espiras


def resorte(**extra):
    base = dict(tipo_resorte="compresion", diametro_alambre_mm=5.21,
                diametro_exterior_mm=49.28, longitud_libre_mm=63.5)
    base.update(extra)
    return base


class TestPorAlturaSolida:
    """Ls = Nt·d con las puntas esmeriladas; (Nt+1)·d sin esmerilar."""

    def test_esmerilados_todas_las_espiras_se_apoyan(self):
        nt, porque = espiras.totales_por_altura_solida(
            resorte(altura_solida_mm=49.5, tipo_extremos="closed and ground"))
        assert nt == pytest.approx(9.5, abs=0.01)
        assert "solid height" in porque

    def test_sin_esmerilar_la_punta_deja_un_calibre_de_mas(self):
        # Mismo resorte, 5.21 mm más de altura sólida: las mismas espiras.
        nt, _ = espiras.totales_por_altura_solida(
            resorte(altura_solida_mm=54.71, tipo_extremos="closed"))
        assert nt == pytest.approx(9.5, abs=0.01)

    def test_sin_altura_solida_no_hay_nada_que_deducir(self):
        assert espiras.totales_por_altura_solida(resorte()) == (None, None)

    def test_sin_calibre_tampoco(self):
        d = resorte(altura_solida_mm=49.5)
        d["diametro_alambre_mm"] = None
        assert espiras.totales_por_altura_solida(d) == (None, None)


class TestPorPaso:
    """L0 = p·Na + 2d con extremos cerrados y esmerilados; +3d sin esmerilar."""

    def test_el_paso_da_las_activas_y_se_le_suman_las_muertas(self):
        nt, porque = espiras.totales_por_paso(
            resorte(paso_mm=7.1, tipo_extremos="closed and ground"))
        # (63.5 - 2x5.21) / 7.1 = 7.48 activas, + 2 muertas
        assert nt == pytest.approx(9.48, abs=0.02)
        assert "pitch" in porque

    def test_un_paso_que_no_cabe_en_la_longitud_libre_se_descarta(self):
        # Los extremos ya ocupan más que L0: la lectura está mal.
        nt, _ = espiras.totales_por_paso(
            resorte(paso_mm=7.1, longitud_libre_mm=5.0,
                    tipo_extremos="closed and ground"))
        assert nt is None


class TestPorRigidez:
    """Na = G·d⁴ / (8·Dm³·k). Necesita el módulo, y ahí está la trampa."""

    def test_sin_modulo_no_se_adivina(self):
        # El núcleo ya tiene su tabla de módulos. Poner otra aquí repetiría el
        # fallo de las espiras muertas: dos tablas que divergen en silencio.
        nt, porque = espiras.totales_por_rigidez(
            resorte(constante_resorte_N_mm=12.0))
        assert nt is None and porque is None

    def test_con_el_modulo_sale_el_numero(self):
        nt, porque = espiras.totales_por_rigidez(
            resorte(constante_resorte_N_mm=12.0, diametro_medio_mm=44.07),
            modulo_cortante_psi=11_500_000)
        assert nt is not None
        assert "spring rate" in porque


class TestElOrdenDePreferencia:

    def test_lo_acotado_gana_a_todo(self):
        nt, porque = espiras.espiras_totales(
            resorte(numero_espiras_totales=8.0, altura_solida_mm=49.5,
                    tipo_extremos="closed and ground"))
        assert nt == 8.0
        assert porque is None          # venía leído: nada que explicar

    def test_las_activas_ganan_a_la_altura_solida(self):
        nt, porque = espiras.espiras_totales(
            resorte(numero_espiras_activas=6.0, altura_solida_mm=49.5,
                    tipo_extremos="closed and ground"))
        assert nt == 8.0               # 6 activas + 2 muertas
        assert "active coils" in porque

    def test_la_altura_solida_gana_al_paso(self):
        # Es la más fiable de las dos: no depende de dónde empiece a contarse
        # el paso.
        nt, porque = espiras.espiras_totales(
            resorte(altura_solida_mm=49.5, paso_mm=7.1,
                    tipo_extremos="closed and ground"))
        assert "solid height" in porque

    def test_los_cuatro_caminos_coinciden_en_un_resorte_coherente(self):
        # Si las convenciones estuvieran mal, esto se separaría.
        comun = dict(tipo_extremos="closed and ground")
        valores = [
            espiras.espiras_totales(resorte(numero_espiras_totales=9.5, **comun))[0],
            espiras.espiras_totales(resorte(numero_espiras_activas=7.5, **comun))[0],
            espiras.espiras_totales(resorte(altura_solida_mm=49.5, **comun))[0],
            espiras.espiras_totales(resorte(paso_mm=7.1, **comun))[0],
        ]
        assert max(valores) - min(valores) < 0.1


class TestLoQueSeDescarta:
    """Un número imposible no puede llegar al precio."""

    @pytest.mark.parametrize("altura", [2.0, 5.0])
    def test_demasiadas_pocas_espiras_no_es_un_resorte(self, altura):
        nt, _ = espiras.totales_por_altura_solida(
            resorte(altura_solida_mm=altura, tipo_extremos="closed and ground"))
        assert nt is None

    def test_demasiadas_espiras_es_una_cota_mal_leida(self):
        nt, _ = espiras.totales_por_altura_solida(
            resorte(altura_solida_mm=5000.0, tipo_extremos="closed and ground"))
        assert nt is None

    def test_fuera_de_compresion_no_se_deduce_nada(self):
        # En extensión las espiras del plano ya son las del cuerpo; en torsión
        # la fórmula del desarrollo es otra.
        for tipo in ("extension", "torsion"):
            nt, _ = espiras.espiras_totales(
                resorte(tipo_resorte=tipo, altura_solida_mm=49.5))
            assert nt is None

    def test_sin_ninguna_de_las_cotas_sigue_sin_saberse(self):
        # El caso de INT-097CBB6A: el plano no da espiras, ni altura sólida,
        # ni paso. Aquí sí hay que preguntarle al cliente.
        assert espiras.espiras_totales(resorte()) == (None, None)


class TestElLectorLasPide:

    def test_el_prompt_pide_la_altura_solida(self):
        import app.vision.pipeline as pipeline
        assert "altura_solida_mm" in pipeline.PROMPT_TECNICO
        assert "solid height" in pipeline.PROMPT_TECNICO

    def test_y_le_prohibe_hacer_la_cuenta_el(self):
        # La convención depende del tipo de extremo, y eso lo sabe el sistema.
        import app.vision.pipeline as pipeline
        assert "NO calcules tú las espiras" in pipeline.PROMPT_TECNICO

    def test_el_extractor_la_guarda(self):
        from app.vision.spring_extractor import normalizar
        r = normalizar({"tipo_resorte": "compresion", "altura_solida_mm": 49.5})
        assert r.altura_solida_mm == 49.5
