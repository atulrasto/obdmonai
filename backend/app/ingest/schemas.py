"""Pydantic schema for the OBD telemetry payload emitted by on-board units."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class GPS(BaseModel):
    lat: float = 0.0
    lon: float = 0.0
    alt: float = 0.0
    hdg: float = 0.0
    spd: float = 0.0


class OBD(BaseModel):
    rpm: float = 0.0
    speed: float = 0.0
    coolant: float = 0.0
    load: float = 0.0
    throttle: float = 0.0
    intake_temp: float = 0.0
    fuel_level: float = 0.0
    run_time: float = 0.0


class IMU(BaseModel):
    ax: float = 0.0
    ay: float = 0.0
    az: float = 0.0
    gx: float = 0.0
    gy: float = 0.0
    gz: float = 0.0


class TelemetryPayload(BaseModel):
    device_id: UUID
    ts: datetime
    seq: int = Field(..., ge=0)
    gps: GPS = Field(default_factory=GPS)
    obd: OBD = Field(default_factory=OBD)
    imu: IMU = Field(default_factory=IMU)
    dtc: list[str] = Field(default_factory=list)
    ign: bool = True

    @field_validator("ts", mode="before")
    @classmethod
    def _parse_ts(cls, v: object) -> datetime:
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v, tz=timezone.utc)
        return v  # type: ignore[return-value]

    @field_validator("ts")
    @classmethod
    def _ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)
