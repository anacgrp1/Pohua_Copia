#!/usr/bin/env bash
# Levanta PostgreSQL (docker compose), espera a que acepte conexiones y
# carga sql/schema.sql. Idempotente: schema.sql usa CREATE TABLE IF NOT EXISTS.
#
# Variables (con los mismos defaults que config.py):
#   PG_DATABASE (cotizador)  PG_USER (postgres)  PG_PORT (5432)
set -euo pipefail

# Ubicarse en Programación/ (raíz del proyecto), sea cual sea el CWD.
cd "$(dirname "$0")/.."

PG_USER="${PG_USER:-postgres}"
PG_DATABASE="${PG_DATABASE:-cotizador}"

echo ">> Levantando el contenedor de PostgreSQL..."
# Sólo el servicio db: PostgREST está detrás del perfil "tools" y no hace falta
# para trabajar (la aplicación se conecta por psycopg2, no por PostgREST).
docker compose up -d db

echo ">> Esperando a que PostgreSQL acepte conexiones..."
for i in $(seq 1 30); do
  if docker compose exec -T db pg_isready -U "$PG_USER" -d "$PG_DATABASE" >/dev/null 2>&1; then
    echo ">> PostgreSQL listo."
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "!! Timeout esperando a PostgreSQL." >&2
    exit 1
  fi
  sleep 2
done

echo ">> Cargando sql/schema.sql..."
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DATABASE" < sql/schema.sql

# Aplicar las migraciones en orden (004, 005, ...). Se omiten los "down".
echo ">> Aplicando migraciones (sql/migrations/*.sql)..."
for mig in $(ls sql/migrations/*.sql 2>/dev/null | grep -v '_down\.sql$' | sort); do
    echo "   - $mig"
    docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DATABASE" < "$mig"
done

TABLAS=$(docker compose exec -T db psql -tA -U "$PG_USER" -d "$PG_DATABASE" \
  -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" | tr -d '[:space:]')

echo ">> Esquema + migraciones cargados ($TABLAS tablas). Base '$PG_DATABASE' lista en localhost:${PG_PORT:-5432}."
echo ">> Siguiente paso: crea tu usuario con"
echo "     make usuario CORREO=tu@correo.com NOMBRE=\"Tu Nombre\" ROL=admin"
