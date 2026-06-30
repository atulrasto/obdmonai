"""Predictive maintenance via IsolationForest anomaly detection.

Trained on synthetic normal (healthy) engine readings.
Output: is_anomaly (bool) + raw anomaly_score (lower = more anomalous).

No DB access, no tier_a imports.
"""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest


def train_maintenance_model(random_state: int = 42) -> IsolationForest:
    """Train an IsolationForest on synthetic healthy engine readings."""
    rng = np.random.default_rng(random_state)
    n = 3_000

    X = np.column_stack([
        rng.normal(50,  12, n),     # speed_avg (km/h)
        rng.normal(75,  15, n),     # speed_max
        rng.normal(8,    3, n),     # speed_std
        rng.normal(1400, 180, n),   # rpm_avg
        rng.normal(2200, 280, n),   # rpm_max
        rng.normal(83,   4, n),     # coolant_max (°C) — healthy: ~80-90
        rng.beta(1, 25, n),         # harsh_brake_r
        rng.beta(1, 25, n),         # harsh_accel_r
        rng.beta(2,  8, n),         # idle_ratio
        rng.beta(1, 40, n),         # overspeed_r
    ])

    model = IsolationForest(
        n_estimators=120, contamination=0.04, random_state=random_state,
    )
    model.fit(X)
    return model


def predict_anomaly(model: IsolationForest, features: np.ndarray) -> dict:
    """Return anomaly decision and score.

    anomaly_score: IsolationForest score_samples value.
                   Negative values closer to -1 indicate anomalies.
    is_anomaly:    True when the forest classifies as outlier.
    """
    vec = features.reshape(1, -1)
    score   = float(model.score_samples(vec)[0])
    is_anom = bool(model.predict(vec)[0] == -1)
    return {"is_anomaly": is_anom, "anomaly_score": round(score, 4)}
