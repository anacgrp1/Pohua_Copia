"""Pasa a «Esperando al cliente» los RFQ que quedaron en revisión sin estar completos.

    python scripts/pasar_a_esperando.py                      # sólo enseña cuáles
    python scripts/pasar_a_esperando.py --si                 # los pasa
    python scripts/pasar_a_esperando.py --si --enviar        # y le pide los datos al comprador
    python scripts/pasar_a_esperando.py --rfq INT-36A51545 --si --enviar

Para qué
--------
Hasta 2026-09-26 un correo al que le faltaban datos (sin volumen, sin número
de parte…) podía entrar a la revisión del PM si además traía un dato leído con
poca confianza: la revisión ganaba a los datos faltantes. El PM se encontraba
una ventana sin cantidades que dictaminar y al comprador no se le pedía nada.

La regla ahora es la contraria (``app/rfq/flow.py``): si falta algo, sólo sale
el correo pidiéndolo y el RFQ queda «Esperando al cliente» hasta que conteste.
Esto arregla los que entraron antes del cambio: busca los RFQ en revisión (o
nuevos) a los que les falta número de parte, volumen, material o cliente, y
los pasa a ``Incomplete`` con lo que falta apuntado. Con ``--enviar`` les
manda además el correo de datos faltantes, el mismo que el lector manda solo
(y sólo si ``ENVIO_AUTOMATICO`` está encendido).

Sin ``--si`` no cambia nada: enseña la lista y se va.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)

from app.persistence.duplicates import conexion_bd  # noqa: E402

SQL_LISTA = """
SELECT r.id, r.rfq_id, r.version, r.estado, r.part_number, r.volumen, r.material,
       r.cliente_id, r.datos_json
  FROM rfqs r
 WHERE r.estado IN ('RequiresReview', 'New')
   AND r.version = (SELECT MAX(x.version) FROM rfqs x WHERE x.rfq_id = r.rfq_id)
   AND (%(rfq)s IS NULL OR r.rfq_id = %(rfq)s)
 ORDER BY r.fecha_registro;
"""


def _vacio(valor) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip()) or valor == []


def faltantes(fila: dict) -> list:
    """Lo que le falta a un RFQ para poder dictaminarse, como lo diría el lector."""
    datos = fila.get("datos") or {}
    falta = []
    if _vacio(datos.get("customer")) and _vacio(fila.get("cliente_id")):
        falta.append("customer")
    if _vacio(fila.get("part_number")) and _vacio(datos.get("part_number")):
        falta.append("part_number")
    if _vacio(fila.get("volumen")) and _vacio(datos.get("volumen")):
        falta.append("volumen")
    if _vacio(fila.get("material")) and _vacio(datos.get("material")):
        falta.append("material")
    return falta


def _a_dict(valor) -> dict:
    if isinstance(valor, dict):
        return valor
    if isinstance(valor, str) and valor.strip():
        try:
            d = json.loads(valor)
            return d if isinstance(d, dict) else {}
        except ValueError:
            return {}
    return {}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--rfq", help="sólo este RFQ")
    parser.add_argument("--si", action="store_true", help="pasarlos de verdad")
    parser.add_argument("--enviar", action="store_true",
                        help="mandar además el correo de datos faltantes al comprador")
    args = parser.parse_args(argv)

    with conexion_bd() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_LISTA, {"rfq": args.rfq})
            columnas = [c[0] for c in cur.description]
            filas = [dict(zip(columnas, f)) for f in cur.fetchall()]

    candidatos = []
    for fila in filas:
        fila["datos"] = _a_dict(fila.pop("datos_json"))
        falta = faltantes(fila)
        if falta:
            candidatos.append((fila, falta))

    if not candidatos:
        print("No hay RFQ en revisión a los que les falten datos.")
        return 0

    print(f"{len(candidatos)} RFQ en revisión sin estar completos:")
    for fila, falta in candidatos:
        print(f"  {fila['rfq_id']} v{fila['version']}  [{fila['estado']}]  "
              f"{fila['datos'].get('remitente') or '—'}  falta: {', '.join(falta)}")

    if not args.si:
        print("\nNo se cambió nada. Repite con --si para pasarlos a «Esperando al cliente»"
              " (y --enviar para pedirle los datos al comprador).")
        return 0

    import app.rfq.flow as flow

    with conexion_bd() as conn:
        with conn.cursor() as cur:
            for fila, falta in candidatos:
                datos = dict(fila["datos"], campos_faltantes=falta,
                             motivo_incompleto="datos_faltantes")
                cur.execute("UPDATE rfqs SET estado = 'Incomplete', datos_json = %s WHERE id = %s;",
                            (json.dumps(datos, ensure_ascii=False, default=str), fila["id"]))
                print(f"  {fila['rfq_id']}: → Esperando al cliente")
        conn.commit()

    if args.enviar:
        for fila, falta in candidatos:
            salio = flow.responder_datos_faltantes(fila["datos"], falta, fila["rfq_id"])
            print(f"  {fila['rfq_id']}: correo de datos faltantes "
                  f"{'enviado' if salio else 'NO enviado (mira el registro / ENVIO_AUTOMATICO)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
