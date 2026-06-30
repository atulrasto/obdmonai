# obdmonai

A multi-tenant SaaS platform that ingests OBD-II / CAN telematics from in-vehicle On-Board Units (OBUs), stores it, runs deterministic alerts and ML analytics on it, and serves a fleet dashboard.

## Architecture

- **MQTT ingest** → **FastAPI backend** → **TimescaleDB** (PostgreSQL 16 + TimescaleDB)
- **Tier A**: deterministic rules engine + threshold alerts (never imports Tier B)
- **Tier B**: ML driver-behaviour scoring + predictive-maintenance anomaly detection (reads Tier A data only)
- **FleetView**: read-only LLM layer (Anthropic API) for natural-language summaries
- **Frontend**: React + Vite + TypeScript + Recharts + MapLibre GL

## Quick start

```bash
cp .env.example .env          # fill in secrets
make certs                    # generate dev TLS certs
make up                       # bring up the stack
make migrate                  # run Alembic migrations
make seed                     # load demo data
```

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, asyncpg |
| Database | PostgreSQL 16 + TimescaleDB, pgbouncer |
| Messaging | Eclipse Mosquitto (TLS 8883) |
| Reverse proxy | Caddy 2 (auto-HTTPS) |
| Frontend | React, Vite, TypeScript, Recharts, MapLibre GL |
| Reports | ReportLab (PDF) |
| LLM | Anthropic API (server-side, FleetView only) |
| Tests | pytest, pytest-asyncio, httpx |
| Firmware | ESP32-WROOM, PlatformIO, TWAI (CAN), MQTT/TLS |

## Development

See `PROGRESS.md` for phase status and `RUNBOOK.md` (Phase 10) for ops procedures.
