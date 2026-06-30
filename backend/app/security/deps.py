from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.security.jwt import TokenData, decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_401 = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)

_CHANGE_PW = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="password_change_required",
)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    try:
        return decode_access_token(token)
    except ValueError:
        raise _401


def require_role(*allowed: str):
    """Return a dependency that checks role and enforces password-change gate."""

    async def _check(user: TokenData = Depends(get_current_user)) -> TokenData:
        if user.must_change_password:
            raise _CHANGE_PW
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _check


async def get_tenant_db(
    user: TokenData = Depends(get_current_user),
) -> AsyncIterator[AsyncSession]:
    """Yield a DB session with the tenant RLS GUC set for the transaction."""
    if user.must_change_password:
        raise _CHANGE_PW
    if user.client_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin has no tenant context",
        )
    factory = get_session()
    async with factory() as session:
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL app.current_client_id = '{user.client_id}'")
            )
            yield session
