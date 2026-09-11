"""Pruebas de src/engine.py (COT-75). Sin BD, sin red, sin archivo.

Las reglas se inyectan en cada test, así que el dictamen se prueba contra
valores fijos y no contra los rangos del repo, que cambian cada vez que la
planta revisa sus directrices (COT-73).
"""
import unittest

import app.feasibility.engine as mf
import app.feasibility.rules as rf
import app.vision.spring_extractor as spring_extractor

REGLAS = rf.Reglas({
    "version": "test-1",
    "tipos_fabricables": ["compresion", "torsion", "extension"],
    "tolerancia_minima_mm": 0.05,
    "confianza_minima": 0.7,
    "materiales_soportados": [
        {"nombre": "Acero inoxidable AISI 302", "alias": ["302", "aisi 302"]},
        {"nombre": "Acero al carbono ASTM A228", "alias": ["a228", "music wire"]},
    ],
    "rangos": {
        "_comun": {
            "diametro_alambre_mm": {"min": 0.2, "max": 12.0},
            "diametro_exterior_mm": {"min": 1.0, "max": 150.0},
            "longitud_libre_mm": {"min": 2.0, "max": 600.0},
            "indice_resorte": {"min": 4.0, "max": 14.0},
        },
        "torsion": {"angulo_brazos_grados": {"min": 0, "max": 360}},
    },
    "requeridos": {
        "_comun": ["diametro_alambre_mm", "diametro_exterior_mm", "material"],
        "compresion": ["longitud_libre_mm"],
        "torsion": ["angulo_brazos_grados"],
    },
})

# Resorte que pasa todas las comprobaciones: C = (12 - 1.2) / 1.2 = 9.
FACTIBLE = {
    "tipo_resorte": "compresion",
    "material": "AISI 302",
    "diametro_alambre_mm": 1.2,
    "diametro_exterior_mm": 12.0,
    "longitud_libre_mm": 40.0,
    "tolerancias": "±0.20 mm",
    "confianza": 0.95,
}


def evaluar(**cambios):
    """Evalúa el resorte factible con los campos que indique cada test."""
    return mf.evaluar_factibilidad(dict(FACTIBLE, **cambios), reglas=REGLAS)


def sin(*campos):
    """Evalúa el resorte factible al que le falta algún campo."""
    datos = {k: v for k, v in FACTIBLE.items() if k not in campos}
    return mf.evaluar_factibilidad(datos, reglas=REGLAS)


def codigos(resultado):
    return [motivo["codigo"] for motivo in resultado["motivos"]]


class TestCasoLimpio(unittest.TestCase):
    def test_resorte_factible(self):
        resultado = evaluar()
        self.assertEqual(resultado["veredicto"], mf.VEREDICTO_FACTIBLE)
        self.assertEqual(resultado["motivos"], [])
        self.assertTrue(mf.es_factible(resultado))

    def test_devuelve_la_version_de_las_reglas(self):
        self.assertEqual(evaluar()["reglas_version"], "test-1")

    def test_solo_hay_dos_veredictos(self):
        # COT-75 define feasible / requires review. Nada más.
        for resultado in (evaluar(), evaluar(diametro_alambre_mm=99)):
            self.assertIn(resultado["veredicto"],
                          (mf.VEREDICTO_FACTIBLE, mf.VEREDICTO_REVISION))

    def test_los_niveles_son_los_de_rfq_banderas(self):
        resultado = evaluar(diametro_alambre_mm=99, material="titanio", confianza=0.1)
        for motivo in resultado["motivos"]:
            self.assertIn(motivo["nivel"], ("ok", "info", "warn", "crit"))


class TestReglaDeNegocio(unittest.TestCase):
    """El sistema no declina: detecta, y el plant manager dictamina.

    Si el PM resuelve que no es factible, entonces sí sale el correo de
    declinación al cliente — pero eso lo dispara `veredicto_final`, no este
    módulo.
    """

    def test_el_motor_nunca_declina(self):
        # Un resorte imposible por todos lados sigue siendo "requires review".
        peor = evaluar(tipo_resorte="espiral plana", material="titanio grado 5",
                       diametro_alambre_mm=99.0, diametro_exterior_mm=900.0,
                       tolerancias="±0.001 mm", confianza=0.1)
        self.assertEqual(peor["veredicto"], mf.VEREDICTO_REVISION)
        self.assertNotEqual(peor["veredicto"], mf.FINAL_NO_FACTIBLE)

    def test_el_veredicto_final_es_otro_vocabulario(self):
        # `veredicto_final` lo escribe la pantalla del PM, no el motor.
        self.assertNotIn(mf.FINAL_NO_FACTIBLE,
                         (mf.VEREDICTO_FACTIBLE, mf.VEREDICTO_REVISION))


