from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.security.deps import get_tenant_db, require_role
from app.security.jwt import TokenData

router = APIRouter()

_30D_AGO = datetime.now(tz=timezone.utc) - timedelta(days=30)


# ── Pydantic response schemas ─────────────────────────────────────────────────

class VehicleKPIRead(BaseModel):
    vehicle_id: uuid.UUID
    reading_count: int
    drive_time_sec: float
    idle_time_sec: float
    distance_km: float
    avg_speed: float | None
    max_speed: float | None
    harsh_braking_count: int
    overspeed_count: int


class TripRead(BaseModel):
    trip_num: int
    start_ts: datetime
    end_ts: datetime
    duration_sec: float
    distance_km: float
    avg_speed: float | None
    max_speed: float | None
    reading_count: int


class TripPointRead(BaseModel):
    ts: datetime
    obd_speed: float | None
    obd_rpm: float | None
    obd_coolant: float | None
    obd_fuel_level: float | None
    gps_lat: float | None
    gps_lon: float | None
    imu_ax: float | None
    dtc: list[str]
    ign: bool | None


class LatestTelemetryRead(BaseModel):
    ts: datetime
    obd_rpm: float | None
    obd_speed: float | None
    obd_coolant: float | None
    obd_load: float | None
    obd_throttle: float | None
    obd_intake_temp: float | None
    obd_fuel_level: float | None
    obd_run_time: float | None
    gps_lat: float | None
    gps_lon: float | None
    gps_alt: float | None
    gps_hdg: float | None
    gps_spd: float | None
    imu_ax: float | None
    imu_ay: float | None
    imu_az: float | None
    dtc: list[str]
    ign: bool | None


class FleetVehicleRead(BaseModel):
    vehicle_id: uuid.UUID
    reading_count: int
    distance_km: float
    avg_speed: float | None
    max_speed: float | None
    drive_min: int
    idle_min: int


# ── Per-vehicle KPIs ──────────────────────────────────────────────────────────

@router.get("/vehicles/{vehicle_id}/kpis", response_model=VehicleKPIRead)
async def vehicle_kpis(
    vehicle_id: uuid.UUID,
    from_ts: datetime = Query(default=..., alias="from"),
    to_ts: datetime = Query(default=..., alias="to"),
    user: TokenData = Depends(require_role("owner", "fleet_admin", "viewer")),
    db: AsyncSession = Depends(get_tenant_db),
) -> VehicleKPIRead:
    row = (await db.execute(
        text(
            "SELECT * FROM analytics_vehicle_kpis"
            "(:vehicle_id, :client_id, :from_ts, :to_ts)"
        ),
        {
            "vehicle_id": str(vehicle_id),
            "client_id": user.client_id,
            "from_ts": from_ts,
            "to_ts": to_ts,
        },
    )).fetchone()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No telemetry found")

    return VehicleKPIRead(
        vehicle_id=vehicle_id,
        reading_count=row.reading_count or 0,
        drive_time_sec=float(row.drive_time_sec or 0),
        idle_time_sec=float(row.idle_time_sec or 0),
        distance_km=float(row.distance_km or 0),
        avg_speed=float(row.avg_speed) if row.avg_speed is not None else None,
        max_speed=float(row.max_speed) if row.max_speed is not None else None,
        harsh_braking_count=row.harsh_braking_count or 0,
        overspeed_count=row.overspeed_count or 0,
    )


# ── Trips list ────────────────────────────────────────────────────────────────

@router.get("/vehicles/{vehicle_id}/trips", response_model=list[TripRead])
async def list_trips(
    vehicle_id: uuid.UUID,
    from_ts: datetime = Query(default=..., alias="from"),
    to_ts: datetime = Query(default=..., alias="to"),
    user: TokenData = Depends(require_role("owner", "fleet_admin", "viewer")),
    db: AsyncSession = Depends(get_tenant_db),
) -> list[TripRead]:
    rows = (await db.execute(
        text(
            "SELECT * FROM analytics_list_trips"
            "(:vehicle_id, :client_id, :from_ts, :to_ts)"
        ),
        {
            "vehicle_id": str(vehicle_id),
            "client_id": user.client_id,
            "from_ts": from_ts,
            "to_ts": to_ts,
        },
    )).fetchall()

    return [
        TripRead(
            trip_num=int(r.trip_num),
            start_ts=r.start_ts,
            end_ts=r.end_ts,
            duration_sec=float(r.duration_sec or 0),
            distance_km=float(r.distance_km or 0),
            avg_speed=float(r.avg_speed) if r.avg_speed is not None else None,
            max_speed=float(r.max_speed) if r.max_speed is not None else None,
            reading_count=int(r.reading_count),
        )
        for r in rows
    ]


