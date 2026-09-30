"""Lectura continua del buzón dentro del horario (ventas, 2026-09-30).

Antes: un ciclo cada cinco minutos. Ahora: cada pocos segundos, de 7 a 17 h
de Kansas City, lunes a viernes.
"""
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

import app.core.config as config
import app.rfq.horario as horario

KC = ZoneInfo("America/Chicago")


def test_el_intervalo_es_de_segundos_y_no_de_cinco_minutos():
    assert config.settings.INTERVALO_SEGUNDOS <= 60
    assert not hasattr(config.settings, "INTERVALO_MINUTOS")
    with mock.patch.object(config.settings, "INTERVALO_SEGUNDOS", 1):
        assert config.intervalo_segundos() == 5          # nunca menos de 5 s


def test_el_horario_es_de_7_a_17_en_kansas_city():
    assert config.settings.HORARIO_ZONA == "America/Chicago"
    assert (config.settings.HORARIO_DESDE, config.settings.HORARIO_HASTA) == (7, 17)
    miercoles = datetime(2026, 9, 30, tzinfo=KC)
    with mock.patch.object(config.settings, "HORARIO_ACTIVO", True):
        assert not horario.abierto(miercoles.replace(hour=6, minute=59))
        assert horario.abierto(miercoles.replace(hour=7))
        assert horario.abierto(miercoles.replace(hour=16, minute=59))
        assert not horario.abierto(miercoles.replace(hour=17))


def test_el_servidor_se_aparta_con_un_latido_de_hace_dos_minutos():
    # El escritorio late cada minuto: la tolerancia no puede depender ya del
    # intervalo de lectura (20 s), o el servidor leería a la vez.
    assert config.TOLERANCIA_LATIDO_S >= 120
