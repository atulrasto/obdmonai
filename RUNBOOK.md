# obdmonai — Operations Runbook

## Quick reference

| Service       | Role                            | Internal address    |
|---------------|---------------------------------|---------------------|
| `db`          | TimescaleDB 2.17 / PG 16        | `db:5432`           |
| `pgbouncer`   | Transaction-mode connection pool | `pgbouncer:5432`   |
| `mosquitto`   | MQTT broker (TLS 8883)          | `mosquitto:8883`    |
| `backend`     | FastAPI app                     | `backend:8000`      |
| `ingest`      | MQTT → DB worker                | (no HTTP port)      |
| `frontend`    | React SPA (nginx)               | `frontend:80`       |
| `caddy`       | Reverse proxy + auto-HTTPS      | `:80` / `:443`      |

---

## Bringing the stack up / down

```bash
# Dev (includes mailhog + simulator)
docker compose --profile dev up -d

# Production overlay (no host ports for db/api, resource limits)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Tail all logs
docker compose logs -f

# Graceful shutdown
docker compose down
```

---

## Migrations

Always run Alembic via the `migrate` service — it connects as the superuser directly to TimescaleDB, bypassing pgbouncer.

```bash
# Apply all pending migrations
docker compose run --rm migrate

# Show current revision
docker compose run --rm migrate alembic current

# Create a new migration (auto-generate from model diff)
docker compose run --rm migrate alembic revision --autogenerate -m "add_foo_column"

# Roll back one revision
docker compose run --rm migrate alembic downgrade -1
```

Migrations MUST be idempotent (use `IF NOT EXISTS` / `IF NOT EXISTS` guards) and MUST have a working `downgrade()`.  Never call `Base.metadata.create_all()`.

---

## Database backup and restore

### Backup

```bash
# Full logical dump (recommended for < 100 GB)
docker compose exec db pg_dump \
  -U ${POSTGRES_SUPERUSER} \
  -d ${POSTGRES_DB} \
  --format=custom \
  --compress=9 \
  -f /tmp/obdmonai_$(date +%Y%m%d_%H%M%S).dump

# Copy the dump out of the container
docker cp obdmonai-db-1:/tmp/obdmonai_*.dump ./backups/
```

For the hypertable (continuous read load), prefer TimescaleDB's own tooling:

```bash
docker compose exec db bash -c "
  timescaledb-parallel-copy --db-name ${POSTGRES_DB} --table telemetry --format csv …
"
```

### Restore

```bash
# 1. Bring up only the DB
docker compose up -d db
# 2. Restore (superuser)
docker cp ./backups/obdmonai_20260101_000000.dump obdmonai-db-1:/tmp/restore.dump
docker compose exec db pg_restore \
  -U ${POSTGRES_SUPERUSER} \
  -d ${POSTGRES_DB} \
  --clean --if-exists \
  /tmp/restore.dump
# 3. Re-run migrations to ensure revision pointer is up to date
docker compose run --rm migrate
# 4. Bring up the rest
docker compose up -d
```

---

## TLS certificates

### Caddy (auto-HTTPS)

Caddy stores its certificate state in the `caddy_data` Docker volume.  On first startup it issues a certificate from Let's Encrypt automatically (requires `CADDY_EMAIL` and `CADDY_DOMAIN` to be set in `.env`).

```bash
# Force certificate renewal (Caddy handles this automatically; manual only if needed)
docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile

# Inspect stored certs
docker compose exec caddy find /data/caddy/certificates -name '*.crt' -exec openssl x509 -noout -dates -in {} \;
```

### MQTT / Mosquitto (device TLS)

Device certificates live in `./infra/mosquitto/certs/`.  The broker uses mutual TLS — every OBD device has its own client certificate signed by your private CA.

```bash
# Rotate broker server cert (replace ca.crt, server.crt, server.key then restart)
docker compose restart mosquitto

# Revoke a compromised device cert
#   1. Add the device serial to infra/mosquitto/crl.pem (or issue a new CA CRL)
#   2. docker compose restart mosquitto
```

**Private keys must never be committed to git.**  Keep your CA key offline; store signed certs in the mounted `./infra/mosquitto/certs/` directory only.

---

## Seeding demo data

```bash
docker compose run --rm backend python -m app.seed
```

