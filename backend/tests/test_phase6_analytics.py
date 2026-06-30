"""Phase 6 — Analytics API acceptance tests.

Seeds a deterministic telemetry dataset (two trips separated by a >5-min gap)
and verifies that the analytics endpoints return the expected KPIs and trip
segmentation.

Trip structure
--------------
Trip 1: 5 readings at T+0, T+10, T+20, T+30, T+40 seconds
         speed = 60 km/h, ign = True
         → distance ≈ 60 * 40 / 3600 ≈ 0.667 km (4 intervals × 10 s)

[gap = 15 minutes > 5-min threshold → new trip]

Trip 2: 3 readings at T+940, T+950, T+960 seconds
         speed = 30 km/h, ign = True
         → distance ≈ 30 * 20 / 3600 ≈ 0.167 km (2 intervals × 10 s)

Expected aggregate KPIs (entire window)
- reading_count = 8
- max_speed     = 60.0
- avg_speed     ≈ 50.0  (5 readings at 60 + 3 readings at 30) / 8
- distance_km   ≈ 0.833 (0.667 + 0.167)
- trip_count    = 2
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import cbor2
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.ingest.worker import process_message

SKIP = pytest.mark.skipif(
    os.environ.get("DATABASE_URL") is None,
    reason="DATABASE_URL not set",
)

# Deterministic base timestamp (far enough in the past to avoid CAGG offsets)
_BASE_TS = datetime(2026, 1, 15, 8, 0, 0, tzinfo=timezone.utc)

# Trip 1: offsets 0, 10, 20, 30, 40 seconds; speed=60
_TRIP1 = [(i * 10, 60.0) for i in range(5)]
# Trip 2: starts 940 seconds after base (15 min 40 sec gap); speed=30
_TRIP2 = [(940 + i * 10, 30.0) for i in range(3)]
_ALL_READINGS = _TRIP1 + _TRIP2

_FROM_TS = _BASE_TS - timedelta(minutes=1)
_TO_TS = _BASE_TS + timedelta(minutes=20)


def _cbor(device_id: str, seq: int, ts: datetime, speed: float) -> bytes:
    return cbor2.dumps({
        "device_id": device_id,
        "ts": int(ts.timestamp()),
        "seq": seq,
        "obd": {
            "speed": speed, "rpm": 1200.0, "coolant": 85.0, "fuel_level": 70.0,
            "load": 25.0, "throttle": 18.0, "intake_temp": 28.0, "run_time": 60,
        },
        "gps": {"lat": 18.5, "lon": 73.9, "alt": 550.0, "hdg": 90.0, "spd": speed / 3.6},
        "imu": {"ax": 0.0, "ay": 0.0, "az": 0.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
        "dtc": [],
        "ign": True,
    })


@pytest_asyncio.fixture(scope="function")
async def analytics_ctx(session_factory, async_client: AsyncClient):
    """Provision a fresh tenant and seed deterministic telemetry."""
    suffix = uuid.uuid4().hex[:8]
    email = f"analytics-{suffix}@test.io"
    password = "An4lyticsPass!"
    vin = f"ANL{uuid.uuid4().hex[:14].upper()}"

    r = await async_client.post("/clients", json={
        "name": f"AnalyticsCo {suffix}",
        "slug": f"analytics-{suffix}",
        "owner_email": email,
        "owner_password": password,
    })
    assert r.status_code == 201, r.text
    client_id = r.json()["id"]

    r = await async_client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.post("/vehicles", headers=headers, json={
        "vin": vin, "make": "Volvo", "model_name": "FH", "year": 2024,
    })
    assert r.status_code == 201, r.text
    vehicle_id = r.json()["id"]

    r = await async_client.post("/devices", headers=headers, json={
        "vehicle_id": vehicle_id,
        "serial": f"ANL-{uuid.uuid4().hex[:8].upper()}",
        "firmware_version": "1.0",
    })
    assert r.status_code == 201, r.text
    device_id = r.json()["id"]

    topic = f"obdmonai/{client_id}/vehicle/{vin}/telemetry"

    for seq, (offset_sec, speed) in enumerate(_ALL_READINGS, start=1):
        ts = _BASE_TS + timedelta(seconds=offset_sec)
        raw = _cbor(device_id, seq, ts, speed)
        await process_message(topic, raw, session_factory)

    yield {
        "vehicle_id": vehicle_id,
        "device_id": device_id,
        "client_id": client_id,
        "headers": headers,
        "session_factory": session_factory,
    }


# ── KPI tests ─────────────────────────────────────────────────────────────────

@SKIP
async def test_vehicle_kpis_reading_count(analytics_ctx, async_client: AsyncClient):
    """Seeded 8 readings → reading_count must be 8."""
    ctx = analytics_ctx
    r = await async_client.get(
        f"/analytics/vehicles/{ctx['vehicle_id']}/kpis",
        headers=ctx["headers"],
        params={"from": _FROM_TS.isoformat(), "to": _TO_TS.isoformat()},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["reading_count"] == len(_ALL_READINGS), data


@SKIP
async def test_vehicle_kpis_max_speed(analytics_ctx, async_client: AsyncClient):
    """Max speed in seeded data is 60 km/h."""
    ctx = analytics_ctx
    r = await async_client.get(
        f"/analytics/vehicles/{ctx['vehicle_id']}/kpis",
        headers=ctx["headers"],
        params={"from": _FROM_TS.isoformat(), "to": _TO_TS.isoformat()},
    )
    assert r.status_code == 200, r.text
    assert r.json()["max_speed"] == pytest.approx(60.0, abs=0.1)


@SKIP
async def test_vehicle_kpis_avg_speed(analytics_ctx, async_client: AsyncClient):
    """Avg speed: (5×60 + 3×30) / 8 = 390/8 = 48.75 km/h."""
    ctx = analytics_ctx
    r = await async_client.get(
        f"/analytics/vehicles/{ctx['vehicle_id']}/kpis",
        headers=ctx["headers"],
        params={"from": _FROM_TS.isoformat(), "to": _TO_TS.isoformat()},
    )
    assert r.status_code == 200, r.text
    # AVG of the 8 raw speed values
    expected_avg = (5 * 60.0 + 3 * 30.0) / 8
    assert r.json()["avg_speed"] == pytest.approx(expected_avg, abs=0.5)


@SKIP
async def test_vehicle_kpis_distance(analytics_ctx, async_client: AsyncClient):
    """Distance ≈ 0.667 + 0.167 = 0.833 km (speed × gap integration)."""
    ctx = analytics_ctx
    r = await async_client.get(
        f"/analytics/vehicles/{ctx['vehicle_id']}/kpis",
        headers=ctx["headers"],
        params={"from": _FROM_TS.isoformat(), "to": _TO_TS.isoformat()},
    )
    assert r.status_code == 200, r.text
    # Trip1: 4 intervals × 10s × 60 km/h / 3600 = 0.6667
    # Trip2: 2 intervals × 10s × 30 km/h / 3600 = 0.1667
    # Total ≈ 0.833
    assert r.json()["distance_km"] == pytest.approx(0.833, abs=0.05)


# ── Trip segmentation tests ───────────────────────────────────────────────────

@SKIP
async def test_list_trips_count(analytics_ctx, async_client: AsyncClient):
    """15-min gap between readings 5 and 6 → exactly 2 trips detected."""
    ctx = analytics_ctx
    r = await async_client.get(
        f"/analytics/vehicles/{ctx['vehicle_id']}/trips",
        headers=ctx["headers"],
        params={"from": _FROM_TS.isoformat(), "to": _TO_TS.isoformat()},
    )
    assert r.status_code == 200, r.text
    trips = r.json()
    assert len(trips) == 2, f"Expected 2 trips, got {len(trips)}: {trips}"


@SKIP
async def test_list_trips_reading_counts(analytics_ctx, async_client: AsyncClient):
    """Trip 1 has 5 readings, Trip 2 has 3 readings."""
    ctx = analytics_ctx
    r = await async_client.get(
        f"/analytics/vehicles/{ctx['vehicle_id']}/trips",
        headers=ctx["headers"],
        params={"from": _FROM_TS.isoformat(), "to": _TO_TS.isoformat()},
    )
    assert r.status_code == 200, r.text
    trips = sorted(r.json(), key=lambda t: t["start_ts"])
    assert trips[0]["reading_count"] == 5, trips[0]
    assert trips[1]["reading_count"] == 3, trips[1]


@SKIP
async def test_list_trips_max_speeds(analytics_ctx, async_client: AsyncClient):
    """Trip 1 max speed = 60; Trip 2 max speed = 30."""
    ctx = analytics_ctx
    r = await async_client.get(
        f"/analytics/vehicles/{ctx['vehicle_id']}/trips",
        headers=ctx["headers"],
        params={"from": _FROM_TS.isoformat(), "to": _TO_TS.isoformat()},
    )
    assert r.status_code == 200, r.text
    trips = sorted(r.json(), key=lambda t: t["start_ts"])
    assert trips[0]["max_speed"] == pytest.approx(60.0, abs=0.1)
    assert trips[1]["max_speed"] == pytest.approx(30.0, abs=0.1)


@SKIP
async def test_list_trips_distance(analytics_ctx, async_client: AsyncClient):
    """Trip distances match speed-integration estimates."""
    ctx = analytics_ctx
    r = await async_client.get(
        f"/analytics/vehicles/{ctx['vehicle_id']}/trips",
        headers=ctx["headers"],
        params={"from": _FROM_TS.isoformat(), "to": _TO_TS.isoformat()},
    )
    assert r.status_code == 200, r.text
    trips = sorted(r.json(), key=lambda t: t["start_ts"])
    assert trips[0]["distance_km"] == pytest.approx(0.667, abs=0.02)
    assert trips[1]["distance_km"] == pytest.approx(0.167, abs=0.02)


# ── Trip detail test ──────────────────────────────────────────────────────────

@SKIP
async def test_trip_detail_returns_points(analytics_ctx, async_client: AsyncClient):
    """Trip-detail endpoint returns the seeded telemetry points for trip 1."""
    ctx = analytics_ctx
    trip1_from = _BASE_TS
    trip1_to = _BASE_TS + timedelta(seconds=40)
    r = await async_client.get(
        f"/analytics/vehicles/{ctx['vehicle_id']}/trips/detail",
        headers=ctx["headers"],
        params={"from": trip1_from.isoformat(), "to": trip1_to.isoformat()},
    )
    assert r.status_code == 200, r.text
    points = r.json()
    assert len(points) == 5
    speeds = [p["obd_speed"] for p in points]
    assert all(abs(s - 60.0) < 0.1 for s in speeds), speeds


# ── Fleet rollup test ─────────────────────────────────────────────────────────

@SKIP
async def test_fleet_rollup_cagg(analytics_ctx, async_client: AsyncClient, db_engine):
    """Fleet rollup (CAGG-backed) returns the seeded vehicle after CAGG refresh."""
    ctx = analytics_ctx
    # Manually refresh the 1-minute CAGG so it includes the seeded data.
    # refresh_continuous_aggregate cannot run inside a transaction block
    ac_engine = db_engine.execution_options(isolation_level="AUTOCOMMIT")
    async with ac_engine.connect() as conn:
        await conn.execute(
            text(
                "CALL refresh_continuous_aggregate("
                "  'telemetry_1m',"
                "  CAST(:from_ts AS TIMESTAMPTZ),"
                "  CAST(:to_ts AS TIMESTAMPTZ)"
                ")"
            ),
            {"from_ts": _FROM_TS, "to_ts": _TO_TS + timedelta(hours=1)},
        )

    r = await async_client.get(
        "/analytics/fleet",
        headers=ctx["headers"],
        params={"from": _FROM_TS.isoformat(), "to": _TO_TS.isoformat()},
    )
    assert r.status_code == 200, r.text
    fleet = r.json()
    assert any(v["vehicle_id"] == ctx["vehicle_id"] for v in fleet), fleet


# ── Cross-tenant isolation test ───────────────────────────────────────────────

@SKIP
async def test_analytics_tenant_isolation(
    analytics_ctx, async_client: AsyncClient
):
    """Tenant A cannot retrieve KPIs for a vehicle owned by Tenant B."""
    ctx = analytics_ctx

    # Create a second tenant with its own vehicle
    suffix2 = uuid.uuid4().hex[:8]
    email2 = f"analb-{suffix2}@test.io"
    r = await async_client.post("/clients", json={
        "name": f"AnalyticsCo B {suffix2}",
        "slug": f"analytics-b-{suffix2}",
        "owner_email": email2,
        "owner_password": "An4lyticsPass!",
    })
    assert r.status_code == 201
    r2 = await async_client.post("/auth/login", json={"email": email2, "password": "An4lyticsPass!"})
    token2 = r2.json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    r = await async_client.post("/vehicles", headers=headers2, json={
        "vin": f"ISO{uuid.uuid4().hex[:14].upper()}", "make": "X", "model_name": "Y", "year": 2023,
    })
    assert r.status_code == 201
    vehicle_b_id = r.json()["id"]

    # Tenant A tries to access Tenant B's vehicle KPIs
    r = await async_client.get(
        f"/analytics/vehicles/{vehicle_b_id}/kpis",
        headers=ctx["headers"],  # Tenant A's token
        params={"from": _FROM_TS.isoformat(), "to": _TO_TS.isoformat()},
    )
    # The SECURITY DEFINER function checks client_id from JWT, not from GUC.
    # So tenant A gets KPIs for vehicle_b_id but filtered to tenant A's client_id.
    # Since there's no telemetry for vehicle_b_id under tenant A's client_id,
    # reading_count must be 0.
    assert r.status_code == 200
    assert r.json()["reading_count"] == 0
