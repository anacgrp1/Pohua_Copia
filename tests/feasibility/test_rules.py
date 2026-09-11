"""Pruebas de src/rules.py (COT-74). Sin BD ni red."""
import json
import os
import tempfile
import unittest

import app.feasibility.rules as rf


def _reglas_minimas(**cambios):
    """Directrices válidas mínimas; los tests las estropean a propósito."""
    datos = {
        "version": "test-1",
        "tipos_fabricables": ["compresion", "torsion"],
        "tolerancia_minima_mm": 0.05,
        "confianza_minima": 0.7,
        "materiales_soportados": [
            {"nombre": "Acero inoxidable AISI 302", "alias": ["302", "aisi 302"]},
        ],
        "rangos": {
            "_comun": {"diametro_alambre_mm": {"min": 0.2, "max": 12.0}},
            "torsion": {"diametro_alambre_mm": {"min": 0.2, "max": 8.0}},
        },
        "requeridos": {"_comun": ["diametro_alambre_mm"], "torsion": ["angulo_brazos_grados"]},
    }
    datos.update(cambios)
    return datos


class FuenteFalsa(rf.FuenteReglas):
    """Fuente en memoria: el mismo contrato que tendrá la futura tabla."""

    def __init__(self, datos, marca="1"):
        self.datos = datos
        self.marca = marca
        self.lecturas = 0

    def id(self):
        return f"falsa:{self.marca}"

    def leer(self):
        self.lecturas += 1
        return self.datos


class TestArchivoDelProyecto(unittest.TestCase):
    """El archivo provisional que se versiona en el repo debe ser válido."""

    def setUp(self):
        rf.limpiar_cache()

    def test_carga_el_archivo_real(self):
        reglas = rf.cargar_reglas()
        self.assertTrue(reglas.version)
        self.assertIn("compresion", reglas.tipos_fabricables)
        self.assertTrue(reglas.materiales)

    def test_los_tres_tipos_de_resorte_enrollado(self):
        reglas = rf.cargar_reglas()
        for tipo in ("compresion", "torsion", "extension"):
            self.assertTrue(reglas.tipo_fabricable(tipo), tipo)

    def test_el_alambre_formado_va_a_revision_del_pm(self):
        # Son 40 de 346 partidas cotizadas, pero la planta no tiene reglas
        # declaradas para ellas y las de resorte enrollado no aplican: el
        # índice sobre un doblez leído como OD daría un crítico falso.
        # Decisión del equipo: que las mire una persona hasta que las defina.
        self.assertFalse(rf.cargar_reglas().tipo_fabricable("alambre_formado"))

    def test_los_materiales_son_los_del_catalogo_isc(self):
        reglas = rf.cargar_reglas()
        self.assertEqual(len(reglas.materiales), 15)
        for texto, esperado in (
            ("MUSIC WIRE ASTM A228", "Music Wire (ASTM A228)"),
            ("SS 302", "Stainless Steel 302/304 (ASTM A313)"),
            ("Inconel X-750", "Inconel X-750 (AMS 5698/5699)"),
            ("PHOSB", "Phosphor Bronze (ASTM B159)"),
        ):
            self.assertEqual(reglas.material_soportado(texto), esperado, texto)

    def test_el_limite_duro_del_alambre_es_la_regla_del_negocio(self):
        # ISC Price Calculator: wireMaxIn 0.59" = 15 mm, "NOT FEASIBLE at ISC".
        rango = rf.cargar_reglas().rango("compresion", "diametro_alambre_mm")
        self.assertEqual(rango["max"], 15.0)
        self.assertEqual(rango["preferido_max"], 6.0)   # envolvente de máquinas

    def test_la_torsion_tiene_su_propio_envolvente(self):
        reglas = rf.cargar_reglas()
        # La HX-60 llega a OD 90 pero no hace torsión; la mayor que sí, 80.
        self.assertEqual(
            reglas.rango("torsion", "diametro_exterior_mm")["preferido_max"], 80.0)
        self.assertEqual(
            reglas.rango("compresion", "diametro_exterior_mm")["preferido_max"], 90.0)

    def test_el_modelo_de_puntuacion_es_el_de_isc(self):
        reglas = rf.cargar_reglas()
        self.assertTrue(reglas.puntua)
        self.assertEqual(reglas.umbral_factible, 70)   # banda "Manufacturable"
        self.assertEqual(reglas.banda(100), "Easy to manufacture")
        self.assertEqual(reglas.banda(60), "Engineering review")
        self.assertEqual(reglas.banda(10), "Not recommended")

    def test_sin_tolerancia_declarada_no_se_evalua(self):
        # La planta no tiene un mínimo declarado; en null el motor no revisa.
        self.assertIsNone(rf.cargar_reglas().tolerancia_minima_mm)

    def test_ruta_por_defecto_es_relativa_a_la_raiz(self):
        # No depende del cwd: se resuelve contra la carpeta que contiene src/.
        ruta = rf._resolver_ruta(None)
        self.assertTrue(ruta.is_absolute())
        self.assertTrue(ruta.exists(), f"no existe {ruta}")