class TestRangos(unittest.TestCase):
    def test_fuera_de_rango_por_arriba(self):
        resultado = evaluar(diametro_alambre_mm=25.0)
        self.assertEqual(resultado["veredicto"], mf.VEREDICTO_REVISION)
        self.assertIn(mf.FUERA_DE_RANGO, codigos(resultado))

    def test_fuera_de_rango_por_abajo(self):
        self.assertIn(mf.FUERA_DE_RANGO, codigos(evaluar(diametro_alambre_mm=0.05)))

    def test_el_limite_exacto_es_factible(self):
        # 12.0 es el máximo declarado: fabricable, no rechazable.
        resultado = evaluar(diametro_alambre_mm=12.0, diametro_exterior_mm=120.0,
                            longitud_libre_mm=100.0)
        self.assertEqual(resultado["veredicto"], mf.VEREDICTO_FACTIBLE)

    def test_el_motivo_dice_valor_y_limite(self):
        motivo = evaluar(diametro_alambre_mm=25.0)["motivos"][0]
        self.assertEqual(motivo["campo"], "diametro_alambre_mm")
        self.assertEqual(motivo["valor"], 25.0)
        self.assertIn("0.2", motivo["limite"])

    def test_valor_como_texto_con_unidad(self):
        # El extractor ya normaliza, pero el dict fusionado puede traer texto.
        self.assertIn(mf.FUERA_DE_RANGO, codigos(evaluar(diametro_alambre_mm="25 mm")))

    def test_rango_del_tipo_manda(self):
        resultado = mf.evaluar_factibilidad(
            {"tipo_resorte": "torsion", "material": "AISI 302",
             "diametro_alambre_mm": 1.2, "diametro_exterior_mm": 12.0,
             "angulo_brazos_grados": 400},
            reglas=REGLAS)
        self.assertIn(mf.FUERA_DE_RANGO, codigos(resultado))


class TestDatosAusentes(unittest.TestCase):
    """Dato ausente != dato fuera de rango: los dos van a revisión, con motivo distinto."""

    def test_requerido_ausente_es_dato_ausente(self):
        resultado = sin("longitud_libre_mm")
        self.assertEqual(resultado["veredicto"], mf.VEREDICTO_REVISION)
        self.assertEqual(codigos(resultado), [mf.DATO_AUSENTE])
        self.assertNotIn(mf.FUERA_DE_RANGO, codigos(resultado))

    def test_requerido_ausente_es_warn_no_crit(self):
        motivo = sin("diametro_exterior_mm")["motivos"][0]
        self.assertEqual(motivo["nivel"], mf.NIVEL_WARN)

    def test_no_requerido_ausente_no_estorba(self):
        # numero_espiras_totales no está en las reglas de este test: no aplica.
        self.assertEqual(evaluar()["veredicto"], mf.VEREDICTO_FACTIBLE)

    def test_requerido_no_numerico(self):
        resultado = evaluar(diametro_exterior_mm="ver detalle")
        self.assertIn(mf.DATO_NO_NUMERICO, codigos(resultado))

    def test_requerido_sin_rango_declarado(self):
        reglas = rf.Reglas({
            "version": "t", "tipos_fabricables": ["compresion"],
            "materiales_soportados": [{"nombre": "AISI 302", "alias": ["302"]}],
            "rangos": {}, "requeridos": {"_comun": ["acabado"]},
        })
        resultado = mf.evaluar_factibilidad(
            {"tipo_resorte": "compresion", "material": "302"}, reglas=reglas)
        self.assertEqual(codigos(resultado), [mf.DATO_AUSENTE])


