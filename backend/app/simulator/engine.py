"""Vehicle telemetry simulator.

Publishes realistic OBD-II / CAN-bus + GPS + IMU data to MQTT as if
an ESP32 OBU were attached to the vehicle.  Each call to simulate_vehicle()
runs until cancelled — wrap it in an asyncio.Task.

Driving cycle (loops):
  IDLE (15 s) → ACCEL (25 s) → CRUISE (50 s) → DECEL (15 s) → STOP (10 s)
"""
from __future__ import annotations

import asyncio
import json
import math
import random
import ssl
import time as _time
from datetime import datetime, timezone
from typing import TypedDict

from aiomqtt import Client, MqttError

from app.config import settings

TICK_S = 2.0  # publish interval in seconds


class SimConfig(TypedDict):
    device_id: str
    client_id: str
    vin: str


# --------------------------------------------------------------------------- #
# Driving-cycle state machine
# --------------------------------------------------------------------------- #

_PHASES = ["idle", "accel", "cruise", "decel", "stop"]
_PHASE_TICKS = {
    "idle":  int(15  / TICK_S),
    "accel": int(25  / TICK_S),
    "cruise":int(50  / TICK_S),
    "decel": int(15  / TICK_S),
    "stop":  int(10  / TICK_S),
}
_PHASE_TARGET = {
    # (speed_kmh, rpm, throttle_pct, load_pct)
    "idle":   (0,   800,  2,  5),
    "accel":  (70, 3800, 70, 65),
    "cruise": (65, 2100, 22, 28),
    "decel":  (0,  1100,  3,  8),
    "stop":   (0,     0,  0,  0),
}

# Occasional DTC injection: injected during cruise, cleared at stop
_SAMPLE_DTCS = ["P0420", "P0171", "P0300", "P0128"]


def _tls_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.load_verify_locations(settings.mqtt_ca_cert)
    ctx.load_cert_chain(settings.mqtt_client_cert, settings.mqtt_client_key)
    return ctx


async def simulate_vehicle(cfg: SimConfig) -> None:
    """Publish telemetry continuously until the task is cancelled."""
    topic = f"obdmonai/{cfg['client_id']}/vehicle/{cfg['vin']}/telemetry"

    # Starting position: random offset from Pune city centre
    lat = 18.5204 + random.uniform(-0.08, 0.08)
    lon = 73.8567 + random.uniform(-0.08, 0.08)
    hdg = random.uniform(0, 360.0)

    speed = 0.0       # km/h
    rpm   = 800.0
    coolant = 25.0    # °C — warms up over ~5 min
    oil_temp = 20.0   # °C — slower warm-up
    intake_temp = 32.0
    fuel_pct = 75.0   # %
    run_time = 0.0    # seconds since ignition

    phase_idx  = 0
    phase_tick = 0
    # Start from current Unix timestamp so seq never collides across restarts
    seq        = int(_time.time())
    active_dtc: list[str] = []

    tls = _tls_ctx()

    while True:
        try:
            async with Client(settings.mqtt_host, port=settings.mqtt_port, tls_context=tls) as mqtt:
                while True:
                    phase = _PHASES[phase_idx % len(_PHASES)]
                    tgt_spd, tgt_rpm, tgt_thr, tgt_load = _PHASE_TARGET[phase]

                    # ---- smooth state transitions ----
                    speed += (tgt_spd - speed) * 0.12 + random.gauss(0, 0.4)
                    speed  = max(0.0, speed)
                    rpm   += (tgt_rpm - rpm) * 0.12 + random.gauss(0, 25)
                    rpm    = max(0.0, rpm)

                    # ---- thermal model ----
                    if coolant < 88.0 and rpm > 0:
                        coolant += 0.35 + random.gauss(0, 0.05)
                    coolant = max(18.0, min(108.0, coolant + random.gauss(0, 0.15)))

                    if oil_temp < 95.0 and rpm > 0:
                        oil_temp += 0.20 + random.gauss(0, 0.04)
                    oil_temp = max(18.0, min(120.0, oil_temp + random.gauss(0, 0.1)))

                    intake_temp = max(25.0, min(55.0, intake_temp + random.gauss(0, 0.3)))

                    # ---- fuel consumption ----
                    if rpm > 200:
                        fuel_pct -= (tgt_load / 100) * 0.0008 + 0.0003
                    fuel_pct = max(0.0, fuel_pct)
                    run_time += TICK_S

                    # ---- GPS movement ----
                    spd_ms = speed / 3.6
                    lat += math.cos(math.radians(hdg)) * spd_ms * TICK_S / 111_319
                    lon += math.sin(math.radians(hdg)) * spd_ms * TICK_S / (
                        111_319 * math.cos(math.radians(lat)) or 1
                    )
                    hdg = (hdg + random.gauss(0, 2.5)) % 360

                    # ---- IMU ----
                    long_g = (tgt_spd - speed) * 0.004 + random.gauss(0, 0.08)  # fwd/brk
                    lat_g  = random.gauss(0, 0.06)                               # cornering
                    vert_g = 9.81 + random.gauss(0, 0.12)                        # gravity + road

                    # ---- DTC injection ----
                    if phase == "cruise" and not active_dtc and random.random() < 0.005:
                        active_dtc = [random.choice(_SAMPLE_DTCS)]
                    if phase == "stop":
                        active_dtc = []

                    payload = {
                        "device_id": cfg["device_id"],
                        "ts": datetime.now(timezone.utc).timestamp(),
                        "seq": seq,
                        "gps": {
                            "lat": round(lat, 6),
                            "lon": round(lon, 6),
                            "alt": round(411.0 + random.gauss(0, 0.8), 1),
                            "hdg": round(hdg, 1),
                            "spd": round(spd_ms, 2),
                        },
                        "obd": {
                            "rpm":          round(rpm, 0),
                            "speed":        round(speed, 1),
                            "coolant":      round(coolant, 1),
                            "load":         round(max(0, min(100, tgt_load + random.gauss(0, 3))), 1),
                            "throttle":     round(max(0, min(100, tgt_thr + random.gauss(0, 2))), 1),
                            "intake_temp":  round(intake_temp, 1),
                            "fuel_level":   round(fuel_pct, 1),
                            "run_time":     round(run_time, 0),
                        },
                        "imu": {
                            "ax": round(long_g, 3),
                            "ay": round(lat_g, 3),
                            "az": round(vert_g, 3),
                            "gx": round(random.gauss(0, 0.008), 4),
                            "gy": round(random.gauss(0, 0.008), 4),
                            "gz": round(random.gauss(0, 0.015), 4),
                        },
                        "dtc": active_dtc,
                        "ign": rpm > 100,
                    }

                    await mqtt.publish(topic, json.dumps(payload).encode())
                    seq += 1

                    # ---- phase transition ----
                    phase_tick += 1
                    if phase_tick >= _PHASE_TICKS[phase]:
                        phase_tick = 0
                        phase_idx += 1

                    await asyncio.sleep(TICK_S)

        except asyncio.CancelledError:
            return
        except MqttError:
            # Broker not ready — retry after a short delay
            await asyncio.sleep(5)
        except Exception:
            await asyncio.sleep(5)
