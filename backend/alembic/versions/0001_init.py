"""Enable TimescaleDB extension and create non-superuser app role.

Revision ID: 0001
Revises: -
Create Date: 2026-06-29
"""
from __future__ import annotations

import os
from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable TimescaleDB (requires superuser connection)
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")

    # Create the non-superuser application role.
    # Password is read from the env so it never appears in the migration source.
    app_password = os.environ.get("POSTGRES_PASSWORD", "change_me_db_password")
    app_user = os.environ.get("POSTGRES_USER", "obdmonai_app")
    db_name = os.environ.get("POSTGRES_DB", "obdmonai")

    op.execute(f"""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{app_user}') THEN
            CREATE ROLE "{app_user}" WITH LOGIN PASSWORD '{app_password}';
        END IF;
    END
    $$;
    """)

    # Least-privilege grants: connect + schema usage.
    # Table/sequence grants are set via ALTER DEFAULT PRIVILEGES so every
    # subsequent migration's new objects are automatically covered.
    op.execute(f'GRANT CONNECT ON DATABASE "{db_name}" TO "{app_user}";')
    op.execute(f'GRANT USAGE ON SCHEMA public TO "{app_user}";')
    op.execute(f"""
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{app_user}";
    """)
    op.execute(f"""
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO "{app_user}";
    """)
    # alembic_version is created before any migration runs, so it predates the
    # ALTER DEFAULT PRIVILEGES above.  Grant SELECT explicitly so the app role
    # can verify the migration level in tests and health checks.
    op.execute(f'GRANT SELECT ON alembic_version TO "{app_user}";')

    # Read access to TimescaleDB information views
    op.execute(f'GRANT USAGE ON SCHEMA timescaledb_information TO "{app_user}";')
    op.execute(f"""
    GRANT SELECT ON ALL TABLES IN SCHEMA timescaledb_information TO "{app_user}";
    """)


def downgrade() -> None:
    app_user = os.environ.get("POSTGRES_USER", "obdmonai_app")
    db_name = os.environ.get("POSTGRES_DB", "obdmonai")

    op.execute(f"""
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM "{app_user}";
    """)
    op.execute(f"""
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        REVOKE USAGE, SELECT ON SEQUENCES FROM "{app_user}";
    """)
    op.execute(f'REVOKE CONNECT ON DATABASE "{db_name}" FROM "{app_user}";')
    # DROP OWNED BY revokes ALL privileges granted to the role across all schemas
    # (including timescaledb_information views), allowing DROP ROLE to succeed.
    op.execute(f'DROP OWNED BY "{app_user}";')
    op.execute(f'DROP ROLE IF EXISTS "{app_user}";')
    # Intentionally NOT dropping the timescaledb extension on downgrade.
