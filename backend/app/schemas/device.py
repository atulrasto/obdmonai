from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class DeviceCreate(BaseModel):
    serial: str
    vehicle_id: uuid.UUID | None = None


class DeviceRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    client_id: uuid.UUID
    vehicle_id: uuid.UUID | None
    serial: str
    cert_fingerprint: str | None
    is_active: bool
    created_at: datetime


class ProvisionResponse(BaseModel):
    device_id: uuid.UUID
    serial: str
    provisioning_token: str  # one-time short-lived JWT for device enrollment


class CertRegisterRequest(BaseModel):
    cert_fingerprint: str  # hex SHA-256 fingerprint; private key NEVER sent or stored
