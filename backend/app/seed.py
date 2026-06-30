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

from app.config import settings
from app.db import get_session
from app.ingest.worker import process_message
from app.main import app

_UTC = timezone.utc

# ── Superadmin credentials (read from env) ────────────────────────────────────
SUPERADMIN_EMAIL    = settings.superadmin_email or "admin@obdmonai.local"
SUPERADMIN_PASSWORD = settings.superadmin_password or "password123"

# ── Demo tenant credentials ────────────────────────────────────────────────────
DEMO_EMAIL    = "demo@acmefleet.io"
CLIENT_NAME   = "Acme Logistics"
CLIENT_SLUG   = "acme-logistics"

VEHICLES = [
    {"vin": "ACME01VOLVO0FH160", "make": "Volvo",    "model_name": "FH16",    "year": 2023},
    {"vin": "ACME02SCANI0R4500", "make": "Scania",   "model_name": "R450",    "year": 2022},
    {"vin": "ACME03MERCE0ACTRO", "make": "Mercedes", "model_name": "Actros",  "year": 2024},
]
SERIALS = ["OBU-ACM-0001", "OBU-ACM-0002", "OBU-ACM-0003"]

# Demo final password (seeder sets this after clearing must_change_password)
DEMO_PASSWORD = "AcmeFleet2024!"

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
    if frac < 0.05:
        return 0.0, False
    if frac < 0.40:
        t = (frac - 0.05) / 0.35
        speed = 65.0 * math.sin(math.pi * t) + random.gauss(0, 4)
        return max(0.0, min(100.0, speed)), True
    if frac < 0.55:
        return 0.0, True
    if frac < 0.95:
        t = (frac - 0.55) / 0.40
        speed = 75.0 * math.sin(math.pi * t) + random.gauss(0, 5)
        return max(0.0, min(110.0, speed)), True
    return 0.0, False


async def _seed_vehicle(
    client_id: str,
    vehicle_id: str,
    device_id: str,
    vin: str,
    session_factory,
) -> int:
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


def _decode_client_id(token: str) -> str:
    import base64
    import json as _json
    part = token.split(".")[1]
    part += "=" * (-len(part) % 4)
    return _json.loads(base64.b64decode(part))["client_id"]


async def run() -> None:
    session_factory = get_session()

    print("⬡  obdmonai demo seeder")
    print(f"   Superadmin : {SUPERADMIN_EMAIL}")
    print(f"   Tenant     : {CLIENT_NAME}")
    print()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as http:

        # ── 1. Login as superadmin ────────────────────────────────────────────
        r = await http.post("/auth/login", json={
            "email": SUPERADMIN_EMAIL, "password": SUPERADMIN_PASSWORD,
        })
        if r.status_code != 200:
            print(f"  ✗ Superadmin login failed: {r.status_code} {r.text}")
            sys.exit(1)

        sa_data = r.json()
        sa_token = sa_data["access_token"]

        # Clear must_change_password for superadmin if set (keeps same password)
        if sa_data.get("must_change_password"):
            r2 = await http.post("/auth/change-password",
                                  headers={"Authorization": f"Bearer {sa_token}"},
                                  json={"current_password": SUPERADMIN_PASSWORD,
                                        "new_password": SUPERADMIN_PASSWORD})
            if r2.status_code != 200:
                print(f"  ✗ Could not clear superadmin must_change_password: {r2.text}")
                sys.exit(1)
            r = await http.post("/auth/login", json={
                "email": SUPERADMIN_EMAIL, "password": SUPERADMIN_PASSWORD,
            })
            sa_token = r.json()["access_token"]

        sa_headers = {"Authorization": f"Bearer {sa_token}"}
        print(f"  ✓ Superadmin logged in")

        # ── 2. Create demo client ─────────────────────────────────────────────
        r = await http.post("/clients",
                             headers=sa_headers,
                             json={"name": CLIENT_NAME, "slug": CLIENT_SLUG,
                                   "owner_email": DEMO_EMAIL})
        if r.status_code == 201:
            temp_password = r.json()["temp_password"]
            print(f"  ✓ Created tenant '{CLIENT_NAME}'  (temp pw: {temp_password})")
        elif r.status_code == 409:
            print(f"  → Tenant already exists — skipping vehicle+telemetry seeding")
            print(f"\n  Done!  Login: {DEMO_EMAIL} / {DEMO_PASSWORD}\n")
            return
        else:
            print(f"  ✗ Client creation failed: {r.status_code} {r.text}")
            sys.exit(1)

        # ── 3. Login as demo owner (with temp password) ───────────────────────
        r = await http.post("/auth/login", json={"email": DEMO_EMAIL, "password": temp_password})
        if r.status_code != 200:
            print(f"  ✗ Demo owner login failed: {r.status_code} {r.text}")
            sys.exit(1)

        owner_token = r.json()["access_token"]
        client_id = _decode_client_id(owner_token)

        # ── 4. Change demo owner password to well-known value ─────────────────
        r = await http.post("/auth/change-password",
                             headers={"Authorization": f"Bearer {owner_token}"},
                             json={"current_password": temp_password,
                                   "new_password": DEMO_PASSWORD})
        if r.status_code != 200:
            print(f"  ✗ Password change failed: {r.status_code} {r.text}")
            sys.exit(1)

        # Re-login with final password
        r = await http.post("/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
        owner_token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {owner_token}"}
        print(f"  ✓ Demo owner ready  ({DEMO_EMAIL} / {DEMO_PASSWORD})")

        # ── 5. Create vehicles + devices ──────────────────────────────────────
        combos: list[tuple[str, str, str]] = []
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

    # ── 6. Seed telemetry ─────────────────────────────────────────────────────
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
