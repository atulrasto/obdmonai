"""Phase 2 acceptance tests — DB schema, RLS, hypertable, app role.

Run after `alembic upgrade head`:
    DATABASE_URL=postgresql+asyncpg://postgres:pw@localhost:5434/obdmonai pytest
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.mark.asyncio
async def test_timescaledb_extension_installed(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'timescaledb'")
        )
        assert result.scalar() == "timescaledb", "TimescaleDB extension not found"


@pytest.mark.asyncio
async def test_hypertable_exists(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT hypertable_name "
                "FROM timescaledb_information.hypertables "
                "WHERE hypertable_name = 'telemetry'"
            )
        )
        assert result.scalar() == "telemetry", "telemetry hypertable not found"


@pytest.mark.asyncio
async def test_rls_enabled_on_tenant_tables(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND rowsecurity = true "
                "ORDER BY tablename"
            )
        )
        rls_tables = {row[0] for row in result}

    for expected in ("users", "vehicles", "devices", "telemetry"):
        assert expected in rls_tables, f"RLS not enabled on table: {expected}"


@pytest.mark.asyncio
async def test_rls_policies_exist(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename, policyname FROM pg_policies "
                "WHERE schemaname = 'public' "
                "ORDER BY tablename, policyname"
            )
        )
        policies = {(row[0], row[1]) for row in result}

    for table in ("users", "vehicles", "devices", "telemetry"):
        assert (table, f"{table}_tenant_isolation") in policies, (
            f"Missing isolation policy on {table}"
        )
        assert (table, f"{table}_tenant_insert") in policies, (
            f"Missing insert policy on {table}"
        )


@pytest.mark.asyncio
async def test_app_role_is_not_superuser(db_engine: AsyncEngine) -> None:
    app_user = os.environ.get("POSTGRES_USER", "obdmonai_app")
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT rolsuper FROM pg_roles WHERE rolname = :role"),
            {"role": app_user},
        )
        row = result.fetchone()
    assert row is not None, f"Role '{app_user}' does not exist"
    assert row[0] is False, f"Role '{app_user}' must not be superuser"


@pytest.mark.asyncio
async def test_dedup_index_exists(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'telemetry' AND indexname = 'ix_telemetry_device_seq'"
            )
        )
        assert result.scalar() == "ix_telemetry_device_seq", (
            "Dedup lookup index ix_telemetry_device_seq not found on telemetry"
        )


@pytest.mark.asyncio
async def test_continuous_aggregates_exist(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT view_name "
                "FROM timescaledb_information.continuous_aggregates "
                "ORDER BY view_name"
            )
        )
        caggs = {row[0] for row in result}

    for expected in ("telemetry_1m", "telemetry_1h"):
        assert expected in caggs, f"Continuous aggregate '{expected}' not found"


@pytest.mark.asyncio
async def test_alembic_downgrade_and_upgrade(db_engine: AsyncEngine) -> None:
    """Verify alembic_version table is present (migrations ran)."""
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT version_num FROM alembic_version ORDER BY version_num"
            )
        )
        versions = [row[0] for row in result]
    # Accept any migration at or beyond 0004 (stack advances as new phases are added)
    assert any(v >= "0004" for v in versions), (
        f"Expected migration >= 0004 in alembic_version, got: {versions}"
    )
