from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Float, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String

from .base import Base


class Telemetry(Base):
    """Append-only hypertable for OBD-II / CAN telemetry.

    Partitioned by `time` (device event timestamp, never cloud arrival time).
    Dedup key: (device_id, seq) — enforced via unique index + ON CONFLICT DO NOTHING.
    RLS key: client_id.

    PRIMARY KEY is (time, device_id, seq) to satisfy both TimescaleDB's requirement
    that the partition key is part of any unique constraint and the logical dedup key.
    """

    __tablename__ = "telemetry"

    # Partitioning / composite PK
    time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, primary_key=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, primary_key=True
    )
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, primary_key=True)

    # Tenant + routing
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # GPS
    gps_lat: Mapped[float | None] = mapped_column(Float)
    gps_lon: Mapped[float | None] = mapped_column(Float)
    gps_alt: Mapped[float | None] = mapped_column(Float)
    gps_hdg: Mapped[float | None] = mapped_column(Float)
    gps_spd: Mapped[float | None] = mapped_column(Float)

    # OBD-II PIDs
    obd_rpm: Mapped[float | None] = mapped_column(Float)
    obd_speed: Mapped[float | None] = mapped_column(Float)
    obd_coolant: Mapped[float | None] = mapped_column(Float)
    obd_load: Mapped[float | None] = mapped_column(Float)
    obd_throttle: Mapped[float | None] = mapped_column(Float)
    obd_intake_temp: Mapped[float | None] = mapped_column(Float)
    obd_fuel_level: Mapped[float | None] = mapped_column(Float)
    obd_run_time: Mapped[float | None] = mapped_column(Float)

    # IMU (accelerometer + gyroscope)
    imu_ax: Mapped[float | None] = mapped_column(Float)
    imu_ay: Mapped[float | None] = mapped_column(Float)
    imu_az: Mapped[float | None] = mapped_column(Float)
    imu_gx: Mapped[float | None] = mapped_column(Float)
    imu_gy: Mapped[float | None] = mapped_column(Float)
    imu_gz: Mapped[float | None] = mapped_column(Float)

    # DTC + ignition
    dtc: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    ign: Mapped[bool | None] = mapped_column(Boolean)

    # Cloud arrival time (for latency monitoring, never used as event time)
    received_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
