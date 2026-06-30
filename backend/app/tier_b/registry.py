"""Model registry: loads ML artifacts from ml_models table via SECURITY DEFINER.

Models are cached in-process after first load.  Loading is offloaded to a
thread-pool executor so joblib.load() never blocks the asyncio event loop.

The app_user role reads models only via ml_get_model() — no direct table access.

No tier_a imports.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
from typing import Any

import joblib
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

_cache: dict[str, Any] = {}


def _joblib_load(data: bytes) -> Any:
    return joblib.load(io.BytesIO(data))


async def _load(name: str, db: AsyncSession) -> Any:
    if name in _cache:
        return _cache[name]
    row = (await db.execute(
        text("SELECT ml_get_model(:name, NULL)"),
        {"name": name},
    )).scalar()
    if row is None:
        raise LookupError(f"ML model '{name}' not found in ml_models table")
    artifact = base64.b64decode(row)
    loop = asyncio.get_running_loop()
    model = await loop.run_in_executor(None, _joblib_load, artifact)
    _cache[name] = model
    log.info("loaded ML model '%s' from DB (%d bytes)", name, len(artifact))
    return model


async def get_driver_model(db: AsyncSession) -> Any:
    return await _load("driver_score", db)


async def get_maintenance_model(db: AsyncSession) -> Any:
    return await _load("maintenance", db)


def clear_cache() -> None:
    """Evict all cached models (used in tests that need a fresh DB load)."""
    _cache.clear()
