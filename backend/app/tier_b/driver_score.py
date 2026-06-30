"""Driver behaviour scoring via gradient-boosted classifier.

Trained on synthetic data: "safe" vs "risky" driver profiles.
Output: probability-of-safe scaled to 0–100 (100 = safest).

No DB access, no tier_a imports.
"""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier


def train_driver_model(random_state: int = 42) -> GradientBoostingClassifier:
    """Train a GradientBoostingClassifier on synthetic safe/risky profiles."""
    rng = np.random.default_rng(random_state)
    n = 2_000

    safe = np.column_stack([
        rng.normal(50, 10, n),      # speed_avg
        rng.normal(75, 15, n),      # speed_max
        rng.normal(8,   3, n),      # speed_std
        rng.normal(1400, 200, n),   # rpm_avg
        rng.normal(2200, 300, n),   # rpm_max
        rng.normal(83,   5, n),     # coolant_max
        rng.beta(1, 25, n),         # harsh_brake_r  ~0.04
        rng.beta(1, 25, n),         # harsh_accel_r  ~0.04
        rng.beta(2,  8, n),         # idle_ratio     ~0.20
        rng.beta(1, 40, n),         # overspeed_r    ~0.02
    ])

    risky = np.column_stack([
        rng.normal(85, 15, n),      # speed_avg
        rng.normal(135, 20, n),     # speed_max
        rng.normal(28,   8, n),     # speed_std
        rng.normal(2100, 300, n),   # rpm_avg
        rng.normal(4500, 500, n),   # rpm_max
        rng.normal(96,   8, n),     # coolant_max
        rng.beta(6, 10, n),         # harsh_brake_r  ~0.37
        rng.beta(6, 10, n),         # harsh_accel_r  ~0.37
        rng.beta(2,  5, n),         # idle_ratio     ~0.29
        rng.beta(6, 10, n),         # overspeed_r    ~0.37
    ])

    X = np.vstack([safe, risky])
    y = np.array([1] * n + [0] * n)

    model = GradientBoostingClassifier(
        n_estimators=60, max_depth=3, learning_rate=0.1,
        subsample=0.8, random_state=random_state,
    )
    model.fit(X, y)
    return model


def predict_score(model: GradientBoostingClassifier, features: np.ndarray) -> float:
    """Return a 0–100 safety score (100 = safest driver)."""
    prob_safe = float(model.predict_proba(features.reshape(1, -1))[0][1])
    return round(prob_safe * 100.0, 1)
