from __future__ import annotations

import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.mailer import send_welcome_email
from app.models.tenant import Client
from app.schemas.client import ClientCreate, ClientCreateResponse, ClientRead, ClientUpdate
from app.security.deps import require_role
from app.security.jwt import TokenData
from app.security.password import hash_password

router = APIRouter()

_PW_ALPHABET = string.ascii_letters + string.digits


def _gen_password(length: int = 16) -> str:
    return "".join(secrets.choice(_PW_ALPHABET) for _ in range(length))


@router.post("", response_model=ClientCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    body: ClientCreate,
    _user: TokenData = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
) -> ClientCreateResponse:
    """Create a new tenant. Superadmin only.

    A random temporary password is generated, returned once in this response,
    and emailed to the owner. The owner must change it on first login.
    """
    existing = (await db.execute(select(Client).where(Client.slug == body.slug))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already taken")

    temp_password = _gen_password()

    client = Client(name=body.name, slug=body.slug)
    db.add(client)
    await db.flush()

    await db.execute(
        text("SELECT auth_create_initial_owner(:cid, :email, :ph, TRUE)"),
        {
            "cid": str(client.id),
            "email": body.owner_email,
            "ph": hash_password(temp_password),
        },
    )
    await db.commit()
    await db.refresh(client)

    # Send welcome email best-effort — failure does not roll back the client
    try:
        await send_welcome_email(body.owner_email, body.name, temp_password)
    except Exception:
        pass

    return ClientCreateResponse(
        id=client.id,
        name=client.name,
        slug=client.slug,
        is_active=client.is_active,
        created_at=client.created_at,
        owner_email=body.owner_email,
        temp_password=temp_password,
    )


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
