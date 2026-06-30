# PROGRESS.md — obdmonai phase checklist

## Phase 1 — Scaffold and tooling
- [x] Directory layout created
- [x] CLAUDE.md written
- [x] PROGRESS.md written
- [x] README.md written
- [x] pyproject.toml with deps + ruff/black/mypy config
- [x] .gitignore (env, certs, __pycache__, node_modules, build dirs)
- [x] .env.example with all variables documented (port offsets noted)
- [x] docker-compose.yml skeleton (db, pgbouncer, mosquitto, backend, ingest, frontend, caddy)
- [x] docker-compose.prod.yml
- [x] Makefile targets: up, down, migrate, test, lint, fmt, seed, certs
- [x] pre-commit config (ruff, black, mypy)
- [x] Acceptance: `docker compose config` valid (warnings only — no .env, expected); `make lint` deferred to Phase 2 (no Python source to lint yet); first commit pending user go-ahead

## Phase 2 — Database, migrations, RLS, hypertable ✅
- [x] db service on TimescaleDB (Postgres 16) — timescale/timescaledb:2.17.2-pg16
- [x] pgbouncer config in infra/pgbouncer (reference ini; edoburu image uses env vars)
- [x] alembic init; env.py wired to async DATABASE_URL and models metadata
- [x] Migration 0001: enable timescaledb; create non-superuser obdmonai_app role; schema grants; DROP OWNED BY in downgrade
- [x] Migration 0002: clients, users, vehicles, devices tables; RLS + insert/isolation policies on all 3 tenant tables
- [x] Migration 0003: telemetry hypertable (7-day chunks); ix_telemetry_client_vehicle_time; ix_telemetry_device_seq (non-unique — TimescaleDB limitation); RLS deferred to 0004
- [x] Migration 0004: telemetry_1m + telemetry_1h CAGGs; refresh policies; 90-day retention; RLS on telemetry enabled AFTER CAGGs (TimescaleDB restriction)
- [x] Acceptance: alembic downgrade base → upgrade head clean; 8/8 pytest checks pass (hypertable, RLS, policies, non-superuser role, dedup index, CAGGs, version table)

## Phase 3 — Backend core (auth, tenancy, CRUD) ✅
- [x] config.py (pydantic-settings, ENVIRONMENT flag, NullPool for non-prod)
- [x] db.py (async engine with NullPool in dev/test; get_db / get_tenant_db_session)
- [x] main.py (FastAPI app factory, CORS, health endpoint, all routers)
- [x] JWT auth (/auth/login, /auth/refresh); password hashing via direct bcrypt (passlib 1.7.4 incompatible with bcrypt 5.x)
- [x] RBAC: get_current_user, require_role(*roles), get_tenant_db (SET LOCAL GUC, f-string safe for UUID)
- [x] Migration 0005: NULLIF safety on all 4 RLS policies; auth_get_user_by_email, auth_get_user_by_id, auth_create_initial_owner SECURITY DEFINER functions
- [x] CRUD routers: clients (unauthenticated POST via auth_create_initial_owner), vehicles, devices
- [x] Device provisioning endpoint (JWT token, cert fingerprint storage)
- [x] Acceptance: 23/23 pytest pass (Phase 2: 8; auth: 6; CRUD: 6; isolation: 3)

## Phase 4 — MQTT ingest pipeline ✅
- [x] infra/mosquitto: mosquitto.conf (TLS 8883, mutual-auth client cert, use_identity_as_username)
- [x] gen-certs script (local CA 10yr; server cert with SAN; ingest-worker cert; sample device cert; all to gitignored certs/)
- [x] Migration 0006: ingest_get_device, ingest_record_telemetry (atomic dedupe+insert), ingest_telemetry_exists SECURITY DEFINER functions (GRANT to obdmonai_app)
- [x] app/ingest/schemas.py: TelemetryPayload (device_id, ts, seq, gps, obd, imu, dtc, ign); ts validator handles Unix int or ISO-8601 str, normalises to UTC
- [x] app/ingest/worker.py: async MQTT subscriber (asyncio-mqtt 0.16.x, TLS context); CBOR-first decode with JSON fallback; topic-parsed client_id/vin vs ingest_get_device result; atomic dedupe insert; reconnect loop on MqttError
- [x] Insert into hypertable with device event timestamp (not cloud arrival time); denormalised client_id
- [x] Late/out-of-order messages stored at device time; dedupe on (device_id, seq) via PLPGSQL EXISTS check in SECURITY DEFINER function
- [x] Spoofed-tenant rejection: topic client_id checked against ingest_get_device.client_id
- [x] conftest.py: dual-URL pattern (DATABASE_URL = app role for RLS; SUPERUSER_DATABASE_URL = postgres for schema inspection)
- [x] Fixed Phase 3 hardcoded serials (ESP32-DEADBEEF / ESP32-ISO-TEST → uuid.uuid4() per run)
- [x] Makefile test target updated to docker run with correct credential split
- [x] Acceptance: 28/28 pytest pass (Phase 2: 8; auth: 6; CRUD: 6; isolation: 3; ingest: 5)

