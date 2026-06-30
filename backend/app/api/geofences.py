from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.security.deps import get_tenant_db, require_role
from app.security.jwt import TokenData

router = APIRouter()


class GeofenceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    center_lat: float = Field(..., ge=-90.0, le=90.0)
    center_lon: float = Field(..., ge=-180.0, le=180.0)
    radius_m: float = Field(..., gt=0)


class GeofenceRead(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    center_lat: float
    center_lon: float
    radius_m: float
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[GeofenceRead])
async def list_geofences(
    user: TokenData = Depends(require_role("owner", "fleet_admin", "viewer")),
    db: AsyncSession = Depends(get_tenant_db),
) -> list[GeofenceRead]:
    rows = (await db.execute(
        text(
            "SELECT id, client_id, name, center_lat, center_lon, radius_m, is_active, created_at"
            " FROM geofences WHERE is_active = true ORDER BY created_at"
        ),
    )).fetchall()
    return [GeofenceRead.model_validate(dict(r._mapping)) for r in rows]


@router.post("", response_model=GeofenceRead, status_code=status.HTTP_201_CREATED)
async def create_geofence(
    body: GeofenceCreate,
    user: TokenData = Depends(require_role("owner", "fleet_admin")),
    db: AsyncSession = Depends(get_tenant_db),
) -> GeofenceRead:
    row = (await db.execute(
        text(
            "INSERT INTO geofences (client_id, name, center_lat, center_lon, radius_m)"
            " VALUES (:client_id, :name, :lat, :lon, :radius)"
            " RETURNING id, client_id, name, center_lat, center_lon, radius_m, is_active, created_at"
        ),
        {
            "client_id": user.client_id,
            "name": body.name,
            "lat": body.center_lat,
            "lon": body.center_lon,
            "radius": body.radius_m,
        },
    )).fetchone()
    return GeofenceRead.model_validate(dict(row._mapping))  # type: ignore[union-attr]


@router.delete("/{geofence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_geofence(
    geofence_id: uuid.UUID,
    user: TokenData = Depends(require_role("owner", "fleet_admin")),
    db: AsyncSession = Depends(get_tenant_db),
) -> None:
    result = await db.execute(
        text(
            "UPDATE geofences SET is_active = false"
            " WHERE id = :id RETURNING id"
        ),
        {"id": str(geofence_id)},
    )
    if result.fetchone() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Geofence not found")
