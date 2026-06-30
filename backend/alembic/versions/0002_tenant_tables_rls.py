"""Create tenant tables (clients, users, vehicles, devices) with RLS.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-29

RLS design
----------
Every tenant-scoped table has Row-Level Security enabled. Policies key on the
per-transaction GUC `app.current_client_id`, which the application sets with
  SET LOCAL app.current_client_id = '<uuid>';
at the start of every transaction before any tenant-scoped query.

`clients` itself is NOT RLS-protected — it is managed by the superuser / owner
API layer which never goes through pgbouncer's transaction-pooled app role in
normal operation.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS_TABLES = ("users", "vehicles", "devices")

# Helper: build the RLS policy expression for a tenant-scoped table
_RLS_USING = "client_id = current_setting('app.current_client_id', true)::uuid"


def upgrade() -> None:
    # ------------------------------------------------------------------ clients
    op.create_table(
        "clients",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # ------------------------------------------------------------------ users
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.Text, nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", sa.String(20), nullable=False),          # owner | fleet_admin | viewer
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('owner', 'fleet_admin', 'viewer')",
    )
    op.create_index("ix_users_client_id", "users", ["client_id"])

    # ------------------------------------------------------------------ vehicles
    op.create_table(
        "vehicles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vin", sa.String(17), nullable=False),
        sa.Column("make", sa.Text),
        sa.Column("model_name", sa.Text),
        sa.Column("year", sa.Integer),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_vehicles_client_id", "vehicles", ["client_id"])
    op.create_unique_constraint("uq_vehicles_client_vin", "vehicles", ["client_id", "vin"])

    # ------------------------------------------------------------------ devices
    op.create_table(
        "devices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vehicle_id", UUID(as_uuid=True), sa.ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("serial", sa.Text, nullable=False, unique=True),
        sa.Column("cert_fingerprint", sa.Text),                    # fingerprint only, never the private key
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_devices_client_id", "devices", ["client_id"])
    op.create_index("ix_devices_vehicle_id", "devices", ["vehicle_id"])

    # ------------------------------------------------------------------ RLS
    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        # SELECT / UPDATE / DELETE: only rows belonging to the session tenant
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
                USING ({_RLS_USING});
        """)
        # INSERT: enforce client_id matches the session tenant
        op.execute(f"""
            CREATE POLICY {table}_tenant_insert ON {table}
                FOR INSERT
                WITH CHECK ({_RLS_USING});
        """)


def downgrade() -> None:
    for table in reversed(_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_insert ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.drop_table("devices")
    op.drop_table("vehicles")
    op.drop_table("users")
    op.drop_table("clients")
