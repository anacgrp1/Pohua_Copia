# -*- coding: utf-8 -*-
"""Una respuesta cortada no tira la llamada entera.

Por qué existe
--------------
En el registro de producción, el mismo plano y el mismo modelo fallaban a
ratos: «No se encontró ningún objeto JSON en la respuesta», tres veces de cada
siete, intercaladas con lecturas buenas. Esa intermitencia es lo que hacía
pensar en el modelo, o en el PDF, o en la red.

No era nada de eso. La respuesta se acercaba al tope de `VISION_MAX_TOKENS` y
a veces lo pasaba; al pasarlo se cortaba a media frase y el JSON llegaba sin
cerrar. Empeoró justo cuando al lector se le empezó a pedir que ANOTARA lo que
suponía: seis advertencias razonadas más el esquema entero no caben en 2048.

Dos arreglos, y hacen falta los dos. El tope sube —para que no se corte— y el
extractor aprende a cerrar lo que llegue —para que el día que se corte igual,
no se pierda la llamada, que se paga—.

Lo que se rescata no es poca cosa: las cotas van al PRINCIPIO del esquema y
las advertencias al final, así que un corte se lleva casi siempre lo menos
importante.
"""

import pytest

from app.vision.spring_extractor import ExtraccionError, extraer_json


def cortada(texto):
    """El JSON tal y como llega cuando el modelo no pudo terminar."""
    return texto


class TestSeRescataLoQueLlego:

    def test_cortada_a_media_advertencia(self):
        # El caso real del registro: las cotas ya estaban, se cortó al final.
        d = extraer_json(cortada(
            '{"tipo_resorte": "compresion", "diametro_exterior_mm": 49.28, '
            '"diametro_interior_mm": 38.86, "longitud_libre_mm": 63.5, '
            '"advertencias": ["no indica espiras", "El diámetro NO está acot'))
        assert d["diametro_exterior_mm"] == 49.28
        assert d["diametro_interior_mm"] == 38.86
        assert d["longitud_libre_mm"] == 63.5

    @pytest.mark.parametrize("texto, esperados", [
        # tras una coma
        ('{"a": 1, "b": 2,', ["a", "b"]),
        # en una clave, sin su valor
        ('{"a": 1, "b": 2, "c":', ["a", "b"]),
        # en medio de un número
        ('{"a": 1, "b": 2, "c": 38.', ["a", "b"]),
        # dentro de un array
        ('{"a": 1, "normas": ["ASTM A228", "AS', ["a", "normas"]),
        # dentro de un objeto anidado
        ('{"a": 1, "extra": {"x": 1, "y": "sin cer', ["a", "extra"]),
    ])
    def test_cada_forma_de_cortarse(self, texto, esperados):
        d = extraer_json(cortada(texto))
        for clave in esperados:
            assert clave in d

    def test_se_avisa_de_que_venia_cortada(self):
        # Quien mire la ficha tiene que saber que esto no es todo lo que el
        # lector vio. Si no, un plano leído a medias pasa por uno leído entero.
        d = extraer_json(cortada('{"tipo_resorte": "compresion", "a": 1,'))
        assert any("cortó" in a for a in d.get("advertencias", []))

    def test_no_pisa_las_advertencias_que_sí_llegaron(self):
        d = extraer_json(cortada(
            '{"advertencias": ["el dibujo no indica el número de espiras"], '
            '"diametro_exterior_mm": 49.28,'))
        assert "el dibujo no indica el número de espiras" in d["advertencias"]
        assert len(d["advertencias"]) == 2


class TestLoQueNoSeRescata:
    """Rescatar no puede convertirse en inventar."""

    def test_sin_nada_de_json_sigue_fallando(self):
        with pytest.raises(ExtraccionError):
            extraer_json("No puedo leer este plano.")

    def test_una_llave_suelta_no_es_una_respuesta(self):
        with pytest.raises(ExtraccionError):
            extraer_json("{")

    def test_vacío_sigue_fallando(self):
        with pytest.raises(ExtraccionError):
            extraer_json("")

    def test_no_se_rellena_ningún_campo_que_no_viniera(self):
        d = extraer_json(cortada('{"tipo_resorte": "compresion", "a": 1,'))
        for campo in ("diametro_alambre_mm", "diametro_exterior_mm",
                      "numero_espiras_totales"):
            assert campo not in d


class TestLoQueYaFuncionabaSigueIgual:

    def test_json_puro(self):
        d = extraer_json('{"tipo_resorte": "compresion", "a": 1}')
        assert d["a"] == 1
        # Entera: no se le cuelga el aviso de corte.
        assert "advertencias" not in d

    def test_entre_fences(self):
        d = extraer_json('Aquí tienes:\n```json\n{"a": 1}\n```')
        assert d["a"] == 1
        assert "advertencias" not in d

    def test_con_texto_delante(self):
        d = extraer_json('Claro, este es el análisis: {"a": 1}')
        assert d["a"] == 1


class TestElTopeSubio:

    def test_cuatro_mil_noventa_y_seis(self):
        # 2048 era el tope con el que se cortaba. Si alguien lo vuelve a bajar,
        # que se entere aquí y no en un fallo intermitente dentro de un mes.
        import app.core.config as config
        assert config.settings.VISION_MAX_TOKENS >= 4096