class TestTipo(unittest.TestCase):
    def test_tipo_no_fabricable(self):
        resultado = evaluar(tipo_resorte="espiral plana")
        self.assertIn(mf.TIPO_NO_FABRICABLE, codigos(resultado))
        self.assertEqual(resultado["motivos"][0]["nivel"], mf.NIVEL_CRIT)

    def test_tipo_desconocido_avisa_pero_no_es_crit(self):
        resultado = evaluar(tipo_resorte="desconocido")
        self.assertIn(mf.TIPO_DESCONOCIDO, codigos(resultado))
        self.assertEqual(resultado["motivos"][0]["nivel"], mf.NIVEL_WARN)

    def test_tipo_ausente_se_trata_como_desconocido(self):
        self.assertIn(mf.TIPO_DESCONOCIDO, codigos(sin("tipo_resorte")))

    def test_sin_tipo_valido_sigue_evaluando_los_rangos_comunes(self):
        # El PM merece ver todo lo que está mal, no sólo el primer problema.
        resultado = evaluar(tipo_resorte="espiral plana", diametro_alambre_mm=25.0)
        self.assertIn(mf.TIPO_NO_FABRICABLE, codigos(resultado))
        self.assertIn(mf.FUERA_DE_RANGO, codigos(resultado))

    def test_tipo_con_acentos(self):
        self.assertEqual(evaluar(tipo_resorte="Compresión")["veredicto"],
                         mf.VEREDICTO_FACTIBLE)


class TestMaterial(unittest.TestCase):
    def test_material_ausente(self):
        resultado = sin("material")
        self.assertIn(mf.MATERIAL_AUSENTE, codigos(resultado))

    def test_material_no_soportado(self):
        resultado = evaluar(material="titanio grado 5")
        self.assertIn(mf.MATERIAL_NO_SOPORTADO, codigos(resultado))
        self.assertEqual(resultado["motivos"][0]["nivel"], mf.NIVEL_CRIT)

    def test_material_reconocido_por_alias(self):
        self.assertEqual(evaluar(material="MUSIC WIRE ASTM A228")["veredicto"],
                         mf.VEREDICTO_FACTIBLE)


class TestTolerancias(unittest.TestCase):
    def test_mas_fina_que_la_planta(self):
        resultado = evaluar(tolerancias="±0.01 mm")
        self.assertIn(mf.TOLERANCIA_MAS_FINA, codigos(resultado))

    def test_la_mas_estrecha_es_la_que_manda(self):
        self.assertIn(mf.TOLERANCIA_MAS_FINA,
                      codigos(evaluar(tolerancias="±0.5 mm en L0, ±0.02 mm en OD")))

    def test_tolerancia_holgada_no_estorba(self):
        self.assertEqual(evaluar(tolerancias="+/- 0.5 mm")["veredicto"],
                         mf.VEREDICTO_FACTIBLE)

    def test_tolerancia_igual_al_minimo_pasa(self):
        self.assertEqual(evaluar(tolerancias="±0.05")["veredicto"],
                         mf.VEREDICTO_FACTIBLE)

    def test_coma_decimal(self):
        self.assertIn(mf.TOLERANCIA_MAS_FINA, codigos(evaluar(tolerancias="±0,01 mm")))

    def test_texto_sin_simbolo_no_se_interpreta(self):
        # Un número suelto en ese campo puede ser cualquier cosa.
        self.assertEqual(evaluar(tolerancias="segun norma 0.01")["veredicto"],
                         mf.VEREDICTO_FACTIBLE)

    def test_pulgadas_se_ignoran(self):
        # Comparar ±0.002 in contra un mínimo en mm daría un falso positivo.
        self.assertEqual(evaluar(tolerancias='±0.002 in')["veredicto"],
                         mf.VEREDICTO_FACTIBLE)


class TestIndiceResorte(unittest.TestCase):
    def test_se_calcula_desde_el_exterior(self):
        # d=1.0, OD=4.0 -> Dm=3.0 -> C=3.0, por debajo del mínimo de 4.
        resultado = evaluar(diametro_alambre_mm=1.0, diametro_exterior_mm=4.0)
        motivos = [m for m in resultado["motivos"] if m["campo"] == mf.INDICE_RESORTE]
        self.assertEqual(len(motivos), 1)
        self.assertEqual(motivos[0]["codigo"], mf.FUERA_DE_RANGO)

    def test_el_medio_tiene_prioridad(self):
        resultado = evaluar(diametro_medio_mm=10.8)
        self.assertEqual(resultado["veredicto"], mf.VEREDICTO_FACTIBLE)

    def test_sin_datos_no_inventa_indice(self):
        resultado = mf.evaluar_factibilidad(
            {"tipo_resorte": "compresion", "material": "302",
             "diametro_alambre_mm": 1.2, "diametro_exterior_mm": 12.0,
             "longitud_libre_mm": 40.0, "diametro_medio_mm": 0},
            reglas=REGLAS)
        self.assertNotIn(mf.INDICE_RESORTE,
                         [m["campo"] for m in resultado["motivos"]])


