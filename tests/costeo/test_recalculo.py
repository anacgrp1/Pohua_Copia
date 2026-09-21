"""El PM corrige, recalcula, y el dictamen sale de lo recalculado.

El veredicto de factibilidad se calculaba UNA vez, al entrar el correo, y se
quedaba grabado. El PM miraba el dibujo, veía que el modelo leyó 1.6 donde dice
1.8, y esa corrección no tenía dónde ir: o dictaminaba sobre un dato que sabe
malo, o lo corregía en la calculadora y el RFQ se quedaba con el valor viejo.
"""

import pytest

import app.rfq.recalculo as recalculo


BASE = {
    "tipo_resorte": "compresion",
    "material": "Music Wire (ASTM A228)",
    "diametro_alambre_mm": 1.6,
    "diametro_exterior_mm": 12.0,
    "longitud_libre_mm": 40.0,
    "numero_espiras_totales": 9,
    "confianza": 0.92,
    "num_parte": "1060-022",
    "advertencias": ["cota borrosa"],
}


# --------------------------------------------------------------------------- #
# Fusionar: qué se pisa y qué no
# --------------------------------------------------------------------------- #

def test_lo_que_el_pm_corrige_manda():
    r = recalculo.fusionar_ajustes(BASE, {"diametro_alambre_mm": "1.8"})

    assert r["resorte"]["diametro_alambre_mm"] == 1.8
    assert r["tocados"] == ["diametro_alambre_mm"]


def test_la_coma_decimal_se_entiende():
    """Aquí se escribe 1,8 tanto como 1.8."""
    r = recalculo.fusionar_ajustes(BASE, {"diametro_alambre_mm": "1,8"})
    assert r["resorte"]["diametro_alambre_mm"] == 1.8


def test_un_campo_vacio_no_borra_lo_que_habia():
    """Vacío es «no lo mandé», no «bórralo»: si no, mandar el formulario
    entero se llevaría por delante las cotas que el PM no tocó."""
    r = recalculo.fusionar_ajustes(BASE, {"diametro_alambre_mm": "",
                                          "longitud_libre_mm": "   "})

    assert r["resorte"]["diametro_alambre_mm"] == 1.6
    assert r["resorte"]["longitud_libre_mm"] == 40.0
    assert r["tocados"] == []


def test_para_vaciar_a_proposito_se_manda_un_guion():
    r = recalculo.fusionar_ajustes(BASE, {"diametro_alambre_mm": "-"})

    assert r["resorte"]["diametro_alambre_mm"] is None
    assert r["tocados"] == ["diametro_alambre_mm"]


def test_el_mismo_valor_no_cuenta_como_cambio():
    """Si contara, cada recálculo marcaría el resorte como «ajustado por una
    persona» aunque nadie tocara nada."""
    r = recalculo.fusionar_ajustes(BASE, {"diametro_alambre_mm": "1.6"})
    assert r["tocados"] == []


def test_no_se_puede_tocar_lo_que_no_es_del_formulario():
    """Por aquí entra lo que alguien escribe: la confianza del modelo, el
    número de parte y las advertencias no son suyas."""
    r = recalculo.fusionar_ajustes(BASE, {
        "confianza": 1.0, "num_parte": "OTRO", "advertencias": [],
        "campos_ajustados": ["todo"], "lo_que_sea": 1})

    assert r["resorte"]["confianza"] == 0.92
    assert r["resorte"]["num_parte"] == "1060-022"
    assert r["resorte"]["advertencias"] == ["cota borrosa"]
    assert "lo_que_sea" not in r["resorte"]
    assert r["tocados"] == []


def test_un_numero_ilegible_se_ignora_no_se_pone_en_cero():
    """Un diámetro en cero haría costear con cero en vez de decir que falta."""
    r = recalculo.fusionar_ajustes(BASE, {"diametro_alambre_mm": "como 2 mm"})

    assert r["resorte"]["diametro_alambre_mm"] == 1.6
    assert r["tocados"] == []


def test_el_texto_se_limpia():
    r = recalculo.fusionar_ajustes(BASE, {"material": "  ASTM A228  "})
    assert r["resorte"]["material"] == "ASTM A228"


