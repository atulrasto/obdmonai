"""SECURITY DEFINER helper functions for the MQTT ingest worker.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-29

Changes
-------
1. ``ingest_get_device(device_id)``
   Returns (client_id, vehicle_id, vin, is_active) for a device_id, bypassing
   RLS so the ingest worker (app role, no GUC) can validate device registration.

2. ``ingest_record_telemetry(...)``
   Validates dedupe on (device_id, seq) and inserts one row into the telemetry
   hypertable, all in a single atomic operation. Returns TRUE if inserted, FALSE
   if the (device_id, seq) already exists (duplicate suppressed).

3. ``ingest_telemetry_exists(device_id, seq)``
   Test helper: checks whether a specific (device_id, seq) is in the hypertable
   without needing the client_id GUC.
"""
from __future__ import annotations

import os
from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    app_user = os.environ.get("POSTGRES_USER", "obdmonai_app")

    # ── Device lookup ──────────────────────────────────────────────────────────
    op.execute("""
        CREATE FUNCTION ingest_get_device(p_device_id UUID)
        RETURNS TABLE(
            client_id   UUID,
            vehicle_id  UUID,
            vin         TEXT,
            is_active   BOOL
        )
        LANGUAGE SQL SECURITY DEFINER STABLE
        AS $$
            SELECT d.client_id, d.vehicle_id, v.vin, d.is_active
            FROM   devices  d
            JOIN   vehicles v ON v.id = d.vehicle_id
            WHERE  d.id = p_device_id
            LIMIT  1;
        $$;
    """)
    op.execute(f'GRANT EXECUTE ON FUNCTION ingest_get_device(UUID) TO "{app_user}";')

    # ── Atomic dedupe + insert ─────────────────────────────────────────────────
    op.execute("""
        CREATE FUNCTION ingest_record_telemetry(
            p_time          TIMESTAMPTZ,
            p_client_id     UUID,
            p_vehicle_id    UUID,
            p_device_id     UUID,
            p_seq           BIGINT,
            p_gps_lat       DOUBLE PRECISION,
            p_gps_lon       DOUBLE PRECISION,
            p_gps_alt       DOUBLE PRECISION,
            p_gps_hdg       DOUBLE PRECISION,
            p_gps_spd       DOUBLE PRECISION,
            p_obd_rpm       DOUBLE PRECISION,
            p_obd_speed     DOUBLE PRECISION,
            p_obd_coolant   DOUBLE PRECISION,
            p_obd_load      DOUBLE PRECISION,
            p_obd_throttle  DOUBLE PRECISION,
            p_obd_intake_temp DOUBLE PRECISION,
            p_obd_fuel_level  DOUBLE PRECISION,
            p_obd_run_time    DOUBLE PRECISION,
            p_imu_ax        DOUBLE PRECISION,
            p_imu_ay        DOUBLE PRECISION,
            p_imu_az        DOUBLE PRECISION,
            p_imu_gx        DOUBLE PRECISION,
            p_imu_gy        DOUBLE PRECISION,
            p_imu_gz        DOUBLE PRECISION,
            p_dtc           TEXT[],
            p_ign           BOOL
        )
        RETURNS BOOL
        LANGUAGE PLPGSQL SECURITY DEFINER VOLATILE
        AS $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM telemetry
                WHERE device_id = p_device_id AND seq = p_seq
            ) THEN
                RETURN FALSE;
            END IF;

            INSERT INTO telemetry (
                time, client_id, vehicle_id, device_id, seq,
                gps_lat, gps_lon, gps_alt, gps_hdg, gps_spd,
                obd_rpm, obd_speed, obd_coolant, obd_load, obd_throttle,
                obd_intake_temp, obd_fuel_level, obd_run_time,
                imu_ax, imu_ay, imu_az, imu_gx, imu_gy, imu_gz,
                dtc, ign
            ) VALUES (
                p_time, p_client_id, p_vehicle_id, p_device_id, p_seq,
                p_gps_lat, p_gps_lon, p_gps_alt, p_gps_hdg, p_gps_spd,
                p_obd_rpm, p_obd_speed, p_obd_coolant, p_obd_load, p_obd_throttle,
                p_obd_intake_temp, p_obd_fuel_level, p_obd_run_time,
                p_imu_ax, p_imu_ay, p_imu_az, p_imu_gx, p_imu_gy, p_imu_gz,
                p_dtc, p_ign
            );
            RETURN TRUE;
        END;
        $$;
    """)
    op.execute(f"""
        GRANT EXECUTE ON FUNCTION ingest_record_telemetry(
            TIMESTAMPTZ, UUID, UUID, UUID, BIGINT,
            DOUBLE PRECISION, DOUBLE PRECISION, DOUBLE PRECISION,
            DOUBLE PRECISION, DOUBLE PRECISION,
            DOUBLE PRECISION, DOUBLE PRECISION, DOUBLE PRECISION,
            DOUBLE PRECISION, DOUBLE PRECISION, DOUBLE PRECISION,
            DOUBLE PRECISION, DOUBLE PRECISION,
            DOUBLE PRECISION, DOUBLE PRECISION, DOUBLE PRECISION,
            DOUBLE PRECISION, DOUBLE PRECISION, DOUBLE PRECISION,
            TEXT[], BOOL
        ) TO "{app_user}";
    """)

    # ── Test helper: check existence by (device_id, seq) ──────────────────────
    op.execute("""
        CREATE FUNCTION ingest_telemetry_exists(p_device_id UUID, p_seq BIGINT)
        RETURNS BOOL
        LANGUAGE SQL SECURITY DEFINER STABLE
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM telemetry
                WHERE device_id = p_device_id AND seq = p_seq
            );
        $$;
    """)
    op.execute(
        f'GRANT EXECUTE ON FUNCTION ingest_telemetry_exists(UUID, BIGINT) TO "{app_user}";'
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS ingest_telemetry_exists(UUID, BIGINT);")
    op.execute("""
        DROP FUNCTION IF EXISTS ingest_record_telemetry(
            TIMESTAMPTZ, UUID, UUID, UUID, BIGINT,
            DOUBLE PRECISION, DOUBLE PRECISION, DOUBLE PRECISION,
            DOUBLE PRECISION, DOUBLE PRECISION,
            DOUBLE PRECISION, DOUBLE PRECISION, DOUBLE PRECISION,
            DOUBLE PRECISION, DOUBLE PRECISION, DOUBLE PRECISION,
            DOUBLE PRECISION, DOUBLE PRECISION,
            DOUBLE PRECISION, DOUBLE PRECISION, DOUBLE PRECISION,
            DOUBLE PRECISION, DOUBLE PRECISION, DOUBLE PRECISION,
            TEXT[], BOOL
        );
    """)
    op.execute("DROP FUNCTION IF EXISTS ingest_get_device(UUID);")
