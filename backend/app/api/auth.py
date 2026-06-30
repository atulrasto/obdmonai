from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas.auth import AccessTokenResponse, LoginRequest, RefreshRequest, TokenResponse
from app.security.jwt import (
    TokenData,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from app.security.password import verify_password

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    # auth_get_user_by_email is a SECURITY DEFINER function — bypasses RLS so
    # we can look up the user before we know their client_id.
    row = (
        await db.execute(
            text("SELECT * FROM auth_get_user_by_email(:email)"),
            {"email": body.email},
        )
    ).fetchone()

    if row is None or not verify_password(body.password, row.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not row.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account inactive")

    user_id = uuid.UUID(str(row.id))
    client_id = uuid.UUID(str(row.client_id))
    role: str = row.role

    return TokenResponse(
        access_token=create_access_token(user_id, client_id, role),
        refresh_token=create_refresh_token(user_id),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> AccessTokenResponse:
    try:
        user_id = decode_refresh_token(body.refresh_token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # auth_get_user_by_id is SECURITY DEFINER — bypasses RLS so we can look up
    # the user without a client_id GUC (which we don't have yet at refresh time).
    row = (
        await db.execute(
            text("SELECT * FROM auth_get_user_by_id(:uid)"),
            {"uid": str(user_id)},
        )
    ).fetchone()

    if row is None or not row.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return AccessTokenResponse(
        access_token=create_access_token(
            uuid.UUID(str(row.id)),
            uuid.UUID(str(row.client_id)),
            row.role,
        )
    )
