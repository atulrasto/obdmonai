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
