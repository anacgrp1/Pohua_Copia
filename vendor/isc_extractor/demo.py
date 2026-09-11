"""Modo demo: datos de un plano REAL ya extraido, para probar sin API key.

Existe solo para que se pueda montar la interfaz sin gastar creditos. Todo lo
que sale de aqui va marcado como demo en el payload y en los avisos: nunca debe
poder confundirse con la lectura del plano que el usuario acaba de subir.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def cargar():
    spec = json.loads((HERE / "demo_spec.json").read_text(encoding="utf-8"))
    spec.setdefault("metadatos_extraccion", {})
    if isinstance(spec["metadatos_extraccion"], dict):
        spec["metadatos_extraccion"]["comentarios"] = (
            "MODO DEMO - datos de ejemplo, NO leidos del plano subido."
        )
        spec["metadatos_extraccion"]["confianza_general"] = "baja"
    tipo = spec.get("tipo_resorte", "compresion")
    router = {"tipo": tipo, "confianza": "baja", "razon": "modo demo"}
    diag = {"jsonschema": "omitido (demo)", "errores_schema": [],
            "reparaciones": 0, "truncado": False, "uso": []}
    return spec, tipo, router, diag
