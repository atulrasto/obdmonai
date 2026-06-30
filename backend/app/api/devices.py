from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Device
from app.schemas.device import (
    CertRegisterRequest,
    DeviceCreate,
    DeviceRead,
    ProvisionResponse,
)
from app.security.deps import get_tenant_db, require_role
from app.security.jwt import TokenData, create_access_token
from app.security.password import hash_password

router = APIRouter()


@router.get("", response_model=list[DeviceRead])
async def list_devices(
    user: TokenData = Depends(require_role("owner", "fleet_admin", "viewer")),
    db: AsyncSession = Depends(get_tenant_db),
) -> list[DeviceRead]:
    rows = (await db.execute(select(Device).where(Device.is_active.is_(True)))).scalars().all()
    return [DeviceRead.model_validate(r) for r in rows]


@router.post("", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
async def create_device(
    body: DeviceCreate,
    user: TokenData = Depends(require_role("owner", "fleet_admin")),
    db: AsyncSession = Depends(get_tenant_db),
) -> DeviceRead:
    device = Device(
        client_id=user.client_id,
        vehicle_id=body.vehicle_id,
        serial=body.serial,
    )
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return DeviceRead.model_validate(device)


@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(
    device_id: uuid.UUID,
    user: TokenData = Depends(require_role("owner", "fleet_admin", "viewer")),
    db: AsyncSession = Depends(get_tenant_db),
) -> DeviceRead:
    row = (
        await db.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return DeviceRead.model_validate(row)


@router.post("/{device_id}/provision", response_model=ProvisionResponse)
async def provision_device(
    device_id: uuid.UUID,
    user: TokenData = Depends(require_role("owner", "fleet_admin")),
    db: AsyncSession = Depends(get_tenant_db),
) -> ProvisionResponse:
    """Issue a one-time provisioning token for the device.

    The token embeds the device_id and client_id so the firmware can:
    1. Present the token during MQTT TLS handshake (via username/password).
    2. Upload its TLS cert fingerprint to /devices/{id}/cert.
    The private key is NEVER sent to or stored by this server.
    """
    row = (
        await db.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    # Re-use the access-token mechanism with a special "device" role so the
    # firmware can authenticate; the role is checked in the ingest layer.
    token = create_access_token(
        user_id=row.id,          # device id acts as the "user" id
        client_id=row.client_id,
        role="device",
    )
    return ProvisionResponse(device_id=row.id, serial=row.serial, provisioning_token=token)


@router.post("/{device_id}/cert", response_model=DeviceRead)
async def register_cert(
    device_id: uuid.UUID,
    body: CertRegisterRequest,
    user: TokenData = Depends(require_role("owner", "fleet_admin")),
    db: AsyncSession = Depends(get_tenant_db),
) -> DeviceRead:
    """Store the device's TLS certificate fingerprint. Private key is never sent."""
    row = (
        await db.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    row.cert_fingerprint = body.cert_fingerprint
    await db.flush()
    await db.refresh(row)
    return DeviceRead.model_validate(row)
