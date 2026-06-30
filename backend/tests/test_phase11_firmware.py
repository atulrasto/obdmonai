"""Phase 11 — host-side firmware payload schema validation.

These tests run in Python without hardware and verify that the CBOR
payload format produced by the ESP32 firmware (cbor_payload.cpp)
is fully compatible with the backend's TelemetryPayload Pydantic schema.

All tests mirror the exact map structure emitted by cbor_encode_frame():
  - Top-level 8-key map: device_id, ts, seq, gps, obd, imu, dtc, ign
  - gps: 5 keys (lat, lon, alt, hdg, spd)
  - obd: 8 keys (speed, rpm, coolant, fuel_level, load, throttle, intake_temp, run_time)
  - imu: 6 keys (ax, ay, az, gx, gy, gz)
  - dtc: array of strings
  - ign: boolean
"""
from __future__ import annotations

import struct
import uuid
from datetime import datetime, timezone

import cbor2
import pytest

from app.ingest.schemas import GPS, IMU, OBD, TelemetryPayload


def _f32(v: float) -> float:
    """Round-trip through float32 to mimic firmware float precision."""
    return struct.unpack("f", struct.pack("f", v))[0]


def _make_cbor(
    device_id: str | None = None,
    ts: int | None = None,
    seq: int = 1,
    lat: float = 18.52,
    lon: float = 73.86,
    alt: float = 550.0,
    hdg: float = 90.0,
    spd: float = 16.7,
    speed: float = 60.0,
    rpm: float = 1800.0,
    coolant: float = 88.0,
    fuel_level: float = 75.0,
    load: float = 25.0,
    throttle: float = 18.0,
    intake_temp: float = 32.0,
    run_time: int = 420,
    ax: float = 0.0,
    ay: float = 0.05,
    az: float = 9.81,
    gx: float = 0.0,
    gy: float = 0.0,
    gz: float = 0.02,
    dtc: list[str] | None = None,
    ign: bool = True,
) -> bytes:
    """Build a CBOR payload exactly as cbor_encode_frame() would produce it."""
    if device_id is None:
        device_id = str(uuid.uuid4())
    if ts is None:
        ts = int(datetime.now(timezone.utc).timestamp())
    if dtc is None:
        dtc = []
    return cbor2.dumps({
        "device_id": device_id,
        "ts":        ts,
        "seq":       seq,
        "gps": {"lat": lat, "lon": lon, "alt": alt, "hdg": hdg, "spd": spd},
        "obd": {
            "speed":       speed,
            "rpm":         rpm,
            "coolant":     coolant,
            "fuel_level":  fuel_level,
            "load":        load,
            "throttle":    throttle,
            "intake_temp": intake_temp,
            "run_time":    run_time,
        },
        "imu": {"ax": ax, "ay": ay, "az": az, "gx": gx, "gy": gy, "gz": gz},
        "dtc": dtc,
        "ign": ign,
    })


# ── Schema validation ──────────────────────────────────────────────────────────

def test_basic_payload_validates():
    """A standard driving reading validates against TelemetryPayload."""
    device_id = str(uuid.uuid4())
    now_ts    = int(datetime.now(timezone.utc).timestamp())
    raw       = _make_cbor(device_id=device_id, ts=now_ts, seq=42)
    payload   = TelemetryPayload.model_validate(cbor2.loads(raw))

    assert str(payload.device_id) == device_id
    assert payload.seq == 42
    assert payload.ts.tzinfo is not None
    assert payload.ign is True
    assert payload.dtc == []


def test_ts_unix_int_converts_to_utc_datetime():
    """Backend field_validator converts Unix int ts → timezone-aware UTC datetime."""
    now = datetime.now(timezone.utc)
    ts  = int(now.timestamp())
    raw = _make_cbor(ts=ts)
    payload = TelemetryPayload.model_validate(cbor2.loads(raw))

    assert isinstance(payload.ts, datetime)
    assert payload.ts.tzinfo is not None
    # Accept ±1 s rounding from int truncation
    assert abs((payload.ts - now).total_seconds()) < 2


def test_gps_fields_round_trip():
    """GPS sub-map fields are parsed into the GPS model."""
    raw = _make_cbor(lat=18.52, lon=73.86, alt=550.0, hdg=90.0, spd=16.7)
    gps = TelemetryPayload.model_validate(cbor2.loads(raw)).gps

    assert isinstance(gps, GPS)
    assert gps.lat  == pytest.approx(18.52,  rel=1e-3)
    assert gps.lon  == pytest.approx(73.86,  rel=1e-3)
    assert gps.alt  == pytest.approx(550.0,  rel=1e-3)
    assert gps.hdg  == pytest.approx(90.0,   rel=1e-3)
    assert gps.spd  == pytest.approx(16.7,   rel=1e-3)


