from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class VehicleCreate(BaseModel):
    vin: str
    make: str | None = None
    model_name: str | None = None
    year: int | None = None


class VehicleRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    client_id: uuid.UUID
    vin: str
    make: str | None
    model_name: str | None
    year: int | None
    is_active: bool
    created_at: datetime


class VehicleUpdate(BaseModel):
    make: str | None = None
    model_name: str | None = None
    year: int | None = None
    is_active: bool | None = None