class TestFuentes(unittest.TestCase):
    def setUp(self):
        rf.limpiar_cache()

    def test_fuente_alterna_sin_tocar_el_motor(self):
        fuente = FuenteFalsa(_reglas_minimas())
        reglas = rf.cargar_reglas(fuente=fuente)
        self.assertEqual(reglas.version, "test-1")

    def test_cachea_por_fuente(self):
        fuente = FuenteFalsa(_reglas_minimas())
        primera = rf.cargar_reglas(fuente=fuente)
        segunda = rf.cargar_reglas(fuente=fuente)
        self.assertIs(primera, segunda)
        self.assertEqual(fuente.lecturas, 1)

    def test_refrescar_vuelve_a_leer(self):
        fuente = FuenteFalsa(_reglas_minimas())
        rf.cargar_reglas(fuente=fuente)
        rf.cargar_reglas(fuente=fuente, refrescar=True)
        self.assertEqual(fuente.lecturas, 2)

    def test_id_distinto_es_otra_carga(self):
        rf.cargar_reglas(fuente=FuenteFalsa(_reglas_minimas(), marca="1"))
        otras = rf.cargar_reglas(
            fuente=FuenteFalsa(_reglas_minimas(version="test-2"), marca="2"))
        self.assertEqual(otras.version, "test-2")

    def test_archivo_inexistente(self):
        with self.assertRaises(rf.ReglasInvalidasError):
            rf.FuenteArchivo(os.path.join(tempfile.gettempdir(), "no_existe_xyz.json")).leer()

    def test_archivo_con_json_roto(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "reglas.json")
            with open(ruta, "w", encoding="utf-8") as fh:
                fh.write("{ esto no es json")
            with self.assertRaises(rf.ReglasInvalidasError):
                rf.FuenteArchivo(ruta).leer()

    def test_archivo_valido_en_disco(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "reglas.json")
            with open(ruta, "w", encoding="utf-8") as fh:
                json.dump(_reglas_minimas(), fh)
            reglas = rf.cargar_reglas(fuente=rf.FuenteArchivo(ruta))
            self.assertEqual(reglas.version, "test-1")


