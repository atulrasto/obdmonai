from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class ClientCreate(BaseModel):
    name: str
    slug: str
    owner_email: EmailStr
    owner_password: str


class ClientRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime


class ClientUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