# ── Trip detail (raw telemetry points) ───────────────────────────────────────

@router.get("/vehicles/{vehicle_id}/trips/detail", response_model=list[TripPointRead])
async def trip_detail(
    vehicle_id: uuid.UUID,
    from_ts: datetime = Query(default=..., alias="from"),
    to_ts: datetime = Query(default=..., alias="to"),
    user: TokenData = Depends(require_role("owner", "fleet_admin", "viewer")),
    db: AsyncSession = Depends(get_tenant_db),
) -> list[TripPointRead]:
    rows = (await db.execute(
        text(
            "SELECT * FROM analytics_trip_detail"
            "(:vehicle_id, :client_id, :from_ts, :to_ts)"
        ),
        {
            "vehicle_id": str(vehicle_id),
            "client_id": user.client_id,
            "from_ts": from_ts,
            "to_ts": to_ts,
        },
    )).fetchall()

    return [
        TripPointRead(
            ts=r.ts,
            obd_speed=r.obd_speed,
            obd_rpm=r.obd_rpm,
            obd_coolant=r.obd_coolant,
            obd_fuel_level=r.obd_fuel_level,
            gps_lat=r.gps_lat,
            gps_lon=r.gps_lon,
            imu_ax=r.imu_ax,
            dtc=list(r.dtc or []),
            ign=r.ign,
        )
        for r in rows
    ]


# ── OBD parameter trend (time-bucketed averages) ─────────────────────────────

_ALLOWED_PARAMS = {
    "obd_rpm", "obd_speed", "obd_coolant", "obd_load", "obd_throttle",
    "obd_intake_temp", "obd_fuel_level", "obd_run_time",
}
# bucket_size=None → raw individual rows (no time_bucket aggregation)
_PERIOD_CONFIG: dict[str, tuple[str | None, str]] = {
    "5min":    (None,         "5 minutes"),
    "15min":   (None,         "15 minutes"),
    "30min":   (None,         "30 minutes"),
    "1hour":   ("30 seconds", "1 hour"),
    "daily":   ("5 minutes",  "24 hours"),
    "weekly":  ("1 hour",     "7 days"),
    "monthly": ("6 hours",    "30 days"),
}

def _bucket_for_minutes(minutes: int) -> str | None:
    if minutes <= 30:    return None          # raw — show every reading
    if minutes <= 120:   return "30 seconds"
    if minutes <= 720:   return "5 minutes"
    if minutes <= 2880:  return "15 minutes"
    return "1 hour"


class TrendPoint(BaseModel):
    ts: datetime
    value: float | None


@router.get("/vehicles/{vehicle_id}/trend", response_model=list[TrendPoint])
async def vehicle_trend(
    vehicle_id: uuid.UUID,
    param: str = Query(..., description="OBD column name, e.g. obd_coolant"),
    period: str = Query("daily"),
    minutes: int | None = Query(None, ge=1, le=10080, description="Custom window in minutes (overrides period)"),
    user: TokenData = Depends(require_role("owner", "fleet_admin", "viewer")),
    db: AsyncSession = Depends(get_tenant_db),
) -> list[TrendPoint]:
    if param not in _ALLOWED_PARAMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid param. Allowed: {sorted(_ALLOWED_PARAMS)}",
        )

    if minutes is not None:
        # Custom window — both values derived from a safe integer
        bucket_size = _bucket_for_minutes(minutes)
        interval    = f"{minutes} minutes"
    else:
        if period not in _PERIOD_CONFIG:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid period")
        bucket_size, interval = _PERIOD_CONFIG[period]

    bind = {"vid": str(vehicle_id), "cid": str(user.client_id)}

    if bucket_size is None:
        # Raw mode: every individual reading in the window
        sql = (
            f"SELECT time AS ts, CAST({param} AS DOUBLE PRECISION) AS value"
            " FROM telemetry"
            " WHERE vehicle_id = :vid AND client_id = :cid"
            f" AND time > NOW() - INTERVAL '{interval}'"
            " ORDER BY ts"
        )
    else:
        sql = (
            f"SELECT time_bucket(INTERVAL '{bucket_size}', time) AS ts, AVG({param}) AS value"
            " FROM telemetry"
            " WHERE vehicle_id = :vid AND client_id = :cid"
            f" AND time > NOW() - INTERVAL '{interval}'"
            " GROUP BY ts ORDER BY ts"
        )

    rows = (await db.execute(text(sql), bind)).fetchall()

    return [TrendPoint(ts=r.ts, value=float(r.value) if r.value is not None else None) for r in rows]


