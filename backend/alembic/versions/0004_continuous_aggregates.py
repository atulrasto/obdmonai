"""Create continuous aggregates telemetry_1m and telemetry_1h, plus policies.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-29

Aggregates
----------
telemetry_1m — 1-minute buckets: avg/min/max speed, rpm, coolant; idle count.
telemetry_1h — 1-hour buckets: same metrics, plus reading count for SLA.

Refresh policies keep the caggs up to date automatically.
Retention policy on the raw hypertable defaults to 90 days.

RLS on telemetry
-----------------
TimescaleDB refuses to create a CAGG on an RLS-enabled hypertable (background
refresh jobs need unrestricted read access). So RLS on telemetry is ENABLED
HERE (after CAGG creation), not in migration 0003.
Tenant isolation invariant is still met: every API query path sets the GUC
`app.current_client_id` before touching telemetry.
"""
from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ 1-minute cagg
    op.execute("""
        CREATE MATERIALIZED VIEW telemetry_1m
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 minute', time)  AS bucket,
            client_id,
            vehicle_id,
            AVG(obd_speed)                 AS avg_speed,
            MIN(obd_speed)                 AS min_speed,
            MAX(obd_speed)                 AS max_speed,
            AVG(obd_rpm)                   AS avg_rpm,
            MIN(obd_rpm)                   AS min_rpm,
            MAX(obd_rpm)                   AS max_rpm,
            AVG(obd_coolant)               AS avg_coolant,
            MIN(obd_coolant)               AS min_coolant,
            MAX(obd_coolant)               AS max_coolant,
            COUNT(*)                       AS reading_count,
            SUM(CASE WHEN ign IS TRUE AND (obd_speed IS NULL OR obd_speed < 1)
                     THEN 1 ELSE 0 END)   AS idle_count
        FROM telemetry
        GROUP BY bucket, client_id, vehicle_id
        WITH NO DATA;
    """)

    op.execute("""
        SELECT add_continuous_aggregate_policy(
            'telemetry_1m',
            start_offset  => INTERVAL '10 minutes',
            end_offset    => INTERVAL '1 minute',
            schedule_interval => INTERVAL '1 minute'
        );
    """)

    # ------------------------------------------------------------------ 1-hour cagg
    op.execute("""
        CREATE MATERIALIZED VIEW telemetry_1h
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 hour', time)    AS bucket,
            client_id,
            vehicle_id,
            AVG(obd_speed)                 AS avg_speed,
            MIN(obd_speed)                 AS min_speed,
            MAX(obd_speed)                 AS max_speed,
            AVG(obd_rpm)                   AS avg_rpm,
            MIN(obd_rpm)                   AS min_rpm,
            MAX(obd_rpm)                   AS max_rpm,
            AVG(obd_coolant)               AS avg_coolant,
            MIN(obd_coolant)               AS min_coolant,
            MAX(obd_coolant)               AS max_coolant,
            COUNT(*)                       AS reading_count,
            SUM(CASE WHEN ign IS TRUE AND (obd_speed IS NULL OR obd_speed < 1)
                     THEN 1 ELSE 0 END)   AS idle_count
        FROM telemetry
        GROUP BY bucket, client_id, vehicle_id
        WITH NO DATA;
    """)

    op.execute("""
        SELECT add_continuous_aggregate_policy(
            'telemetry_1h',
            start_offset  => INTERVAL '3 hours',
            end_offset    => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour'
        );
    """)

    # ------------------------------------------------------------------ retention
    # Raw telemetry retained for 90 days; caggs keep data indefinitely (by default).
    op.execute("""
        SELECT add_retention_policy(
            'telemetry',
            INTERVAL '90 days'
        );
    """)

    # ------------------------------------------------------------------ RLS on telemetry
    # Enable AFTER CAGGs so TimescaleDB background refresh jobs can still read the table.
    _rls = "client_id = current_setting('app.current_client_id', true)::uuid"
    op.execute("ALTER TABLE telemetry ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE telemetry FORCE ROW LEVEL SECURITY;")
    op.execute(f"""
        CREATE POLICY telemetry_tenant_isolation ON telemetry
            USING ({_rls});
    """)
    op.execute(f"""
        CREATE POLICY telemetry_tenant_insert ON telemetry
            FOR INSERT
            WITH CHECK ({_rls});
    """)

    # ------------------------------------------------------------------ grants on CAGGs
    app_user = os.environ.get("POSTGRES_USER", "obdmonai_app")
    op.execute(f'GRANT SELECT ON telemetry_1m TO "{app_user}";')
    op.execute(f'GRANT SELECT ON telemetry_1h TO "{app_user}";')


def downgrade() -> None:
    app_user = os.environ.get("POSTGRES_USER", "obdmonai_app")

    # Remove RLS from telemetry first (before dropping CAGGs)
    op.execute("DROP POLICY IF EXISTS telemetry_tenant_insert ON telemetry;")
    op.execute("DROP POLICY IF EXISTS telemetry_tenant_isolation ON telemetry;")
    op.execute("ALTER TABLE telemetry DISABLE ROW LEVEL SECURITY;")

    op.execute(f'REVOKE SELECT ON telemetry_1m FROM "{app_user}";')
    op.execute(f'REVOKE SELECT ON telemetry_1h FROM "{app_user}";')
    op.execute("SELECT remove_retention_policy('telemetry', if_exists => true);")
    op.execute("SELECT remove_continuous_aggregate_policy('telemetry_1h', if_exists => true);")
    op.execute("SELECT remove_continuous_aggregate_policy('telemetry_1m', if_exists => true);")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS telemetry_1h;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS telemetry_1m;")
