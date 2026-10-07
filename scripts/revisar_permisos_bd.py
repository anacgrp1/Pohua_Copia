"""Revisa qué roles y permisos tiene de verdad la base (Neon), sin cambiar nada.

    python scripts/revisar_permisos_bd.py

Para qué
--------
Hasta 2026-10 ``sql/schema.sql`` creaba el rol ``web_anon`` (para un PostgREST
de desarrollo que se quitó del proyecto) y le daba SELECT, INSERT, UPDATE y
DELETE sobre todas las tablas de ``public``. ``schema.sql`` también se aplica en
Neon —lo corre el workflow ``update-neon.yml`` y la API al arrancar
(``app/persistence/migraciones.py``)—, así que el rol llegó a producción. Esto
enseña lo que hay realmente aplicado allá:

  1. Los roles que no son del sistema y qué pueden hacer (login, superusuario…).
  2. Las tablas a las que ``web_anon`` tiene acceso y con qué permisos.
  3. Quién puede convertirse en ``web_anon`` (miembros del rol).
  4. Permisos concedidos a PUBLIC (cualquier rol) sobre las tablas.
  5. Privilegios por defecto (lo que heredarán las tablas nuevas).
  6. Qué archivos de ``sql/`` constan como aplicados y cuáles faltan.

Sólo lee: abre la transacción en modo READ ONLY, así que aunque hubiera un
error en una consulta no puede escribir nada. No imprime la cadena de
conexión ni contraseñas; sólo el host y el nombre de la base.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)

from app.persistence.duplicates import conexion_bd  # noqa: E402

ROL = "web_anon"

SQL_DONDE = "SELECT current_database(), current_user, inet_server_addr()::text, version();"

SQL_ROLES = """
SELECT rolname, rolcanlogin, rolsuper, rolcreaterole, rolcreatedb, rolbypassrls,
       rolinherit, rolconnlimit
  FROM pg_roles
 WHERE rolname !~ '^pg_'
 ORDER BY rolname;
"""

SQL_EXISTE = "SELECT 1 FROM pg_roles WHERE rolname = %s;"

SQL_ESQUEMA = "SELECT has_schema_privilege(%s, 'public', 'USAGE'), has_schema_privilege(%s, 'public', 'CREATE');"

SQL_TABLAS_ROL = """
SELECT table_name, string_agg(privilege_type, ', ' ORDER BY privilege_type)
  FROM information_schema.role_table_grants
 WHERE grantee = %s AND table_schema = 'public'
 GROUP BY table_name
 ORDER BY table_name;
"""

SQL_TABLAS_TODAS = """
SELECT c.relname
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm')
 ORDER BY c.relname;
"""

SQL_SECUENCIAS_ROL = """
SELECT c.relname
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind = 'S'
   AND (has_sequence_privilege(%s, c.oid, 'USAGE') OR has_sequence_privilege(%s, c.oid, 'SELECT'))
 ORDER BY c.relname;
"""

SQL_MIEMBROS = """
SELECT m.rolname AS miembro, r.rolname AS de_rol
  FROM pg_auth_members am
  JOIN pg_roles r ON r.oid = am.roleid
  JOIN pg_roles m ON m.oid = am.member
 WHERE r.rolname = %s OR m.rolname = %s
 ORDER BY 1, 2;
"""

SQL_PUBLIC = """
SELECT table_name, string_agg(privilege_type, ', ' ORDER BY privilege_type)
  FROM information_schema.role_table_grants
 WHERE grantee = 'PUBLIC' AND table_schema = 'public'
 GROUP BY table_name
 ORDER BY table_name;
"""

SQL_DEFAULT = """
SELECT pg_get_userbyid(d.defaclrole), COALESCE(n.nspname, '(todos)'),
       CASE d.defaclobjtype WHEN 'r' THEN 'tablas' WHEN 'S' THEN 'secuencias'
            WHEN 'f' THEN 'funciones' WHEN 'T' THEN 'tipos' WHEN 'n' THEN 'esquemas'
            ELSE d.defaclobjtype::text END,
       array_to_string(d.defaclacl, ' ')
  FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace
 ORDER BY 1, 2, 3;
"""

SQL_RLS = """
SELECT c.relname, c.relrowsecurity
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND c.relrowsecurity
 ORDER BY c.relname;
