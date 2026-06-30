from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import settings


class TokenData(BaseModel):
    user_id: uuid.UUID
    client_id: uuid.UUID | None   # None for superadmin (no tenant)
    role: str                     # superadmin | owner | fleet_admin | viewer
    must_change_password: bool = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    user_id: uuid.UUID,
    client_id: uuid.UUID | None,
    role: str,
    must_change_password: bool = False,
) -> str:
    payload = {
        "sub": str(user_id),
        "client_id": str(client_id) if client_id else None,
        "role": role,
        "must_change_password": must_change_password,
        "type": "access",
        "exp": _now() + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: uuid.UUID) -> str:
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": _now() + timedelta(days=settings.jwt_refresh_token_expire_days),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except JWTError as exc:
        raise ValueError("invalid token") from exc
    if payload.get("type") != "access":
        raise ValueError("not an access token")
    cid = payload.get("client_id")
    return TokenData(
        user_id=uuid.UUID(payload["sub"]),
        client_id=uuid.UUID(cid) if cid else None,
        role=payload["role"],
        must_change_password=payload.get("must_change_password", False),
    )


def decode_refresh_token(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except JWTError as exc:
        raise ValueError("invalid token") from exc
    if payload.get("type") != "refresh":
        raise ValueError("not a refresh token")
    return uuid.UUID(payload["sub"])
