"""Quita la marca de «procesado» a correos que no llegaron a RFQ, para que el
lector los vuelva a tomar.

    python scripts/reintentar_correos.py --remitente daniela.diaz@cgr-international.com
    python scripts/reintentar_correos.py --remitente daniela.diaz@cgr-international.com --hoy --si
    python scripts/reintentar_correos.py --message-id "<AS8P193MB...@...OUTLOOK.COM>" --si
    python scripts/reintentar_correos.py --asunto TEST --si

Para qué
--------
Un correo que el sistema apuntó como procesado no se vuelve a leer nunca,
aunque en Outlook se marque como no leído: el ciclo lo ve en
``correos_procesados`` y lo salta con «Duplicado omitido». Es lo que pasó con
cinco correos de prueba que la cuarentena paró por una comprobación de más
(2026-09-25): al corregirla seguían sin entrar, porque ya estaban apuntados.

Esto borra esa marca —sólo la marca, y sólo de correos que NO tienen RFQ dado
de alta, que esos ya se atendieron— y dice cuáles. Después hay que marcar el
correo como **no leído** en Outlook: el lector sólo mira los no leídos.

Sin ``--si`` no borra nada: enseña la lista y se va.
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
SELECT c.id, c.message_id, c.remitente, c.asunto, c.fecha_correo, c.fecha_registro
  FROM correos_procesados c
 WHERE NOT EXISTS (SELECT 1 FROM rfqs r WHERE r.message_id = c.message_id)
   AND (%(remitente)s IS NULL OR lower(c.remitente) = lower(%(remitente)s))
   AND (%(asunto)s IS NULL OR c.asunto ILIKE '%%' || %(asunto)s || '%%')
   AND (%(ids)s IS NULL OR c.message_id = ANY(%(ids)s))
   AND (NOT %(hoy)s OR c.fecha_registro::date = CURRENT_DATE)
 ORDER BY c.fecha_registro;
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--remitente", help="sólo los de este remitente")
    parser.add_argument("--asunto", help="sólo los que lleven esto en el asunto")
    parser.add_argument("--message-id", action="append", dest="ids",
                        help="un Message-ID concreto (se puede repetir)")
    parser.add_argument("--hoy", action="store_true", help="sólo los apuntados hoy")
    parser.add_argument("--si", action="store_true", help="borrar de verdad la marca")
    args = parser.parse_args(argv)

    if not (args.remitente or args.asunto or args.ids or args.hoy):
        parser.error("di cuáles: --remitente, --asunto, --message-id o --hoy")

    filtros = {"remitente": args.remitente, "asunto": args.asunto,
               "ids": args.ids or None, "hoy": bool(args.hoy)}
    with conexion_bd() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_LISTA, filtros)
            filas = cur.fetchall()
            if not filas:
                print("No hay correos apuntados sin RFQ que cumplan eso.")
                return 0
            print(f"{len(filas)} correo/s apuntado/s sin RFQ:")
            for _id, message_id, remitente, asunto, fecha, registro in filas:
                print(f"  · {remitente} | {asunto!r} | {fecha} | "
                      f"apuntado {registro:%Y-%m-%d %H:%M}")
                print(f"    {message_id}")
            if not args.si:
                print("\nNo se borró nada (falta --si).")
                return 0
            cur.execute("DELETE FROM correos_procesados WHERE id = ANY(%s);",
                        ([f[0] for f in filas],))
            print(f"\nMarca quitada a {cur.rowcount} correo/s. Ahora márcalos como NO leídos "
                  "en Outlook (carpeta TEST) y el lector los toma en el siguiente ciclo "
                  "o con «Leer ahora».")
    return 0


if __name__ == "__main__":
    sys.exit(main())