"""

SQL_MIGRACIONES = """
SELECT archivo, aplicada_en::text FROM schema_migraciones ORDER BY archivo;
"""

SQL_HAY_REGISTRO = "SELECT to_regclass('public.schema_migraciones') IS NOT NULL;"


def _si(v) -> str:
    return "sí" if v else "no"


def _titulo(texto: str) -> None:
    print(f"\n== {texto} " + "=" * max(3, 70 - len(texto)))


def _archivos_sql() -> list:
    lista = []
    if (RAIZ / "sql" / "schema.sql").is_file():
        lista.append("schema.sql")
    carpeta = RAIZ / "sql" / "migrations"
    if carpeta.is_dir():
        lista += sorted(f.name for f in carpeta.glob("*.sql") if not f.name.endswith("_down.sql"))
    return lista


def revisar(cur) -> dict:
    """Hace todas las consultas e imprime el informe. Devuelve un resumen."""
    resumen = {"existe": False, "tablas_rol": [], "escribe": [], "miembros": [], "public": []}

    cur.execute(SQL_DONDE)
    base, usuario, host, version = cur.fetchone()
    print(f"Base: {base}   usuario: {usuario}   servidor: {host or 'socket local'}")
    print(f"PostgreSQL: {version.split(',')[0]}")

    _titulo("1. Roles (sin los del sistema pg_*)")
    cur.execute(SQL_ROLES)
    print(f"  {'rol':28} login super crearol crearbd salta_RLS")
    for nombre, login, sup, crol, cbd, rls, _inh, _lim in cur.fetchall():
        print(f"  {nombre:28} {_si(login):5} {_si(sup):5} {_si(crol):7} {_si(cbd):7} {_si(rls)}")

    _titulo(f"2. Permisos de «{ROL}»")
    cur.execute(SQL_EXISTE, (ROL,))
    if not cur.fetchone():
        print(f"  El rol {ROL} NO existe en esta base.")
    else:
        resumen["existe"] = True
        cur.execute(SQL_ESQUEMA, (ROL, ROL))
        uso, crear = cur.fetchone()
        print(f"  Esquema public: USAGE {_si(uso)}, CREATE {_si(crear)}")
        cur.execute(SQL_TABLAS_ROL, (ROL,))
        filas = cur.fetchall()
        resumen["tablas_rol"] = [t for t, _ in filas]
        resumen["escribe"] = [t for t, p in filas if any(x in p for x in ("INSERT", "UPDATE", "DELETE"))]
        cur.execute(SQL_TABLAS_TODAS)
        todas = [f[0] for f in cur.fetchall()]
        if filas:
            print(f"  Tablas con permiso: {len(filas)} de {len(todas)}")
            for tabla, permisos in filas:
                print(f"    {tabla:34} {permisos}")
        else:
            print("  Ninguna tabla con permisos.")
        sin = [t for t in todas if t not in resumen["tablas_rol"]]
        if sin:
            print(f"  Tablas SIN permiso para {ROL} ({len(sin)}): {', '.join(sin)}")
        cur.execute(SQL_SECUENCIAS_ROL, (ROL, ROL))
        sec = [f[0] for f in cur.fetchall()]
        print(f"  Secuencias con USAGE/SELECT: {len(sec)}" + (f" ({', '.join(sec)})" if sec else ""))

    _titulo("3. Quién puede convertirse en (o hereda de) ese rol")
    cur.execute(SQL_MIEMBROS, (ROL, ROL))
    filas = cur.fetchall()
    resumen["miembros"] = filas
    if filas:
        for miembro, de in filas:
            print(f"  {miembro} es miembro de {de}")
    else:
        print("  Nadie: ningún rol es miembro de él ni él de otro.")

    _titulo("4. Permisos concedidos a PUBLIC (cualquier rol) sobre tablas")
    cur.execute(SQL_PUBLIC)
    filas = cur.fetchall()
    resumen["public"] = filas
    if filas:
        for tabla, permisos in filas:
            print(f"  {tabla:34} {permisos}")
    else:
        print("  Ninguno.")

    _titulo("5. Privilegios por defecto (tablas futuras)")
    cur.execute(SQL_DEFAULT)
    filas = cur.fetchall()
    if filas:
        for dueno, esquema, tipo, acl in filas:
            print(f"  dueño {dueno}, esquema {esquema}, {tipo}: {acl}")
    else:
        print("  Ninguno definido (las tablas nuevas no dan permisos a nadie más).")

    _titulo("6. Seguridad por filas (RLS) activa")
    cur.execute(SQL_RLS)
    filas = cur.fetchall()
    print("  " + (", ".join(f[0] for f in filas) if filas else "En ninguna tabla."))

    _titulo("7. Archivos de sql/ aplicados")
    cur.execute(SQL_HAY_REGISTRO)
    if not cur.fetchone()[0]:
        print("  No existe la tabla schema_migraciones (la API nunca aplicó migraciones aquí).")
    else:
        cur.execute(SQL_MIGRACIONES)
        hechas = dict(cur.fetchall())
        locales = _archivos_sql()
        for nombre in locales:
            marca = hechas.get(nombre)
            print(f"  {'✔' if marca else '✘'} {nombre:42} {marca[:19] if marca else 'PENDIENTE'}")
        extra = sorted(set(hechas) - set(locales))
        if extra:
            print(f"  En la base pero no en tu carpeta sql/: {', '.join(extra)}")

    _titulo("Conclusión")
    if not resumen["existe"]:
        print(f"  {ROL} no existe: nada que limpiar.")
    else:
        print(f"  {ROL} existe con acceso a {len(resumen['tablas_rol'])} tabla(s)"
              f"; con escritura en {len(resumen['escribe'])}.")
        if any(t == "usuarios" for t in resumen["tablas_rol"]):
            print("  Incluye la tabla usuarios (hashes de contraseña).")
        print("  Es NOLOGIN: nadie entra directamente con él; sólo un rol miembro o un"
              " PostgREST conectado a esta base podría usarlo.")
        otros = [m for m, de in resumen["miembros"] if de == ROL and m != usuario]
        if otros:
            print(f"  Roles que pueden actuar como él: {', '.join(otros)}.")
        elif resumen["miembros"]:
            print(f"  {usuario} figura como miembro porque lo creó (PostgreSQL 16+ lo hace"
                  " solo); no le da nada que no tuviera ya como dueño de las tablas.")
    if resumen["public"]:
        print("  Hay permisos para PUBLIC: revísalos, aplican a cualquier rol de la base.")
    return resumen


def main() -> int:
    with conexion_bd() as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY;")
            revisar(cur)
        conn.rollback()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
