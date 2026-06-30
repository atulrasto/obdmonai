"""Tier B read-only scoring endpoints.

GET /scores/vehicles/{vehicle_id}/driver       — driver behaviour score (0-100)
GET /scores/vehicles/{vehicle_id}/maintenance  — predictive maintenance anomaly

INVARIANT: these endpoints NEVER write to the database.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.security.deps import get_tenant_db, require_role
from app.security.jwt import TokenData
from app.tier_b.inference import score_driver, score_maintenance

router = APIRouter()


class DriverScoreResponse(BaseModel):
    vehicle_id: uuid.UUID
    score: float | None
    window_hours: int
    computed_at: datetime


class MaintenanceResponse(BaseModel):
    vehicle_id: uuid.UUID
    is_anomaly: bool | None
    anomaly_score: float | None
    computed_at: datetime


@router.get("/vehicles/{vehicle_id}/driver", response_model=DriverScoreResponse)
async def driver_score(
    vehicle_id: uuid.UUID,
    hours: int = 24,
    user: TokenData = Depends(require_role("owner", "fleet_admin", "viewer")),
    db: AsyncSession = Depends(get_tenant_db),
) -> DriverScoreResponse:
    result = await score_driver(vehicle_id, user.client_id, db, hours=hours)
    return DriverScoreResponse(**result)


@router.get("/vehicles/{vehicle_id}/maintenance", response_model=MaintenanceResponse)
async def maintenance_score(
    vehicle_id: uuid.UUID,
    user: TokenData = Depends(require_role("owner", "fleet_admin", "viewer")),
    db: AsyncSession = Depends(get_tenant_db),
) -> MaintenanceResponse:
    result = await score_maintenance(vehicle_id, user.client_id, db)
    return MaintenanceResponse(**result)
