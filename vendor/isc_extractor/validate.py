"""Validacion del JSON extraido contra su schema (jsonschema, draft-07)."""

import json

from . import config

LF = chr(10)

try:
    import jsonschema
except ImportError:                                   # pragma: no cover
    jsonschema = None


def disponible():
    return jsonschema is not None


def exigir():
    """Aborta si falta jsonschema. Se llama al arrancar, nunca a mitad de lectura.

    Sin jsonschema, `errores()` devuelve None y toda la red de seguridad (schema
    + reparacion dirigida) desaparece en silencio: el JSON del modelo se acepta
    tal cual venga. En un puesto de cotizacion eso es peor que no arrancar, asi
    que se comprueba una vez, al principio, y con un mensaje que diga que hacer.
    """
    if jsonschema is None:
        raise RuntimeError(
            "The 'jsonschema' package is missing. It is what checks the "
            "model reply; without it, readings are not validated and mistakes "
            "go through unnoticed." + LF + LF +
            "    python -m pip install jsonschema" + LF + LF +
            "or just run \"Setup - install packages.bat\" again.")


def errores(spec, tipo, max_errores=25):
    """Lista de errores legibles. Vacia = conforma. None = jsonschema no instalado."""
    if jsonschema is None:
        return None
    schema = config.leer_schema(tipo)
    v = jsonschema.Draft7Validator(schema)
    out = []
    for e in sorted(v.iter_errors(spec), key=lambda x: list(x.absolute_path)):
        ruta = "$" + "".join(
            "[%d]" % p if isinstance(p, int) else ".%s" % p for p in e.absolute_path)
        out.append("%s -> %s" % (ruta, e.message))
        if len(out) >= max_errores:
            out.append("... (mas errores omitidos)")
            break
    return out


def texto_errores(errs):
    return "\n".join("- " + e for e in errs)


def extraer_json(texto):
    """Saca el objeto JSON de la respuesta del modelo, tolerando fences y ruido."""
    t = (texto or "").strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t[:4].lower() == "json":
            t = t[4:].strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    ini, fin = t.find("{"), t.rfind("}")
    if ini != -1 and fin > ini:
        return json.loads(t[ini:fin + 1])
    raise RuntimeError("The model reply contains no readable JSON.")