class TestValidacion(unittest.TestCase):
    def _falla(self, **cambios):
        with self.assertRaises(rf.ReglasInvalidasError):
            rf.Reglas(_reglas_minimas(**cambios))

    def test_no_es_objeto(self):
        with self.assertRaises(rf.ReglasInvalidasError):
            rf.Reglas(["no", "es", "objeto"])

    def test_sin_version(self):
        datos = _reglas_minimas()
        del datos["version"]
        with self.assertRaises(rf.ReglasInvalidasError):
            rf.Reglas(datos)

    def test_tipos_vacios(self):
        self._falla(tipos_fabricables=[])

    def test_materiales_vacios(self):
        self._falla(materiales_soportados=[])

    def test_material_sin_nombre(self):
        self._falla(materiales_soportados=[{"alias": ["302"]}])

    def test_alias_mal_formado(self):
        self._falla(materiales_soportados=[{"nombre": "X", "alias": "302"}])

    def test_rango_invertido(self):
        self._falla(rangos={"_comun": {"diametro_alambre_mm": {"min": 9, "max": 2}}})

    def test_rango_no_numerico(self):
        self._falla(rangos={"_comun": {"diametro_alambre_mm": {"min": "dos"}}})

    def test_clave_desconocida_en_la_raiz(self):
        # `tolerancia_minima` sin el _mm apagaría la comprobación en silencio.
        datos = _reglas_minimas()
        datos["tolerancia_minima"] = 0.05
        with self.assertRaises(rf.ReglasInvalidasError):
            rf.Reglas(datos)

    def test_los_bloques_de_documentacion_si_valen(self):
        # El motor no los lee, pero viajan con el archivo.
        reglas = rf.Reglas(_reglas_minimas(
            pendientes=["falta la tolerancia"], referencia={"maquinas": []},
            fuente="ISC_V4_DATA.json", actualizado="2026-08-20"))
        self.assertEqual(reglas.fuente, "ISC_V4_DATA.json")

    def test_clave_desconocida_en_puntuacion(self):
        with self.assertRaises(rf.ReglasInvalidasError):
            rf.Reglas(_reglas_minimas(puntuacion={
                "umbral_factible": 70, "umbral": 80,
                "bandas": [{"desde": 0, "banda": "X"}]}))

    def test_clave_desconocida_en_un_rango(self):
        # Un `preferido_maximo` mal escrito dejaría el límite sin efecto.
        self._falla(rangos={"_comun": {"diametro_alambre_mm":
                                       {"max": 10, "preferido_maximo": 6}}})

    def test_clave_desconocida_en_un_material(self):
        self._falla(materiales_soportados=[
            {"nombre": "X", "alias": ["x"], "rango_alambre": {"min": 1}}])

    def test_las_claves_documentales_del_material_si_valen(self):
        reglas = rf.Reglas(_reglas_minimas(materiales_soportados=[
            {"nombre": "Music Wire", "codigo": "MW", "alias": ["mw"],
             "rango_alambre_mm": {"min": 0.1, "max": 6.5}}]))
        self.assertEqual(reglas.materiales, ("Music Wire",))

    def test_rango_vacio(self):
        self._falla(rangos={"_comun": {"diametro_alambre_mm": {}}})

    def test_banda_preferida_invertida(self):
        self._falla(rangos={"_comun": {"diametro_alambre_mm":
                                       {"preferido_min": 9, "preferido_max": 2}}})

    def test_preferido_min_por_debajo_del_min(self):
        # La banda preferida vive dentro de la fabricable; al revés no dice nada.
        self._falla(rangos={"_comun": {"diametro_alambre_mm":
                                       {"min": 1, "max": 10, "preferido_min": 0.5}}})

    def test_preferido_max_por_encima_del_max(self):
        self._falla(rangos={"_comun": {"diametro_alambre_mm":
                                       {"min": 1, "max": 10, "preferido_max": 12}}})

    def test_solo_banda_preferida_es_valido(self):
        # Un límite "blando" sin límite duro: fabricable, pero fuera de lo habitual.
        reglas = rf.Reglas(_reglas_minimas(
            rangos={"_comun": {"diametro_exterior_mm": {"preferido_max": 90}}}))
        self.assertEqual(reglas.rango(None, "diametro_exterior_mm")["preferido_max"], 90)

    def test_nota_debe_ser_texto(self):
        self._falla(rangos={"_comun": {"diametro_alambre_mm": {"max": 10, "nota": 5}}})

    def test_rango_de_material_mal_formado(self):
        self._falla(materiales_soportados=[
            {"nombre": "X", "rango_alambre_mm": {"min": 9, "max": 2}}])

    def test_requeridos_mal_formados(self):
        self._falla(requeridos={"_comun": "diametro_alambre_mm"})

    def test_confianza_fuera_de_0_1(self):
        self._falla(confianza_minima=1.5)

    def test_tolerancia_no_numerica(self):
        self._falla(tolerancia_minima_mm="cero coma cero cinco")


