"""Tier B: ml_models table, SECURITY DEFINER helpers, and synthetic model seed.

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-30

Tables
------
ml_models   Non-tenant-scoped; stores base64-encoded joblib artifacts.
            app_user has NO direct access — reads via ml_get_model() only.

Functions (all SECURITY DEFINER)
---------
ml_get_model(p_name TEXT, p_version INT DEFAULT NULL) RETURNS TEXT
    Reads the latest (or specific) model artifact.  GRANT EXECUTE to app_user.

ml_get_telemetry_window(p_vehicle_id UUID, p_client_id UUID, p_from TIMESTAMPTZ)
    Returns the telemetry columns needed for feature extraction, filtered by
    explicit client_id (bypasses RLS safely).  GRANT EXECUTE to app_user.
"""
from __future__ import annotations

import os
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    app_user = os.environ.get("POSTGRES_USER", "obdmonai_app")

    # ── ml_models table ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE ml_models (
            id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            name       TEXT        NOT NULL,
            version    INT         NOT NULL DEFAULT 1,
            artifact   TEXT        NOT NULL,  -- base64-encoded joblib artifact
            trained_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (name, version)
        );
    """)
    # Intentionally NO GRANT INSERT/UPDATE/DELETE to app_user.
    # app_user reads models only via the SECURITY DEFINER function below.

    # ── ml_get_model ─────────────────────────────────────────────────────────
    op.execute("""
        CREATE FUNCTION ml_get_model(
            p_name    TEXT,
            p_version INT DEFAULT NULL
        )
        RETURNS TEXT
        LANGUAGE SQL SECURITY DEFINER STABLE AS $$
            SELECT artifact
            FROM ml_models
            WHERE name = p_name
              AND (p_version IS NULL OR version = p_version)
            ORDER BY version DESC
            LIMIT 1;
        $$;
    """)
    op.execute(
        f'GRANT EXECUTE ON FUNCTION ml_get_model(TEXT, INT) TO "{app_user}";'
    )

    # ── ml_get_telemetry_window ───────────────────────────────────────────────
    op.execute("""
        CREATE FUNCTION ml_get_telemetry_window(
            p_vehicle_id UUID,
            p_client_id  UUID,
            p_from       TIMESTAMPTZ
        )
        RETURNS TABLE(
            obd_speed      DOUBLE PRECISION,
            obd_rpm        DOUBLE PRECISION,
            obd_coolant    DOUBLE PRECISION,
            obd_fuel_level DOUBLE PRECISION,
            imu_ax         DOUBLE PRECISION,
            ign            BOOL
        )
        LANGUAGE SQL SECURITY DEFINER STABLE AS $$
            SELECT obd_speed, obd_rpm, obd_coolant, obd_fuel_level, imu_ax, ign
            FROM telemetry
            WHERE vehicle_id = p_vehicle_id
              AND client_id  = p_client_id
              AND time >= p_from
            ORDER BY time;
        $$;
    """)
    op.execute(
        f'GRANT EXECUTE ON FUNCTION '
        f'ml_get_telemetry_window(UUID, UUID, TIMESTAMPTZ) TO "{app_user}";'
    )

    # ── Seed synthetic models ─────────────────────────────────────────────────
    _seed_models()


def _seed_models() -> None:
    """Train lightweight synthetic models and store in ml_models."""
    import base64
    import io

    import joblib

    from app.tier_b.driver_score import train_driver_model
    from app.tier_b.maintenance import train_maintenance_model

    bind = op.get_bind()

    for name, train_fn in [
        ("driver_score", train_driver_model),
        ("maintenance",  train_maintenance_model),
    ]:
        model = train_fn()
        buf = io.BytesIO()
        joblib.dump(model, buf, compress=3)
        artifact_b64 = base64.b64encode(buf.getvalue()).decode()
        bind.execute(
            text(
                "INSERT INTO ml_models (name, version, artifact) "
                "VALUES (:name, :version, :artifact)"
            ),
            {"name": name, "version": 1, "artifact": artifact_b64},
        )


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION IF EXISTS ml_get_telemetry_window(UUID, UUID, TIMESTAMPTZ);"
    )
    op.execute("DROP FUNCTION IF EXISTS ml_get_model(TEXT, INT);")
    op.execute("DROP TABLE IF EXISTS ml_models;")
