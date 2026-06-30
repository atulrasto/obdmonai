"""Phase 7 — Tier B ML module acceptance tests.

Structure
---------
Pure unit tests (no DB, always run):
  test_feature_extraction_empty
  test_feature_extraction_values
  test_driver_model_safe_beats_risky
  test_maintenance_detects_anomaly

Architectural isolation tests (no DB, always run):
  test_tier_b_no_tier_a_import

Integration tests (require DATABASE_URL):
  test_driver_score_endpoint
  test_maintenance_endpoint
  test_scores_readonly_guard
  test_scores_tenant_isolation
"""
from __future__ import annotations

import ast
import os
import pathlib
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import cbor2
import numpy as np
import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.tier_b.driver_score import predict_score, train_driver_model
from app.tier_b.features import FEATURE_DIM, extract_features
from app.tier_b.maintenance import predict_anomaly, train_maintenance_model

SKIP = pytest.mark.skipif(
    os.environ.get("DATABASE_URL") is None,
    reason="DATABASE_URL not set",
)

_UTC = timezone.utc


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row(
    speed=60.0, rpm=1500.0, coolant=85.0, fuel=70.0,
    imu_ax=0.0, ign=True,
):
    return SimpleNamespace(
        obd_speed=speed, obd_rpm=rpm, obd_coolant=coolant,
        obd_fuel_level=fuel, imu_ax=imu_ax, ign=ign,
    )


def _safe_features() -> np.ndarray:
    """Feature vector for a calm, safe driver."""
    rows = [_row(speed=50.0, rpm=1400.0, coolant=83.0, imu_ax=0.0) for _ in range(20)]
    return extract_features(rows)


def _risky_features() -> np.ndarray:
    """Feature vector for an aggressive driver (high speed, harsh events)."""
    rows = (
        [_row(speed=130.0, rpm=4500.0, coolant=97.0, imu_ax=-0.8) for _ in range(10)]
        + [_row(speed=140.0, rpm=5000.0, coolant=99.0, imu_ax=0.9) for _ in range(10)]
    )
    return extract_features(rows)


def _healthy_features() -> np.ndarray:
    """Realistic healthy readings with natural speed/RPM variation.

    Uses a fixed seed so the feature vector is deterministic.  Variation is
    important: a window with speed_std=0 looks statistically anomalous to an
    IsolationForest trained on N(8, 3) std values.
    """
    rng = np.random.default_rng(7)
    rows = [_row(
        speed=float(np.clip(rng.normal(50, 8), 20, 90)),
        rpm=float(np.clip(rng.normal(1400, 150), 800, 2500)),
        coolant=float(np.clip(rng.normal(83, 4), 70, 90)),
    ) for _ in range(30)]
    return extract_features(rows)


def _anomalous_features() -> np.ndarray:
    """Severe overheating + over-revving."""
    rows = [_row(speed=0.0, rpm=7500.0, coolant=118.0, imu_ax=-0.9) for _ in range(30)]
    return extract_features(rows)


# ── Pure unit tests ───────────────────────────────────────────────────────────

def test_feature_extraction_empty():
    vec = extract_features([])
    assert vec.shape == (FEATURE_DIM,)
    assert np.all(vec == 0)


def test_feature_extraction_values():
    rows = [_row(speed=80.0, rpm=2000.0, coolant=90.0, imu_ax=-0.5)]
    vec = extract_features(rows)
    assert vec.shape == (FEATURE_DIM,)
    assert vec[0] == pytest.approx(80.0)   # speed_avg
    assert vec[1] == pytest.approx(80.0)   # speed_max
    assert vec[3] == pytest.approx(2000.0) # rpm_avg
    assert vec[5] == pytest.approx(90.0)   # coolant_max
    assert vec[6] == pytest.approx(1.0)    # harsh_brake_r (imu_ax=-0.5 < -0.3)
    assert vec[9] == pytest.approx(0.0)    # overspeed_r (80 < 100)


def test_feature_extraction_idle():
    rows = [_row(speed=0.5, ign=True), _row(speed=60.0, ign=True)]
    vec = extract_features(rows)
    assert vec[8] == pytest.approx(0.5)  # idle_ratio: 1 of 2 rows idle