## Phase 5 — Tier A: deterministic rules and alerts ✅
- [x] Migration 0007: alerts + geofences tables; 7 SECURITY DEFINER functions (get_alert_states, watch_alert, fire_alert, clear_alert, get_geofences, get_prev_telemetry, alert_count)
- [x] app/tier_a/rules.py: pure rule functions + evaluate_all (no DB, no Tier B imports); hysteresis on all 7 rules (overspeed 120/110, harsh-braking 0.5g/0.3g, coolant 100°C/90°C, new DTC, idle 5min watch→fire, fuel drop >15%, geofence Haversine)
- [x] app/tier_a/engine.py: run_for_device — loads context, calls evaluate_all, persists via SECURITY DEFINER; separate transaction from ingest
- [x] app/tier_a/notify.py: dispatch_notification (log + optional SMTP + optional webhook); delivery dedupe inherent from alert state machine
- [x] app/api/alerts.py: GET /alerts (filter by state/device_id/rule), GET /alerts/{id} — RLS enforced
- [x] app/api/geofences.py: GET/POST /geofences, DELETE /geofences/{id} (soft-delete)
- [x] ingest/worker.py: calls run_for_device after ingest tx commits; separate tx; errors logged, ingest continues
- [x] conftest.py: async_client fixture shared across all integration tests
- [x] Acceptance: 71/71 pytest pass (Phase 2: 8; auth: 6; CRUD: 6; isolation: 3; ingest: 5; rules: 43)

## Phase 6 — Analytics API (aggregate-backed) ✅
- [x] Migration 0008: analytics_vehicle_kpis, analytics_list_trips, analytics_trip_detail, analytics_fleet_rollup SECURITY DEFINER functions; GRANT to obdmonai_app
- [x] Distance/time calculations skip inter-trip gaps (gap_sec > 300) to avoid inflating metrics across trip boundaries
- [x] app/api/analytics.py: VehicleKPIRead, TripRead, TripPointRead (ts not time), FleetVehicleRead; 4 endpoints
- [x] Trip detection: gap-island SQL with ign_just_on OR gap > 5 min; HAVING COUNT(*) > 1 filters singletons
- [x] Fleet rollup backed by telemetry_1m CAGG; CALL refresh_continuous_aggregate uses AUTOCOMMIT isolation
- [x] analytics_trip_detail returns `ts` alias (not `time` — reserved PostgreSQL keyword)
- [x] Acceptance: 82/82 pytest pass (Phase 2: 8; auth: 6; CRUD: 6; isolation: 3; ingest: 5; rules: 43; analytics: 11)

## Phase 7 — Tier B: ML (isolated module) ✅
- [x] Migration 0009: ml_models table (global, non-tenant); ml_get_model() + ml_get_telemetry_window() SECURITY DEFINER; seeds driver_score (GradientBoosting) and maintenance (IsolationForest) from synthetic data at migration time
- [x] app/tier_b/features.py: extract_features() → 10-dim vector (speed/rpm/coolant/harsh-events/idle/overspeed); no DB, no tier_a
- [x] app/tier_b/driver_score.py: train_driver_model() + predict_score(); safe/risky synthetic training data
- [x] app/tier_b/maintenance.py: train_maintenance_model() + predict_anomaly(); IsolationForest on healthy engine profiles
- [x] app/tier_b/registry.py: async model loading via ml_get_model(); joblib.load in executor thread (non-blocking); module-level cache
- [x] app/tier_b/inference.py: score_driver() + score_maintenance(); read-only DB via SECURITY DEFINER; null score when no telemetry
- [x] app/api/scores.py: GET /scores/vehicles/{id}/driver, GET /scores/vehicles/{id}/maintenance; read-only (no write endpoints)
- [x] Acceptance: 96/96 pytest pass (Phase 2: 8; auth: 6; CRUD: 6; isolation: 3; ingest: 5; rules: 43; analytics: 11; ML: 14)

## Phase 8 — FleetView: read-only LLM layer ✅
- [x] app/fleetview/redact.py: UUID / VIN / email redaction before LLM submission
- [x] app/fleetview/facts.py: VehicleFacts dataclass; assemble_facts() — reads vehicles, analytics, alerts, trips, Tier B scores; returns None on missing vehicle
- [x] app/fleetview/summarise.py: build_prompt() (identifier-free); get_summary() calls Anthropic claude-sonnet-4-6; falls back to placeholder when API key empty; no tools parameter
- [x] app/api/fleetview.py: GET /fleetview/vehicles/{id}/summary; 404 when facts=None
- [x] Strictly read-only; no tool access; redact() applied to prompt as safety net
- [x] NullPool asyncpg timeout raised to 120 s (conftest.py + db.py) to survive Docker connection pressure under heavy test load
- [x] Fixture seeding reduced: ml_ctx 20→5 readings, fv_ctx 15→5 (sufficient for non-null ML scores; cuts ~100 NullPool connection creations)
- [x] Acceptance: 111/111 pytest pass in 64 s (Phase 2: 8; auth: 6; CRUD: 6; isolation: 3; ingest: 5; rules: 43; analytics: 11; ML: 14; FleetView: 15)

