"""Adaptador de costeo: geometría del resorte y armado del PN.

El caso que más importa: que un dato ausente no se convierta en una constante
inventada. La versión anterior de este módulo ponía 2.50 USD/lb, máquina
«AIM 3000», 6 h de setup y 327 pph a cualquier resorte.
"""

import math
import os
import subprocess
import unittest
from pathlib import Path

os.environ.setdefault("IMAP_SERVER", "smtp.test.local")
os.environ.setdefault("IMAP_USER", "remitente@cgr.com")
os.environ.setdefault("IMAP_PASSWORD", "secreto")

from pricing import rodea_adapter  # noqa: E402
from tests.pricing.test_repository import (  # noqa: E402
    _EMPAQUE,
    _MAQUINA,
    _MATERIAL,
    FakeConn,
)

RAIZ = Path(__file__).resolve().parents[2]


def _conn(params=None, maquina=_MAQUINA, material=_MATERIAL, empaque=_EMPAQUE):
    return FakeConn([params if params is not None else [("matMk", 6), ("scrapDefault", 5)],
                     maquina, material, empaque])


_RESORTE = {
    "tipo_resorte": "compresion",
    "material": "MW",
    "diametro_alambre_mm": 1.6,
    "diametro_exterior_mm": 12.0,
    "numero_espiras_totales": 10,
    "cantidad": 5000,
}


class TestGeometria(unittest.TestCase):

    def test_longitud_desarrollada_desde_diametro_exterior(self):
        # Dm = OD - d = 12 - 1.6 = 10.4 mm; L = pi * Dm * Nt
        esperado = math.pi * (10.4 / 25.4) * 10
        self.assertAlmostEqual(
            rodea_adapter.longitud_desarrollada_pulg(_RESORTE), esperado, places=6)

    def test_tambien_sirve_el_diametro_interior(self):
        datos = {"diametro_alambre_mm": 1.6, "diametro_interior_mm": 8.8,
                 "numero_espiras_totales": 10}
        # Dm = ID + d = 8.8 + 1.6 = 10.4, el mismo resorte por el otro lado
        self.assertAlmostEqual(
            rodea_adapter.longitud_desarrollada_pulg(datos),
            rodea_adapter.longitud_desarrollada_pulg(_RESORTE), places=6)

    def test_el_diametro_medio_tiene_prioridad(self):
        datos = dict(_RESORTE, diametro_medio_mm=10.4)
        self.assertAlmostEqual(
            rodea_adapter.longitud_desarrollada_pulg(datos),
            rodea_adapter.longitud_desarrollada_pulg(_RESORTE), places=6)

    def test_en_compresion_se_estima_el_total_desde_las_activas(self):
        """Compresión lleva dos espiras de cierre; en otros tipos no aplica."""
        datos = {"tipo_resorte": "compresion", "diametro_alambre_mm": 1.6,
                 "diametro_exterior_mm": 12.0, "numero_espiras_activas": 8}
        self.assertAlmostEqual(
            rodea_adapter.longitud_desarrollada_pulg(datos),
            rodea_adapter.longitud_desarrollada_pulg(_RESORTE), places=6)

    def test_sin_geometria_suficiente_devuelve_none(self):
        incompletos = [
            {},
            {"diametro_alambre_mm": 1.6},                                  # sin diámetros
            {"diametro_alambre_mm": 1.6, "diametro_exterior_mm": 12.0},    # sin espiras
            {"diametro_exterior_mm": 12.0, "numero_espiras_totales": 10},  # sin alambre
            {"diametro_alambre_mm": 0, "diametro_exterior_mm": 12.0,
             "numero_espiras_totales": 10},
            # Las espiras activas sólo permiten estimar el total en compresión:
            {"tipo_resorte": "torsion", "diametro_alambre_mm": 1.6,
             "diametro_exterior_mm": 12.0, "numero_espiras_activas": 8},
        ]
        for datos in incompletos:
            with self.subTest(datos=datos):
                self.assertIsNone(rodea_adapter.longitud_desarrollada_pulg(datos))

    def test_el_peso_coincide_con_el_del_motor_javascript(self):
        """Si las dos fórmulas divergen, el costo de material que calculamos no
        es el que el motor habría calculado."""
        longitud = rodea_adapter.longitud_desarrollada_pulg(_RESORTE)
        nuestro = rodea_adapter.peso_alambre_lb(longitud, 1.6, "MW")

        script = (
            "const {ENGINE}=require('./pricing/nucleo/engine.js');"
            f"process.stdout.write(String(ENGINE.wireFormWeight({longitud!r},{1.6/25.4!r},'MW')))"
        )
        try:
            salida = subprocess.run(["node", "-e", script], cwd=RAIZ, text=True,
                                    capture_output=True, timeout=30, check=True)
        except (FileNotFoundError, subprocess.SubprocessError) as err:
            self.skipTest(f"Node.js no disponible: {err}")

        self.assertAlmostEqual(nuestro, float(salida.stdout), places=10)

    def test_la_tabla_de_densidades_es_la_del_motor(self):
        """Ninguna densidad de más, ninguna de menos, ninguna distinta.

        Llegó a haber dos entradas (SS177 y 316) que el motor no tiene: para
        esos materiales el peso calculado aquí y el que el motor habría
        calculado no coincidían, y el costo de materia prima salía distinto
        según por dónde se mirara.
        """
        # Las claves salen de la tabla del propio motor (WIRE_DENS), no de la
        # nuestra: así se nota tanto una que falte aquí como una de más.
        script = (
            "const fs=require('fs');"
            "const {ENGINE}=require('./pricing/nucleo/engine.js');"
            "const src=fs.readFileSync('./pricing/nucleo/engine.js','utf8');"
            "const tabla=src.match(/WIRE_DENS=\\{([^}]*)\\}/)[1];"
            "const o={};"
            "for(const par of tabla.split(',')) {const c=par.split(':')[0].trim(); if(c) o[c]=ENGINE.wireDensity(c);}"
            "process.stdout.write(JSON.stringify(o))"
        )
        try:
            salida = subprocess.run(["node", "-e", script], cwd=RAIZ, text=True,
                                    capture_output=True, timeout=30, check=True)
        except (FileNotFoundError, subprocess.SubprocessError) as err:
            self.skipTest(f"Node.js no disponible: {err}")

        import json
        del_motor = json.loads(salida.stdout)
        self.assertEqual(set(del_motor), set(rodea_adapter._DENSIDAD_LB_IN3))
        for codigo, densidad_motor in del_motor.items():
            with self.subTest(material=codigo):
                nuestra = rodea_adapter._DENSIDAD_LB_IN3.get(
                    codigo, rodea_adapter._DENSIDAD_POR_DEFECTO)
                self.assertAlmostEqual(
                    nuestra, densidad_motor, places=6,
                    msg=f"{codigo}: {nuestra} aquí vs {densidad_motor} en el motor")

    def test_la_densidad_depende_del_material(self):
        longitud = 10.0
        acero = rodea_adapter.peso_alambre_lb(longitud, 1.6, "MW")     # 0.284
        bronce = rodea_adapter.peso_alambre_lb(longitud, 1.6, "PHOSB")  # 0.320
        self.assertGreater(bronce, acero)

    def test_material_desconocido_usa_la_densidad_del_acero(self):
        self.assertAlmostEqual(
            rodea_adapter.peso_alambre_lb(10.0, 1.6, "NO-EXISTE"),
            rodea_adapter.peso_alambre_lb(10.0, 1.6, "MW"))