_PUNTUACION = {
    "umbral_factible": 70,
    "bandas": [
        {"desde": 90, "banda": "Easy to manufacture"},
        {"desde": 70, "banda": "Manufacturable"},
        {"desde": 50, "banda": "Engineering review"},
        {"desde": 30, "banda": "High manufacturing risk"},
        {"desde": 0, "banda": "Not recommended"},
    ],
    "penalizaciones": {"fuera_de_rango": 24, "fuera_del_preferido": 9},
}


class TestPuntuacion(unittest.TestCase):
    """El modelo de puntuación es opcional y vive en el archivo (COT-74)."""

    def setUp(self):
        rf.limpiar_cache()

    def test_sin_bloque_no_puntua(self):
        self.assertFalse(rf.Reglas(_reglas_minimas()).puntua)

    def test_con_bloque_puntua(self):
        reglas = rf.Reglas(_reglas_minimas(puntuacion=_PUNTUACION))
        self.assertTrue(reglas.puntua)
        self.assertEqual(reglas.umbral_factible, 70)

    def test_bandas_por_tramo(self):
        reglas = rf.Reglas(_reglas_minimas(puntuacion=_PUNTUACION))
        for score, esperada in ((100, "Easy to manufacture"),
                                (90, "Easy to manufacture"),
                                (89, "Manufacturable"),
                                (70, "Manufacturable"),
                                (69, "Engineering review"),
                                (30, "High manufacturing risk"),
                                (0, "Not recommended")):
            self.assertEqual(reglas.banda(score), esperada, score)

    def test_banda_de_none(self):
        self.assertIsNone(rf.Reglas(_reglas_minimas(puntuacion=_PUNTUACION)).banda(None))

    def test_penalizacion_general(self):
        reglas = rf.Reglas(_reglas_minimas(puntuacion=_PUNTUACION))
        self.assertEqual(reglas.penalizacion("fuera_de_rango"), 24)
        self.assertEqual(reglas.penalizacion("codigo_inventado"), 0)

    def test_la_del_rango_manda(self):
        reglas = rf.Reglas(_reglas_minimas(puntuacion=_PUNTUACION))
        limites = {"min": 4, "max": 15, "penalizacion": {"fuera_de_rango": 26}}
        self.assertEqual(reglas.penalizacion("fuera_de_rango", limites), 26)
        # Lo que el rango no declara sigue saliendo de la tabla general.
        self.assertEqual(reglas.penalizacion("fuera_del_preferido", limites), 9)


class TestValidacionPuntuacion(unittest.TestCase):

    def _falla(self, puntuacion):
        with self.assertRaises(rf.ReglasInvalidasError):
            rf.Reglas(_reglas_minimas(puntuacion=puntuacion))

    def test_sin_umbral(self):
        self._falla({"bandas": _PUNTUACION["bandas"]})

    def test_umbral_fuera_de_0_100(self):
        self._falla(dict(_PUNTUACION, umbral_factible=150))

    def test_sin_bandas(self):
        self._falla({"umbral_factible": 70, "bandas": []})

    def test_bandas_desordenadas(self):
        self._falla({"umbral_factible": 70, "bandas": [
            {"desde": 0, "banda": "Not recommended"},
            {"desde": 90, "banda": "Easy to manufacture"}]})

    def test_la_ultima_banda_no_arranca_en_cero(self):
        # Si no, hay scores bajos que se quedan sin banda.
        self._falla({"umbral_factible": 70, "bandas": [
            {"desde": 90, "banda": "Easy"}, {"desde": 50, "banda": "Review"}]})

    def test_banda_sin_etiqueta(self):
        self._falla({"umbral_factible": 70, "bandas": [{"desde": 0}]})

    def test_penalizacion_negativa(self):
        self._falla(dict(_PUNTUACION, penalizaciones={"fuera_de_rango": -5}))

    def test_penalizacion_no_numerica(self):
        self._falla(dict(_PUNTUACION, penalizaciones={"fuera_de_rango": "mucho"}))

    def test_penalizacion_del_rango_mal_formada(self):
        with self.assertRaises(rf.ReglasInvalidasError):
            rf.Reglas(_reglas_minimas(rangos={"_comun": {
                "diametro_alambre_mm": {"max": 10, "penalizacion": {"x": -1}}}}))


