"""Qué RFQ en revisión se pasan a «Esperando al cliente» (scripts/pasar_a_esperando.py)."""
import importlib.util
import os

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _script():
    spec = importlib.util.spec_from_file_location(
        "pasar_a_esperando", os.path.join(RAIZ, "scripts", "pasar_a_esperando.py"))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_sin_volumen_se_pasa_y_sólo_se_pide_el_volumen():
    s = _script()
    fila = {"part_number": None, "volumen": "", "material": None, "cliente_id": "CGRMX",
            "datos": {"remitente": "daniela.diaz@cgr-international.com"}}
    # Número de parte y material salen del plano: no se le piden al comprador.
    assert s.faltantes(fila) == ["volumen"]


def test_con_volumen_pero_sin_numero_de_parte_se_queda_en_revision():
    s = _script()
    fila = {"part_number": None, "volumen": "200000", "material": None, "cliente_id": "CGRMX",
            "datos": {}}
    assert s.faltantes(fila) == []


def test_completo_se_queda_en_revision():
    s = _script()
    fila = {"part_number": "1-633064", "volumen": "333000", "material": "MW", "cliente_id": None,
            "datos": {"customer": "cgr-international.com"}}
    assert s.faltantes(fila) == []


def test_lo_que_esta_en_datos_json_tambien_cuenta():
    s = _script()
    fila = {"part_number": None, "volumen": None, "material": None, "cliente_id": None,
            "datos": {"customer": "x", "part_number": "A", "volumen": 5000, "material": "MW"}}
    assert s.faltantes(fila) == []
