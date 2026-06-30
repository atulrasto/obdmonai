"""Phase 5 — Tier A rules engine tests.

Unit tests (pure, no DB) + two end-to-end integration tests via process_message.
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
from app.tier_a.rules import (
    AlertState,
    Geofence,
    RuleResult,
    TelemetryReading,
    evaluate_all,
    haversine_m,
    rule_coolant,
    rule_fuel_anomaly,
    rule_geofences,
    rule_harsh_braking,
    rule_idling,
    rule_new_dtc,
    rule_overspeed,
)

SKIP = pytest.mark.skipif(
    os.environ.get("DATABASE_URL") is None,
    reason="DATABASE_URL not set",
)

# ── Helpers ────────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 6, 30, 12, 0, 0, tzinfo=timezone.utc)


def _reading(**kwargs) -> TelemetryReading:
    defaults = dict(
        device_id=str(uuid.uuid4()),
        vehicle_id=str(uuid.uuid4()),
        client_id=str(uuid.uuid4()),
        ts=_NOW,
        seq=1,
        obd_speed=50.0,
        obd_coolant=80.0,
        obd_rpm=1500.0,
        obd_fuel_level=60.0,
        imu_ax=0.0,
        gps_lat=0.0,
        gps_lon=0.0,
        dtc=[],
        ign=True,
    )
    defaults.update(kwargs)
    return TelemetryReading(**defaults)


def _active_alert(rule: str, **kwargs) -> AlertState:
    defaults = dict(
        id=str(uuid.uuid4()),
        rule=rule,
        state="active",
        fired_at=_NOW - timedelta(minutes=5),
        detail={},
    )
    defaults.update(kwargs)
    return AlertState(**defaults)


def _watching_alert(rule: str, **kwargs) -> AlertState:
    defaults = dict(
        id=str(uuid.uuid4()),
        rule=rule,
        state="watching",
        fired_at=_NOW - timedelta(minutes=1),
        detail={},
    )
    defaults.update(kwargs)
    return AlertState(**defaults)


# ── Rule 1: Overspeed ─────────────────────────────────────────────────────────

def test_overspeed_fires_at_threshold():
    r = rule_overspeed(_reading(obd_speed=120.0), None)
    assert r.action == "fire"


def test_overspeed_fires_above_threshold():
    r = rule_overspeed(_reading(obd_speed=150.0), None)
    assert r.action == "fire"
    assert r.detail["speed_kmh"] == 150.0


def test_overspeed_no_action_below_threshold():
    r = rule_overspeed(_reading(obd_speed=119.9), None)
    assert r.action == "none"


def test_overspeed_hysteresis_between_thresholds():
    """Active alert; speed between CLEAR=110 and SET=120 → no change."""
    r = rule_overspeed(_reading(obd_speed=115.0), _active_alert("overspeed"))
    assert r.action == "none"


def test_overspeed_clears_below_clear_threshold():
    r = rule_overspeed(_reading(obd_speed=109.9), _active_alert("overspeed"))
    assert r.action == "clear"


def test_overspeed_no_refire_while_active():
    """Already active at 130 km/h — should not fire again."""
    r = rule_overspeed(_reading(obd_speed=130.0), _active_alert("overspeed"))
    assert r.action == "none"


# ── Rule 2: Harsh Braking ─────────────────────────────────────────────────────

def test_harsh_braking_fires():
    r = rule_harsh_braking(_reading(imu_ax=-0.5), None)
    assert r.action == "fire"
    assert r.detail["braking_g"] == pytest.approx(0.5, abs=1e-3)


def test_harsh_braking_no_action_mild():
    r = rule_harsh_braking(_reading(imu_ax=-0.3), None)
    assert r.action == "none"


def test_harsh_braking_positive_imu_no_fire():
    """Forward acceleration should never trigger braking alert."""
    r = rule_harsh_braking(_reading(imu_ax=0.8), None)
    assert r.action == "none"


def test_harsh_braking_hysteresis():
    """Between CLEAR=0.3g and SET=0.5g → no change."""
    r = rule_harsh_braking(_reading(imu_ax=-0.4), _active_alert("harsh_braking"))
    assert r.action == "none"


def test_harsh_braking_clears():
    r = rule_harsh_braking(_reading(imu_ax=-0.2), _active_alert("harsh_braking"))
    assert r.action == "clear"


# ── Rule 3: Coolant Overheating ───────────────────────────────────────────────

def test_coolant_fires_at_threshold():
    r = rule_coolant(_reading(obd_coolant=100.0), None)
    assert r.action == "fire"
    assert r.severity == "critical"


def test_coolant_no_action_normal():
    r = rule_coolant(_reading(obd_coolant=95.0), None)
    assert r.action == "none"


def test_coolant_hysteresis():
    r = rule_coolant(_reading(obd_coolant=95.0), _active_alert("coolant_overheat"))
    assert r.action == "none"


def test_coolant_clears():
    r = rule_coolant(_reading(obd_coolant=89.9), _active_alert("coolant_overheat"))
    assert r.action == "clear"


# ── Rule 4: New DTC ───────────────────────────────────────────────────────────

def test_new_dtc_fires_on_first_code():
    r = rule_new_dtc(_reading(dtc=["P0300"]), None, None)
    assert r.action == "fire"
    assert r.detail["codes"] == ["P0300"]


def test_new_dtc_fires_on_new_code_added():
    r = rule_new_dtc(_reading(dtc=["P0300", "P0420"]), None, {"P0300"})
    assert r.action == "fire"
    assert "P0420" in r.detail["codes"]
    assert "P0300" not in r.detail["codes"]


def test_new_dtc_no_action_same_codes():
    r = rule_new_dtc(_reading(dtc=["P0300"]), None, {"P0300"})
    assert r.action == "none"


def test_new_dtc_clears_when_empty():
    r = rule_new_dtc(_reading(dtc=[]), _active_alert("new_dtc"), {"P0300"})
    assert r.action == "clear"


def test_new_dtc_no_action_when_codes_persist():
    r = rule_new_dtc(_reading(dtc=["P0300"]), _active_alert("new_dtc"), {"P0300"})
    assert r.action == "none"


# ── Rule 5: Excessive Idling ──────────────────────────────────────────────────

def test_idling_watches_on_first_idle():
    r = rule_idling(_reading(obd_speed=0.0, ign=True), None)
    assert r.action == "watch"
    assert "idle_since" in r.detail


def test_idling_no_watch_when_moving():
    r = rule_idling(_reading(obd_speed=5.0, ign=True), None)
    assert r.action == "none"


def test_idling_no_watch_when_ign_off():
    r = rule_idling(_reading(obd_speed=0.0, ign=False), None)
    assert r.action == "none"


def test_idling_still_watching_under_threshold():
    idle_since = _NOW - timedelta(seconds=240)
    alert = _watching_alert(
        "excessive_idle",
        fired_at=idle_since,
        detail={"idle_since": idle_since.isoformat()},
    )
    reading = _reading(obd_speed=0.0, ign=True, ts=_NOW)
    r = rule_idling(reading, alert, idle_set_sec=300)
    assert r.action == "none"


def test_idling_fires_after_threshold():
    idle_since = _NOW - timedelta(seconds=310)
    alert = _watching_alert(
        "excessive_idle",
        fired_at=idle_since,
        detail={"idle_since": idle_since.isoformat()},
    )
    reading = _reading(obd_speed=0.0, ign=True, ts=_NOW)
    r = rule_idling(reading, alert, idle_set_sec=300)
    assert r.action == "fire"
    assert r.detail["duration_sec"] >= 300


def test_idling_clears_on_movement():
    r = rule_idling(_reading(obd_speed=10.0, ign=True), _active_alert("excessive_idle"))
    assert r.action == "clear"


def test_idling_clears_watching_on_movement():
    r = rule_idling(_reading(obd_speed=10.0, ign=True), _watching_alert("excessive_idle"))
    assert r.action == "clear"


# ── Rule 6: Fuel Level Anomaly ────────────────────────────────────────────────

def test_fuel_anomaly_fires_on_big_drop():
    r = rule_fuel_anomaly(_reading(obd_fuel_level=40.0), None, prev_fuel=60.0)
    assert r.action == "fire"
    assert r.detail["drop_pct"] == pytest.approx(20.0, abs=0.1)
    assert r.severity == "critical"


def test_fuel_anomaly_no_action_small_drop():
    r = rule_fuel_anomaly(_reading(obd_fuel_level=50.0), None, prev_fuel=60.0)
    assert r.action == "none"


def test_fuel_anomaly_no_action_no_prev():
    r = rule_fuel_anomaly(_reading(obd_fuel_level=30.0), None, prev_fuel=None)
    assert r.action == "none"


def test_fuel_anomaly_clears_on_refuel():
    alert = _active_alert("fuel_anomaly", detail={"curr_pct": 30.0})
    r = rule_fuel_anomaly(_reading(obd_fuel_level=35.0), alert, prev_fuel=None)
    assert r.action == "clear"


def test_fuel_anomaly_no_clear_without_enough_refuel():
    alert = _active_alert("fuel_anomaly", detail={"curr_pct": 30.0})
    r = rule_fuel_anomaly(_reading(obd_fuel_level=31.0), alert, prev_fuel=None)
    assert r.action == "none"


# ── Haversine ─────────────────────────────────────────────────────────────────

def test_haversine_same_point():
    assert haversine_m(0.0, 0.0, 0.0, 0.0) == pytest.approx(0.0, abs=0.01)


def test_haversine_known_distance():
    # London (51.5074, -0.1278) to Paris (48.8566, 2.3522) ≈ 342 km
    dist = haversine_m(51.5074, -0.1278, 48.8566, 2.3522)
    assert 340_000 < dist < 345_000


# ── Rule 7: Geofence ─────────────────────────────────────────────────────────

def _gf(lat=0.0, lon=0.0, radius=1000.0) -> Geofence:
    return Geofence(
        id=str(uuid.uuid4()), name="office",
        center_lat=lat, center_lon=lon, radius_m=radius,
    )


def test_geofence_fires_on_entry():
    gf = _gf(lat=0.0, lon=0.0, radius=5000.0)
    r = rule_geofences(_reading(gps_lat=0.0, gps_lon=0.0), [gf], {})
    assert len(r) == 1 and r[0].action == "fire"


def test_geofence_no_action_outside():
    gf = _gf(lat=10.0, lon=10.0, radius=100.0)
    r = rule_geofences(_reading(gps_lat=0.0, gps_lon=0.0), [gf], {})
    assert r[0].action == "none"


def test_geofence_clears_on_exit():
    gf = _gf(lat=10.0, lon=10.0, radius=100.0)
    rule_name = f"geofence:{gf.id}"
    r = rule_geofences(_reading(gps_lat=0.0, gps_lon=0.0), [gf], {rule_name: _active_alert(rule_name)})
    assert r[0].action == "clear"


def test_geofence_no_refire_while_inside():
    gf = _gf(lat=0.0, lon=0.0, radius=5000.0)
    rule_name = f"geofence:{gf.id}"
    r = rule_geofences(_reading(gps_lat=0.0, gps_lon=0.0), [gf], {rule_name: _active_alert(rule_name)})
    assert r[0].action == "none"


# ── evaluate_all ─────────────────────────────────────────────────────────────

def test_evaluate_all_no_alerts_normal_reading():
    results = evaluate_all(_reading(), None, [], [])
    assert all(r.action == "none" for r in results)


def test_evaluate_all_overspeed_fires():
    results = evaluate_all(_reading(obd_speed=130.0), None, [], [])
    actions = {r.rule: r.action for r in results}
    assert actions["overspeed"] == "fire"


def test_evaluate_all_includes_geofence_results():
    gf = _gf(lat=0.0, lon=0.0, radius=5000.0)
    results = evaluate_all(_reading(gps_lat=0.0, gps_lon=0.0), None, [], [gf])
    assert any(r.rule == f"geofence:{gf.id}" for r in results)


# ── End-to-end integration tests ─────────────────────────────────────────────

@pytest_asyncio.fixture(scope="function")
async def rules_ctx(session_factory, async_client: AsyncClient):
    """Create tenant → vehicle → device; return context dict for e2e tests."""
    suffix = uuid.uuid4().hex[:8]
    slug = f"rules-{suffix}"
    email = f"rules-{suffix}@test.io"
    password = "Passw0rd!"
    serial = f"R5-{uuid.uuid4().hex[:8].upper()}"
    vin = f"RVW{uuid.uuid4().hex[:14].upper()}"

    r = await async_client.post("/clients", json={
        "name": f"RulesCo {suffix}",
        "slug": slug,
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
        "vin": vin, "make": "Ford", "model_name": "Transit", "year": 2023,
    })
    assert r.status_code == 201, r.text
    vehicle_id = r.json()["id"]

    r = await async_client.post("/devices", headers=headers, json={
        "vehicle_id": vehicle_id, "serial": serial, "firmware_version": "1.0",
    })
    assert r.status_code == 201, r.text
    device_id = r.json()["id"]

    yield {
        "topic": f"obdmonai/{client_id}/vehicle/{vin}/telemetry",
        "device_id": device_id,
        "vehicle_id": vehicle_id,
        "client_id": client_id,
        "headers": headers,
        "session_factory": session_factory,
    }


def _cbor_msg(device_id: str, seq: int, speed: float = 50.0,
              ts: datetime | None = None) -> bytes:
    if ts is None:
        ts = datetime.now(tz=timezone.utc)
    return cbor2.dumps({
        "device_id": device_id,
        "ts": int(ts.timestamp()),
        "seq": seq,
        "obd": {
            "speed": speed, "rpm": 1500.0, "coolant": 80.0, "fuel_level": 60.0,
            "load": 20.0, "throttle": 15.0, "intake_temp": 30.0, "run_time": 120,
        },
        "gps": {"lat": 0.0, "lon": 0.0, "alt": 0.0, "hdg": 0.0, "spd": 0.0},
        "imu": {"ax": 0.0, "ay": 0.0, "az": 0.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
        "dtc": [],
        "ign": True,
    })


@SKIP
async def test_overspeed_alert_created_then_cleared(rules_ctx, db_engine):
    """Overspeed telemetry → alert fires; normal speed → alert clears."""
    sf = rules_ctx["session_factory"]
    device_id = rules_ctx["device_id"]
    topic = rules_ctx["topic"]
    now = datetime.now(tz=timezone.utc)

    # Seq 1: overspeed → alert should fire
    await process_message(topic, _cbor_msg(device_id, seq=1, speed=130.0, ts=now), sf)

    async with db_engine.connect() as conn:
        count = (await conn.execute(
            text("SELECT tier_a_alert_count(:did, :rule, :state)"),
            {"did": device_id, "rule": "overspeed", "state": "active"},
        )).scalar()
    assert count == 1, f"Expected 1 active overspeed alert, got {count}"

    # Seq 2: normal speed → alert should clear
    await process_message(
        topic,
        _cbor_msg(device_id, seq=2, speed=100.0, ts=now + timedelta(seconds=10)),
        sf,
    )

    async with db_engine.connect() as conn:
        active = (await conn.execute(
            text("SELECT tier_a_alert_count(:did, :rule, :state)"),
            {"did": device_id, "rule": "overspeed", "state": "active"},
        )).scalar()
        cleared = (await conn.execute(
            text("SELECT tier_a_alert_count(:did, :rule, :state)"),
            {"did": device_id, "rule": "overspeed", "state": "cleared"},
        )).scalar()

    assert active == 0, "Expected overspeed alert to be cleared"
    assert cleared == 1, "Expected one cleared overspeed alert record"


@SKIP
async def test_alerts_api_list(rules_ctx, async_client: AsyncClient):
    """After firing an alert, GET /alerts returns it scoped to the tenant."""
    sf = rules_ctx["session_factory"]
    device_id = rules_ctx["device_id"]
    topic = rules_ctx["topic"]
    now = datetime.now(tz=timezone.utc)

    await process_message(topic, _cbor_msg(device_id, seq=200, speed=135.0, ts=now), sf)

    r = await async_client.get("/alerts", headers=rules_ctx["headers"], params={"state": "active"})
    assert r.status_code == 200
    data = r.json()
    assert any(
        a["rule"] == "overspeed" and a["device_id"] == device_id
        for a in data
    ), f"Overspeed alert not found in response: {data}"
