from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.security.deps import get_tenant_db, require_role
from app.security.jwt import TokenData
from app.simulator import state

router = APIRouter()


class SimStatus(BaseModel):
    vehicle_id: str
    is_running: bool


@router.get("", response_model=list[SimStatus])
async def list_sims(
    user: TokenData = Depends(require_role("owner", "fleet_admin")),
    db: AsyncSession = Depends(get_tenant_db),
) -> list[SimStatus]:
    rows = (await db.execute(
        text("SELECT id FROM vehicles WHERE is_active = true"),
    )).fetchall()
    return [SimStatus(vehicle_id=str(r.id), is_running=state.is_running(str(r.id))) for r in rows]


@router.post("/{vehicle_id}/start", response_model=SimStatus)
async def start_sim(
    vehicle_id: str,
    user: TokenData = Depends(require_role("owner", "fleet_admin")),
    db: AsyncSession = Depends(get_tenant_db),
) -> SimStatus:
    veh = (await db.execute(
        text("SELECT id, vin, client_id FROM vehicles WHERE id = :id AND is_active = true"),
        {"id": vehicle_id},
    )).fetchone()
    if not veh:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    dev = (await db.execute(
        text("SELECT id FROM devices WHERE vehicle_id = :vid AND is_active = true LIMIT 1"),
        {"vid": vehicle_id},
    )).fetchone()
    if not dev:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active device attached to this vehicle — register one on the Devices page first",
        )

    state.start(vehicle_id, {
        "device_id": str(dev.id),
        "client_id": str(veh.client_id),
        "vin": veh.vin,
    })
    return SimStatus(vehicle_id=vehicle_id, is_running=True)


@router.post("/{vehicle_id}/stop", response_model=SimStatus)
async def stop_sim(
    vehicle_id: str,
    user: TokenData = Depends(require_role("owner", "fleet_admin")),
    db: AsyncSession = Depends(get_tenant_db),
) -> SimStatus:
    state.stop(vehicle_id)
    return SimStatus(vehicle_id=vehicle_id, is_running=False)
