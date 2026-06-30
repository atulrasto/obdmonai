"""Demo data seeder — run via: docker compose run --rm backend python -m app.seed

Creates a demo tenant with 3 vehicles and ~200 realistic telemetry readings
so the dashboard, analytics, ML scores, and FleetView all have data on first
startup.  Safe to run multiple times — duplicate client/vehicle creation is
skipped gracefully.
"""
from __future__ import annotations

import asyncio
import math
import random
import sys
from datetime import datetime, timedelta, timezone

import cbor2
from httpx import AsyncClient, ASGITransport

from app.db import get_session
from app.ingest.worker import process_message
from app.main import app

_UTC = timezone.utc

# ── Demo tenant credentials ────────────────────────────────────────────────────
DEMO_EMAIL    = "demo@acmefleet.io"
DEMO_PASSWORD = "AcmeFleet2024!"
CLIENT_NAME   = "Acme Logistics"
CLIENT_SLUG   = "acme-logistics"

VEHICLES = [
    {"vin": "ACME01VOLVO0FH1600", "make": "Volvo",    "model_name": "FH16",    "year": 2023},
    {"vin": "ACME02SCANI0R45000", "make": "Scania",   "model_name": "R450",    "year": 2022},
    {"vin": "ACME03MERCE0ACTROS", "make": "Mercedes", "model_name": "Actros",  "year": 2024},
]
SERIALS = ["OBU-ACM-0001", "OBU-ACM-0002", "OBU-ACM-0003"]

# Route simulation: small circular loop around Pune, India
_ROUTE_LAT_CENTRE, _ROUTE_LON_CENTRE = 18.52, 73.86


def _gps(step: int, total: int, radius_km: float = 8.0) -> tuple[float, float]:
    angle = 2 * math.pi * step / total
    dlat = radius_km / 111.0 * math.sin(angle)
    dlon = radius_km / (111.0 * math.cos(math.radians(_ROUTE_LAT_CENTRE))) * math.cos(angle)
    return _ROUTE_LAT_CENTRE + dlat, _ROUTE_LON_CENTRE + dlon


