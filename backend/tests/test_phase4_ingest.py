"""Phase 4 acceptance tests — MQTT ingest pipeline (process_message unit tests)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import cbor2
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.ingest.worker import process_message
from app.main import app

SKIP = pytest.mark.skipif(
    __import__("os").environ.get("DATABASE_URL") is None,
    reason="DATABASE_URL not set",
)


async def _register_and_login(ac: AsyncClient, suffix: str) -> tuple[str, str]:
    reg = await ac.post("/clients", json={
        "name": f"Ingest Tenant {suffix}",
        "slug": f"ingest-{suffix}",
        "owner_email": f"ingest-{suffix}@example.com",
        "owner_password": "IngestPass789!",
    })
    assert reg.status_code == 201, reg.text
    login = await ac.post("/auth/login", json={
        "email": f"ingest-{suffix}@example.com",
        "password": "IngestPass789!",
    })
    assert login.status_code == 200, login.text
    return login.json()["access_token"], reg.json()["id"]


@pytest_asyncio.fixture
async def ingest_ctx(session_factory):
    """Provision tenant → vehicle → device; yield (topic, device_id, client_id, sf)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        suffix = uuid.uuid4().hex[:8]
        token, client_id = await _register_and_login(ac, suffix)
        headers = {"Authorization": f"Bearer {token}"}

        # 17-char alphanumeric VIN — unique per test run
        vin = f"TEST{uuid.uuid4().hex[:13].upper()}"

        v = await ac.post("/vehicles", headers=headers, json={
            "vin": vin, "make": "TestMake", "model_name": "TestModel", "year": 2024,
        })
        assert v.status_code == 201, v.text

        d = await ac.post("/devices", headers=headers, json={
            "vehicle_id": v.json()["id"], "serial": f"TEST-{suffix}",
        })
        assert d.status_code == 201, d.text
        device_id = d.json()["id"]

        topic = f"obdmonai/{client_id}/vehicle/{vin}/telemetry"
        yield topic, device_id, client_id, session_factory


def _cbor_payload(device_id: str, seq: int, ts: datetime | None = None, ign: bool = True) -> bytes:
    if ts is None:
        ts = datetime.now(timezone.utc)
    return cbor2.dumps({
        "device_id": device_id,
        "ts": ts.isoformat(),
        "seq": seq,
        "gps": {"lat": 18.52, "lon": 73.85, "alt": 560.0, "hdg": 270.0, "spd": 45.0},
        "obd": {
            "rpm": 2000.0, "speed": 45.0, "coolant": 88.0, "load": 35.0,
            "throttle": 22.0, "intake_temp": 30.0, "fuel_level": 65.0, "run_time": 120.0,
        },
        "imu": {"ax": 0.1, "ay": 0.02, "az": 9.8, "gx": 0.0, "gy": 0.0, "gz": 0.1},
        "dtc": [],
        "ign": ign,
    })


@SKIP
async def test_valid_insert_lands_in_db(ingest_ctx):
    """A well-formed CBOR message results in exactly one hypertable row."""
    topic, device_id, _, sf = ingest_ctx
    await process_message(topic, _cbor_payload(device_id, 1001), sf)

    async with sf() as session:
        exists = (await session.execute(
            text("SELECT ingest_telemetry_exists(:did, :seq)"),
            {"did": device_id, "seq": 1001},
        )).scalar()
    assert exists is True


@SKIP
async def test_duplicate_is_ignored(ingest_ctx):
    """Replaying the same (device_id, seq) does not create a second row."""
    topic, device_id, _, sf = ingest_ctx
    raw = _cbor_payload(device_id, 2001)
    await process_message(topic, raw, sf)
    await process_message(topic, raw, sf)

    async with sf() as session:
        count = (await session.execute(
            text("SELECT COUNT(*) FROM telemetry WHERE device_id = :did AND seq = :seq"),
            {"did": device_id, "seq": 2001},
        )).scalar()
    assert count == 1


@SKIP
async def test_out_of_order_stored_at_device_time(ingest_ctx):
    """Late/backfilled message is stored with the device event timestamp, not cloud arrival time."""
    topic, device_id, _, sf = ingest_ctx
    old_ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    await process_message(topic, _cbor_payload(device_id, 3001, ts=old_ts), sf)

    async with sf() as session:
        row = (await session.execute(
            text("SELECT time FROM telemetry WHERE device_id = :did AND seq = :seq"),
            {"did": device_id, "seq": 3001},
        )).fetchone()
    assert row is not None
    stored = row.time if row.time.tzinfo else row.time.replace(tzinfo=timezone.utc)
    assert abs((stored - old_ts).total_seconds()) < 2


@SKIP
async def test_spoofed_tenant_rejected(ingest_ctx):
    """Message whose topic client_id does not match the device's registered client is dropped."""
    topic, device_id, _, sf = ingest_ctx
    parts = topic.split("/")
    spoofed_topic = f"obdmonai/{uuid.uuid4()}/vehicle/{parts[3]}/telemetry"
    await process_message(spoofed_topic, _cbor_payload(device_id, 4001), sf)

    async with sf() as session:
        exists = (await session.execute(
            text("SELECT ingest_telemetry_exists(:did, :seq)"),
            {"did": device_id, "seq": 4001},
        )).scalar()
    assert exists is False


@SKIP
async def test_malformed_payload_rejected(ingest_ctx):
    """Garbage bytes that fail CBOR and JSON decoding are dropped without crashing."""
    topic, device_id, _, sf = ingest_ctx
    await process_message(topic, b"\xff\xfe not-cbor-not-json", sf)

    async with sf() as session:
        count = (await session.execute(
            text("SELECT COUNT(*) FROM telemetry WHERE device_id = :did"),
            {"did": device_id},
        )).scalar()
    assert count == 0
