FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install deps in a separate layer for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY alembic.ini .
COPY alembic/ alembic/
COPY app/ app/
COPY tests/ tests/
COPY pytest.ini .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------------------------------------------------------------------------
# simulator target — DEV ONLY; publishes fake OBD telemetry via MQTT
# (built via `docker compose build simulator`)
# ---------------------------------------------------------------------------
FROM base AS simulator
CMD ["python", "-m", "app.ingest.simulator"]
