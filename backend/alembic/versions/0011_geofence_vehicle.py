"""Add vehicle_id to geofences table.

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-30
"""
from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0011"
down_revision: Union[str, Sequence[str], None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable vehicle_id — geofences can be fleet-wide (NULL) or per-vehicle
    op.execute("""
        ALTER TABLE geofences
            ADD COLUMN IF NOT EXISTS vehicle_id UUID
                REFERENCES vehicles(id) ON DELETE SET NULL;
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_geofences_vehicle
            ON geofences (vehicle_id)
            WHERE vehicle_id IS NOT NULL;
    """)

    # Recreate tier_a_get_geofences to include vehicle_id
    op.execute("DROP FUNCTION IF EXISTS tier_a_get_geofences(UUID);")
    op.execute("""
        CREATE FUNCTION tier_a_get_geofences(p_client_id UUID)
        RETURNS TABLE(
            id          UUID,
            vehicle_id  UUID,
            name        TEXT,
            center_lat  DOUBLE PRECISION,
            center_lon  DOUBLE PRECISION,
            radius_m    DOUBLE PRECISION
        )
        LANGUAGE SQL SECURITY DEFINER STABLE AS $$
            SELECT id, vehicle_id, name, center_lat, center_lon, radius_m
            FROM   geofences
            WHERE  client_id = p_client_id AND is_active = true;
        $$;
    """)
    app_user = os.environ.get("POSTGRES_USER", "obdmonai_app")
    op.execute(f'GRANT EXECUTE ON FUNCTION tier_a_get_geofences(UUID) TO "{app_user}";')


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS tier_a_get_geofences(UUID);")
    # Restore original function without vehicle_id
    op.execute("""
        CREATE FUNCTION tier_a_get_geofences(p_client_id UUID)
        RETURNS TABLE(
            id          UUID,
            name        TEXT,
            center_lat  DOUBLE PRECISION,
            center_lon  DOUBLE PRECISION,
            radius_m    DOUBLE PRECISION
        )
        LANGUAGE SQL SECURITY DEFINER STABLE AS $$
            SELECT id, name, center_lat, center_lon, radius_m
            FROM   geofences
            WHERE  client_id = p_client_id AND is_active = true;
        $$;
    """)
    app_user = os.environ.get("POSTGRES_USER", "obdmonai_app")
    op.execute(f'GRANT EXECUTE ON FUNCTION tier_a_get_geofences(UUID) TO "{app_user}";')

    op.execute("DROP INDEX IF EXISTS ix_geofences_vehicle;")
    op.execute("ALTER TABLE geofences DROP COLUMN IF EXISTS vehicle_id;")