# --------------------------------------------------------------------------- #
# Recalcular: el dictamen y el rastro
# --------------------------------------------------------------------------- #

@pytest.fixture
def espias(monkeypatch):
    """Motor y base de mentira: aquí se prueba el orquestado, no el motor."""
    visto = {"evaluado": [], "resortes": [], "veredictos": []}

    import app.feasibility.engine as engine
    import app.persistence.spring_repository as spring_repository
    import app.rfq.repository as repository

    def evaluar(resorte, reglas=None):
        visto["evaluado"].append(dict(resorte))
        return {"veredicto": "feasible", "score": 88, "banda": "Manufacturable",
                "motivos": []}

    monkeypatch.setattr(engine, "evaluar_factibilidad", evaluar)
    monkeypatch.setattr(spring_repository, "guardar",
                        lambda rfq, mid, origen, datos:
                        visto["resortes"].append((rfq, origen, dict(datos))) or 1)
    monkeypatch.setattr(repository, "guardar_veredicto",
                        lambda rfq, res, version=None, conexion=None:
                        visto["veredictos"].append((rfq, res, version)) or {})
    return visto


def test_el_dictamen_se_hace_sobre_el_valor_corregido(espias):
    r = recalculo.recalcular("INT-1", BASE, {"diametro_alambre_mm": "1.8"},
                             usuario="pm@cgr.com")

    # Lo que vio el motor es el 1.8, no el 1.6 que leyó la IA.
    assert espias["evaluado"][0]["diametro_alambre_mm"] == 1.8
    assert r["factibilidad"]["veredicto"] == "feasible"
    assert espias["veredictos"][0][0] == "INT-1"


def test_lo_que_toca_una_persona_queda_marcado(espias):
    """Un 1.8 escrito a mano y un 1.8 leído del plano no pueden ser
    indistinguibles para siempre."""
    r = recalculo.recalcular("INT-1", BASE, {"diametro_alambre_mm": "1.8"},
                             usuario="pm@cgr.com")

    assert r["resorte"]["ajustado_por"] == "pm@cgr.com"
    assert r["resorte"]["campos_ajustados"] == ["diametro_alambre_mm"]
    assert r["resorte"]["ajustado_en"]
    # Y se guarda con el origen diciendo quién fue.
    rfq, origen, _ = espias["resortes"][0]
    assert "pm@cgr.com" in origen


def test_sin_cambios_no_se_marca_ni_se_guarda_un_resorte_nuevo(espias):
    """Recalcular sólo para ver el dictamen con las cotas de ahora no
    convierte al PM en autor de lo que leyó la IA."""
    r = recalculo.recalcular("INT-1", BASE, {}, usuario="pm@cgr.com")

    assert r["tocados"] == []
    assert "ajustado_por" not in r["resorte"]
    assert espias["resortes"] == []
    # Pero el veredicto sí se rehace: es justo para lo que se pulsó.
    assert len(espias["veredictos"]) == 1


def test_un_motor_que_revienta_no_tumba_la_ventana(monkeypatch):
    import app.feasibility.engine as engine

    def revienta(resorte, reglas=None):
        raise RuntimeError("reglas ilegibles")

    monkeypatch.setattr(engine, "evaluar_factibilidad", revienta)
    r = recalculo.recalcular("INT-1", BASE, {}, usuario="pm@cgr.com")

    assert r["factibilidad"] is None
    assert "reglas ilegibles" in r["error"]


def test_si_no_se_puede_guardar_se_dice_pero_se_devuelve_el_dictamen(espias, monkeypatch):
    import app.rfq.repository as repository

    def revienta(*a, **k):
        raise RuntimeError("la base no contesta")

    monkeypatch.setattr(repository, "guardar_veredicto", revienta)
    r = recalculo.recalcular("INT-1", BASE, {"diametro_alambre_mm": "1.8"},
                             usuario="pm@cgr.com")

    assert r["factibilidad"]["veredicto"] == "feasible"
    assert "la base no contesta" in r["error"]
