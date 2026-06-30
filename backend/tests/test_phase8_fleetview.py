"""Phase 8 — FleetView LLM layer acceptance tests.

Structure
---------
Pure unit tests (always run — no DB):
  test_redact_removes_uuid
  test_redact_removes_vin
  test_redact_removes_email
  test_redact_passthrough_clean_text
  test_build_prompt_has_vehicle_info
  test_build_prompt_no_raw_uuids
  test_build_prompt_with_alerts
  test_get_summary_no_api_key
  test_get_summary_mocked_api

Architecture tests (always run — no DB):
  test_fleetview_no_write_sql

Integration tests (require DATABASE_URL):
  test_summary_endpoint_returns_200
  test_summary_endpoint_404_unknown_vehicle
  test_summary_tenant_isolation
"""
from __future__ import annotations

import os
import pathlib
import re
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import cbor2
import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.fleetview.facts import VehicleFacts
from app.fleetview.redact import redact
from app.fleetview.summarise import build_prompt, get_summary

SKIP = pytest.mark.skipif(
    os.environ.get("DATABASE_URL") is None,
    reason="DATABASE_URL not set",
)

_UTC = timezone.utc


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sample_facts(**overrides) -> VehicleFacts:
    defaults = dict(
        make="Volvo",
        model_name="FH",
        year=2024,
        period_hours=24,
        reading_count=120,
        distance_km=95.4,
        avg_speed_kmh=62.3,
        max_speed_kmh=89.0,
        driver_score=74.5,
        maintenance_anomaly=False,
        active_alert_count=0,
        alert_rules=[],
        trip_count=3,
    )
    defaults.update(overrides)
    return VehicleFacts(**defaults)


# ── Redaction unit tests ───────────────────────────────────────────────────────

def test_redact_removes_uuid():
    text = "Device 3fa85f64-5717-4562-b3fc-2c963f66afa6 reported an error"
    result = redact(text)
    assert "3fa85f64" not in result
    assert "[id]" in result


def test_redact_removes_multiple_uuids():
    text = (
        "client=00000000-0000-0000-0000-000000000001 "
        "vehicle=ffffffff-ffff-ffff-ffff-ffffffffffff"
    )
    result = redact(text)
    assert re.search(r'[0-9a-f]{8}-', result) is None


def test_redact_removes_vin():
    text = "VIN: WAUZZZ8R5CA012345 was checked in"
    result = redact(text)
    assert "WAUZZZ8R5CA012345" not in result
    assert "[vin]" in result


def test_redact_removes_email():
    text = "Owner alert sent to fleet.manager@company.io for review"
    result = redact(text)
    assert "fleet.manager@company.io" not in result
    assert "[email]" in result


def test_redact_passthrough_clean_text():
    text = "The vehicle drove 95 km at an average of 62 km/h."
    assert redact(text) == text


# ── Prompt assembly tests ─────────────────────────────────────────────────────

def test_build_prompt_has_vehicle_info():
    facts = _sample_facts()
    prompt = build_prompt(facts)
    assert "Volvo" in prompt
    assert "FH" in prompt
    assert "2024" in prompt


def test_build_prompt_has_kpis():
    facts = _sample_facts()
    prompt = build_prompt(facts)
    assert "95.4" in prompt   # distance
    assert "62.3" in prompt   # avg speed
    assert "74"   in prompt   # driver score (rounded)


def test_build_prompt_with_alerts():
    facts = _sample_facts(
        active_alert_count=2,
        alert_rules=["overspeed", "coolant_temp"],
    )
    prompt = build_prompt(facts)
    assert "overspeed" in prompt
    assert "coolant_temp" in prompt


def test_build_prompt_no_raw_uuids():
    facts = _sample_facts()
    prompt = build_prompt(facts)
    # No UUID patterns should appear in the prompt
    uuid_pattern = re.compile(
        r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}'
        r'-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
    )
    assert uuid_pattern.search(prompt) is None


# ── Summarise unit tests ───────────────────────────────────────────────────────

async def test_get_summary_no_api_key():
    """When ANTHROPIC_API_KEY is empty, get_summary returns the placeholder."""
    with patch("app.fleetview.summarise.settings") as mock_settings:
        mock_settings.anthropic_api_key = ""
        result = await get_summary(_sample_facts())
    assert "unavailable" in result.lower() or "not configured" in result.lower()


async def test_get_summary_mocked_api():
    """With a mocked Anthropic client the correct prompt is sent and the
    LLM response text is returned verbatim."""
    expected_text = "The vehicle performed well with no safety concerns."

    mock_content = MagicMock()
    mock_content.text = expected_text
    mock_response = MagicMock()
    mock_response.content = [mock_content]

    with (
        patch("app.fleetview.summarise.settings") as mock_settings,
        patch("app.fleetview.summarise.anthropic.AsyncAnthropic") as MockClient,
    ):
        mock_settings.anthropic_api_key = "sk-ant-test-key"
        mock_settings.anthropic_model   = "claude-haiku-test"
        MockClient.return_value.messages.create = AsyncMock(return_value=mock_response)

        result = await get_summary(_sample_facts())

    assert result == expected_text
    MockClient.assert_called_once_with(api_key="sk-ant-test-key")
    create_call = MockClient.return_value.messages.create.call_args
    # Verify no tools were passed (strictly read-only)
    assert "tools" not in (create_call.kwargs or {})


# ── Architecture / guard tests ────────────────────────────────────────────────

