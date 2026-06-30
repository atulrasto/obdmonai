.PHONY: up down migrate test lint fmt seed certs help

# Bring up the full stack (dev profile)
up:
	docker compose --profile dev up -d

# Tear down the stack
down:
	docker compose --profile dev down

# Run Alembic migrations
migrate:
	docker compose run --rm migrate

# Run the full pytest suite.
# DATABASE_URL       → app role (obdmonai_app) — RLS is enforced, isolation tests are meaningful.
# SUPERUSER_DATABASE_URL → postgres superuser — used by db_engine / ingest_engine fixtures
#                          for schema inspection and direct hypertable queries in tests.
test:
	docker run --rm --network obdmonai_internal \
		-e DATABASE_URL="postgresql+asyncpg://$${POSTGRES_USER}:$${POSTGRES_PASSWORD}@db:5432/$${POSTGRES_DB}" \
		-e SUPERUSER_DATABASE_URL="postgresql+asyncpg://$${POSTGRES_SUPERUSER}:$${POSTGRES_SUPERUSER_PASSWORD}@db:5432/$${POSTGRES_DB}" \
		obdmonai-backend pytest tests/ -v --tb=short

# Lint (ruff + mypy)
lint:
	ruff check backend/
	mypy backend/app

# Format (black)
fmt:
	black backend/
	ruff check --fix backend/

# Load demo seed data
seed:
	docker compose run --rm backend python -m app.seed

# Generate local dev TLS certs for Mosquitto (CA + server cert + sample device certs)
certs:
	bash infra/mosquitto/gen-certs.sh

help:
	@echo "Targets: up | down | migrate | test | lint | fmt | seed | certs"