class TestConfianza(unittest.TestCase):
    def test_confianza_baja_va_a_revision(self):
        resultado = evaluar(confianza=0.4)
        self.assertEqual(resultado["veredicto"], mf.VEREDICTO_REVISION)
        self.assertIn(mf.CONFIANZA_BAJA, codigos(resultado))

    def test_confianza_ausente_no_penaliza(self):
        self.assertEqual(sin("confianza")["veredicto"], mf.VEREDICTO_FACTIBLE)


class TestEntradas(unittest.TestCase):
    def test_acepta_el_dataclass_del_extractor(self):
        resorte = spring_extractor.ResorteCotizacion(
            tipo_resorte="compresion", material="AISI 302",
            diametro_alambre_mm=1.2, diametro_exterior_mm=12.0,
            longitud_libre_mm=40.0, cantidad=500, confianza=0.9)
        self.assertEqual(mf.evaluar_factibilidad(resorte, reglas=REGLAS)["veredicto"],
                         mf.VEREDICTO_FACTIBLE)

    def test_acepta_el_dict_fusionado_del_flujo(self):
        # flow.fusionar deja el resorte anidado bajo "resorte".
        fusionado = {"customer": "ACME", "volumen": 500, "resorte": dict(FACTIBLE)}
        self.assertEqual(
            mf.evaluar_factibilidad(fusionado, reglas=REGLAS)["veredicto"],
            mf.VEREDICTO_FACTIBLE)

    def test_entrada_vacia_no_revienta(self):
        resultado = mf.evaluar_factibilidad({}, reglas=REGLAS)
        self.assertEqual(resultado["veredicto"], mf.VEREDICTO_REVISION)
        self.assertTrue(resultado["motivos"])

    def test_entrada_none(self):
        self.assertEqual(mf.evaluar_factibilidad(None, reglas=REGLAS)["veredicto"],
                         mf.VEREDICTO_REVISION)

    def test_entrada_de_tipo_invalido(self):
        with self.assertRaises(TypeError):
            mf.evaluar_factibilidad("un resorte", reglas=REGLAS)


class TestSalidaLegible(unittest.TestCase):
    def test_resumen_lista_los_motivos(self):
        texto = mf.resumen(evaluar(diametro_alambre_mm=25.0, material="titanio"))
        self.assertIn("crit", texto)
        self.assertEqual(len(texto.splitlines()), 2)

    def test_resumen_sin_motivos(self):
        self.assertEqual(mf.resumen(evaluar()), "Sin observaciones.")

    def test_cada_motivo_trae_texto_para_el_pm(self):
        for motivo in evaluar(diametro_alambre_mm=25.0)["motivos"]:
            self.assertTrue(motivo["texto"].strip())


REGLAS_BANDAS = rf.Reglas({
    "version": "bandas-1",
    "tipos_fabricables": ["compresion"],
    "materiales_soportados": [
        {"nombre": "Music Wire (ASTM A228)", "alias": ["mw", "music wire", "a228"],
         "rango_alambre_mm": {"min": 0.1, "max": 6.5}},
        {"nombre": "Brass Wire", "alias": ["brass", "laton"]},
    ],
    "rangos": {
        "_comun": {
            "diametro_alambre_mm": {
                "max": 15.0, "preferido_min": 0.15, "preferido_max": 6.0,
                "nota": "15 mm es el límite del negocio; 6 mm, la envolvente de máquinas.",
            },
            "diametro_exterior_mm": {"preferido_max": 90.0},
        },
    },
    "requeridos": {"_comun": ["diametro_alambre_mm", "material"]},
})

def _por_codigo(resultado, codigo):
    """El primer motivo con ese código, o None. Dos reglas distintas pueden
    señalar el mismo campo, así que filtrar por campo no basta."""
    return next((m for m in resultado["motivos"] if m["codigo"] == codigo), None)