class TestPenalizacionPorLadoYTipo(unittest.TestCase):
    """Los números de ISC: distintos por tipo de resorte y por extremo."""

    def setUp(self):
        rf.limpiar_cache()

    def test_el_archivo_real_trae_los_numeros_de_isc(self):
        reglas = rf.cargar_reglas()
        esperado = {
            # tipo:        (C<4, C>15, C 4-5, C 12-15)
            "compresion":  (26, 20, 10, 8),
            "extension":   (24, 18, 9, 7),
            "torsion":     (24, 18, 9, 7),
        }
        for tipo, (dur_min, dur_max, pref_min, pref_max) in esperado.items():
            limites = reglas.rango(tipo, "indice_resorte")
            self.assertEqual(
                (reglas.penalizacion("fuera_de_rango", limites, "min"),
                 reglas.penalizacion("fuera_de_rango", limites, "max"),
                 reglas.penalizacion("fuera_del_preferido", limites, "min"),
                 reglas.penalizacion("fuera_del_preferido", limites, "max")),
                (dur_min, dur_max, pref_min, pref_max), tipo)

    def test_los_umbrales_del_indice_se_heredan(self):
        # Torsión y extensión sólo declaran penalizaciones; los límites
        # (4-15, 5-12) vienen de `_comun`.
        reglas = rf.cargar_reglas()
        for tipo in ("compresion", "extension", "torsion"):
            limites = reglas.rango(tipo, "indice_resorte")
            self.assertEqual((limites["min"], limites["max"]), (4.0, 15.0), tipo)
            self.assertEqual(
                (limites["preferido_min"], limites["preferido_max"]), (5.0, 12.0), tipo)

    def test_espiras_solo_donde_isc_las_tiene(self):
        reglas = rf.cargar_reglas()
        compresion = reglas.rango("compresion", "numero_espiras_activas")
        torsion = reglas.rango("torsion", "numero_espiras_activas")
        self.assertEqual(reglas.penalizacion("fuera_del_preferido", compresion, "min"), 10)
        self.assertEqual(reglas.penalizacion("fuera_del_preferido", torsion, "min"), 8)
        # ISC no puntúa las espiras en extensión: no hay regla que heredar.
        self.assertIsNone(reglas.rango("extension", "numero_espiras_activas"))

    def test_numero_suelto_aplica_a_los_dos_lados(self):
        reglas = rf.Reglas(_reglas_minimas(puntuacion=_PUNTUACION))
        limites = {"min": 1, "max": 9, "penalizacion": {"fuera_de_rango": 12}}
        self.assertEqual(reglas.penalizacion("fuera_de_rango", limites, "min"), 12)
        self.assertEqual(reglas.penalizacion("fuera_de_rango", limites, "max"), 12)

    def test_penalizacion_por_lado_donde_no_hay_lado(self):
        # Captura equivocada: mejor que penalice de más y se note.
        reglas = rf.Reglas(_reglas_minimas(puntuacion=dict(
            _PUNTUACION, penalizaciones={"confianza_baja": {"min": 12, "max": 5}})))
        self.assertEqual(reglas.penalizacion("confianza_baja"), 12)

    def test_lado_no_declarado_no_resta(self):
        reglas = rf.Reglas(_reglas_minimas(puntuacion=_PUNTUACION))
        limites = {"preferido_min": 3, "penalizacion": {"fuera_del_preferido": {"min": 8}}}
        self.assertEqual(reglas.penalizacion("fuera_del_preferido", limites, "min"), 8)
        self.assertEqual(reglas.penalizacion("fuera_del_preferido", limites, "max"), 0)

    def test_lado_invalido_en_el_archivo(self):
        with self.assertRaises(rf.ReglasInvalidasError):
            rf.Reglas(_reglas_minimas(rangos={"_comun": {"diametro_alambre_mm": {
                "max": 10, "penalizacion": {"fuera_de_rango": {"arriba": 5}}}}}))

    def test_bloque_de_tipo_solo_con_penalizaciones(self):
        # Válido: hereda los límites de `_comun`.
        reglas = rf.Reglas(_reglas_minimas(
            puntuacion=_PUNTUACION,
            rangos={"_comun": {"indice_resorte": {"min": 4, "max": 15}},
                    "torsion": {"indice_resorte": {
                        "penalizacion": {"fuera_de_rango": {"min": 24}}}}}))
        limites = reglas.rango("torsion", "indice_resorte")
        self.assertEqual(limites["min"], 4)
        self.assertEqual(reglas.penalizacion("fuera_de_rango", limites, "min"), 24)

    def test_rango_vacio_sigue_siendo_invalido(self):
        with self.assertRaises(rf.ReglasInvalidasError):
            rf.Reglas(_reglas_minimas(rangos={"torsion": {"indice_resorte": {}}}))