def test_obd_fields_round_trip():
    """OBD sub-map fields are parsed into the OBD model."""
    raw = _make_cbor(
        speed=65.0, rpm=1950.0, coolant=92.0, fuel_level=68.0,
        load=30.0, throttle=22.0, intake_temp=35.0, run_time=600,
    )
    obd = TelemetryPayload.model_validate(cbor2.loads(raw)).obd

    assert isinstance(obd, OBD)
    assert obd.speed       == pytest.approx(65.0,  rel=1e-3)
    assert obd.rpm         == pytest.approx(1950.0, rel=1e-3)
    assert obd.coolant     == pytest.approx(92.0,  rel=1e-3)
    assert obd.fuel_level  == pytest.approx(68.0,  rel=1e-3)
    assert obd.load        == pytest.approx(30.0,  rel=1e-3)
    assert obd.throttle    == pytest.approx(22.0,  rel=1e-3)
    assert obd.intake_temp == pytest.approx(35.0,  rel=1e-3)
    assert obd.run_time    == pytest.approx(600.0, rel=1e-3)


def test_imu_fields_round_trip():
    """IMU sub-map fields are parsed into the IMU model."""
    raw = _make_cbor(ax=0.15, ay=-0.05, az=9.80, gx=0.01, gy=0.0, gz=-0.02)
    imu = TelemetryPayload.model_validate(cbor2.loads(raw)).imu

    assert isinstance(imu, IMU)
    assert imu.ax == pytest.approx(0.15,  abs=1e-4)
    assert imu.ay == pytest.approx(-0.05, abs=1e-4)
    assert imu.az == pytest.approx(9.80,  rel=1e-3)


def test_dtc_list_preserved():
    """DTC codes survive CBOR round-trip as a list of strings."""
    raw     = _make_cbor(dtc=["P0300", "P0171", "C1234"])
    payload = TelemetryPayload.model_validate(cbor2.loads(raw))
    assert payload.dtc == ["P0300", "P0171", "C1234"]


def test_empty_dtc_list():
    """Empty DTC list (no faults) parses as an empty Python list."""
    raw     = _make_cbor(dtc=[])
    payload = TelemetryPayload.model_validate(cbor2.loads(raw))
    assert payload.dtc == []


def test_ignition_off_bool():
    """ign=False (ignition off) parses correctly."""
    raw     = _make_cbor(ign=False)
    payload = TelemetryPayload.model_validate(cbor2.loads(raw))
    assert payload.ign is False


def test_float32_precision_acceptable():
    """Float32 precision from firmware (≈ 6 significant digits) is within tolerance."""
    # Simulate firmware float32 encode then decode
    lat = _f32(18.520001)   # lat after float32 roundtrip
    lon = _f32(73.860001)
    raw = _make_cbor(lat=lat, lon=lon)
    gps = TelemetryPayload.model_validate(cbor2.loads(raw)).gps

    # float32 has ~6 significant decimal digits; 1e-4 relative tolerance is generous
    assert gps.lat == pytest.approx(18.52, rel=1e-4)
    assert gps.lon == pytest.approx(73.86, rel=1e-4)


def test_seq_zero_is_valid():
    """seq=0 satisfies the ge=0 constraint (first reading after cold boot)."""
    raw     = _make_cbor(seq=0)
    payload = TelemetryPayload.model_validate(cbor2.loads(raw))
    assert payload.seq == 0


def test_large_seq_accepted():
    """seq wraps at uint32 max; large values still validate."""
    raw     = _make_cbor(seq=2**32 - 1)
    payload = TelemetryPayload.model_validate(cbor2.loads(raw))
    assert payload.seq == 2**32 - 1


def test_missing_optional_fields_use_defaults():
    """Sub-models default to zero when keys are missing (tolerant parsing)."""
    # Minimal payload — only required top-level keys
    device_id = str(uuid.uuid4())
    raw = cbor2.dumps({
        "device_id": device_id,
        "ts":  int(datetime.now(timezone.utc).timestamp()),
        "seq": 1,
        "ign": True,
        "dtc": [],
    })
    payload = TelemetryPayload.model_validate(cbor2.loads(raw))
    assert payload.gps.lat == 0.0
    assert payload.obd.speed == 0.0
    assert payload.imu.ax == 0.0


def test_cbor_bytes_are_decodable_by_cbor2():
    """cbor2.loads does not raise on a well-formed firmware payload."""
    raw = _make_cbor()
    decoded = cbor2.loads(raw)
    assert isinstance(decoded, dict)
    assert set(decoded.keys()) == {"device_id", "ts", "seq", "gps", "obd", "imu", "dtc", "ign"}


def test_multiple_sequential_readings():
    """Consecutive seq numbers validate as independent payloads."""
    device_id = str(uuid.uuid4())
    now_ts    = int(datetime.now(timezone.utc).timestamp())

    payloads = [
        TelemetryPayload.model_validate(cbor2.loads(_make_cbor(
            device_id=device_id,
            ts=now_ts + i * 10,
            seq=i,
            speed=float(50 + i),
        )))
        for i in range(1, 6)
    ]

    assert [p.seq for p in payloads] == [1, 2, 3, 4, 5]
    assert payloads[-1].obd.speed == pytest.approx(55.0, rel=1e-3)
