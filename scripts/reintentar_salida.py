"""Vuelve a poner en la cola las ofertas de la bandeja de salida que se dieron por perdidas.

    python scripts/reintentar_salida.py            # enseña cuáles
    python scripts/reintentar_salida.py --si       # las devuelve a la cola

Para qué
--------
Un correo de la bandeja de salida (``correos_salida``) se intenta cinco veces;
al quinto fallo pasa a ``fallo`` y ya no se vuelve a intentar solo, para que
uno imposible no tape a los demás. El 2026-09-29 la computadora del Outlook
arrancó Pohua con un Python sin pywin32: cada intento fallaba sin llegar a
Outlook, y las ofertas gastaron sus cinco intentos en minutos por algo que
nada tenía que ver con ellas.

Esto las devuelve a ``pendiente`` con los intentos a cero —sólo las que están
en ``fallo``; las enviadas no se tocan— y el siguiente ciclo del lector de
escritorio las manda. Arregla antes lo que las hizo fallar (la aplicación de
escritorio lo dice al abrir, en «Falta: …»), o volverán a agotarse.

Sin ``--si`` no cambia nada: enseña la lista y se va.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)

from app.persistence.duplicates import conexion_bd  # noqa: E402

SQL_LISTA = """
SELECT id, rfq_id, clase, destinatario, asunto, intentos,
       LEFT(COALESCE(ultimo_error, ''), 160), creado_en::text
  FROM correos_salida
 WHERE estado = 'fallo'
   AND (%(rfq)s IS NULL OR rfq_id = %(rfq)s)
 ORDER BY id;
"""

SQL_REPONER = """
UPDATE correos_salida
   SET estado = 'pendiente', intentos = 0
 WHERE estado = 'fallo' AND id = ANY(%s);
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--rfq", help="sólo las de este RFQ")
    parser.add_argument("--si", action="store_true", help="devolverlas de verdad a la cola")
    args = parser.parse_args(argv)

    with conexion_bd() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_LISTA, {"rfq": args.rfq})
            filas = cur.fetchall()

    if not filas:
        print("No hay correos en 'fallo' en la bandeja de salida.")
        return 0

    print(f"{len(filas)} correo(s) que se dieron por perdidos:")
    for f in filas:
        print(f"  id={f[0]}  {f[1] or '—'}  [{f[2]}]  → {f[3]}  «{f[4]}»  "
              f"({f[5]} intentos, {f[7][:16]})")
        if f[6]:
            print(f"      último error: {f[6]}")

    if not args.si:
        print("\nNo se cambió nada. Repite con --si para devolverlos a la cola.")
        return 0

    with conexion_bd() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_REPONER, ([f[0] for f in filas],))
            print(f"\n{cur.rowcount} devuelto(s) a la cola: salen en el próximo "
                  "ciclo del lector de escritorio.")
        try:
            conn.commit()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