# Dentro de las dos bandas: alambre de 2 mm, OD 20.
EN_BANDA = {"tipo_resorte": "compresion", "material": "Music Wire",
            "diametro_alambre_mm": 2.0, "diametro_exterior_mm": 20.0}


class TestDosBandas(unittest.TestCase):
    """Fabricable vs. habitual: el tramo intermedio existe y se avisa.

    La planta cotizó 11 de 346 partidas con alambre por encima de la
    envolvente de sus máquinas declaradas, pero ninguna por encima del límite
    del negocio. Ese tramo no es "no se puede": es "que lo vea alguien".
    """

    def evaluar(self, **cambios):
        return mf.evaluar_factibilidad(dict(EN_BANDA, **cambios), reglas=REGLAS_BANDAS)

    def test_dentro_de_la_banda_preferida_es_factible(self):
        self.assertEqual(self.evaluar()["veredicto"], mf.VEREDICTO_FACTIBLE)

    def test_entre_lo_preferido_y_lo_fabricable_es_aviso(self):
        resultado = self.evaluar(diametro_alambre_mm=8.0)
        self.assertEqual(resultado["veredicto"], mf.VEREDICTO_REVISION)
        motivo = _por_codigo(resultado, mf.FUERA_DEL_PREFERIDO)
        self.assertIsNotNone(motivo)
        self.assertEqual(motivo["campo"], "diametro_alambre_mm")
        self.assertEqual(motivo["nivel"], mf.NIVEL_WARN)

    def test_fuera_de_lo_fabricable_es_critico(self):
        resultado = self.evaluar(diametro_alambre_mm=16.0)
        motivo = _por_codigo(resultado, mf.FUERA_DE_RANGO)
        self.assertIsNotNone(motivo)
        self.assertEqual(motivo["nivel"], mf.NIVEL_CRIT)

    def test_lo_critico_no_se_reporta_dos_veces(self):
        # Un alambre de 16 mm también está fuera del preferido; sobra decirlo.
        resultado = self.evaluar(diametro_alambre_mm=16.0)
        self.assertIsNone(_por_codigo(resultado, mf.FUERA_DEL_PREFERIDO))

    def test_la_nota_del_archivo_viaja_aparte_del_titulo(self):
        # `texto` va a rfq_banderas.titulo; la nota larga, a datos_json.
        motivo = _por_codigo(self.evaluar(diametro_alambre_mm=8.0),
                             mf.FUERA_DEL_PREFERIDO)
        self.assertIn("límite del negocio", motivo["nota"])
        self.assertNotIn("límite del negocio", motivo["texto"])

    def test_banda_solo_preferida_no_es_nunca_critica(self):
        # diametro_exterior_mm no declara máximo duro.
        resultado = self.evaluar(diametro_exterior_mm=200.0)
        niveles = [m["nivel"] for m in resultado["motivos"]
                   if m["campo"] == "diametro_exterior_mm"]
        self.assertEqual(niveles, [mf.NIVEL_WARN])


class TestRangoDelMaterial(unittest.TestCase):
    """El alambre se compra en ciertos calibres; la máquina es otra cosa."""

    def evaluar(self, **cambios):
        return mf.evaluar_factibilidad(dict(EN_BANDA, **cambios), reglas=REGLAS_BANDAS)

    def test_calibre_fuera_del_material(self):
        # Music Wire llega a 6.5 mm; 7 mm no se consigue.
        resultado = self.evaluar(diametro_alambre_mm=7.0)
        codigos = [m["codigo"] for m in resultado["motivos"]]
        self.assertIn(mf.MATERIAL_FUERA_DE_RANGO, codigos)
        motivo = _por_codigo(resultado, mf.MATERIAL_FUERA_DE_RANGO)
        self.assertEqual(motivo["nivel"], mf.NIVEL_WARN)

    def test_calibre_dentro_del_material(self):
        codigos = [m["codigo"] for m in self.evaluar()["motivos"]]
        self.assertNotIn(mf.MATERIAL_FUERA_DE_RANGO, codigos)

    def test_material_sin_rango_declarado_no_estorba(self):
        resultado = self.evaluar(material="Brass", diametro_alambre_mm=5.0)
        self.assertEqual(resultado["veredicto"], mf.VEREDICTO_FACTIBLE)


