"""Fix RLS NULLIF safety and add SECURITY DEFINER auth helper.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-29

Changes
-------
1. Fix RLS expressions: replace ``current_setting(...)::uuid`` with
   ``NULLIF(current_setting(...), '')::uuid`` so the expression returns NULL
   (deny all) rather than erroring when the GUC is unset.

2. Add ``auth_get_user_by_email(email)`` SECURITY DEFINER function so the
   login endpoint can look up a user without a tenant context (chicken-and-egg:
   we don't know client_id until after we validate the password).
"""
from __future__ import annotations

import os
from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS_TABLES = ("users", "vehicles", "devices", "telemetry")
_OLD_EXPR = "client_id = current_setting('app.current_client_id', true)::uuid"
_NEW_EXPR = "client_id = NULLIF(current_setting('app.current_client_id', true), '')::uuid"


def upgrade() -> None:
    # ---- Fix RLS expressions ----
    for table in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_insert ON {table};")
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
                USING ({_NEW_EXPR});
        """)
        op.execute(f"""
            CREATE POLICY {table}_tenant_insert ON {table}
                FOR INSERT
                WITH CHECK ({_NEW_EXPR});
        """)

    # ---- SECURITY DEFINER function for login ----
    op.execute("""
        CREATE FUNCTION auth_get_user_by_email(p_email TEXT)
        RETURNS TABLE(
            id         UUID,
            client_id  UUID,
            password_hash TEXT,
            role       TEXT,
            is_active  BOOL
        )
        LANGUAGE SQL SECURITY DEFINER STABLE
        AS $$
            SELECT id, client_id, password_hash, role, is_active
            FROM users
            WHERE email = p_email
            LIMIT 1;
        $$;
    """)

    # ---- SECURITY DEFINER function for token refresh ----
    op.execute("""
        CREATE FUNCTION auth_get_user_by_id(p_id UUID)
        RETURNS TABLE(
            id         UUID,
            client_id  UUID,
            role       TEXT,
            is_active  BOOL
        )
        LANGUAGE SQL SECURITY DEFINER STABLE
        AS $$
            SELECT id, client_id, role, is_active
            FROM users
            WHERE id = p_id
            LIMIT 1;
        $$;
    """)

    # ---- SECURITY DEFINER function for bootstrap user creation ----
    # create_client (POST /clients) must insert the initial owner user, but the
    # users table has RLS enabled and the GUC is not set at registration time.
    # This function bypasses RLS to insert the owner row safely.
    op.execute("""
        CREATE FUNCTION auth_create_initial_owner(
            p_client_id   UUID,
            p_email       TEXT,
            p_password_hash TEXT
        )
        RETURNS UUID
        LANGUAGE SQL SECURITY DEFINER VOLATILE
        AS $$
            INSERT INTO users (client_id, email, password_hash, role)
            VALUES (p_client_id, p_email, p_password_hash, 'owner')
            RETURNING id;
        $$;
    """)

    app_user = os.environ.get("POSTGRES_USER", "obdmonai_app")
    op.execute(f'GRANT EXECUTE ON FUNCTION auth_get_user_by_email(TEXT) TO "{app_user}";')
    op.execute(f'GRANT EXECUTE ON FUNCTION auth_get_user_by_id(UUID) TO "{app_user}";')
    op.execute(f'GRANT EXECUTE ON FUNCTION auth_create_initial_owner(UUID, TEXT, TEXT) TO "{app_user}";')


def downgrade() -> None:
    # DROP cascades all GRANTs automatically — no explicit REVOKE needed.
    op.execute("DROP FUNCTION IF EXISTS auth_create_initial_owner(UUID, TEXT, TEXT);")
    op.execute("DROP FUNCTION IF EXISTS auth_get_user_by_id(UUID);")
    op.execute("DROP FUNCTION IF EXISTS auth_get_user_by_email(TEXT);")

    # Revert to the old (buggy) expressions
    for table in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_insert ON {table};")
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
                USING ({_OLD_EXPR});
        """)
        op.execute(f"""
            CREATE POLICY {table}_tenant_insert ON {table}
                FOR INSERT
                WITH CHECK ({_OLD_EXPR});
        """)