Creates tenant **Acme Logistics** (`demo@acmefleet.io` / `AcmeFleet2024!`) with 3 vehicles and 200 realistic telemetry readings each.  Safe to run multiple times — existing tenant and vehicles are skipped.

---

## Health checks

```bash
# Backend API
curl http://localhost:8002/health          # {"status": "ok"}

# Frontend nginx
curl http://localhost/nginx-health         # (via Caddy)

# Postgres
docker compose exec db pg_isready -U ${POSTGRES_SUPERUSER}

# TimescaleDB hypertable row count
docker compose exec db psql -U ${POSTGRES_SUPERUSER} -d ${POSTGRES_DB} \
  -c "SELECT count(*) FROM telemetry;"
```

---

## PDF reports

```bash
# Generate a PDF report for a vehicle (replace UUIDs and timestamps)
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8002/reports/vehicles/<vehicle_id>/pdf?from_ts=2026-01-01T00:00:00Z&to_ts=2026-01-02T00:00:00Z" \
  -o report.pdf
```

---

## Scaling

### Horizontal backend replicas

The FastAPI backend is stateless.  Add replicas behind a load balancer or with Docker Swarm:

```bash
docker compose up -d --scale backend=3
```

Update the Caddyfile `reverse_proxy` target to the service name — Docker's internal DNS will round-robin across replicas.

### TimescaleDB read replicas

For read-heavy analytics, add a streaming replica and point the `DATABASE_URL_DIRECT` (analytics queries) to the replica endpoint.  The `backend` container reads `DATABASE_URL_DIRECT` for direct-connection paths (migrations, heavy analytics).

### pgbouncer pool tuning

Edit `docker-compose.yml` environment variables for pgbouncer:

| Variable            | Default | Notes                           |
|---------------------|---------|---------------------------------|
| `MAX_CLIENT_CONN`   | 1000    | Max connections from app layer  |
| `DEFAULT_POOL_SIZE` | 25      | Connections to Postgres per db  |

---

## Structured logs

In production (`ENVIRONMENT=production`) the backend and ingest worker emit **JSON logs** to stdout — collect them with Loki, Datadog, or CloudWatch.

```bash
# Pretty-print JSON logs locally (requires jq)
docker compose logs -f backend | jq .

# Filter for errors only
docker compose logs -f backend | jq 'select(.level == "error")'
```

---

## Common incidents

### "503 from Caddy"

1. Check backend health: `docker compose ps backend` — is it `healthy`?
2. Check frontend health: `docker compose ps frontend`
3. Tail backend logs: `docker compose logs --tail=100 backend`

### "DB connection pool exhausted"

- Reduce load or increase `DEFAULT_POOL_SIZE` in pgbouncer env.
- Check for long-running transactions: `SELECT * FROM pg_stat_activity WHERE state = 'active';`

### "MQTT broker refusing connections"

- Confirm device cert is not in the CRL.
- Check Mosquitto logs: `docker compose logs mosquitto`
- Verify port 8884 is reachable: `mosquitto_sub -h <host> -p 8884 --cafile ca.crt --cert client.crt --key client.key -t '#'`

### "ML score endpoint 503"

The ML models are loaded lazily on first request.  If the model file is missing, the endpoint returns 503 instead of 500 to indicate a transient error.  Check:

```bash
docker compose exec backend ls -lh /app/models/
```

If empty, trigger a training run or copy pre-trained `.joblib` files into the image / a mounted volume.

---

## Environment variables reference

See `.env.example` for the full list with safe placeholder values.  Every secret is injected via `.env` (gitignored) — **never commit real values**.

Key variables:

| Variable                    | Purpose                                  |
|-----------------------------|------------------------------------------|
| `POSTGRES_SUPERUSER`        | PG superuser (migrations only)           |
| `POSTGRES_USER`             | App role (non-superuser, RLS enforced)   |
| `DATABASE_URL`              | asyncpg URL for app (via pgbouncer)      |
| `JWT_SECRET`                | HS256 signing key — rotate periodically  |
| `ANTHROPIC_API_KEY`         | FleetView AI (optional; falls back to placeholder) |
| `CADDY_DOMAIN`              | Your public domain for auto-HTTPS        |
| `CADDY_EMAIL`               | Let's Encrypt contact email              |
| `ENVIRONMENT`               | `development` or `production`            |
