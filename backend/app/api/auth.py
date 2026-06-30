from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas.auth import (
    AccessTokenResponse,
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)
from app.security.deps import get_current_user
from app.security.jwt import (
    TokenData,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from app.security.password import hash_password, verify_password

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
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
    client_id = uuid.UUID(str(row.client_id)) if row.client_id else None
    role: str = row.role
    must_change: bool = bool(row.must_change_password)

    return TokenResponse(
        access_token=create_access_token(user_id, client_id, role, must_change),
        refresh_token=create_refresh_token(user_id),
        must_change_password=must_change,
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

    cid = uuid.UUID(str(row.client_id)) if row.client_id else None
    return AccessTokenResponse(
        access_token=create_access_token(
            uuid.UUID(str(row.id)),
            cid,
            row.role,
            bool(row.must_change_password),
        )
    )


@router.post("/change-password", response_model=TokenResponse)
async def change_password(
    body: ChangePasswordRequest,
    user: TokenData = Depends(get_current_user),  # works even if must_change_password=True
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Change password. Required on first login when must_change_password=True."""
    row = (
        await db.execute(
            text("SELECT * FROM auth_get_user_by_id(:uid)"),
            {"uid": str(user.user_id)},
        )
    ).fetchone()

    if row is None or not row.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if not verify_password(body.current_password, row.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if len(body.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters",
        )

    new_hash = hash_password(body.new_password)
    await db.execute(
        text("SELECT auth_set_password(:uid, :hash, false)"),
        {"uid": str(user.user_id), "hash": new_hash},
    )
    await db.commit()

    cid = uuid.UUID(str(row.client_id)) if row.client_id else None
    return TokenResponse(
        access_token=create_access_token(user.user_id, cid, row.role, False),
        refresh_token=create_refresh_token(user.user_id),
        must_change_password=False,
    )