class TestArmadoDelPn(unittest.TestCase):

    def test_los_valores_salen_del_catalogo_no_de_constantes(self):
        # Un catálogo completo también trae las capacidades de la máquina, su
        # tope por material (aquí, ninguno) y el transporte del alambre: sin
        # ellos el adaptador lo anota como faltante, y con razón.
        from unittest import mock
        from pricing import repository
        cap = {"alambre_min_mm": 0.5, "alambre_max_mm": 3.0, "od_max_mm": 40.0}
        with mock.patch.object(repository, "capacidad_de_maquina", return_value=cap), \
             mock.patch.object(repository, "tope_de_maquina", return_value={}):
            pn, cat = rodea_adapter.build_pn_for_engine(
                "RFQ-1", _RESORTE,
                conexion=_conn([("matMk", 6), ("scrapDefault", 5), ("transpPerLb", 0.3)]))

        ruta = pn["tiers"][0]["routing"][0]
        self.assertEqual(ruta["machine"], "NUCOIL CSF-200")   # no "AIM 3000"
        self.assertEqual(ruta["setupH"], 6.0)
        self.assertEqual(ruta["pph"], 327)
        self.assertEqual(ruta["scrapPct"], 5)                 # de param_valores
        self.assertEqual(pn["material"]["basePerLb"], 2.55)   # no 2.50
        self.assertEqual(pn["material"]["mkPct"], 6)          # de param_valores
        self.assertEqual(pn["tiers"][0]["qty"], 5000)
        self.assertTrue(cat.completo, cat.faltantes)

    def test_manda_el_peso_para_que_el_material_no_salga_en_cero(self):
        pn, _ = rodea_adapter.build_pn_for_engine("RFQ-1", _RESORTE, conexion=_conn())
        self.assertIsNotNone(pn["material"]["weightLb"])
        self.assertGreater(pn["material"]["weightLb"], 0)
        self.assertIsNotNone(pn["material"]["devLenIn"])

    def test_sin_geometria_lo_reporta_en_vez_de_costear_material_cero(self):
        sin_espiras = dict(_RESORTE)
        sin_espiras.pop("numero_espiras_totales")
        pn, cat = rodea_adapter.build_pn_for_engine("RFQ-1", sin_espiras, conexion=_conn())
        self.assertIsNone(pn["material"]["weightLb"])
        self.assertFalse(cat.completo)
        self.assertTrue(any("peso del alambre" in f for f in cat.faltantes), cat.faltantes)

    def test_extension_avisa_de_los_ganchos(self):
        """El peso sólo cubre el cuerpo: en extensión faltan los ganchos."""
        datos = dict(_RESORTE, tipo_resorte="extension")
        _, cat = rodea_adapter.build_pn_for_engine("RFQ-1", datos, conexion=_conn())
        self.assertTrue(any("ganchos o patas" in f for f in cat.faltantes), cat.faltantes)

    def test_material_desconocido_no_se_sustituye_por_music_wire(self):
        conn = FakeConn([[("matMk", 6)], _MAQUINA, None, _EMPAQUE])
        datos = dict(_RESORTE, material="XXX")
        pn, cat = rodea_adapter.build_pn_for_engine("RFQ-1", datos, conexion=conn)
        self.assertEqual(pn["material"]["code"], "XXX")   # antes caía a "MW"
        self.assertIsNone(pn["material"]["basePerLb"])
        self.assertFalse(cat.completo)

    def test_sin_cantidad_lo_reporta(self):
        sin_cantidad = dict(_RESORTE)
        sin_cantidad.pop("cantidad")
        _, cat = rodea_adapter.build_pn_for_engine("RFQ-1", sin_cantidad, conexion=_conn())
        self.assertTrue(any("cantidad" in f for f in cat.faltantes), cat.faltantes)

    def test_datos_basura_no_revientan(self):
        """El extractor de visión puede devolver cadenas o None en cualquier campo."""
        basura = {"tipo_resorte": None, "material": None,
                  "diametro_alambre_mm": "no es un número",
                  "diametro_exterior_mm": None, "cantidad": "muchas"}
        pn, cat = rodea_adapter.build_pn_for_engine("RFQ-1", basura, conexion=_conn())
        self.assertIsInstance(pn, dict)
        self.assertFalse(cat.completo)

    def test_el_pn_tiene_siempre_cinco_escalones(self):
        pn, _ = rodea_adapter.build_pn_for_engine("RFQ-1", _RESORTE, conexion=_conn())
        self.assertEqual(len(pn["tiers"]), 5)

    def test_los_escalones_vacios_no_comparten_el_mismo_diccionario(self):
        """Con dict() se copia; con la misma referencia, escribir en un escalón
        vacío los cambiaría todos."""
        pn, _ = rodea_adapter.build_pn_for_engine("RFQ-1", _RESORTE, conexion=_conn())
        pn["tiers"][1]["qty"] = 999
        self.assertIsNone(pn["tiers"][2]["qty"])

    def test_el_tipo_determina_la_descripcion(self):
        for tipo, desc in [("compresion", "Compression Spring"),
                           ("extension", "Tension Spring"),
                           ("torsion", "Torsion Spring"),
                           ("wireform", "Wire Form")]:
            with self.subTest(tipo=tipo):
                pn, _ = rodea_adapter.build_pn_for_engine(
                    "RFQ-1", dict(_RESORTE, tipo_resorte=tipo), conexion=_conn())
                self.assertEqual(pn["desc"], desc)


