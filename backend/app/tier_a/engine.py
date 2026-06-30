"""Tier A rules engine — DB-aware orchestration layer.

Loads context from the database, delegates rule evaluation to the pure
``rules.evaluate_all``, and persists the results.  Imports nothing from Tier B.
"""
from __future__ import annotations

import json
import logging
from datetime import timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.tier_a.notify import dispatch_notification
from app.tier_a.rules import (
    AlertState,
    Geofence,
    RuleResult,
    TelemetryReading,
    evaluate_all,
)

log = logging.getLogger(__name__)


async def run_for_device(
    reading: TelemetryReading,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Evaluate all rules for one telemetry reading and persist the results.

    Runs in its own transaction, separate from the ingest transaction.
    """
    async with session_factory() as session:
        async with session.begin():
            prev = await _load_prev(session, reading)
            alert_states = await _load_alert_states(session, reading.device_id)
            geofences = await _load_geofences(session, reading.client_id)

            results = evaluate_all(reading, prev, alert_states, geofences)

            alert_map = {a.rule: a for a in alert_states}
            for result in results:
                await _apply_result(session, result, reading, alert_map)
                if result.action in ("fire", "clear"):
                    dispatch_notification(result, reading)


async def _load_prev(
    session: AsyncSession,
    reading: TelemetryReading,
) -> TelemetryReading | None:
    row = (await session.execute(
        text("SELECT * FROM tier_a_get_prev_telemetry(:device_id, :seq)"),
        {"device_id": reading.device_id, "seq": reading.seq},
    )).fetchone()
    if row is None:
        return None
    return TelemetryReading(
        device_id=reading.device_id,
        vehicle_id=reading.vehicle_id,
        client_id=reading.client_id,
        ts=row.ts,
        seq=int(row.seq),
        obd_speed=float(row.obd_speed or 0.0),
        obd_coolant=float(row.obd_coolant or 0.0),
        obd_rpm=0.0,
        obd_fuel_level=float(row.obd_fuel_level or 0.0),
        imu_ax=float(row.imu_ax or 0.0),
        gps_lat=float(row.gps_lat or 0.0),
        gps_lon=float(row.gps_lon or 0.0),
        dtc=list(row.dtc or []),
        ign=bool(row.ign),
    )


async def _load_alert_states(
    session: AsyncSession,
    device_id: str,
) -> list[AlertState]:
    rows = (await session.execute(
        text("SELECT * FROM tier_a_get_alert_states(:device_id)"),
        {"device_id": device_id},
    )).fetchall()
    return [
        AlertState(
            id=str(row.id),
            rule=row.rule,
            state=row.state,
            fired_at=row.fired_at,
            detail=dict(row.detail) if row.detail else {},
        )
        for row in rows
    ]


async def _load_geofences(
    session: AsyncSession,
    client_id: str,
) -> list[Geofence]:
    rows = (await session.execute(
        text("SELECT * FROM tier_a_get_geofences(:client_id)"),
        {"client_id": client_id},
    )).fetchall()
    return [
        Geofence(
            id=str(row.id),
            name=row.name,
            center_lat=float(row.center_lat),
            center_lon=float(row.center_lon),
            radius_m=float(row.radius_m),
        )
        for row in rows
    ]


async def _apply_result(
    session: AsyncSession,
    result: RuleResult,
    reading: TelemetryReading,
    alert_map: dict[str, AlertState],
) -> None:
    if result.action == "none":
        return

    ts = reading.ts
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    detail_json = json.dumps(result.detail)

    if result.action == "watch":
        await session.execute(
            text(
                "SELECT tier_a_watch_alert(:device_id, :vehicle_id, :client_id,"
                " :rule, CAST(:detail AS JSONB), :started_at)"
            ),
            {
                "device_id": reading.device_id,
                "vehicle_id": reading.vehicle_id,
                "client_id": reading.client_id,
                "rule": result.rule,
                "detail": detail_json,
                "started_at": ts,
            },
        )

    elif result.action == "fire":
        await session.execute(
            text(
                "SELECT tier_a_fire_alert(:device_id, :vehicle_id, :client_id,"
                " :rule, :severity, CAST(:detail AS JSONB), :fired_at)"
            ),
            {
                "device_id": reading.device_id,
                "vehicle_id": reading.vehicle_id,
                "client_id": reading.client_id,
                "rule": result.rule,
                "severity": result.severity,
                "detail": detail_json,
                "fired_at": ts,
            },
        )

    elif result.action == "clear":
        alert = alert_map.get(result.rule)
        if alert:
            await session.execute(
                text("SELECT tier_a_clear_alert(:alert_id, :cleared_at)"),
                {"alert_id": alert.id, "cleared_at": ts},
            )
        else:
            log.debug("clear action for '%s' but no active alert found; skipping", result.rule)
