"""Qué saca el modelo del cuerpo de un correo, y si eso basta para pasar.

    python scripts/probar_extraccion.py correo.txt
    python scripts/probar_extraccion.py correo.txt --asunto "test rfq"
    type correo.txt | python scripts/probar_extraccion.py

Para cuando un RFQ se queda "Esperando al cliente" y no se sabe por qué. El
registro dice qué campo faltó, pero no POR QUÉ faltó: si el modelo no lo vio,
si lo vio y lo guardó en otro sitio (unas cantidades escalonadas no son lo
mismo que un volumen anual), o si lo vio con poca confianza y se apartó para
que lo revise una persona. Esto lo enseña los tres casos, y además dice si el
filtro temprano —el que decide si se abre el plano— dejaría pasar el correo.

No toca la base de datos ni el buzón: sólo llama al modelo con ese texto.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)          # el .env vive aquí, se lance desde donde se lance


def _leer_texto(argumentos):
    ruta = next((a for a in argumentos if not a.startswith("--")), None)
    if ruta:
        return Path(ruta).read_text(encoding="utf-8", errors="replace")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    print(__doc__)
    raise SystemExit(2)


def _opcion(argumentos, nombre, por_defecto=""):
    if nombre in argumentos:
        i = argumentos.index(nombre)
        if i + 1 < len(argumentos):
            return argumentos[i + 1]
    return por_defecto


def main() -> int:
    argumentos = sys.argv[1:]
    texto = _leer_texto(argumentos)
    asunto = _opcion(argumentos, "--asunto", "test rfq")

    import app.extraction.email_extractor as extractor
    import app.rfq.flow as flow

    print(f"Modelo: {extractor._modelo()}")
    print(f"Umbral de confianza: {extractor._umbral()}")
    print(f"Cuerpo: {len(texto)} caracteres | Asunto: {asunto!r}\n")

    try:
        salida = extractor.extraer(texto, asunto=asunto)
    except Exception as error:
        print(f"La extracción falló: {error}")
        return 1

    campos = salida.get("campos") or {}
    confianzas = salida.get("confianzas") or {}
    revision = salida.get("en_revision") or {}

    print("LO QUE SE USA")
    if campos:
        for clave, valor in campos.items():
            print(f"   {clave:26} = {valor!r}   (confianza "
                  f"{confianzas.get(clave, '?')})")
    else:
        print("   nada")

    if revision:
        print("\nAPARTADO POR POCA CONFIANZA (lo revisa una persona, y para el "
              "validador es como si no estuviera)")
        for clave, valor in revision.items():
            print(f"   {clave:26} = {valor!r}   (confianza "
                  f"{confianzas.get(clave, '?')})")

    # El filtro temprano, con los mismos datos que tendría el flujo: el
    # adjunto y el cliente se dan por buenos para no confundir el diagnóstico.
    datos = {"tiene_adjunto": True, "customer": "diagnostico.example"}
    datos.update({k: v for k, v in campos.items() if v not in (None, "")})
    temprano = flow.validar(datos, flow.campos_gate_temprano(campos))

    print("\nFILTRO TEMPRANO (el que decide si se abre el plano)")
    if temprano["es_valido"]:
        print("   pasa: el plano se leería y después se validaría todo junto.")
    else:
        print("   NO pasa; falta: " + ", ".join(temprano["campos_faltantes"]))
        print("   Con este correo, el RFQ queda 'Esperando al cliente' y se le "
              "pide ese dato al comprador.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
