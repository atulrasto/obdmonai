from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Vehicle
from app.schemas.vehicle import VehicleCreate, VehicleRead, VehicleUpdate
from app.security.deps import get_tenant_db, require_role
from app.security.jwt import TokenData

router = APIRouter()


@router.get("", response_model=list[VehicleRead])
async def list_vehicles(
    user: TokenData = Depends(require_role("owner", "fleet_admin", "viewer")),
    db: AsyncSession = Depends(get_tenant_db),
) -> list[VehicleRead]:
    rows = (await db.execute(select(Vehicle).where(Vehicle.is_active.is_(True)))).scalars().all()
    return [VehicleRead.model_validate(r) for r in rows]


@router.post("", response_model=VehicleRead, status_code=status.HTTP_201_CREATED)
async def create_vehicle(
    body: VehicleCreate,
    user: TokenData = Depends(require_role("owner", "fleet_admin")),
    db: AsyncSession = Depends(get_tenant_db),
) -> VehicleRead:
    vehicle = Vehicle(
        client_id=user.client_id,
        vin=body.vin,
        make=body.make,
        model_name=body.model_name,
        year=body.year,
    )
    db.add(vehicle)
    await db.flush()
    await db.refresh(vehicle)
    return VehicleRead.model_validate(vehicle)


@router.get("/{vehicle_id}", response_model=VehicleRead)
async def get_vehicle(
    vehicle_id: uuid.UUID,
    user: TokenData = Depends(require_role("owner", "fleet_admin", "viewer")),
    db: AsyncSession = Depends(get_tenant_db),
) -> VehicleRead:
    row = (
        await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    return VehicleRead.model_validate(row)


@router.patch("/{vehicle_id}", response_model=VehicleRead)
async def update_vehicle(
    vehicle_id: uuid.UUID,
    body: VehicleUpdate,
    user: TokenData = Depends(require_role("owner", "fleet_admin")),
    db: AsyncSession = Depends(get_tenant_db),
) -> VehicleRead:
    row = (
        await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(row, field, value)

    await db.flush()
    await db.refresh(row)
    return VehicleRead.model_validate(row)


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vehicle(
    vehicle_id: uuid.UUID,
    user: TokenData = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_tenant_db),
) -> None:
    row = (
        await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    row.is_active = False  # soft-delete; telemetry history preserved
    await db.flush()
