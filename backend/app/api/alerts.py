from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.security.deps import get_tenant_db, require_role
from app.security.jwt import TokenData

router = APIRouter()


class AlertRead(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    vehicle_id: uuid.UUID
    device_id: uuid.UUID
    rule: str
    state: str
    severity: str
    detail: dict[str, Any]
    fired_at: datetime
    cleared_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AlertRead])
async def list_alerts(
    state: str | None = Query(None, pattern="^(watching|active|cleared)$"),
    device_id: uuid.UUID | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user: TokenData = Depends(require_role("owner", "fleet_admin", "viewer")),
    db: AsyncSession = Depends(get_tenant_db),
) -> list[AlertRead]:
    filters = ["TRUE"]
    params: dict = {"limit": limit, "offset": offset}

    if state is not None:
        filters.append("state = :state")
        params["state"] = state
    if device_id is not None:
        filters.append("device_id = :device_id")
        params["device_id"] = str(device_id)

    where = " AND ".join(filters)
    rows = (await db.execute(
        text(
            f"SELECT id, client_id, vehicle_id, device_id, rule, state, severity, detail,"
            f" fired_at, cleared_at, created_at"
            f" FROM alerts WHERE {where}"
            f" ORDER BY fired_at DESC LIMIT :limit OFFSET :offset"
        ),
        params,
    )).fetchall()

    return [AlertRead.model_validate(dict(r._mapping)) for r in rows]


@router.get("/{alert_id}", response_model=AlertRead)
async def get_alert(
    alert_id: uuid.UUID,
    user: TokenData = Depends(require_role("owner", "fleet_admin", "viewer")),
    db: AsyncSession = Depends(get_tenant_db),
) -> AlertRead:
    row = (await db.execute(
        text(
            "SELECT id, client_id, vehicle_id, device_id, rule, state, severity, detail,"
            " fired_at, cleared_at, created_at"
            " FROM alerts WHERE id = :id"
        ),
        {"id": str(alert_id)},
    )).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return AlertRead.model_validate(dict(row._mapping))