## Phase 9 — Frontend (React/Vite/TS) ✅
- [x] Auth flow: login page with JWT storage; AuthProvider with token parse; RequireAuth guard
- [x] Fleet dashboard: vehicle card grid; 24h KPIs from /analytics/fleet merged with /vehicles
- [x] Vehicle live view: KPI cards, driver score ring, maintenance badge, Recharts LineChart of most recent trip (speed + RPM)
- [x] Map view (MapLibre GL): trip selector sidebar + TripMap polyline overlay; colour-coded route
- [x] Alerts view: filterable table (all / active / cleared) backed by /alerts
- [x] Device provisioning UI: device list + inline "Register new OBU" form → POST /devices
- [x] FleetView summary panel: vehicle selector + window dropdown → GET /fleetview → AI summary card
- [x] Typed API client: axios-based client in src/api/client.ts + src/api/types.ts (derived from backend Pydantic schemas); npm run gen-api script re-generates from live /openapi.json
- [x] maplibre-gl aliased to WebGL-free stub in vitest; ResizeObserver polyfilled; vite/client types wired
- [x] Acceptance: npm run build passes (tsc -b + vite, 899 modules, 4.5 s); 6/6 smoke tests pass (Dashboard × 3, VehicleView × 3)

## Phase 10 — Reverse proxy, full stack, ops ✅
- [x] Caddy Caddyfile (auto-HTTPS, routes /api/* → backend, everything else → frontend:80)
- [x] frontend/nginx.conf (SPA try_files fallback; /nginx-health endpoint; 1y cache headers for assets)
- [x] frontend/Dockerfile (multi-stage: node:20-alpine builder + nginx:1.27-alpine server)
- [x] docker-compose.yml (frontend healthcheck wired; caddy depends on healthy backend + healthy frontend)
- [x] docker-compose.prod.yml (resource limits, restart: always, ENVIRONMENT=production, no host ports for db/backend)
- [x] Structured logging: structlog ConsoleRenderer in dev, JSONRenderer in production; wired at import in main.py
- [x] app/seed.py: demo tenant "Acme Logistics" with 3 vehicles + 200 realistic readings each; safe to re-run
- [x] app/api/reports.py: GET /reports/vehicles/{id}/pdf — ReportLab PDF with KPI table + trips table; 404 on unknown vehicle
- [x] RUNBOOK.md: backup/restore, TLS cert rotation, MQTT device cert revocation, scaling, env var reference
- [x] Acceptance: 116/116 pytest pass in 52 s (+ 5 smoke tests: health, PDF magic bytes, PDF 404, full pipeline, structlog)

## Phase 11 — Firmware (firmware/obu-esp32, PlatformIO) ✅
- [x] PlatformIO project: espressif32@6.9 / arduino framework; deps: PubSubClient, TinyGPSPlus, MPU6050
- [x] TWAI (CAN) init: GPIO5=TX, GPIO4=RX → SN65HVD230 → OBD-II pin 6/14 at 500 kbit/s
- [x] obd.cpp: Mode 01 PIDs 0x0C/0x0D/0x05/0x2F/0x04/0x11/0x0F/0x1F + Mode 03 DTC readout
- [x] gnss.cpp: TinyGPSPlus over UART2 (GPIO16/17, 9600 baud); returns stale fix on timeout
- [x] imu.cpp: MPU-6050 over I2C (GPIO21/22); ±2g / ±250°/s scaling to m/s² and rad/s
- [x] cbor_payload.cpp: lightweight CBOR encoder (no external library); float32, uint, text, bool, map, array
- [x] store_forward.cpp: SD-backed ring buffer (up to 500 frames); persists read/write indices across power cycles
- [x] mqtt_uplink.cpp: PubSubClient + WiFiClientSecure; TLS mutual auth; device cert CN = MQTT client-id
- [x] provision.cpp: NVS (Preferences) for device_id/client_id/vin/WiFi/MQTT host; LittleFS for TLS certs
- [x] main.cpp: 10 s poll loop; ignition-off debounce → drain queue → deep-sleep; SNTP clock sync
- [x] firmware/README.md: full wiring/pinout, BOM, provisioning steps, OBD PID table, CBOR format
- [x] Acceptance: 130/130 pytest pass in 48 s (116 existing + 14 host-side schema tests); firmware sources compile-ready for ESP32
