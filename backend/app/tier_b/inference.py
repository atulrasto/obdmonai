"""Orchestrates Tier B inference: fetch telemetry → extract features → score.

All DB reads go through SECURITY DEFINER functions that accept explicit
(vehicle_id, client_id) so they bypass RLS without needing the GUC.

No tier_a imports. Read-only — never writes to the database.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.tier_b.driver_score import predict_score
from app.tier_b.features import extract_features
from app.tier_b.maintenance import predict_anomaly
from app.tier_b.registry import get_driver_model, get_maintenance_model

_UTC = timezone.utc


async def score_driver(
    vehicle_id: uuid.UUID,
    client_id: str,
    db: AsyncSession,
    *,
    hours: int = 24,
) -> dict:
    model = await get_driver_model(db)
    from_ts = datetime.now(_UTC) - timedelta(hours=hours)

    rows = (await db.execute(
        text(
            "SELECT * FROM ml_get_telemetry_window"
            "(:vehicle_id, :client_id, :from_ts)"
        ),
        {"vehicle_id": str(vehicle_id), "client_id": client_id, "from_ts": from_ts},
    )).fetchall()

    score: float | None = None
    if rows:
        features = extract_features(rows)
        score = predict_score(model, features)

    return {
        "vehicle_id": vehicle_id,
        "score": score,
        "window_hours": hours,
        "computed_at": datetime.now(_UTC),
    }


async def score_maintenance(
    vehicle_id: uuid.UUID,
    client_id: str,
    db: AsyncSession,
    *,
    hours: int = 168,  # default: last 7 days
) -> dict:
    model = await get_maintenance_model(db)
    from_ts = datetime.now(_UTC) - timedelta(hours=hours)

    rows = (await db.execute(
        text(
            "SELECT * FROM ml_get_telemetry_window"
            "(:vehicle_id, :client_id, :from_ts)"
        ),
        {"vehicle_id": str(vehicle_id), "client_id": client_id, "from_ts": from_ts},
    )).fetchall()

    if not rows:
        return {
            "vehicle_id": vehicle_id,
            "is_anomaly": None,
            "anomaly_score": None,
            "computed_at": datetime.now(_UTC),
        }

    features = extract_features(rows)
    result = predict_anomaly(model, features)
    return {
        "vehicle_id": vehicle_id,
        "is_anomaly": result["is_anomaly"],
        "anomaly_score": result["anomaly_score"],
        "computed_at": datetime.now(_UTC),
    }
