# Atajos de base de datos para el Cotizador RFQ (requiere Docker).
.PHONY: db-up db-down db-reset db-psql db-smoke

# Levanta PostgreSQL y carga el esquema.
db-up:
	bash scripts/db_init.sh

# Detiene el contenedor (conserva los datos).
db-down:
	docker compose down

# Borra los datos y recrea la base desde cero.
db-reset:
	docker compose down -v
	bash scripts/db_init.sh

# Abre una sesión psql interactiva.
db-psql:
	docker compose exec db psql -U $${PG_USER:-postgres} -d $${PG_DATABASE:-cotizador}

# Corre el test de humo del DDL contra la base ya levantada.
db-smoke:
	python -m unittest tests.test_smoke_postgres -v
