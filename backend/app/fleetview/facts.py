"""Assemble structured, identifier-free facts about a vehicle for LLM consumption.

All DB access is read-only.  Identifiers (UUIDs, VINs) are never included in
VehicleFacts — they stay in the application layer and are never forwarded to
the LLM.

Imports tier_b for ML-derived scores; never imports tier_a Python code.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.tier_b.inference import score_driver, score_maintenance

_UTC = timezone.utc


@dataclass
class VehicleFacts:
    """Structured, identifier-free facts assembled for a single vehicle."""
    make: str
    model_name: str
    year: int
    period_hours: int
    reading_count: int
    distance_km: float
    avg_speed_kmh: float | None
    max_speed_kmh: float | None
    driver_score: float | None         # 0-100, from Tier B
    maintenance_anomaly: bool | None   # from Tier B IsolationForest
    active_alert_count: int
    alert_rules: list[str] = field(default_factory=list)
    trip_count: int = 0


async def assemble_facts(
    vehicle_id: uuid.UUID,
    client_id: str,
    db: AsyncSession,
    *,
    hours: int = 24,
) -> VehicleFacts | None:
    """Return VehicleFacts for the given vehicle, or None if not found / no access."""
    now = datetime.now(_UTC)
    from_ts = now - timedelta(hours=hours)

    # ── Vehicle info ──────────────────────────────────────────────────────────
    # RLS on the vehicles table ensures client isolation automatically.
    vrow = (await db.execute(
        text("SELECT make, model_name, year FROM vehicles WHERE id = :vid"),
        {"vid": str(vehicle_id)},
    )).fetchone()
    if vrow is None:
        return None

    # ── Driving KPIs ─────────────────────────────────────────────────────────
    krow = (await db.execute(
        text(
            "SELECT * FROM analytics_vehicle_kpis"
            "(:vehicle_id, :client_id, :from_ts, :to_ts)"
        ),
        {
            "vehicle_id": str(vehicle_id),
            "client_id": client_id,
            "from_ts": from_ts,
            "to_ts": now,
        },
    )).fetchone()

    reading_count = int(krow.reading_count or 0) if krow else 0
    distance_km   = float(krow.distance_km or 0)  if krow else 0.0
    avg_speed     = float(krow.avg_speed)  if krow and krow.avg_speed  is not None else None
    max_speed     = float(krow.max_speed)  if krow and krow.max_speed  is not None else None

    # ── Active alerts (RLS-filtered by session GUC) ───────────────────────────
    alert_rows = (await db.execute(
        text(
            "SELECT DISTINCT rule FROM alerts "
            "WHERE vehicle_id = :vid AND state = 'active'"
        ),
        {"vid": str(vehicle_id)},
    )).fetchall()
    alert_rules = [r.rule for r in alert_rows]

    # ── Trip count ────────────────────────────────────────────────────────────
    trip_rows = (await db.execute(
        text(
            "SELECT COUNT(*) FROM analytics_list_trips"
            "(:vehicle_id, :client_id, :from_ts, :to_ts)"
        ),
        {
            "vehicle_id": str(vehicle_id),
            "client_id": client_id,
            "from_ts": from_ts,
            "to_ts": now,
        },
    )).scalar()
    trip_count = int(trip_rows or 0)

    # ── Tier B scores ─────────────────────────────────────────────────────────
    driver_result = await score_driver(vehicle_id, client_id, db, hours=hours)
    maint_result  = await score_maintenance(vehicle_id, client_id, db, hours=hours * 7)

    return VehicleFacts(
        make=vrow.make,
        model_name=vrow.model_name,
        year=vrow.year,
        period_hours=hours,
        reading_count=reading_count,
        distance_km=distance_km,
        avg_speed_kmh=avg_speed,
        max_speed_kmh=max_speed,
        driver_score=driver_result["score"],
        maintenance_anomaly=maint_result["is_anomaly"],
        active_alert_count=len(alert_rules),
        alert_rules=alert_rules,
        trip_count=trip_count,
    )
