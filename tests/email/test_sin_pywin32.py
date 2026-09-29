"""Sin pywin32 en el Python de la computadora del Outlook (2026-09-29).

La aplicación arrancó con un Python recién instalado: el ciclo decía «0 sin
leer» sin haber hablado con Outlook y las ofertas de la bandeja de salida
gastaban sus cinco intentos. Ahora se dice qué falta y la cola no se toca.
"""
from unittest import mock

import app.core.config as config
import app.email.entrada as entrada
import app.email.outbound as outbound
import app.email.outlook_provider as outlook


def _en_windows_sin_pywin32():
    return (mock.patch("sys.platform", "win32"),
            mock.patch.object(outlook, "falta_pywin32",
                              return_value="ModuleNotFoundError: No module named 'win32com'"),
            mock.patch.object(config.settings, "MAIL_MODE", "outlook"))


def test_no_puede_mandar_ni_leer_y_dice_como_instalarlo():
    a, b, c = _en_windows_sin_pywin32()
    with a, b, c:
        envio = outbound.diagnostico_envio()
        lectura = entrada.diagnostico_lectura()
    for diag in (envio, lectura):
        assert diag["puede"] is False and diag["faltan"] == ["pywin32"]
        assert "pip install -r requirements.txt -r requirements-desktop.txt" in diag["nota"]


def test_la_bandeja_de_salida_no_gasta_intentos():
    import app.email.bandeja_salida as bandeja
    a, b, c = _en_windows_sin_pywin32()
    with a, b, c, \
         mock.patch.object(bandeja, "hay_pendientes", return_value=4), \
         mock.patch.object(bandeja, "pendientes") as pendientes, \
         mock.patch.object(bandeja, "marcar_fallo") as marcar:
        resumen = bandeja.drenar()
    assert resumen["omitidos"] == 4 and resumen["fallidos"] == 0
    pendientes.assert_not_called()
    marcar.assert_not_called()


def test_un_buzon_que_no_abre_no_es_un_buzon_vacio():
    import importlib.util
    import os
    import sys
    raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    sys.modules.setdefault("schedule", mock.MagicMock())
    spec = importlib.util.spec_from_file_location("cotizador_main_pywin32",
                                                  os.path.join(raiz, "app", "main.py"))
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)
    proveedor = mock.MagicMock()
    proveedor.connect.return_value = False
    proveedor.ultimo_error = "No se pudo hablar con Outlook"
    with mock.patch("app.rfq.horario.abierto", return_value=True), \
         mock.patch.object(entrada, "diagnostico_lectura",
                           return_value={"puede": True, "modo": "outlook", "faltan": []}), \
         mock.patch("app.email.factory.EmailProviderFactory.get_provider",
                    return_value=proveedor):
        resultado = main.ciclo_deteccion()
    assert resultado.errores == 1
    assert "No se pudo hablar con Outlook" in " ".join(resultado.detalles)
    proveedor.fetch_unread_messages.assert_not_called()
