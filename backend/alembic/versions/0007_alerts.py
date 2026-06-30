"""Tier A alerts and geofences tables with SECURITY DEFINER helpers.

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-30

Changes
-------
1. ``alerts`` hypertable-style table: id, client_id, vehicle_id, device_id,
   rule, state ('watching'/'active'/'cleared'), severity, detail (JSONB),
   fired_at, cleared_at.  RLS on client_id.

2. ``geofences`` table: per-tenant circular geofence zones.  RLS on client_id.

3. SECURITY DEFINER functions for the tier-A rules engine (app role, no GUC):
   - tier_a_get_alert_states(device_id)     → watching + active alerts
   - tier_a_watch_alert(...)                → create a 'watching' alert
   - tier_a_fire_alert(...)                 → promote watching→active or insert new
   - tier_a_clear_alert(alert_id, ts)       → mark alert cleared
   - tier_a_get_geofences(client_id)        → active geofences for client
   - tier_a_get_prev_telemetry(device_id, seq) → last row before current seq
   - tier_a_alert_count(device_id, rule, state) → test helper
"""
from __future__ import annotations

import os
from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    app_user = os.environ.get("POSTGRES_USER", "obdmonai_app")

    # ── alerts ────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE alerts (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            client_id   UUID        NOT NULL,
            vehicle_id  UUID        NOT NULL,
            device_id   UUID        NOT NULL,
            rule        TEXT        NOT NULL,
            state       TEXT        NOT NULL
                        CHECK (state IN ('watching', 'active', 'cleared')),
            severity    TEXT        NOT NULL DEFAULT 'warning',
            detail      JSONB       NOT NULL DEFAULT '{}',
            fired_at    TIMESTAMPTZ NOT NULL,
            cleared_at  TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("""
        CREATE INDEX ix_alerts_device_rule
            ON alerts (device_id, rule)
            WHERE state IN ('watching', 'active');
    """)
    op.execute("""
        CREATE INDEX ix_alerts_client_time ON alerts (client_id, fired_at DESC);
    """)
    op.execute("ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY alerts_tenant ON alerts FOR ALL
            USING      (client_id = NULLIF(current_setting('app.current_client_id', true), '')::uuid)
            WITH CHECK (client_id = NULLIF(current_setting('app.current_client_id', true), '')::uuid);
    """)

    # ── geofences ─────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE geofences (
            id          UUID              PRIMARY KEY DEFAULT gen_random_uuid(),
            client_id   UUID              NOT NULL,
            name        TEXT              NOT NULL,
            center_lat  DOUBLE PRECISION  NOT NULL,
            center_lon  DOUBLE PRECISION  NOT NULL,
            radius_m    DOUBLE PRECISION  NOT NULL CHECK (radius_m > 0),
            is_active   BOOL              NOT NULL DEFAULT true,
            created_at  TIMESTAMPTZ       NOT NULL DEFAULT now()
        );
    """)
    op.execute("""
        CREATE INDEX ix_geofences_client
            ON geofences (client_id)
            WHERE is_active = true;
    """)
    op.execute("ALTER TABLE geofences ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY geofences_tenant ON geofences FOR ALL
            USING      (client_id = NULLIF(current_setting('app.current_client_id', true), '')::uuid)
            WITH CHECK (client_id = NULLIF(current_setting('app.current_client_id', true), '')::uuid);
    """)

    # ── tier_a_get_alert_states ───────────────────────────────────────────────
    op.execute("""
        CREATE FUNCTION tier_a_get_alert_states(p_device_id UUID)
        RETURNS TABLE(id UUID, rule TEXT, state TEXT, fired_at TIMESTAMPTZ, detail JSONB)
        LANGUAGE SQL SECURITY DEFINER STABLE AS $$
            SELECT id, rule, state, fired_at, detail
            FROM   alerts
            WHERE  device_id = p_device_id AND state != 'cleared'
            ORDER BY fired_at;
        $$;
    """)
    op.execute(f'GRANT EXECUTE ON FUNCTION tier_a_get_alert_states(UUID) TO "{app_user}";')

    # ── tier_a_watch_alert ────────────────────────────────────────────────────
    op.execute("""
        CREATE FUNCTION tier_a_watch_alert(
            p_device_id  UUID,
            p_vehicle_id UUID,
            p_client_id  UUID,
            p_rule       TEXT,
            p_detail     JSONB,
            p_started_at TIMESTAMPTZ
        )
        RETURNS UUID
        LANGUAGE PLPGSQL SECURITY DEFINER VOLATILE AS $$
        DECLARE v_id UUID;
        BEGIN
            SELECT id INTO v_id FROM alerts
            WHERE  device_id = p_device_id AND rule = p_rule
              AND  state != 'cleared'
            LIMIT 1;

            IF v_id IS NULL THEN
                INSERT INTO alerts
                    (client_id, vehicle_id, device_id, rule, state, severity, detail, fired_at)
                VALUES
                    (p_client_id, p_vehicle_id, p_device_id, p_rule,
                     'watching', 'info', p_detail, p_started_at)
                RETURNING id INTO v_id;
            END IF;
            RETURN v_id;
        END;
        $$;
    """)
    op.execute(
        f'GRANT EXECUTE ON FUNCTION '
        f'tier_a_watch_alert(UUID, UUID, UUID, TEXT, JSONB, TIMESTAMPTZ) TO "{app_user}";'
    )

    # ── tier_a_fire_alert ─────────────────────────────────────────────────────
    op.execute("""
        CREATE FUNCTION tier_a_fire_alert(
            p_device_id  UUID,
            p_vehicle_id UUID,
            p_client_id  UUID,
            p_rule       TEXT,
            p_severity   TEXT,
            p_detail     JSONB,
            p_fired_at   TIMESTAMPTZ
        )
        RETURNS UUID
        LANGUAGE PLPGSQL SECURITY DEFINER VOLATILE AS $$
        DECLARE v_id UUID;
        BEGIN
            -- Promote watching → active
            UPDATE alerts
            SET    state = 'active', severity = p_severity, detail = p_detail
            WHERE  device_id = p_device_id AND rule = p_rule AND state = 'watching'
            RETURNING id INTO v_id;

            IF v_id IS NULL THEN
                -- No watching; check for already-active (idempotent)
                SELECT id INTO v_id FROM alerts
                WHERE  device_id = p_device_id AND rule = p_rule AND state = 'active'
                LIMIT 1;

                IF v_id IS NULL THEN
                    INSERT INTO alerts
                        (client_id, vehicle_id, device_id, rule, state, severity, detail, fired_at)
                    VALUES
                        (p_client_id, p_vehicle_id, p_device_id, p_rule,
                         'active', p_severity, p_detail, p_fired_at)
                    RETURNING id INTO v_id;
                END IF;
            END IF;
            RETURN v_id;
        END;
        $$;
    """)
    op.execute(
        f'GRANT EXECUTE ON FUNCTION '
        f'tier_a_fire_alert(UUID, UUID, UUID, TEXT, TEXT, JSONB, TIMESTAMPTZ) TO "{app_user}";'
    )

    # ── tier_a_clear_alert ────────────────────────────────────────────────────
    op.execute("""
        CREATE FUNCTION tier_a_clear_alert(p_alert_id UUID, p_cleared_at TIMESTAMPTZ)
        RETURNS VOID
        LANGUAGE SQL SECURITY DEFINER VOLATILE AS $$
            UPDATE alerts
            SET    state = 'cleared', cleared_at = p_cleared_at
            WHERE  id = p_alert_id;
        $$;
    """)
    op.execute(
        f'GRANT EXECUTE ON FUNCTION tier_a_clear_alert(UUID, TIMESTAMPTZ) TO "{app_user}";'
    )

    # ── tier_a_get_geofences ──────────────────────────────────────────────────
    op.execute("""
        CREATE FUNCTION tier_a_get_geofences(p_client_id UUID)
        RETURNS TABLE(
            id          UUID,
            name        TEXT,
            center_lat  DOUBLE PRECISION,
            center_lon  DOUBLE PRECISION,
            radius_m    DOUBLE PRECISION
        )
        LANGUAGE SQL SECURITY DEFINER STABLE AS $$
            SELECT id, name, center_lat, center_lon, radius_m
            FROM   geofences
            WHERE  client_id = p_client_id AND is_active = true;
        $$;
    """)
    op.execute(f'GRANT EXECUTE ON FUNCTION tier_a_get_geofences(UUID) TO "{app_user}";')

    # ── tier_a_get_prev_telemetry ─────────────────────────────────────────────
    op.execute("""
        CREATE FUNCTION tier_a_get_prev_telemetry(p_device_id UUID, p_current_seq BIGINT)
        RETURNS TABLE(
            seq           BIGINT,
            ts            TIMESTAMPTZ,
            obd_speed     DOUBLE PRECISION,
            obd_coolant   DOUBLE PRECISION,
            obd_fuel_level DOUBLE PRECISION,
            imu_ax        DOUBLE PRECISION,
            gps_lat       DOUBLE PRECISION,
            gps_lon       DOUBLE PRECISION,
            dtc           TEXT[],
            ign           BOOL
        )
        LANGUAGE SQL SECURITY DEFINER STABLE AS $$
            SELECT seq, time AS ts, obd_speed, obd_coolant, obd_fuel_level,
                   imu_ax, gps_lat, gps_lon, dtc, ign
            FROM   telemetry
            WHERE  device_id = p_device_id AND seq < p_current_seq
            ORDER BY seq DESC
            LIMIT 1;
        $$;
    """)
    op.execute(
        f'GRANT EXECUTE ON FUNCTION tier_a_get_prev_telemetry(UUID, BIGINT) TO "{app_user}";'
    )

    # ── tier_a_alert_count (test helper) ─────────────────────────────────────
    op.execute("""
        CREATE FUNCTION tier_a_alert_count(p_device_id UUID, p_rule TEXT, p_state TEXT)
        RETURNS BIGINT
        LANGUAGE SQL SECURITY DEFINER STABLE AS $$
            SELECT COUNT(*)
            FROM   alerts
            WHERE  device_id = p_device_id AND rule = p_rule AND state = p_state;
        $$;
    """)
    op.execute(
        f'GRANT EXECUTE ON FUNCTION tier_a_alert_count(UUID, TEXT, TEXT) TO "{app_user}";'
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS tier_a_alert_count(UUID, TEXT, TEXT);")
    op.execute("DROP FUNCTION IF EXISTS tier_a_get_prev_telemetry(UUID, BIGINT);")
    op.execute("DROP FUNCTION IF EXISTS tier_a_get_geofences(UUID);")
    op.execute("DROP FUNCTION IF EXISTS tier_a_clear_alert(UUID, TIMESTAMPTZ);")
    op.execute(
        "DROP FUNCTION IF EXISTS tier_a_fire_alert(UUID, UUID, UUID, TEXT, TEXT, JSONB, TIMESTAMPTZ);"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS tier_a_watch_alert(UUID, UUID, UUID, TEXT, JSONB, TIMESTAMPTZ);"
    )
    op.execute("DROP FUNCTION IF EXISTS tier_a_get_alert_states(UUID);")
    op.execute("DROP TABLE IF EXISTS geofences;")
    op.execute("DROP TABLE IF EXISTS alerts;")
