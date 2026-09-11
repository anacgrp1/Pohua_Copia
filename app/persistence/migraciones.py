"""Aplica el esquema y las migraciones pendientes al arrancar la API.

POR QUÉ EXISTE
--------------
El esquema se aplicaba SÓLO desde el workflow `update-neon.yml`, que corre al
empujar a main cuando cambia algo en `sql/`. Eso deja una grieta: si el código
llega a producción y el esquema no, la aplicación arranca contra una base vieja
y falla al usarla. Pasó de verdad —la migración 008 añade las columnas de la
foto de perfil, nunca llegó a Neon, y Perfil → Usuarios y subir una foto
devolvían 500 mientras todo lo demás funcionaba—, y desde fuera parecía que la
base estaba caída cuando en realidad respondía perfectamente.

Con esto, el esquema viaja con el código: si la aplicación arranca, su base
tiene lo que ese código necesita. Es la misma idea que `migrate` en Django o
Rails, sin traerse un framework entero para siete archivos.

DECISIONES
----------
  * Se aplican los archivos que faltan, en orden, y se apunta cuáles se han
    aplicado en `schema_migraciones`. Un archivo no se repite.

  * Sobre una base que ya venía migrada por el workflow, la tabla de registro
    está vacía y se vuelven a aplicar todos. Es seguro: TODOS los archivos de
    `sql/` son idempotentes a propósito (CREATE ... IF NOT EXISTS, ON CONFLICT,
    comprobaciones previas) y CI los ejecuta contra un PostgreSQL real en cada
    push. Se comprobó además aplicándolos dos veces seguidas sobre la misma
    base: la segunda pasada no da un solo error.

  * Cada archivo va en su propia transacción. Si uno falla, se deshace ese y NO
    se sigue con los de después: aplicar el 009 sin el 008 dejaría la base en un
    estado que nadie ha probado.

  * Un fallo NO tumba la aplicación. Se registra bien fuerte y se sigue
    sirviendo: la web ya estaba en pie con el esquema viejo, y dejar a todo el
    mundo sin cotizador porque una migración no pasó es peor que seguir con las
    pantallas que sí funcionan. El estado queda en el registro y en
    `estado_migraciones()`.

  * Un cerrojo de asesoría de PostgreSQL (`pg_advisory_lock`) impide que dos
    instancias apliquen lo mismo a la vez. Render puede levantar la nueva antes
    de bajar la vieja, y dos `ALTER TABLE` simultáneos sobre la misma tabla es
    justamente lo que no se quiere.

  * `AUTO_MIGRAR=false` lo apaga. Si algún día ISC prefiere aplicar el esquema
    a mano o desde el workflow, se apaga sin tocar código.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List

import app.persistence.duplicates as duplicates

log = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent.parent
SQL = RAIZ / "sql"

# Número arbitrario pero fijo: identifica ESTE cerrojo entre todos los de la
# base. Sólo tiene que ser el mismo en todas las instancias.
CERROJO = 815_2026

TABLA_REGISTRO = """
CREATE TABLE IF NOT EXISTS schema_migraciones (
    archivo     text PRIMARY KEY,
    aplicada_en timestamptz NOT NULL DEFAULT now()
);
"""


def _habilitado() -> bool:
    return os.environ.get("AUTO_MIGRAR", "true").strip().lower() not in (
        "0", "false", "no", "off",
    )


def archivos() -> List[Path]:
    """El esquema y las migraciones, en el orden en que hay que aplicarlos.

    El mismo orden que usa `update-neon.yml`: primero `schema.sql`, que crea las
    tablas base, y después las migraciones por número. Los `_down` se saltan:
    son marcha atrás manual, no parte del camino de ida.
    """
    lista: List[Path] = []
    esquema = SQL / "schema.sql"
    if esquema.is_file():
        lista.append(esquema)
    carpeta = SQL / "migrations"
    if carpeta.is_dir():
        lista.extend(sorted(
            f for f in carpeta.glob("*.sql") if not f.name.endswith("_down.sql")
        ))
    return lista


def _aplicadas(cur) -> set:
    cur.execute("SELECT archivo FROM schema_migraciones;")
    return {fila[0] for fila in cur.fetchall()}


def aplicar_pendientes() -> Dict[str, Any]:
    """Aplica lo que falte. Devuelve un resumen; nunca lanza."""
    resumen: Dict[str, Any] = {
        "habilitado": _habilitado(), "aplicadas": [], "ya_estaban": [], "error": None,
    }
    if not resumen["habilitado"]:
        log.info("Migraciones automáticas desactivadas (AUTO_MIGRAR=false).")
        return resumen

    pendientes = archivos()
    if not pendientes:
        log.warning("No encuentro los archivos SQL en %s.", SQL)
        return resumen

    try:
        with duplicates.conexion_bd() as conexion:
            with conexion.cursor() as cur:
                cur.execute(TABLA_REGISTRO)
                conexion.commit()

                # El cerrojo se suelta solo al cerrar la conexión, incluso si
                # el proceso muere a media migración.
                cur.execute("SELECT pg_advisory_lock(%s);", (CERROJO,))
                hechas = _aplicadas(cur)

            for ruta in pendientes:
                nombre = ruta.name
                if nombre in hechas:
                    resumen["ya_estaban"].append(nombre)
                    continue
                try:
                    with conexion.cursor() as cur:
                        cur.execute(ruta.read_text(encoding="utf-8"))
                        cur.execute(
                            "INSERT INTO schema_migraciones (archivo) VALUES (%s) "
                            "ON CONFLICT (archivo) DO NOTHING;", (nombre,))
                    conexion.commit()
                    resumen["aplicadas"].append(nombre)
                    log.info("Migración aplicada: %s", nombre)
                except Exception as error:
                    conexion.rollback()
                    resumen["error"] = f"{nombre}: {error}"
                    log.error(
                        "La migración %s falló y se detuvo ahí. La aplicación "
                        "sigue en pie con el esquema anterior; las pantallas que "
                        "dependan de ella darán error hasta que se arregle. "
                        "Detalle: %s", nombre, error,
                    )
                    break

            with conexion.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s);", (CERROJO,))
            conexion.commit()

    except Exception as error:
        resumen["error"] = str(error)
        log.warning("No se pudieron aplicar las migraciones: %s", error)
        return resumen

    if resumen["aplicadas"]:
        log.info("Esquema al día. Aplicadas ahora: %s",
                 ", ".join(resumen["aplicadas"]))
    else:
        log.info("Esquema al día. No había nada pendiente.")
    return resumen


def estado() -> Dict[str, Any]:
    """Qué archivos constan como aplicados y cuáles faltan.

    Lo usa `GET /api/system/config` para que se pueda ver desde la propia
    aplicación, sin entrar a la base.
    """
    todos = [f.name for f in archivos()]
    try:
        with duplicates.conexion_bd() as conexion:
            with conexion.cursor() as cur:
                cur.execute(TABLA_REGISTRO)
                conexion.commit()
                hechas = _aplicadas(cur)
    except Exception as error:
        return {"disponible": False, "motivo": str(error),
                "aplicadas": [], "pendientes": todos}

    return {
        "disponible": True,
        "aplicadas": [n for n in todos if n in hechas],
        "pendientes": [n for n in todos if n not in hechas],
    }