def _cbor(device_id: str, seq: int, ts: datetime, lat: float, lon: float,
          speed: float, rpm: float, coolant: float, ign: bool, fuel: float) -> bytes:
    return cbor2.dumps({
        "device_id": device_id,
        "ts": int(ts.timestamp()),
        "seq": seq,
        "gps": {"lat": lat, "lon": lon, "alt": 560.0, "hdg": 0.0, "spd": speed / 3.6},
        "obd": {
            "speed": speed, "rpm": rpm, "coolant": coolant,
            "load": max(5.0, speed / 3),
            "throttle": max(3.0, speed / 4),
            "intake_temp": 32.0,
            "fuel_level": fuel,
            "run_time": seq * 10,
        },
        "imu": {"ax": 0.0, "ay": 0.0, "az": 0.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
        "dtc": [],
        "ign": ign,
    })


def _speed_profile(seq: int, n: int) -> tuple[float, bool]:
    """Simulate two trips separated by an idle gap."""
    frac = seq / n
    # Trip 1: 0-40%
    if frac < 0.05:
        return 0.0, False          # not started yet
    if frac < 0.40:
        t = (frac - 0.05) / 0.35
        speed = 65.0 * math.sin(math.pi * t) + random.gauss(0, 4)
        return max(0.0, min(100.0, speed)), True
    # Mid-stop: 40-55%
    if frac < 0.55:
        return 0.0, True           # engine on, stationary
    # Trip 2: 55-95%
    if frac < 0.95:
        t = (frac - 0.55) / 0.40
        speed = 75.0 * math.sin(math.pi * t) + random.gauss(0, 5)
        return max(0.0, min(110.0, speed)), True
    return 0.0, False              # ignition off


async def _seed_vehicle(
    client_id: str,
    vehicle_id: str,
    device_id: str,
    vin: str,
    session_factory,
) -> int:
    """Push N=200 telemetry readings and return the count inserted."""
    N = 200
    topic = f"obdmonai/{client_id}/vehicle/{vin}/telemetry"
    now = datetime.now(_UTC)

    fuel = 90.0
    inserted = 0
    for seq in range(1, N + 1):
        hours_ago = 22.0 * (1 - seq / N)
        ts = now - timedelta(hours=hours_ago)

        speed, ign = _speed_profile(seq, N)
        rpm = max(750.0, speed * 22 + random.gauss(200, 60)) if ign else 0.0
        coolant = 85.0 + random.gauss(0, 2) + (speed / 200)
        fuel = max(20.0, fuel - 0.04)
        lat, lon = _gps(seq, N)

        raw = _cbor(device_id, seq, ts, lat, lon, speed, rpm, coolant, ign, fuel)
        await process_message(topic, raw, session_factory)
        inserted += 1

    return inserted


async def run() -> None:
    session_factory = get_session()

    print("⬡  obdmonai demo seeder")
    print(f"   Tenant  : {CLIENT_NAME}")
    print(f"   Login   : {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as http:

        # ── 1. Create client + owner ──────────────────────────────────────────
        r = await http.post("/clients", json={
            "name": CLIENT_NAME, "slug": CLIENT_SLUG,
            "owner_email": DEMO_EMAIL, "owner_password": DEMO_PASSWORD,
        })
        if r.status_code == 201:
            print(f"  ✓ Created tenant '{CLIENT_NAME}'")
        elif r.status_code == 409:
            print(f"  → Tenant already exists — skipping")
        else:
            print(f"  ✗ Client creation failed: {r.status_code} {r.text}")
            sys.exit(1)

        # ── 2. Login ──────────────────────────────────────────────────────────
        r = await http.post("/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
        if r.status_code != 200:
            print(f"  ✗ Login failed: {r.status_code} {r.text}")
            sys.exit(1)
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Decode client_id from JWT payload
        import base64, json as _json
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        client_id: str = _json.loads(base64.b64decode(part))["client_id"]

        # ── 3. Create vehicles + devices ──────────────────────────────────────
        combos: list[tuple[str, str, str]] = []   # (vehicle_id, device_id, vin)
        for vdata, serial in zip(VEHICLES, SERIALS):
            r = await http.post("/vehicles", headers=headers, json=vdata)
            if r.status_code == 201:
                vehicle_id = r.json()["id"]
                print(f"  ✓ Vehicle {vdata['make']} {vdata['model_name']}")
            elif r.status_code in (400, 409):
                print(f"  → Vehicle {vdata['vin']} already exists — skipping")
                continue
            else:
                print(f"  ✗ Vehicle creation failed: {r.status_code} {r.text}")
                continue

            r = await http.post("/devices", headers=headers, json={
                "vehicle_id": vehicle_id,
                "serial": serial,
                "firmware_version": "2.1.0",
            })
            if r.status_code == 201:
                device_id = r.json()["id"]
                combos.append((vehicle_id, device_id, vdata["vin"]))
                print(f"  ✓ Device {serial}")
            else:
                print(f"  ✗ Device creation failed: {r.status_code} {r.text}")

    # ── 4. Seed telemetry ─────────────────────────────────────────────────────
    if not combos:
        print("\n  → No new vehicles — skipping telemetry seeding.\n")
        return

    print(f"\n  → Seeding 200 readings per vehicle ({len(combos)} vehicles)…")
    for vehicle_id, device_id, vin in combos:
        n = await _seed_vehicle(client_id, vehicle_id, device_id, vin, session_factory)
        print(f"     {vin}: {n} readings")

    print(f"""
  Done!  Open the dashboard and log in with:
    Email    : {DEMO_EMAIL}
    Password : {DEMO_PASSWORD}
""")


if __name__ == "__main__":
    asyncio.run(run())
