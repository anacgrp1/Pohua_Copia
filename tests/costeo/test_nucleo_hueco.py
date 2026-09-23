# -*- coding: utf-8 -*-
"""Un fichero del núcleo que está pero está vacío.

`pricing/nucleo/reglas.js` eran DIEZ bytes: la línea ``// reglas``. El fichero
existía, así que se encontraba, el origen decía "copia" y el diagnóstico daba
el núcleo por presente. Dentro no había ninguna regla del taller.

Lo que se perdía no daba ningún error. Las operaciones secundarias —el
esmerilado que pide un plano con extremos Ground— no se añadían a la ruta, la
caja no se elegía, y la pieza salía cotizada con una operación en vez de tres.

Un hueco es peor que un fichero ausente: ausente se nota y se cae; hueco se
encuentra, contesta que sí, y devuelve nada.
"""

import pytest

from pricing import nucleo


@pytest.fixture
def falso_nucleo(tmp_path, monkeypatch):
    """Un directorio de núcleo que podemos llenar y vaciar a voluntad."""
    monkeypatch.setattr(nucleo, "VENDOR", tmp_path)
    # Que no se cuele el de verdad por otra vía.
    monkeypatch.setattr(nucleo, "_por_entorno", lambda v: None)
    monkeypatch.setattr(nucleo, "_por_paquete", lambda p: None)
    monkeypatch.setattr(nucleo, "_por_clon", lambda n: None)
    return tmp_path


def escribir(carpeta, nombre, tamano):
    (carpeta / nombre).write_text("/" + "/" * max(tamano - 1, 0))


class TestElHuecoSeDetecta:

    def test_diez_bytes_es_un_hueco(self, falso_nucleo):
        # El caso exacto: "// reglas".
        escribir(falso_nucleo, "reglas.js", 10)
        assert nucleo.es_hueco("reglas") is True

    def test_el_fichero_de_verdad_no_lo_es(self, falso_nucleo):
        escribir(falso_nucleo, "reglas.js", 14383)
        assert nucleo.es_hueco("reglas") is False

    def test_ausente_no_es_hueco(self, falso_nucleo):
        # Son dos estados distintos y se arreglan distinto: uno es traer el
        # fichero, el otro es traerlo DE VERDAD.
        assert nucleo.es_hueco("reglas") is False
        assert nucleo.ruta("reglas") is None

    def test_un_motor_hueco_cuenta_como_ausente(self, falso_nucleo):
        # Es lo único que impide que el costeo siga creyendo que tiene motor.
        escribir(falso_nucleo, "engine.js", 10)
        assert nucleo.disponible() is False

    def test_un_motor_de_verdad_si_esta_disponible(self, falso_nucleo):
        escribir(falso_nucleo, "engine.js", 19004)
        assert nucleo.disponible() is True

    def test_los_lista_todos(self, falso_nucleo):
        escribir(falso_nucleo, "engine.js", 19004)
        escribir(falso_nucleo, "reglas.js", 10)
        escribir(falso_nucleo, "resortes.js", 12)
        assert sorted(nucleo.huecos()) == ["reglas", "resortes"]

    def test_sin_huecos_la_lista_va_vacia(self, falso_nucleo):
        escribir(falso_nucleo, "engine.js", 19004)
        escribir(falso_nucleo, "reglas.js", 14383)
        escribir(falso_nucleo, "resortes.js", 34383)
        assert nucleo.huecos() == []

    def test_el_diagnostico_lo_dice(self, falso_nucleo):
        escribir(falso_nucleo, "engine.js", 19004)
        escribir(falso_nucleo, "reglas.js", 10)
        estado = nucleo.estado()
        assert estado["huecos"] == ["reglas"]
        assert estado["piezas"]["reglas"]["hueco"] is True
        # Y sigue diciendo que lo encontró: las dos cosas son verdad a la vez,
        # y es justo esa combinación la que hay que poder ver.
        assert estado["piezas"]["reglas"]["encontrado"] is True


class TestElNucleoQueSeEmbarca:
    """Las tres piezas de verdad, en el repositorio, ahora mismo."""

    @pytest.mark.parametrize("pieza", ["motor", "reglas", "resortes"])
    def test_ninguna_va_hueca(self, pieza):
        assert not nucleo.es_hueco(pieza), (
            f"{pieza} está pero vacío: el costeo se quedaría sin esa parte "
            f"sin dar ningún error")

    def test_las_reglas_traen_las_secundarias(self):
        # Lo que se perdía con el placeholder, nombrado: si esta función no
        # está, un plano con extremos Ground se cotiza sin esmerilado.
        ruta = nucleo.ruta("reglas")
        assert ruta is not None
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        assert "function secundarias" in texto
        assert "Grinder A" in texto
