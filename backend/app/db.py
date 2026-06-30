from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import settings

# Tests run each test in a fresh event loop (asyncio_default_fixture_loop_scope=function).
# AsyncAdaptedQueuePool binds connections to the loop that created them, so they
# can't be reused across tests.  NullPool creates and closes one connection per
# statement, which avoids the cross-loop "Future attached to different loop" error.
_pool_cls = NullPool if settings.environment != "production" else None

engine = create_async_engine(
    settings.database_url,
    poolclass=_pool_cls,
    pool_pre_ping=_pool_cls is None,
    # pgbouncer transaction mode: server-side prepared statements must be off.
    # 120 s connect timeout: NullPool creates a fresh connection per request;
    # under heavy test load Docker auth can be slow so we allow extra headroom.
    connect_args={"prepared_statement_cache_size": 0, "timeout": 120.0},
)

_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def get_session() -> async_sessionmaker[AsyncSession]:
    """Return the session factory (for use by security/deps.py)."""
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """Plain session with no RLS context — for admin / cross-tenant operations."""
    async with _session_factory() as session:
        yield session


async def get_tenant_db_session(client_id: str) -> AsyncIterator[AsyncSession]:
    """Yield an async session with the tenant RLS GUC set for the transaction.

    Uses SET LOCAL so the GUC is scoped to the transaction; safe with
    pgbouncer in transaction-pooling mode.
    """
    async with _session_factory() as session:
        async with session.begin():
            # PostgreSQL SET does not accept $N bind params; client_id is a
            # UUID string (hex + hyphens only) — safe to interpolate directly.
            await session.execute(
                text(f"SET LOCAL app.current_client_id = '{client_id}'")
            )
            yield session
