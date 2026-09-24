"""Los parámetros del motor en la base son los de la calculadora.

La migración 007 sembró en Neon la escalera de overheads de la V5
(12/16/20/24) y el motor de Pohua pasó a ser el del núcleo (30 plano): la
ventana del RFQ daba $0.3223 y la calculadora $0.3946 para el mismo resorte.
La migración 030 borra el juego de la V5 y deja en la base los DEFAULT_PARAMS
del motor, y la 007 los siembra ya así en una base nueva. Aquí se fija que los
dos no se vuelvan a separar.
"""
import json
import re
from pathlib import Path

from pricing import nucleo

RAIZ = Path(__file__).resolve().parents[2]
MIGRACION = RAIZ / "sql" / "migrations" / "030_parametros_de_la_calculadora.sql"


def _valores_de_la_migracion():
    texto = MIGRACION.read_text(encoding="utf-8")
    pares = re.findall(r"\(nuevo,\s*'(\w+)',\s*'([^']+)'::jsonb\)", texto)
    assert pares, "la migración 030 no tiene valores"
    return {clave: json.loads(valor) for clave, valor in pares}


class TestElMotor:

    def test_se_leen_los_default_params(self):
        p = nucleo.parametros_del_motor()
        assert p["ohLadder"] == [30, 30, 30, 30]
        assert p["ohSub"] == 35
        assert p["contribution"] == 20


class TestLaMigracion030:

    def test_trae_exactamente_los_del_motor(self):
        motor = nucleo.parametros_del_motor()
        migracion = _valores_de_la_migracion()
        for clave, valor in motor.items():
            assert migracion.get(clave) == valor, clave
        # Más el transporte del alambre, que no es del motor sino del extracto.
        assert migracion["transpPerLb"] == 0.3
        assert set(migracion) - set(motor) == {"transpPerLb"}

    def test_borra_el_juego_de_la_v5_y_respeta_el_de_la_v7(self):
        texto = MIGRACION.read_text(encoding="utf-8")
        # La V5 se reconoce por su escalera y se borra: ya no existe en
        # ninguna otra parte del proyecto.
        assert "DELETE FROM param_juegos" in texto
        assert "'[12, 16, 20, 24]'::jsonb" in texto
        # Un juego vigente con la escalera de la V7 no se toca.
        assert "'[30, 30, 30, 30]'::jsonb" in texto and "RETURN;" in texto


class TestLaMigracion007:
    """Una base nueva nace ya con los parámetros de la V7, sin pasar por la V5."""

    def test_siembra_los_del_motor(self):
        ruta = RAIZ / "sql" / "migrations" / "007_catalogo_costeo.sql"
        texto = ruta.read_text(encoding="utf-8")
        pares = dict(re.findall(r"'(\w+)', '([^']+)'::jsonb\)", texto))
        motor = nucleo.parametros_del_motor()
        for clave, valor in motor.items():
            assert json.loads(pares[clave]) == valor, clave
        assert json.loads(pares["transpPerLb"]) == 0.3
        assert "12, 16, 20, 24" not in texto