REGLAS_PUNTUADAS = rf.Reglas({
    "version": "puntos-1",
    "tipos_fabricables": ["compresion"],
    "confianza_minima": 0.7,
    "materiales_soportados": [{"nombre": "Music Wire", "alias": ["mw", "music wire"]}],
    "rangos": {
        "_comun": {
            "diametro_alambre_mm": {"max": 15.0, "preferido_max": 6.0},
            "indice_resorte": {"min": 4.0, "max": 15.0,
                               "preferido_min": 5.0, "preferido_max": 12.0,
                               "penalizacion": {"fuera_del_preferido": 10}},
        },
    },
    "requeridos": {"_comun": ["diametro_alambre_mm", "material"],
                   "compresion": ["longitud_libre_mm"]},
    "puntuacion": {
        "umbral_factible": 70,
        "bandas": [
            {"desde": 90, "banda": "Easy to manufacture"},
            {"desde": 70, "banda": "Manufacturable"},
            {"desde": 50, "banda": "Engineering review"},
            {"desde": 30, "banda": "High manufacturing risk"},
            {"desde": 0, "banda": "Not recommended"},
        ],
        "penalizaciones": {
            "fuera_de_rango": 24,
            "fuera_del_preferido": 9,
            "dato_ausente": 10,
            "confianza_baja": 12,
            "material_no_soportado": 30,
        },
    },
})

# C = (12 - 1.2) / 1.2 = 9: dentro de todo.
PUNTUADO = {"tipo_resorte": "compresion", "material": "Music Wire",
            "diametro_alambre_mm": 1.2, "diametro_exterior_mm": 12.0,
            "longitud_libre_mm": 40.0, "confianza": 0.95}


class TestPuntuacion(unittest.TestCase):
    """Modelo de ISC: cada hallazgo resta, y el umbral decide.

    Antes cualquier hallazgo mandaba a revision. Con el modelo de la planta,
    un aviso suelto no tumba un diseno; lo que tumba es la acumulacion.
    """

    def evaluar(self, **cambios):
        return mf.evaluar_factibilidad(dict(PUNTUADO, **cambios),
                                       reglas=REGLAS_PUNTUADAS)

    def test_sin_hallazgos_es_100(self):
        resultado = self.evaluar()
        self.assertEqual(resultado["score"], 100)
        self.assertEqual(resultado["banda"], "Easy to manufacture")
        self.assertEqual(resultado["veredicto"], mf.VEREDICTO_FACTIBLE)

    def test_un_aviso_suelto_ya_no_manda_a_revision(self):
        # OD 60 para que el índice siga sano: aquí se prueba el alambre.
        resultado = self.evaluar(diametro_alambre_mm=8.0,
                                 diametro_exterior_mm=60.0)   # -9
        self.assertEqual(resultado["score"], 91)
        self.assertEqual(resultado["veredicto"], mf.VEREDICTO_FACTIBLE)

    def test_la_acumulacion_si(self):
        # -9 alambre, -12 confianza, -10 longitud libre ausente = 69 < 70.
        resultado = self.evaluar(diametro_alambre_mm=8.0, diametro_exterior_mm=60.0,
                                 confianza=0.4, longitud_libre_mm=None)
        self.assertEqual(resultado["score"], 69)
        self.assertEqual(resultado["banda"], "Engineering review")
        self.assertEqual(resultado["veredicto"], mf.VEREDICTO_REVISION)

    def test_dos_avisos_todavia_pasan(self):
        # -12 confianza, -10 longitud libre = 78, por encima del umbral.
        resultado = self.evaluar(confianza=0.4, longitud_libre_mm=None)
        self.assertEqual(resultado["score"], 78)
        self.assertEqual(resultado["veredicto"], mf.VEREDICTO_FACTIBLE)

    def test_un_critico_manda_a_revision_aunque_el_score_alcance(self):
        # Limite duro: no se compensa teniendo el resto bien.
        resultado = self.evaluar(material="titanio")            # -30, crit
        self.assertEqual(resultado["score"], 70)
        self.assertEqual(resultado["banda"], "Manufacturable")
        self.assertEqual(resultado["veredicto"], mf.VEREDICTO_REVISION)

    def test_todo_mal_cae_a_la_peor_banda(self):
        # -30 material, -24 alambre, -12 confianza, -10 longitud libre = 24.
        resultado = self.evaluar(material="titanio", diametro_alambre_mm=99.0,
                                 confianza=0.1, longitud_libre_mm=None)
        self.assertEqual(resultado["score"], 24)
        self.assertEqual(resultado["banda"], "Not recommended")

    def test_el_score_esta_acotado_a_0_100(self):
        self.assertEqual(mf.calcular_score([{"penalizacion": 500}]), 0)
        self.assertEqual(mf.calcular_score([]), 100)
        self.assertEqual(mf.calcular_score([{"penalizacion": None}]), 100)

    def test_la_penalizacion_del_rango_manda_sobre_la_general(self):
        # indice_resorte declara 10 para fuera_del_preferido; la general es 9.
        resultado = self.evaluar(diametro_alambre_mm=0.9, diametro_exterior_mm=12.8)
        motivo = _por_codigo(resultado, mf.FUERA_DEL_PREFERIDO)
        self.assertEqual(motivo["campo"], mf.INDICE_RESORTE)
        self.assertEqual(motivo["penalizacion"], 10)
        self.assertEqual(resultado["score"], 90)

    def test_cada_motivo_lleva_lo_que_resto(self):
        for motivo in self.evaluar(diametro_alambre_mm=8.0,
                                   diametro_exterior_mm=60.0)["motivos"]:
            self.assertIsNotNone(motivo["penalizacion"])

    def test_sin_modelo_de_puntuacion_no_hay_score(self):
        # Las directrices pueden no traerlo; entonces manda el criterio viejo.
        resultado = evaluar()
        self.assertIsNone(resultado["score"])
        self.assertIsNone(resultado["banda"])
        self.assertEqual(resultado["veredicto"], mf.VEREDICTO_FACTIBLE)

    def test_sin_modelo_cualquier_hallazgo_manda_a_revision(self):
        resultado = evaluar(confianza=0.4)
        self.assertIsNone(resultado["score"])
        self.assertEqual(resultado["veredicto"], mf.VEREDICTO_REVISION)


