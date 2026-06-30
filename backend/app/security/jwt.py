from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import settings


class TokenData(BaseModel):
    user_id: uuid.UUID
    client_id: uuid.UUID
    role: str  # owner | fleet_admin | viewer


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: uuid.UUID, client_id: uuid.UUID, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "client_id": str(client_id),
        "role": role,
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
    return TokenData(
        user_id=uuid.UUID(payload["sub"]),
        client_id=uuid.UUID(payload["client_id"]),
        role=payload["role"],
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