def test_feature_extraction_overspeed():
    rows = [_row(speed=110.0), _row(speed=50.0), _row(speed=120.0)]
    vec = extract_features(rows)
    assert vec[9] == pytest.approx(2 / 3)  # 2 of 3 rows > 100 km/h


def test_driver_model_safe_beats_risky():
    model = train_driver_model()
    safe_score  = predict_score(model, _safe_features())
    risky_score = predict_score(model, _risky_features())
    assert safe_score > risky_score, f"safe={safe_score} risky={risky_score}"
    assert safe_score > 60.0, f"safe driver scored {safe_score} — expected > 60"
    assert risky_score < 40.0, f"risky driver scored {risky_score} — expected < 40"


def test_driver_model_score_range():
    model = train_driver_model()
    for feat in [_safe_features(), _risky_features()]:
        score = predict_score(model, feat)
        assert 0.0 <= score <= 100.0


def test_maintenance_healthy_not_anomaly():
    model = train_maintenance_model()
    result = predict_anomaly(model, _healthy_features())
    assert result["is_anomaly"] is False
    assert isinstance(result["anomaly_score"], float)


def test_maintenance_detects_anomaly():
    model = train_maintenance_model()
    result = predict_anomaly(model, _anomalous_features())
    assert result["is_anomaly"] is True, (
        f"Severe anomalous reading not detected; score={result['anomaly_score']}"
    )


# ── Architecture test ─────────────────────────────────────────────────────────