class TestPenalizacionPorLado(unittest.TestCase):
    """ISC no cobra igual los dos extremos, y el motor tiene que distinguirlos.

    Enrollar apretado (C bajo) castiga el herramental; enrollar flojo (C alto)
    sólo da una espira inconsistente. De ahí 26 contra 20.
    """

    REGLAS = rf.Reglas({
        "version": "lados-1",
        "tipos_fabricables": ["compresion"],
        "materiales_soportados": [{"nombre": "Music Wire", "alias": ["mw"]}],
        "rangos": {"_comun": {"indice_resorte": {
            "min": 4.0, "max": 15.0, "preferido_min": 5.0, "preferido_max": 12.0,
            "penalizacion": {"fuera_de_rango": {"min": 26, "max": 20},
                             "fuera_del_preferido": {"min": 10, "max": 8}}}}},
        "requeridos": {},
        "puntuacion": {
            "umbral_factible": 70,
            "bandas": [{"desde": 70, "banda": "Manufacturable"},
                       {"desde": 0, "banda": "Engineering review"}],
            "penalizaciones": {},
        },
    })

    def penalizacion(self, od):
        # d = 1.0, así que C = OD - 1.
        resultado = mf.evaluar_factibilidad(
            {"tipo_resorte": "compresion", "material": "MW",
             "diametro_alambre_mm": 1.0, "diametro_exterior_mm": od},
            reglas=self.REGLAS)
        motivo = next(m for m in resultado["motivos"]
                      if m["campo"] == mf.INDICE_RESORTE)
        return motivo["penalizacion"]

    def test_indice_por_debajo_del_minimo(self):
        self.assertEqual(self.penalizacion(4.5), 26)     # C = 3.5

    def test_indice_por_encima_del_maximo(self):
        self.assertEqual(self.penalizacion(17.0), 20)    # C = 16

    def test_banda_preferida_baja(self):
        self.assertEqual(self.penalizacion(5.6), 10)     # C = 4.6

    def test_banda_preferida_alta(self):
        self.assertEqual(self.penalizacion(14.5), 8)     # C = 13.5


class TestReglasDelRepo(unittest.TestCase):
    """Un caso contra el archivo provisional real, para que no quede sin usar."""

    def test_dictamina_con_las_reglas_del_proyecto(self):
        rf.limpiar_cache()
        resultado = mf.evaluar_factibilidad(dict(FACTIBLE))
        self.assertEqual(resultado["veredicto"], mf.VEREDICTO_FACTIBLE)


if __name__ == "__main__":
    unittest.main()
