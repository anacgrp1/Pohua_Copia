"""El registro de la aplicación de escritorio sigue al idioma elegido.

Los mensajes se escriben en español desde varios sitios; la ventana los
traduce al pintarlos (`desktop_app/textos_registro.py`). Esta prueba lee
`desktop_app/main.py` y `app/core/preflight.py` y comprueba que cada frase fija
que puede salir en el registro tenga su traducción, para que un mensaje nuevo
no se quede en español sin que nadie lo note.
"""
import ast
from pathlib import Path

import pytest

import desktop_app.textos_registro as textos

RAIZ = Path(__file__).resolve().parents[2]


def _literales(ruta: Path, llamadas: set, posicion: int) -> list:
    """Los textos constantes pasados como argumento ``posicion`` a esas llamadas."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    fuera = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call) or len(nodo.args) <= posicion:
            continue
        f = nodo.func
        nombre = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        if nombre not in llamadas:
            continue
        arg = nodo.args[posicion]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            fuera.append(arg.value)
    return fuera


def test_los_mensajes_fijos_del_lector_tienen_traduccion():
    frases = _literales(RAIZ / "desktop_app" / "main.py", {"escribir", "emit"}, 1)
    frases = [f for f in frases if f.strip() and f not in ("info", "ok", "aviso", "error")]
    assert frases, "no se encontró ningún mensaje: ¿cambió la forma de escribir?"
    faltan = [f for f in frases if textos.traducir(f, "en") == f]
    assert not faltan, f"Sin traducción: {faltan}"


def test_los_titulos_del_arranque_tienen_traduccion():
    titulos = _literales(RAIZ / "app" / "core" / "preflight.py", {"ojo", "falta"}, 0)
    faltan = [t for t in titulos if textos.traducir(t, "en") == t
              and textos.traducir("Falta: " + t, "en") == "Missing: " + t]
    assert not faltan, f"Sin traducción: {faltan}"


def test_el_detalle_de_lo_que_falta_tiene_traduccion():
    arbol = ast.parse((RAIZ / "app" / "core" / "preflight.py").read_text(encoding="utf-8"))
    detalles = [n.args[1].value for n in ast.walk(arbol)
                if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "falta"
                and len(n.args) > 1 and isinstance(n.args[1], ast.Constant)]
    faltan = [d for d in detalles if textos.traducir(d, "en") == d]
    assert not faltan, f"Sin traducción: {faltan}"


@pytest.mark.parametrize("es,en", [
    ("Lector en marcha. Un ciclo cada 5 min.", "Reader running. One cycle every 5 min."),
    ("Ciclo: 4 sin leer · 0 procesados · 0 RFQ · 0 con error.",
     "Cycle: 4 unread · 0 processed · 0 RFQ · 0 with errors."),
    ("Fuera del horario de atención (7:00–17:00 Kansas City, lunes a viernes). "
     "Los correos esperan a 2026-09-28T07:00:00-05:00.",
     "Outside business hours (7:00–17:00 Kansas City, Monday to Friday). "
     "Emails wait until 2026-09-28T07:00:00-05:00."),
    ("   Duplicado omitido: <abc@x>", "   Duplicate skipped: <abc@x>"),
    ("Falta: Falta APP_URL", "Missing: APP_URL is missing"),
    ("Falta: Faltan credenciales del buzón: Outlook",
     "Missing: Mailbox credentials missing: Outlook"),
    ("Falta: 2 migración(es) sin aplicar", "Missing: 2 migration(s) not applied"),
    ("Recordatorio de dictamen enviado por 3 caso(s) (6 correo/s).",
     "Decision reminder sent for 3 case(s) (6 email(s))."),
])
def test_plantillas(es, en):
    assert textos.traducir(es, "en") == en


def test_en_espanol_y_lo_desconocido_quedan_igual():
    frase = "Revisando el esquema de la base…"
    assert textos.traducir(frase, "es") == frase
    assert textos.traducir("Algo nuevo que nadie tradujo", "en") == "Algo nuevo que nadie tradujo"
    assert textos.traducir("", "fr") == ""
