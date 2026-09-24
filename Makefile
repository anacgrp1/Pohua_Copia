# Atajos del Cotizador. Los de base de datos requieren Docker.
.PHONY: help db-up db-down db-reset db-psql db-smoke usuario test lint

# Lista los atajos.
help:
	@echo "db-up     Levanta PostgreSQL y carga el esquema"
	@echo "db-down   Detiene el contenedor (conserva los datos)"
	@echo "db-reset  Borra los datos y recrea la base"
	@echo "db-psql   Abre psql contra la base local"
	@echo "db-smoke  Test de humo del DDL contra la base levantada"
	@echo "usuario   Alta de usuario: make usuario CORREO=... NOMBRE=\"...\" ROL=admin|pm|quoter"
	@echo "test      Corre la suite de pruebas"
	@echo "lint      Revisa el estilo con ruff"

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
	python -m unittest tests.integration.test_smoke_postgres -v

# Alta de usuario. La contraseña se pide por consola (no queda en el historial).
usuario:
	python scripts/crear_usuario.py --correo "$(CORREO)" --nombre "$(NOMBRE)" --rol "$(ROL)"

test:
	python -m pytest -q

lint:
	ruff check .