class TestConsultas(unittest.TestCase):
    def setUp(self):
        self.reglas = rf.Reglas(_reglas_minimas())

    def test_tipo_fabricable(self):
        self.assertTrue(self.reglas.tipo_fabricable("compresion"))
        self.assertTrue(self.reglas.tipo_fabricable("Compresión"))
        self.assertFalse(self.reglas.tipo_fabricable("extension"))
        self.assertFalse(self.reglas.tipo_fabricable(None))

    def test_material_por_alias(self):
        self.assertEqual(self.reglas.material_soportado("AISI 302"),
                         "Acero inoxidable AISI 302")
        self.assertEqual(self.reglas.material_soportado("ac. inox 302 templado"),
                         "Acero inoxidable AISI 302")

    def test_material_por_nombre_canonico(self):
        self.assertEqual(
            self.reglas.material_soportado("acero inoxidable aisi 302"),
            "Acero inoxidable AISI 302")

    def test_material_no_soportado(self):
        self.assertIsNone(self.reglas.material_soportado("titanio grado 5"))

    def test_material_vacio(self):
        self.assertIsNone(self.reglas.material_soportado(None))
        self.assertIsNone(self.reglas.material_soportado("   "))

    def test_alias_no_casa_dentro_de_otro_numero(self):
        # "302" no debe casar dentro de "1302": daría un material que nadie declaró.
        self.assertIsNone(self.reglas.material_soportado("norma 1302"))

    def test_rangos_del_tipo_pisan_los_comunes(self):
        self.assertEqual(self.reglas.rango("torsion", "diametro_alambre_mm")["max"], 8.0)
        self.assertEqual(
            self.reglas.rango("compresion", "diametro_alambre_mm")["max"], 12.0)

    def test_rangos_de_tipo_desconocido_son_los_comunes(self):
        self.assertEqual(self.reglas.rangos("desconocido"), self.reglas.rangos(None))
        self.assertIn("diametro_alambre_mm", self.reglas.rangos(None))

    def test_requeridos_suma_comunes_y_del_tipo(self):
        self.assertEqual(self.reglas.requeridos("torsion"),
                         ("diametro_alambre_mm", "angulo_brazos_grados"))
        self.assertEqual(self.reglas.requeridos("compresion"), ("diametro_alambre_mm",))

    def test_rango_de_alambre_por_material(self):
        reglas = rf.Reglas(_reglas_minimas(materiales_soportados=[
            {"nombre": "Music Wire", "alias": ["mw"],
             "rango_alambre_mm": {"min": 0.1, "max": 6.5}},
            {"nombre": "Brass", "alias": ["brass"]},
        ]))
        self.assertEqual(reglas.rango_alambre_material("Music Wire"),
                         {"min": 0.1, "max": 6.5})
        self.assertIsNone(reglas.rango_alambre_material("Brass"))
        self.assertIsNone(reglas.rango_alambre_material("Titanio"))
        self.assertIsNone(reglas.rango_alambre_material(None))

    def test_to_dict_es_copia(self):
        copia = self.reglas.to_dict()
        copia["version"] = "manipulada"
        self.assertEqual(self.reglas.version, "test-1")


if __name__ == "__main__":
    unittest.main()