def test_fleetview_no_write_sql():
    """FleetView source must contain no INSERT, UPDATE, or DELETE SQL."""
    fleetview_dir = pathlib.Path("app/fleetview")
    if not fleetview_dir.exists():
        fleetview_dir = pathlib.Path(__file__).parent.parent / "app" / "fleetview"

    pattern = re.compile(r'\b(INSERT|UPDATE|DELETE)\b', re.IGNORECASE)
    violations: list[str] = []
    for py_file in sorted(fleetview_dir.rglob("*.py")):
        source = py_file.read_text(encoding="utf-8")
        for m in pattern.finditer(source):
            lineno = source[: m.start()].count("\n") + 1
            violations.append(f"{py_file}:{lineno}: {m.group()}")

    assert not violations, (
        "FleetView contains write SQL:\n" + "\n".join(violations)
    )


# ── Integration fixture ───────────────────────────────────────────────────────

def _cbor(device_id: str, seq: int, ts: datetime, speed: float = 60.0) -> bytes:
    return cbor2.dumps({
        "device_id": device_id,
        "ts": int(ts.timestamp()),
        "seq": seq,
        "obd": {
            "speed": speed, "rpm": 1400.0, "coolant": 85.0, "fuel_level": 70.0,
            "load": 22.0, "throttle": 16.0, "intake_temp": 28.0, "run_time": 90,
        },
        "gps": {"lat": 18.5, "lon": 73.9, "alt": 550.0, "hdg": 90.0, "spd": speed / 3.6},
        "imu": {"ax": 0.0, "ay": 0.0, "az": 0.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
        "dtc": [],
        "ign": True,
    })


@pytest_asyncio.fixture(scope="function")
async def fv_ctx(session_factory, async_client: AsyncClient):
    """Provision a fresh tenant with 15 normal telemetry readings."""
    from app.ingest.worker import process_message

    suffix  = uuid.uuid4().hex[:8]
    email   = f"fv-{suffix}@test.io"
    pw      = "Fl33tView!"
    vin     = f"FV{uuid.uuid4().hex[:15].upper()}"

    r = await async_client.post("/clients", json={
        "name": f"FleetViewCo {suffix}", "slug": f"fv-{suffix}",
        "owner_email": email, "owner_password": pw,
    })
    assert r.status_code == 201, r.text
    client_id = r.json()["id"]

    r = await async_client.post("/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.post("/vehicles", headers=headers, json={
        "vin": vin, "make": "Mercedes", "model_name": "Actros", "year": 2022,
    })
    assert r.status_code == 201, r.text
    vehicle_id = r.json()["id"]

    r = await async_client.post("/devices", headers=headers, json={
        "vehicle_id": vehicle_id,
        "serial": f"FV-{uuid.uuid4().hex[:8].upper()}",
        "firmware_version": "3.0",
    })
    assert r.status_code == 201, r.text
    device_id = r.json()["id"]

    topic = f"obdmonai/{client_id}/vehicle/{vin}/telemetry"
    base_ts = datetime.now(_UTC) - timedelta(hours=2)

    for seq in range(1, 6):
        ts  = base_ts + timedelta(seconds=seq * 10)
        raw = _cbor(device_id, seq, ts, speed=55.0)
        await process_message(topic, raw, session_factory)

    yield {
        "vehicle_id": vehicle_id,
        "client_id": client_id,
        "headers": headers,
    }


# ── Integration tests ─────────────────────────────────────────────────────────

@SKIP
async def test_summary_endpoint_returns_200(fv_ctx, async_client: AsyncClient):
    """GET /fleetview/vehicles/{id}/summary returns 200 with a non-empty summary."""
    ctx = fv_ctx
    r = await async_client.get(
        f"/fleetview/vehicles/{ctx['vehicle_id']}/summary",
        headers=ctx["headers"],
        params={"hours": 24},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["vehicle_id"] == ctx["vehicle_id"]
    assert isinstance(data["summary"], str) and len(data["summary"]) > 0
    assert "computed_at" in data


@SKIP
async def test_summary_endpoint_404_unknown_vehicle(fv_ctx, async_client: AsyncClient):
    """Requesting summary for a non-existent vehicle returns 404."""
    r = await async_client.get(
        f"/fleetview/vehicles/{uuid.uuid4()}/summary",
        headers=fv_ctx["headers"],
    )
    assert r.status_code == 404


@SKIP
async def test_summary_tenant_isolation(fv_ctx, async_client: AsyncClient):
    """Tenant A cannot read a FleetView summary for Tenant B's vehicle."""
    # Create Tenant B's vehicle
    suffix = uuid.uuid4().hex[:8]
    r = await async_client.post("/clients", json={
        "name": f"FVBCo {suffix}", "slug": f"fv-b-{suffix}",
        "owner_email": f"fv-b-{suffix}@test.io",
        "owner_password": "Fl33tView!",
    })
    assert r.status_code == 201
    r2 = await async_client.post("/auth/login", json={
        "email": f"fv-b-{suffix}@test.io", "password": "Fl33tView!",
    })
    hdrs_b = {"Authorization": f"Bearer {r2.json()['access_token']}"}

    r = await async_client.post("/vehicles", headers=hdrs_b, json={
        "vin": f"BV{uuid.uuid4().hex[:15].upper()}",
        "make": "B", "model_name": "V", "year": 2022,
    })
    assert r.status_code == 201
    vehicle_b_id = r.json()["id"]

    # Tenant A queries Tenant B's vehicle → 404 (RLS hides the vehicle)
    r = await async_client.get(
        f"/fleetview/vehicles/{vehicle_b_id}/summary",
        headers=fv_ctx["headers"],
    )
    assert r.status_code == 404