class TestOverrides(unittest.TestCase):

    def test_sin_parametros_no_manda_nada(self):
        self.assertEqual(rodea_adapter.overrides_de_parametros({}), {})

    def test_incluye_el_representante_cuando_lo_hay(self):
        """Estaba escrito a mano en runner.js, así que todas las cotizaciones
        salían a nombre de la misma persona."""
        overrides = rodea_adapter.overrides_de_parametros({"matMk": 6}, "Nic Scherer")
        self.assertEqual(overrides["rep"], "Nic Scherer")
        self.assertEqual(overrides["params"], {"matMk": 6})

    def test_sin_representante_no_lo_incluye(self):
        self.assertNotIn("rep", rodea_adapter.overrides_de_parametros({"matMk": 6}))

    def test_manda_las_cajas_al_motor(self):
        overrides = rodea_adapter.overrides_de_parametros(
            {"matMk": 6}, None, {"packing": [{"id": "COR11050", "price": 0.83}]})
        self.assertEqual(overrides["dbs"]["packing"][0]["price"], 0.83)


class TestLasCajasDelMotor(unittest.TestCase):
    """El motor busca la caja del tramo por código en `dbs.packing`: si no
    está, el empaque sale en cero y nadie lo ve."""

    def test_van_las_del_catalogo_con_su_precio(self):
        cajas = rodea_adapter._cajas_para_el_motor(
            [{"id": "COR11050", "price": 0.83, "desc": "x"},
             {"id": "COR100803", "price": 0.63}], {})
        self.assertEqual(cajas, [{"id": "COR11050", "price": 0.83},
                                 {"id": "COR100803", "price": 0.63}])

    def test_el_empaque_del_catalogo_entra_si_no_estaba(self):
        cajas = rodea_adapter._cajas_para_el_motor(
            [], {"codigo": "GAYLORD", "precio": 30.0})
        self.assertEqual(cajas, [{"id": "GAYLORD", "price": 30.0}])

    def test_el_pn_armado_las_lleva(self):
        pn, cat = rodea_adapter.build_pn_for_engine("RFQ-1", _RESORTE, conexion=_conn())
        ids = {c["id"] for c in cat.dbs_motor["packing"]}
        self.assertIn(pn["tiers"][0]["packing"]["id"], ids)


if __name__ == "__main__":
    unittest.main()
