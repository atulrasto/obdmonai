# CLAUDE.md — obdmonai project invariants

These invariants are non-negotiable for the whole project.

- **Schema only via Alembic.** Never call `Base.metadata.create_all()`. Every schema change is an Alembic migration. Migrations are **idempotent** (use `IF NOT EXISTS` / guarded DDL) and have working `downgrade()`.
- **Least-privilege DB.** The application connects as a **non-superuser** role. Tenant isolation is enforced by **PostgreSQL Row-Level Security (RLS)**, not application code alone.
- **Tenant key everywhere.** `client_id` is **denormalised onto every tenant-scoped table** and is the RLS key. Every query path sets the tenant context.
- **Telemetry is append-only.** The telemetry hypertable is insert-only. Never update or delete rows in normal operation. Store the **device event timestamp** (when the reading happened on the vehicle), never the cloud arrival time.
- **Tier A vs Tier B separation.** Tier A (deterministic source of truth: capture, store, threshold/rule alerts) must **never import from or depend on** Tier B (ML / LLM augmentation). Tier B reads from Tier A's data; never the reverse. The dependency arrow points one way only.
- **TLS everywhere.** MQTT on 8883 (TLS), HTTP behind Caddy with auto-HTTPS. No plaintext transport in any compose file meant for deployment.
- **Tests gate progress.** A phase is not "done" until its acceptance tests pass. Maintain a growing pytest suite; never let previously passing tests regress.
- **No secrets in git.** Keys, tokens, passwords, certs → `.env` / mounted secrets only. `.env.example` documents every variable with safe placeholder values.