def test_tier_b_no_tier_a_import():
    """Tier B modules must never import from tier_a (CLAUDE.md invariant)."""
    tier_b_dir = pathlib.Path("app/tier_b")
    if not tier_b_dir.exists():
        tier_b_dir = pathlib.Path(__file__).parent.parent / "app" / "tier_b"

    violations: list[str] = []
    for py_file in sorted(tier_b_dir.rglob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("app.tier_a") or node.module == "tier_a":
                    violations.append(f"{py_file}:{node.lineno}: from {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("app.tier_a"):
                        violations.append(f"{py_file}:{node.lineno}: import {alias.name}")

    assert not violations, "tier_b imports tier_a:\n" + "\n".join(violations)


# ── Integration fixtures ──────────────────────────────────────────────────────

def _cbor_msg(device_id: str, seq: int, ts: datetime, speed: float = 60.0) -> bytes:
    return cbor2.dumps({
        "device_id": device_id,
        "ts": int(ts.timestamp()),
        "seq": seq,
        "obd": {
            "speed": speed, "rpm": 1500.0, "coolant": 85.0, "fuel_level": 70.0,
            "load": 25.0, "throttle": 18.0, "intake_temp": 28.0, "run_time": 120,
        },
        "gps": {"lat": 18.5, "lon": 73.9, "alt": 550.0, "hdg": 90.0, "spd": speed / 3.6},
        "imu": {"ax": 0.0, "ay": 0.0, "az": 0.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
        "dtc": [],
        "ign": True,
    })


@pytest_asyncio.fixture(scope="function")
async def ml_ctx(session_factory, async_client: AsyncClient):
    """Provision a fresh tenant with 20 normal telemetry readings (last 2 h)."""
    from app.ingest.worker import process_message

    suffix = uuid.uuid4().hex[:8]
    email = f"ml-{suffix}@test.io"
    pw = "Ml7estPass!"
    vin = f"ML{uuid.uuid4().hex[:15].upper()}"

    r = await async_client.post("/clients", json={
        "name": f"MLCo {suffix}", "slug": f"ml-{suffix}",
        "owner_email": email, "owner_password": pw,
    })
    assert r.status_code == 201, r.text
    client_id = r.json()["id"]

    r = await async_client.post("/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.post("/vehicles", headers=headers, json={
        "vin": vin, "make": "Scania", "model_name": "R450", "year": 2023,
    })
    assert r.status_code == 201, r.text
    vehicle_id = r.json()["id"]

    r = await async_client.post("/devices", headers=headers, json={
        "vehicle_id": vehicle_id,
        "serial": f"ML-{uuid.uuid4().hex[:8].upper()}",
        "firmware_version": "2.0",
    })
    assert r.status_code == 201, r.text
    device_id = r.json()["id"]

    topic = f"obdmonai/{client_id}/vehicle/{vin}/telemetry"
    base_ts = datetime.now(_UTC) - timedelta(hours=2)

    for seq in range(1, 6):
        ts = base_ts + timedelta(seconds=seq * 10)
        raw = _cbor_msg(device_id, seq, ts, speed=60.0)
        await process_message(topic, raw, session_factory)

    yield {
        "vehicle_id": vehicle_id,
        "device_id": device_id,
        "client_id": client_id,
        "headers": headers,
    }


# ── Integration tests ─────────────────────────────────────────────────────────

@SKIP
async def test_driver_score_endpoint(ml_ctx, async_client: AsyncClient):
    """GET /scores/vehicles/{id}/driver returns 200 with a valid score."""
    ctx = ml_ctx
    r = await async_client.get(
        f"/scores/vehicles/{ctx['vehicle_id']}/driver",
        headers=ctx["headers"],
        params={"hours": 24},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["vehicle_id"] == ctx["vehicle_id"]
    assert data["score"] is not None
    assert 0.0 <= data["score"] <= 100.0
    assert data["window_hours"] == 24


@SKIP
async def test_maintenance_endpoint(ml_ctx, async_client: AsyncClient):
    """GET /scores/vehicles/{id}/maintenance returns 200 with a boolean decision."""
    ctx = ml_ctx
    r = await async_client.get(
        f"/scores/vehicles/{ctx['vehicle_id']}/maintenance",
        headers=ctx["headers"],
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["vehicle_id"] == ctx["vehicle_id"]
    assert isinstance(data["is_anomaly"], bool)
    assert isinstance(data["anomaly_score"], float)


@SKIP
async def test_scores_no_data_returns_nulls(ml_ctx, async_client: AsyncClient):
    """Vehicle with no recent telemetry returns null score/anomaly."""
    ctx = ml_ctx
    r = await async_client.get(
        f"/scores/vehicles/{ctx['vehicle_id']}/driver",
        headers=ctx["headers"],
        params={"hours": 0},   # zero-hour window → no rows
    )
    assert r.status_code == 200, r.text
    assert r.json()["score"] is None


@SKIP
async def test_scores_readonly_guard(ml_ctx, async_client: AsyncClient):
    """The scores API exposes no write endpoints."""
    vid = ml_ctx["vehicle_id"]
    hdrs = ml_ctx["headers"]
    for method, path in [
        ("put",    f"/scores/vehicles/{vid}/driver"),
        ("delete", f"/scores/vehicles/{vid}/driver"),
        ("post",   f"/scores/vehicles/{vid}/driver"),
        ("put",    f"/scores/vehicles/{vid}/maintenance"),
        ("delete", f"/scores/vehicles/{vid}/maintenance"),
        ("post",   f"/scores/vehicles/{vid}/maintenance"),
    ]:
        r = await getattr(async_client, method)(path, headers=hdrs)
        assert r.status_code in (404, 405), (
            f"{method.upper()} {path} returned {r.status_code}"
        )


@SKIP
async def test_scores_tenant_isolation(ml_ctx, async_client: AsyncClient):
    """Tenant A cannot read scores for Tenant B's vehicle."""
    # Create Tenant B
    suffix = uuid.uuid4().hex[:8]
    r = await async_client.post("/clients", json={
        "name": f"MLBCo {suffix}", "slug": f"ml-b-{suffix}",
        "owner_email": f"ml-b-{suffix}@test.io",
        "owner_password": "Ml7estPass!",
    })
    assert r.status_code == 201
    r2 = await async_client.post("/auth/login", json={
        "email": f"ml-b-{suffix}@test.io", "password": "Ml7estPass!",
    })
    hdrs_b = {"Authorization": f"Bearer {r2.json()['access_token']}"}

    r = await async_client.post("/vehicles", headers=hdrs_b, json={
        "vin": f"BV{uuid.uuid4().hex[:15].upper()}",
        "make": "B", "model_name": "V", "year": 2022,
    })
    assert r.status_code == 201
    vehicle_b_id = r.json()["id"]

    # Tenant A queries Tenant B's vehicle → score None (no telemetry under A's client_id)
    r = await async_client.get(
        f"/scores/vehicles/{vehicle_b_id}/driver",
        headers=ml_ctx["headers"],
        params={"hours": 24},
    )
    assert r.status_code == 200
    assert r.json()["score"] is None
