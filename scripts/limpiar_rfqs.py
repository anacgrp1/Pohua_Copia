"""Borra RFQ de prueba que se quedaron a medias, para volver a empezar limpio.

    python scripts/limpiar_rfqs.py                 # sólo enseña lo que borraría
    python scripts/limpiar_rfqs.py --borrar        # lo borra de verdad
    python scripts/limpiar_rfqs.py --rfq COT-75 --borrar
    python scripts/limpiar_rfqs.py --estado RequiresReview --borrar
    python scripts/limpiar_rfqs.py --todos --borrar    # empezar de cero

Ensayar el recorrido deja rastro: RFQ en "Esperando al cliente" que nunca se
van a completar, y sus correos apuntados como procesados. Esto se lleva los
RFQ y **también** la marca de sus correos, para que el mismo correo de prueba
se pueda volver a leer sin tener que mandar uno nuevo.

Por defecto sólo toca los **incompletos** (`Incomplete`), que son los de las
pruebas; para tocar otro estado hay que nombrarlo, y una cotización aprobada
no se borra por accidente.

Sin `--borrar` no borra nada: enseña la lista y se va. El borrado no tiene
vuelta atrás, así que se hace de uno en uno y mirando.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)

# Por orden: primero lo que cuelga del RFQ, al final el RFQ. Las partidas y los
# documentos de una cotización se van solos (ON DELETE CASCADE).
_TABLAS = (
    "notificaciones",
    "recordatorios_revision",
    "resortes_cotizacion",
    "cotizaciones",
    # Los planos del correo (migración 021). Van con su RFQ: si el RFQ se
    # borra y el plano se queda, el siguiente con el mismo identificador
    # abriría la calculadora con el dibujo de otra pieza.
    "rfq_planos",
    "rfq_historial",
    "rfqs",
)


def _opcion(argumentos, nombre, por_defecto=None):
    if nombre in argumentos:
        i = argumentos.index(nombre)
        if i + 1 < len(argumentos):
            return argumentos[i + 1]
    return por_defecto


def main() -> int:
    argumentos = sys.argv[1:]
    borrar = "--borrar" in argumentos
    todos = "--todos" in argumentos
    uno = _opcion(argumentos, "--rfq")
    estado = _opcion(argumentos, "--estado", "Incomplete")

    import app.persistence.duplicates as duplicates

    with duplicates.conexion_bd() as conexion:
        with conexion.cursor() as cur:
            if uno:
                cur.execute("SELECT DISTINCT rfq_id, estado FROM rfqs "
                            "WHERE rfq_id = %s;", (uno,))
            elif todos:
                # Para dejar la base como el primer día. Se avisa fuerte: aquí
                # no se distingue una prueba de una cotización de verdad.
                print("--todos: se van TODOS los RFQ de esta base, sea cual "
                      "sea su estado.\n")
                cur.execute("SELECT DISTINCT rfq_id, estado FROM rfqs "
                            "ORDER BY rfq_id;")
            else:
                cur.execute("SELECT DISTINCT rfq_id, estado FROM rfqs "
                            "WHERE estado = %s ORDER BY rfq_id;", (estado,))
            filas = cur.fetchall()

        if not filas and not todos:
            cual = "rfq_id=" + uno if uno else "estado=" + estado
            print(f"No hay RFQ que borrar ({cual}).")
            return 0

        ids = [f[0] for f in filas]
        if filas:
            print(f"RFQ afectados ({len(ids)}):")
            for rfq_id, estado_actual in filas:
                print(f"   {rfq_id:22} {estado_actual}")
        else:
            # Con --todos se sigue aunque no quede ningún RFQ: las marcas de
            # "correo ya procesado" sobreviven al borrado de los RFQ, y son
            # justo las que dejan el embudo en 1 y hacen que el correo de
            # prueba vuelva a entrar como duplicado. Salirse aquí dejaba la
            # base a medio limpiar sin decirlo.
            print("No queda ningún RFQ; se revisa lo que dejaron atrás.")

        # Los correos de esos RFQ: al borrar su marca de "procesado", el mismo
        # correo se puede volver a leer.
        #
        # Con --todos se vacía la tabla ENTERA, no sólo los correos que
        # llegaron a ser RFQ. Un correo que se clasificó como basura, o que se
        # quedó en el gate temprano antes de tener su fila en rfq_historial,
        # deja su marca de "procesado" para siempre: el embudo lo sigue
        # contando en "Customer email" —que cuenta correos_procesados, no
        # RFQ— y el mismo correo de prueba no se puede volver a mandar porque
        # entra como duplicado. Eso convertía "borrar todo y repetir la
        # prueba" en algo que no dejaba la base como el primer día.
        with conexion.cursor() as cur:
            if todos:
                cur.execute("SELECT COUNT(*) FROM correos_procesados;")
                cuantos = cur.fetchone()[0]
                correos = None          # None = todos
                print(f"\nCorreos que volverán a estar sin procesar: {cuantos} "
                      f"(TODOS: también los que nunca llegaron a ser RFQ)")
            else:
                cur.execute("SELECT message_id FROM rfq_historial "
                            "WHERE rfq_id = ANY(%s);", (ids,))
                correos = [f[0] for f in cur.fetchall() if f[0]]
                print(f"\nCorreos que volverán a estar sin procesar: {len(correos)}")

        if not borrar:
            print("\nNo se ha borrado nada. Con --borrar se hace de verdad.")
            return 0

        conexion.autocommit = False
        try:
            with conexion.cursor() as cur:
                for tabla in _TABLAS:
                    # Cada tabla en su punto de control: si una no existe en
                    # este esquema, se deshace SÓLO esa y la limpieza sigue.
                    # Sin esto, un error deja la transacción entera abortada y
                    # no se borraría nada.
                    cur.execute("SAVEPOINT paso;")
                    try:
                        cur.execute(f"DELETE FROM {tabla} WHERE rfq_id = ANY(%s);",
                                    (ids,))
                        print(f"   {tabla:26} {cur.rowcount} fila(s)")
                        cur.execute("RELEASE SAVEPOINT paso;")
                    except Exception as error:
                        cur.execute("ROLLBACK TO SAVEPOINT paso;")
                        print(f"   {tabla:26} se omite ({str(error).strip()})")
                if correos is None:
                    cur.execute("DELETE FROM correos_procesados;")
                    print(f"   {'correos_procesados':26} {cur.rowcount} fila(s) (todas)")
                elif correos:
                    cur.execute("DELETE FROM correos_procesados "
                                "WHERE message_id = ANY(%s);", (correos,))
                    print(f"   {'correos_procesados':26} {cur.rowcount} fila(s)")
            conexion.commit()
        except Exception as error:
            conexion.rollback()
            print(f"\nNo se borró nada: {error}")
            return 1
        finally:
            conexion.autocommit = True

    print("\nHecho.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
