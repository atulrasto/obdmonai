"""Analytics SECURITY DEFINER functions (trips, KPIs, fleet rollup).

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-30

Functions
---------
All functions are SECURITY DEFINER and accept explicit (vehicle_id, client_id)
so they bypass RLS without needing the GUC.  The API layer validates ownership
via JWT before calling them.

analytics_vehicle_kpis   — per-vehicle distance / time / speed / alert KPIs
analytics_list_trips     — segment telemetry into trips by gap/ign detection
analytics_trip_detail    — raw telemetry points for a given time window
analytics_fleet_rollup   — per-vehicle KPI rows for an entire client
"""
from __future__ import annotations

import os
from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    app_user = os.environ.get("POSTGRES_USER", "obdmonai_app")

    # ── analytics_vehicle_kpis ───────────────────────────────────────────────
    op.execute("""
        CREATE FUNCTION analytics_vehicle_kpis(
            p_vehicle_id  UUID,
            p_client_id   UUID,
            p_from        TIMESTAMPTZ DEFAULT now() - INTERVAL '30 days',
            p_to          TIMESTAMPTZ DEFAULT now()
        )
        RETURNS TABLE(
            reading_count       BIGINT,
            drive_time_sec      DOUBLE PRECISION,
            idle_time_sec       DOUBLE PRECISION,
            distance_km         DOUBLE PRECISION,
            avg_speed           DOUBLE PRECISION,
            max_speed           DOUBLE PRECISION,
            harsh_braking_count BIGINT,
            overspeed_count     BIGINT
        )
        LANGUAGE SQL SECURITY DEFINER STABLE AS $$
            WITH lagged AS (
                SELECT
                    ign,
                    obd_speed,
                    EXTRACT(EPOCH FROM (
                        time - LAG(time) OVER (ORDER BY time)
                    )) AS gap_sec
                FROM telemetry
                WHERE vehicle_id = p_vehicle_id
                  AND client_id  = p_client_id
                  AND time BETWEEN p_from AND p_to
            ),
            kpis AS (
                SELECT
                    COUNT(*)::BIGINT                                                  AS reading_count,
                    COALESCE(SUM(CASE
                        WHEN ign AND COALESCE(obd_speed, 0) > 1
                             AND gap_sec IS NOT NULL AND gap_sec <= 300
                        THEN gap_sec ELSE 0 END), 0)                                 AS drive_time_sec,
                    COALESCE(SUM(CASE
                        WHEN ign AND COALESCE(obd_speed, 0) <= 1
                             AND gap_sec IS NOT NULL AND gap_sec <= 300
                        THEN gap_sec ELSE 0 END), 0)                                 AS idle_time_sec,
                    COALESCE(SUM(CASE
                        WHEN gap_sec IS NOT NULL AND gap_sec <= 300
                        THEN COALESCE(obd_speed, 0) * gap_sec / 3600.0
                        ELSE 0 END), 0)                                              AS distance_km,
                    AVG(obd_speed)                                                   AS avg_speed,
                    MAX(obd_speed)                                                   AS max_speed
                FROM lagged
            ),
            alert_counts AS (
                SELECT
                    COUNT(*) FILTER (WHERE rule = 'harsh_braking') AS harsh_braking_count,
                    COUNT(*) FILTER (WHERE rule = 'overspeed')     AS overspeed_count
                FROM alerts
                WHERE vehicle_id = p_vehicle_id
                  AND client_id  = p_client_id
                  AND fired_at BETWEEN p_from AND p_to
                  AND state IN ('active', 'cleared')
            )
            SELECT
                k.reading_count,
                k.drive_time_sec,
                k.idle_time_sec,
                k.distance_km,
                k.avg_speed,
                k.max_speed,
                a.harsh_braking_count,
                a.overspeed_count
            FROM kpis k, alert_counts a;
        $$;
    """)
    op.execute(
        f'GRANT EXECUTE ON FUNCTION '
        f'analytics_vehicle_kpis(UUID, UUID, TIMESTAMPTZ, TIMESTAMPTZ) TO "{app_user}";'
    )

    # ── analytics_list_trips ─────────────────────────────────────────────────
    # Trip detection: gap-island technique.
    # A new trip starts when:
    #   - ign transitions from false → true, or
    #   - the time gap between consecutive readings exceeds 5 minutes, or
    #   - it is the very first reading in the window.
    op.execute("""
        CREATE FUNCTION analytics_list_trips(
            p_vehicle_id  UUID,
            p_client_id   UUID,
            p_from        TIMESTAMPTZ DEFAULT now() - INTERVAL '30 days',
            p_to          TIMESTAMPTZ DEFAULT now()
        )
        RETURNS TABLE(
            trip_num      BIGINT,
            start_ts      TIMESTAMPTZ,
            end_ts        TIMESTAMPTZ,
            duration_sec  DOUBLE PRECISION,
            distance_km   DOUBLE PRECISION,
            avg_speed     DOUBLE PRECISION,
            max_speed     DOUBLE PRECISION,
            reading_count BIGINT
        )
        LANGUAGE SQL SECURITY DEFINER STABLE AS $$
            WITH base AS (
                SELECT
                    time,
                    ign,
                    obd_speed,
                    EXTRACT(EPOCH FROM (
                        time - LAG(time) OVER (ORDER BY time)
                    ))                                                        AS gap_sec,
                    COALESCE(NOT LAG(ign) OVER (ORDER BY time), TRUE)        AS ign_just_on
                FROM telemetry
                WHERE vehicle_id = p_vehicle_id
                  AND client_id  = p_client_id
                  AND time BETWEEN p_from AND p_to
            ),
            marked AS (
                SELECT *,
                    SUM(CASE
                        WHEN ign AND (ign_just_on OR gap_sec > 300 OR gap_sec IS NULL) THEN 1
                        ELSE 0
                    END) OVER (ORDER BY time) AS grp
                FROM base
            ),
            aggregated AS (
                SELECT
                    grp,
                    MIN(time)                                                         AS start_ts,
                    MAX(time)                                                         AS end_ts,
                    EXTRACT(EPOCH FROM (MAX(time) - MIN(time)))                      AS duration_sec,
                    COALESCE(SUM(CASE
                        WHEN gap_sec IS NOT NULL AND gap_sec <= 300
                        THEN COALESCE(obd_speed, 0) * gap_sec / 3600.0
                        ELSE 0 END), 0)                                              AS distance_km,
                    AVG(CASE WHEN obd_speed IS NOT NULL THEN obd_speed END)          AS avg_speed,
                    MAX(obd_speed)                                                   AS max_speed,
                    COUNT(*)::BIGINT                                                 AS reading_count
                FROM marked
                WHERE ign = true
                GROUP BY grp
                HAVING COUNT(*) > 1
            )
            SELECT
                ROW_NUMBER() OVER (ORDER BY start_ts)::BIGINT AS trip_num,
                start_ts,
                end_ts,
                duration_sec,
                distance_km,
                avg_speed,
                max_speed,
                reading_count
            FROM aggregated
            ORDER BY start_ts;
        $$;
    """)
    op.execute(
        f'GRANT EXECUTE ON FUNCTION '
        f'analytics_list_trips(UUID, UUID, TIMESTAMPTZ, TIMESTAMPTZ) TO "{app_user}";'
    )

    # ── analytics_trip_detail ────────────────────────────────────────────────
    op.execute("""
        CREATE FUNCTION analytics_trip_detail(
            p_vehicle_id  UUID,
            p_client_id   UUID,
            p_from        TIMESTAMPTZ,
            p_to          TIMESTAMPTZ
        )
        RETURNS TABLE(
            ts             TIMESTAMPTZ,
            obd_speed      DOUBLE PRECISION,
            obd_rpm        DOUBLE PRECISION,
            obd_coolant    DOUBLE PRECISION,
            obd_fuel_level DOUBLE PRECISION,
            gps_lat        DOUBLE PRECISION,
            gps_lon        DOUBLE PRECISION,
            imu_ax         DOUBLE PRECISION,
            dtc            TEXT[],
            ign            BOOL
        )
        LANGUAGE SQL SECURITY DEFINER STABLE AS $$
            SELECT
                time AS ts, obd_speed, obd_rpm, obd_coolant, obd_fuel_level,
                gps_lat, gps_lon, imu_ax, dtc, ign
            FROM telemetry
            WHERE vehicle_id = p_vehicle_id
              AND client_id  = p_client_id
              AND time BETWEEN p_from AND p_to
            ORDER BY time;
        $$;
    """)
    op.execute(
        f'GRANT EXECUTE ON FUNCTION '
        f'analytics_trip_detail(UUID, UUID, TIMESTAMPTZ, TIMESTAMPTZ) TO "{app_user}";'
    )

    # ── analytics_fleet_rollup ────────────────────────────────────────────────
    # Uses the telemetry_1m continuous aggregate for efficient fleet-wide summaries.
    # The CAGG buckets aggregate avg/max speed and idle counts per minute per vehicle.
    # Distance ≈ avg_speed * (1 minute) summed over all buckets with readings.
    op.execute("""
        CREATE FUNCTION analytics_fleet_rollup(
            p_client_id   UUID,
            p_from        TIMESTAMPTZ DEFAULT now() - INTERVAL '30 days',
            p_to          TIMESTAMPTZ DEFAULT now()
        )
        RETURNS TABLE(
            vehicle_id      UUID,
            reading_count   BIGINT,
            distance_km     DOUBLE PRECISION,
            avg_speed       DOUBLE PRECISION,
            max_speed       DOUBLE PRECISION,
            drive_min       BIGINT,
            idle_min        BIGINT
        )
        LANGUAGE SQL SECURITY DEFINER STABLE AS $$
            SELECT
                vehicle_id,
                SUM(reading_count)::BIGINT                           AS reading_count,
                COALESCE(SUM(avg_speed / 60.0), 0)                  AS distance_km,
                AVG(avg_speed)                                       AS avg_speed,
                MAX(max_speed)                                       AS max_speed,
                SUM(reading_count - idle_count)::BIGINT             AS drive_min,
                SUM(idle_count)::BIGINT                             AS idle_min
            FROM telemetry_1m
            WHERE client_id = p_client_id
              AND bucket BETWEEN p_from AND p_to
            GROUP BY vehicle_id
            ORDER BY vehicle_id;
        $$;
    """)
    op.execute(
        f'GRANT EXECUTE ON FUNCTION '
        f'analytics_fleet_rollup(UUID, TIMESTAMPTZ, TIMESTAMPTZ) TO "{app_user}";'
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS analytics_fleet_rollup(UUID, TIMESTAMPTZ, TIMESTAMPTZ);")
    op.execute("DROP FUNCTION IF EXISTS analytics_trip_detail(UUID, UUID, TIMESTAMPTZ, TIMESTAMPTZ);")
    op.execute("DROP FUNCTION IF EXISTS analytics_list_trips(UUID, UUID, TIMESTAMPTZ, TIMESTAMPTZ);")
    op.execute("DROP FUNCTION IF EXISTS analytics_vehicle_kpis(UUID, UUID, TIMESTAMPTZ, TIMESTAMPTZ);")
