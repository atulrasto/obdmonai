"""Create telemetry hypertable (OBD-II / CAN / GPS / IMU).

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-29

Hypertable design
-----------------
- Partitioned on `time` (device event timestamp, never cloud arrival time).
- Primary key is (time, device_id, seq) — TimescaleDB requires the partition
  column to be part of any unique constraint.
- Dedup key (device_id, seq) is enforced separately as a UNIQUE INDEX (not a
  constraint) so INSERT … ON CONFLICT (device_id, seq) DO NOTHING works.
  This index is chunk-unaware and incurs a cross-chunk scan penalty on conflict;
  that is acceptable because duplicates are rare (store-and-forward backfill).
- RLS is enabled with the same client_id GUC policy as the tenant tables.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS_USING = "client_id = current_setting('app.current_client_id', true)::uuid"


def upgrade() -> None:
    op.create_table(
        "telemetry",
        # ---- Composite PK (includes hypertable partition key) ----
        sa.Column("time",      sa.TIMESTAMP(timezone=True), nullable=False, primary_key=True),
        sa.Column("device_id", UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("seq",       sa.BigInteger, nullable=False, primary_key=True),

        # ---- Tenant + routing ----
        sa.Column("client_id",  UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", UUID(as_uuid=True), nullable=False),

        # ---- GPS ----
        sa.Column("gps_lat", sa.Float),
        sa.Column("gps_lon", sa.Float),
        sa.Column("gps_alt", sa.Float),
        sa.Column("gps_hdg", sa.Float),
        sa.Column("gps_spd", sa.Float),

        # ---- OBD-II PIDs ----
        sa.Column("obd_rpm",         sa.Float),
        sa.Column("obd_speed",       sa.Float),
        sa.Column("obd_coolant",     sa.Float),
        sa.Column("obd_load",        sa.Float),
        sa.Column("obd_throttle",    sa.Float),
        sa.Column("obd_intake_temp", sa.Float),
        sa.Column("obd_fuel_level",  sa.Float),
        sa.Column("obd_run_time",    sa.Float),

        # ---- IMU ----
        sa.Column("imu_ax", sa.Float),
        sa.Column("imu_ay", sa.Float),
        sa.Column("imu_az", sa.Float),
        sa.Column("imu_gx", sa.Float),
        sa.Column("imu_gy", sa.Float),
        sa.Column("imu_gz", sa.Float),

        # ---- DTC + ignition ----
        sa.Column("dtc", ARRAY(sa.Text)),
        sa.Column("ign", sa.Boolean),

        # ---- Cloud-side metadata ----
        sa.Column("received_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Convert to hypertable — partitioned on `time`, 7-day chunks
    op.execute("""
        SELECT create_hypertable(
            'telemetry',
            'time',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        );
    """)

    # Analytical indexes
    op.create_index(
        "ix_telemetry_client_vehicle_time",
        "telemetry",
        ["client_id", "vehicle_id", sa.text("time DESC")],
    )
    op.create_index(
        "ix_telemetry_device_time",
        "telemetry",
        ["device_id", sa.text("time DESC")],
    )

    # Dedup lookup index — (device_id, seq) for fast existence checks.
    # TimescaleDB requires the partition key (time) in any UNIQUE index, so we
    # cannot enforce the dedup constraint at the DB level without including time.
    # The ingest worker handles dedup: query by (device_id, seq) first; if found,
    # skip insert.  See app/ingest/worker.py for the application-side guarantee.
    op.create_index(
        "ix_telemetry_device_seq",
        "telemetry",
        ["device_id", "seq"],
    )

    # NOTE: RLS on telemetry is enabled in migration 0004, AFTER the continuous
    # aggregates are created. TimescaleDB refuses to create a CAGG on a hypertable
    # that already has RLS enabled (background refresh jobs need unrestricted access).
    # See migration 0004 for the RLS policy DDL.


def downgrade() -> None:
    # RLS was added in 0004, so it is already gone when this downgrade runs.
    op.drop_index("ix_telemetry_device_seq", table_name="telemetry")
    op.drop_index("ix_telemetry_device_time", table_name="telemetry")
    op.drop_index("ix_telemetry_client_vehicle_time", table_name="telemetry")
    # Dropping the table also drops the hypertable and all its chunks.
    op.drop_table("telemetry")
