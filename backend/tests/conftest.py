"""Shared pytest fixtures for obdmonai backend tests."""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


@pytest_asyncio.fixture(scope="function")
async def db_engine() -> AsyncEngine:
    """Async SQLAlchemy engine for schema / metadata inspection.

    Prefers SUPERUSER_DATABASE_URL so Phase 2 inspection tests (pg_roles,
    alembic downgrade/upgrade) have the necessary privileges.  Falls back to
    DATABASE_URL when the superuser URL is not provided.
    Function-scoped to avoid event-loop conflicts in pytest-asyncio >= 0.21.
    """
    url = os.environ.get("SUPERUSER_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — start the db service first")
    engine = create_async_engine(url, echo=False)
    yield engine  # type: ignore[misc]
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def ingest_engine() -> AsyncEngine:
    """NullPool engine for ingest pipeline tests.

    Uses SUPERUSER_DATABASE_URL (if set) so tests can query the telemetry
    hypertable directly without needing the RLS GUC.  Falls back to
    DATABASE_URL.  NullPool + no prepared statement cache avoids event-loop
    conflicts across function-scoped async tests.
    """
    url = os.environ.get("SUPERUSER_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — start the db service first")
    engine = create_async_engine(
        url,
        echo=False,
        poolclass=NullPool,
        connect_args={"prepared_statement_cache_size": 0, "timeout": 120.0},
    )
    yield engine  # type: ignore[misc]
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def session_factory(ingest_engine: AsyncEngine) -> async_sessionmaker:
    """async_sessionmaker bound to the ingest test engine."""
    return async_sessionmaker(ingest_engine, expire_on_commit=False)


@pytest_asyncio.fixture(scope="function")
async def async_client():
    """HTTP test client for the FastAPI app (no real network)."""
    from app.main import app  # local import avoids circular-import at collection time
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