# ── Latest single telemetry row (live engine data) ────────────────────────────

@router.get("/vehicles/{vehicle_id}/latest", response_model=LatestTelemetryRead)
async def vehicle_latest(
    vehicle_id: uuid.UUID,
    user: TokenData = Depends(require_role("owner", "fleet_admin", "viewer")),
    db: AsyncSession = Depends(get_tenant_db),
) -> LatestTelemetryRead:
    row = (await db.execute(
        text(
            "SELECT time AS ts,"
            " obd_rpm, obd_speed, obd_coolant, obd_load, obd_throttle,"
            " obd_intake_temp, obd_fuel_level, obd_run_time,"
            " gps_lat, gps_lon, gps_alt, gps_hdg, gps_spd,"
            " imu_ax, imu_ay, imu_az, dtc, ign"
            " FROM telemetry"
            " WHERE vehicle_id = :vid AND client_id = :cid"
            " ORDER BY time DESC LIMIT 1"
        ),
        {"vid": str(vehicle_id), "cid": str(user.client_id)},
    )).fetchone()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No telemetry found")

    m = dict(row._mapping)
    return LatestTelemetryRead(
        ts=m["ts"],
        obd_rpm=m.get("obd_rpm"),
        obd_speed=m.get("obd_speed"),
        obd_coolant=m.get("obd_coolant"),
        obd_load=m.get("obd_load"),
        obd_throttle=m.get("obd_throttle"),
        obd_intake_temp=m.get("obd_intake_temp"),
        obd_fuel_level=m.get("obd_fuel_level"),
        obd_run_time=m.get("obd_run_time"),
        gps_lat=m.get("gps_lat"),
        gps_lon=m.get("gps_lon"),
        gps_alt=m.get("gps_alt"),
        gps_hdg=m.get("gps_hdg"),
        gps_spd=m.get("gps_spd"),
        imu_ax=m.get("imu_ax"),
        imu_ay=m.get("imu_ay"),
        imu_az=m.get("imu_az"),
        dtc=list(m.get("dtc") or []),
        ign=m.get("ign"),
    )


# ── Fleet rollup ──────────────────────────────────────────────────────────────

@router.get("/fleet", response_model=list[FleetVehicleRead])
async def fleet_rollup(
    from_ts: datetime = Query(default=..., alias="from"),
    to_ts: datetime = Query(default=..., alias="to"),
    user: TokenData = Depends(require_role("owner", "fleet_admin", "viewer")),
    db: AsyncSession = Depends(get_tenant_db),
) -> list[FleetVehicleRead]:
    rows = (await db.execute(
        text("SELECT * FROM analytics_fleet_rollup(:client_id, :from_ts, :to_ts)"),
        {
            "client_id": user.client_id,
            "from_ts": from_ts,
            "to_ts": to_ts,
        },
    )).fetchall()

    return [
        FleetVehicleRead(
            vehicle_id=r.vehicle_id,
            reading_count=int(r.reading_count),
            distance_km=float(r.distance_km or 0),
            avg_speed=float(r.avg_speed) if r.avg_speed is not None else None,
            max_speed=float(r.max_speed) if r.max_speed is not None else None,
            drive_min=int(r.drive_min or 0),
            idle_min=int(r.idle_min or 0),
        )
        for r in rows
    ]
