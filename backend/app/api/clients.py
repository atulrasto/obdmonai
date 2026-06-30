from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.tenant import Client
from app.schemas.client import ClientCreate, ClientRead, ClientUpdate
from app.security.deps import require_role
from app.security.jwt import TokenData
from app.security.password import hash_password

router = APIRouter()


@router.post("", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
async def create_client(
    body: ClientCreate,
    db: AsyncSession = Depends(get_db),
) -> ClientRead:
    """Register a new tenant + initial owner user.

    This endpoint is intentionally unauthenticated — it is the onboarding /
    self-registration route.  Future hardening: add invite-code or rate-limit.
    """
    # Check slug uniqueness
    existing = (await db.execute(select(Client).where(Client.slug == body.slug))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already taken")

    client = Client(name=body.name, slug=body.slug)
    db.add(client)
    await db.flush()  # populate client.id

    # auth_create_initial_owner is SECURITY DEFINER — bypasses the users RLS
    # INSERT policy that would otherwise block the insert (no GUC at registration).
    await db.execute(
        text("SELECT auth_create_initial_owner(:cid, :email, :ph)"),
        {
            "cid": str(client.id),
            "email": body.owner_email,
            "ph": hash_password(body.owner_password),
        },
    )
    await db.commit()
    await db.refresh(client)
    return ClientRead.model_validate(client)


@router.get("/me", response_model=ClientRead)
async def get_my_client(
    user: TokenData = Depends(require_role("owner", "fleet_admin", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> ClientRead:
    client = (await db.execute(select(Client).where(Client.id == user.client_id))).scalar_one_or_none()
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return ClientRead.model_validate(client)


@router.patch("/me", response_model=ClientRead)
async def update_my_client(
    body: ClientUpdate,
    user: TokenData = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> ClientRead:
    client = (await db.execute(select(Client).where(Client.id == user.client_id))).scalar_one_or_none()
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    if body.name is not None:
        client.name = body.name
    if body.slug is not None:
        client.slug = body.slug

    await db.commit()
    await db.refresh(client)
    return ClientRead.model_validate(client)
