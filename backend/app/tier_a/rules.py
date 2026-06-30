"""Tier A — pure deterministic rule functions.

All functions are stateless and side-effect-free: they take current telemetry
data plus the existing alert state and return a RuleResult describing what
action the engine should take.  No DB access; no imports from tier_b.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

# ── Thresholds ────────────────────────────────────────────────────────────────

OVERSPEED_SET_KMH: float = 120.0
OVERSPEED_CLEAR_KMH: float = 110.0

HARSH_G_SET: float = 0.5     # g-force deceleration (imu_ax < -HARSH_G_SET)
HARSH_G_CLEAR: float = 0.3

COOLANT_SET_C: float = 100.0
COOLANT_CLEAR_C: float = 90.0

IDLE_SET_SEC: int = 300       # 5 minutes before excessive-idle alert fires
IDLE_CLEAR_KMH: float = 5.0

FUEL_DROP_SET_PCT: float = 15.0  # % point drop in a single reading


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class TelemetryReading:
    device_id: str
    vehicle_id: str
    client_id: str
    ts: datetime
    seq: int
    obd_speed: float       # km/h
    obd_coolant: float     # °C
    obd_rpm: float
    obd_fuel_level: float  # %
    imu_ax: float          # g-force (positive = forward, negative = braking)
    gps_lat: float
    gps_lon: float
    dtc: list[str]
    ign: bool


@dataclass
class AlertState:
    """One non-cleared alert row from the database."""
    id: str
    rule: str
    state: str    # 'watching' | 'active'
    fired_at: datetime
    detail: dict


@dataclass
class Geofence:
    id: str
    name: str
    center_lat: float
    center_lon: float
    radius_m: float


@dataclass
class RuleResult:
    rule: str
    action: str = "none"  # 'none' | 'watch' | 'fire' | 'clear'
    severity: str = "warning"
    detail: dict = field(default_factory=dict)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _no_change(rule: str) -> RuleResult:
    return RuleResult(rule=rule)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two GPS coordinates in metres."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2.0 * R * math.asin(math.sqrt(a))


# ── Rule 1: Overspeed ─────────────────────────────────────────────────────────

def rule_overspeed(
    reading: TelemetryReading,
    alert: AlertState | None,
) -> RuleResult:
    speed = reading.obd_speed
    if alert is None and speed >= OVERSPEED_SET_KMH:
        return RuleResult("overspeed", "fire", "warning", {"speed_kmh": speed})
    if alert is not None and alert.state == "active" and speed < OVERSPEED_CLEAR_KMH:
        return RuleResult("overspeed", "clear")
    return _no_change("overspeed")


# ── Rule 2: Harsh Braking ─────────────────────────────────────────────────────

def rule_harsh_braking(
    reading: TelemetryReading,
    alert: AlertState | None,
) -> RuleResult:
    # imu_ax < 0 means deceleration; braking_g = positive magnitude of decel
    braking_g = -reading.imu_ax
    if alert is None and braking_g >= HARSH_G_SET:
        return RuleResult("harsh_braking", "fire", "warning", {"braking_g": round(braking_g, 3)})
    if alert is not None and alert.state == "active" and braking_g < HARSH_G_CLEAR:
        return RuleResult("harsh_braking", "clear")
    return _no_change("harsh_braking")


# ── Rule 3: Coolant Overheating ───────────────────────────────────────────────

def rule_coolant(
    reading: TelemetryReading,
    alert: AlertState | None,
) -> RuleResult:
    temp = reading.obd_coolant
    if alert is None and temp >= COOLANT_SET_C:
        return RuleResult("coolant_overheat", "fire", "critical", {"coolant_c": temp})
    if alert is not None and alert.state == "active" and temp < COOLANT_CLEAR_C:
        return RuleResult("coolant_overheat", "clear")
    return _no_change("coolant_overheat")


# ── Rule 4: New DTC ───────────────────────────────────────────────────────────

def rule_new_dtc(
    reading: TelemetryReading,
    alert: AlertState | None,
    prev_dtcs: set[str] | None,
) -> RuleResult:
    current = set(reading.dtc)
    prior = prev_dtcs if prev_dtcs is not None else set()

    if alert is None:
        new_codes = current - prior
        if new_codes:
            return RuleResult("new_dtc", "fire", "critical", {"codes": sorted(new_codes)})
    elif alert.state == "active" and not current:
        return RuleResult("new_dtc", "clear")
    return _no_change("new_dtc")


# ── Rule 5: Excessive Idling ──────────────────────────────────────────────────

def rule_idling(
    reading: TelemetryReading,
    alert: AlertState | None,
    idle_set_sec: int = IDLE_SET_SEC,
) -> RuleResult:
    """Two-stage: first reading starts 'watching'; fires after idle_set_sec."""
    is_idling = reading.ign and reading.obd_speed < 1.0

    if is_idling:
        if alert is None:
            return RuleResult("excessive_idle", "watch", "info",
                              {"idle_since": reading.ts.isoformat()})
        if alert.state == "watching":
            idle_since_str = alert.detail.get("idle_since", alert.fired_at.isoformat())
            idle_since = datetime.fromisoformat(idle_since_str)
            duration = (reading.ts - idle_since).total_seconds()
            if duration >= idle_set_sec:
                return RuleResult("excessive_idle", "fire", "warning", {
                    "idle_since": idle_since_str,
                    "duration_sec": int(duration),
                })
        # already active or still watching under threshold
        return _no_change("excessive_idle")
    else:
        if alert is not None:
            return RuleResult("excessive_idle", "clear")
        return _no_change("excessive_idle")


# ── Rule 6: Fuel Level Anomaly ────────────────────────────────────────────────

def rule_fuel_anomaly(
    reading: TelemetryReading,
    alert: AlertState | None,
    prev_fuel: float | None,
    fuel_drop_pct: float = FUEL_DROP_SET_PCT,
) -> RuleResult:
    if alert is None and prev_fuel is not None:
        drop = prev_fuel - reading.obd_fuel_level
        if drop >= fuel_drop_pct:
            return RuleResult("fuel_anomaly", "fire", "critical", {
                "prev_pct": prev_fuel,
                "curr_pct": reading.obd_fuel_level,
                "drop_pct": round(drop, 1),
            })
    if alert is not None and alert.state == "active":
        # Clear once fuel stabilises (current ≥ level at alert time + 2%)
        alert_level = alert.detail.get("curr_pct", 0.0)
        if reading.obd_fuel_level >= alert_level + 2.0:
            return RuleResult("fuel_anomaly", "clear")
    return _no_change("fuel_anomaly")


# ── Rule 7: Geofence Enter/Exit ───────────────────────────────────────────────

def rule_geofences(
    reading: TelemetryReading,
    geofences: list[Geofence],
    alert_map: dict[str, AlertState],
) -> list[RuleResult]:
    """One RuleResult per geofence; rule name = 'geofence:<gf_id>'."""
    results: list[RuleResult] = []
    for gf in geofences:
        rule_name = f"geofence:{gf.id}"
        dist = haversine_m(reading.gps_lat, reading.gps_lon, gf.center_lat, gf.center_lon)
        inside = dist <= gf.radius_m
        alert = alert_map.get(rule_name)
        is_active = alert is not None and alert.state == "active"

        if inside and not is_active:
            results.append(RuleResult(rule_name, "fire", "info", {
                "geofence": gf.name,
                "distance_m": round(dist, 1),
            }))
        elif not inside and is_active:
            results.append(RuleResult(rule_name, "clear"))
        else:
            results.append(_no_change(rule_name))
    return results


# ── Evaluate all rules (pure — no DB) ────────────────────────────────────────

def evaluate_all(
    reading: TelemetryReading,
    prev: TelemetryReading | None,
    alert_states: list[AlertState],
    geofences: list[Geofence],
    *,
    idle_set_sec: int = IDLE_SET_SEC,
) -> list[RuleResult]:
    """Evaluate every rule and return their RuleResults."""
    alert_map: dict[str, AlertState] = {a.rule: a for a in alert_states}
    prev_dtcs = set(prev.dtc) if prev else None
    prev_fuel = prev.obd_fuel_level if prev else None

    results: list[RuleResult] = [
        rule_overspeed(reading, alert_map.get("overspeed")),
        rule_harsh_braking(reading, alert_map.get("harsh_braking")),
        rule_coolant(reading, alert_map.get("coolant_overheat")),
        rule_new_dtc(reading, alert_map.get("new_dtc"), prev_dtcs),
        rule_idling(reading, alert_map.get("excessive_idle"), idle_set_sec),
        rule_fuel_anomaly(reading, alert_map.get("fuel_anomaly"), prev_fuel),
        *rule_geofences(reading, geofences, alert_map),
    ]
    return results
