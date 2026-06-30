"""Feature extraction from telemetry rows for Tier B ML models.

No DB access, no tier_a imports.

Feature vector (dim=10)
-----------------------
[0] speed_avg       — mean obd_speed over window (km/h)
[1] speed_max       — max obd_speed over window
[2] speed_std       — std obd_speed over window
[3] rpm_avg         — mean obd_rpm
[4] rpm_max         — max obd_rpm
[5] coolant_max     — max obd_coolant (°C)
[6] harsh_brake_r   — fraction of rows where imu_ax < -0.3 g
[7] harsh_accel_r   — fraction of rows where imu_ax >  0.3 g
[8] idle_ratio      — fraction of rows where ign=True AND speed < 2 km/h
[9] overspeed_r     — fraction of rows where obd_speed > 100 km/h
"""
from __future__ import annotations

import numpy as np

FEATURE_DIM: int = 10

_HARSH_BRAKE_THRESH = -0.3
_HARSH_ACCEL_THRESH = 0.3
_IDLE_SPEED_KMH = 2.0
_OVERSPEED_KMH = 100.0


def _fv(obj, attr: str, default: float = 0.0) -> float:
    v = obj.get(attr) if isinstance(obj, dict) else getattr(obj, attr, None)
    return float(v) if v is not None else default


def extract_features(rows: list) -> np.ndarray:
    """Return a (FEATURE_DIM,) float64 feature vector.

    Accepts any iterable of objects or dicts with the telemetry attributes.
    Returns a zero vector for an empty window — callers should check len(rows).
    """
    if not rows:
        return np.zeros(FEATURE_DIM, dtype=np.float64)

    n = len(rows)
    speeds   = np.array([_fv(r, "obd_speed")     for r in rows], dtype=np.float64)
    rpms     = np.array([_fv(r, "obd_rpm")        for r in rows], dtype=np.float64)
    coolants = np.array([_fv(r, "obd_coolant")    for r in rows], dtype=np.float64)
    ax       = np.array([_fv(r, "imu_ax")         for r in rows], dtype=np.float64)
    ign      = np.array([bool(_fv(r, "ign", 0.0)) for r in rows])

    return np.array([
        speeds.mean(),
        speeds.max(),
        speeds.std(),
        rpms.mean(),
        rpms.max(),
        coolants.max(),
        float((ax < _HARSH_BRAKE_THRESH).sum()) / n,
        float((ax > _HARSH_ACCEL_THRESH).sum()) / n,
        float((ign & (speeds < _IDLE_SPEED_KMH)).sum()) / n,
        float((speeds > _OVERSPEED_KMH).sum()) / n,
    ], dtype=np.float64)
