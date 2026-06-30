"""Phase 10 — end-to-end smoke tests.

Covers:
  test_health_ok              — /health returns 200 {"status": "ok"}
  test_pdf_magic_bytes        — /reports/vehicles/{id}/pdf returns valid PDF
  test_pdf_404_unknown        — unknown vehicle → 404
  test_full_pipeline          — seed → analytics → FleetView → PDF in one request chain
  test_structlog_configured   — structlog is wired up (returns a logger)
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import cbor2
import pytest
import pytest_asyncio
from httpx import AsyncClient

SKIP = pytest.mark.skipif(
    os.environ.get("DATABASE_URL") is None,
    reason="DATABASE_URL not set",
)

_UTC = timezone.utc


# ── Helpers ────────────────────────────────────────────────────────────────────

def _cbor(device_id: str, seq: int, ts: datetime, speed: float = 60.0) -> bytes:
    return cbor2.dumps({
        "device_id": device_id,
        "ts": int(ts.timestamp()),
        "seq": seq,
        "gps": {"lat": 18.52, "lon": 73.86, "alt": 550.0, "hdg": 90.0, "spd": speed / 3.6},
        "obd": {
            "speed": speed, "rpm": 1500.0, "coolant": 85.0, "fuel_level": 70.0,
            "load": 22.0, "throttle": 15.0, "intake_temp": 30.0, "run_time": seq * 10,
        },
        "imu": {"ax": 0.0, "ay": 0.0, "az": 0.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
        "dtc": [],
        "ign": True,
    })


# ── Fixture ────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="function")
async def smoke_ctx(session_factory, async_client: AsyncClient):
    """Provision a fresh tenant with 5 telemetry readings."""
    from app.ingest.worker import process_message

    suffix = uuid.uuid4().hex[:8]
    email  = f"smoke-{suffix}@test.io"
    pw     = "Sm0keTest!"
    vin    = f"SM{uuid.uuid4().hex[:15].upper()}"

    r = await async_client.post("/clients", json={
        "name": f"SmokeCo {suffix}", "slug": f"smoke-{suffix}",
        "owner_email": email, "owner_password": pw,
    })
    assert r.status_code == 201, r.text
    client_id = r.json()["id"]

    r = await async_client.post("/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    token   = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.post("/vehicles", headers=headers, json={
        "vin": vin, "make": "Volvo", "model_name": "FH16", "year": 2023,
    })
    assert r.status_code == 201, r.text
    vehicle_id = r.json()["id"]

    r = await async_client.post("/devices", headers=headers, json={
        "vehicle_id": vehicle_id,
        "serial": f"SM-{uuid.uuid4().hex[:8].upper()}",
        "firmware_version": "3.0",
    })
    assert r.status_code == 201, r.text
    device_id = r.json()["id"]

    topic    = f"obdmonai/{client_id}/vehicle/{vin}/telemetry"
    base_ts  = datetime.now(_UTC) - timedelta(hours=2)
    for seq in range(1, 6):
        ts  = base_ts + timedelta(seconds=seq * 10)
        raw = _cbor(device_id, seq, ts, speed=65.0)
        await process_message(topic, raw, session_factory)

    yield {
        "vehicle_id": vehicle_id,
        "client_id":  client_id,
        "headers":    headers,
    }


# ── Always-run (no DB needed) ──────────────────────────────────────────────────

def test_structlog_configured():
    """structlog.configure() is called at import time — should always return a logger."""
    import structlog
    log = structlog.get_logger("smoke")
    assert log is not None


# ── Integration tests ──────────────────────────────────────────────────────────

@SKIP
async def test_health_ok(async_client: AsyncClient):
    r = await async_client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@SKIP
async def test_pdf_magic_bytes(smoke_ctx, async_client: AsyncClient):
    """PDF endpoint returns bytes whose first 4 chars are the PDF magic number."""
    ctx = smoke_ctx
    now = datetime.now(_UTC)
    r = await async_client.get(
        f"/reports/vehicles/{ctx['vehicle_id']}/pdf",
        headers=ctx["headers"],
        params={
            "from_ts": (now - timedelta(hours=3)).isoformat(),
            "to_ts": now.isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF", "Response does not start with PDF magic bytes"


@SKIP
async def test_pdf_404_unknown_vehicle(smoke_ctx, async_client: AsyncClient):
    ctx = smoke_ctx
    r = await async_client.get(
        f"/reports/vehicles/{uuid.uuid4()}/pdf",
        headers=ctx["headers"],
    )
    assert r.status_code == 404


@SKIP
async def test_full_pipeline(smoke_ctx, async_client: AsyncClient):
    """End-to-end: seeded telemetry → analytics KPIs > 0 → FleetView → PDF."""
    ctx = smoke_ctx
    now = datetime.now(_UTC)
    params = {
        "from": (now - timedelta(hours=3)).isoformat(),
        "to":   now.isoformat(),
    }

    # 1. Analytics
    r = await async_client.get(
        f"/analytics/vehicles/{ctx['vehicle_id']}/kpis",
        headers=ctx["headers"],
        params=params,
    )
    assert r.status_code == 200
    assert r.json()["reading_count"] > 0, "No readings found in analytics"

    # 2. FleetView (no Anthropic key → returns placeholder)
    r = await async_client.get(
        f"/fleetview/vehicles/{ctx['vehicle_id']}/summary",
        headers=ctx["headers"],
    )
    assert r.status_code == 200
    assert len(r.json()["summary"]) > 0

    # 3. PDF report (uses from_ts/to_ts, not from/to)
    r = await async_client.get(
        f"/reports/vehicles/{ctx['vehicle_id']}/pdf",
        headers=ctx["headers"],
        params={
            "from_ts": (now - timedelta(hours=3)).isoformat(),
            "to_ts":   now.isoformat(),
        },
    )
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
