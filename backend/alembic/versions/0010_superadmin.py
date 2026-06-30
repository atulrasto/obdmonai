"""Add superadmin role, must_change_password flag, and related DB helpers.

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-30

Changes
-------
1. users.client_id  → nullable  (superadmin has no tenant client)
2. users.must_change_password → BOOLEAN NOT NULL DEFAULT false
3. Drop/recreate auth_get_user_by_email — adds must_change_password to output
4. Drop/recreate auth_get_user_by_id   — adds password_hash + must_change_password
5. Add auth_create_superadmin(email, password_hash) SECURITY DEFINER
6. Add auth_set_password(user_id, password_hash, must_change) SECURITY DEFINER
"""
from __future__ import annotations

import os
from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_APP_USER = os.environ.get("POSTGRES_USER", "obdmonai_app")


def upgrade() -> None:
    # 0. Expand role check constraint to include superadmin
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role")
    op.execute("""
        ALTER TABLE users
        ADD CONSTRAINT ck_users_role
        CHECK (role IN ('superadmin', 'owner', 'fleet_admin', 'viewer'))
    """)

    # 1. Make client_id nullable so superadmin rows can have NULL client_id
    op.execute("ALTER TABLE users ALTER COLUMN client_id DROP NOT NULL")

    # 2. Add must_change_password column
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT false
    """)

    # 3. Recreate auth_get_user_by_email with must_change_password in output
    op.execute("DROP FUNCTION IF EXISTS auth_get_user_by_email(TEXT)")
    op.execute("""
        CREATE FUNCTION auth_get_user_by_email(p_email TEXT)
        RETURNS TABLE(
            id                   UUID,
            client_id            UUID,
            password_hash        TEXT,
            role                 TEXT,
            is_active            BOOL,
            must_change_password BOOL
        )
        LANGUAGE SQL SECURITY DEFINER STABLE
        AS $$
            SELECT id, client_id, password_hash, role, is_active, must_change_password
            FROM users
            WHERE email = p_email
            LIMIT 1;
        $$;
    """)
    op.execute(f'GRANT EXECUTE ON FUNCTION auth_get_user_by_email(TEXT) TO "{_APP_USER}";')

    # 4. Recreate auth_get_user_by_id — adds password_hash + must_change_password
    op.execute("DROP FUNCTION IF EXISTS auth_get_user_by_id(UUID)")
    op.execute("""
        CREATE FUNCTION auth_get_user_by_id(p_id UUID)
        RETURNS TABLE(
            id                   UUID,
            client_id            UUID,
            password_hash        TEXT,
            role                 TEXT,
            is_active            BOOL,
            must_change_password BOOL
        )
        LANGUAGE SQL SECURITY DEFINER STABLE
        AS $$
            SELECT id, client_id, password_hash, role, is_active, must_change_password
            FROM users
            WHERE id = p_id
            LIMIT 1;
        $$;
    """)
    op.execute(f'GRANT EXECUTE ON FUNCTION auth_get_user_by_id(UUID) TO "{_APP_USER}";')

    # 4b. Update auth_create_initial_owner to support must_change_password flag
    op.execute("DROP FUNCTION IF EXISTS auth_create_initial_owner(UUID, TEXT, TEXT)")
    op.execute("""
        CREATE FUNCTION auth_create_initial_owner(
            p_client_id          UUID,
            p_email              TEXT,
            p_password_hash      TEXT,
            p_must_change        BOOLEAN DEFAULT false
        )
        RETURNS UUID
        LANGUAGE SQL SECURITY DEFINER VOLATILE
        AS $$
            INSERT INTO users (client_id, email, password_hash, role, must_change_password)
            VALUES (p_client_id, p_email, p_password_hash, 'owner', p_must_change)
            RETURNING id;
        $$;
    """)
    op.execute(f'GRANT EXECUTE ON FUNCTION auth_create_initial_owner(UUID, TEXT, TEXT, BOOLEAN) TO "{_APP_USER}";')

    # 5. SECURITY DEFINER function to create superadmin (bypasses RLS + nullable FK)
    op.execute("""
        CREATE FUNCTION auth_create_superadmin(p_email TEXT, p_password_hash TEXT)
        RETURNS UUID
        LANGUAGE SQL SECURITY DEFINER VOLATILE
        AS $$
            INSERT INTO users (client_id, email, password_hash, role, must_change_password)
            VALUES (NULL, p_email, p_password_hash, 'superadmin', TRUE)
            ON CONFLICT (email) DO NOTHING
            RETURNING id;
        $$;
    """)
    op.execute(f'GRANT EXECUTE ON FUNCTION auth_create_superadmin(TEXT, TEXT) TO "{_APP_USER}";')

    # 6. SECURITY DEFINER to update password + must_change_password flag
    op.execute("""
        CREATE FUNCTION auth_set_password(
            p_user_id     UUID,
            p_hash        TEXT,
            p_must_change BOOLEAN DEFAULT false
        )
        RETURNS VOID
        LANGUAGE SQL SECURITY DEFINER VOLATILE
        AS $$
            UPDATE users
            SET password_hash = p_hash, must_change_password = p_must_change
            WHERE id = p_user_id;
        $$;
    """)
    op.execute(f'GRANT EXECUTE ON FUNCTION auth_set_password(UUID, TEXT, BOOLEAN) TO "{_APP_USER}";')


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS auth_set_password(UUID, TEXT, BOOLEAN)")
    op.execute("DROP FUNCTION IF EXISTS auth_create_superadmin(TEXT, TEXT)")

    # Restore old 3-arg auth_create_initial_owner
    op.execute("DROP FUNCTION IF EXISTS auth_create_initial_owner(UUID, TEXT, TEXT, BOOLEAN)")
    op.execute("""
        CREATE FUNCTION auth_create_initial_owner(
            p_client_id UUID, p_email TEXT, p_password_hash TEXT
        )
        RETURNS UUID LANGUAGE SQL SECURITY DEFINER VOLATILE
        AS $$
            INSERT INTO users (client_id, email, password_hash, role)
            VALUES (p_client_id, p_email, p_password_hash, 'owner')
            RETURNING id;
        $$;
    """)
    op.execute(f'GRANT EXECUTE ON FUNCTION auth_create_initial_owner(UUID, TEXT, TEXT) TO "{_APP_USER}";')

    # Restore old auth_get_user_by_id (no password_hash / must_change_password)
    op.execute("DROP FUNCTION IF EXISTS auth_get_user_by_id(UUID)")
    op.execute("""
        CREATE FUNCTION auth_get_user_by_id(p_id UUID)
        RETURNS TABLE(id UUID, client_id UUID, role TEXT, is_active BOOL)
        LANGUAGE SQL SECURITY DEFINER STABLE
        AS $$
            SELECT id, client_id, role, is_active FROM users WHERE id = p_id LIMIT 1;
        $$;
    """)
    op.execute(f'GRANT EXECUTE ON FUNCTION auth_get_user_by_id(UUID) TO "{_APP_USER}";')

    # Restore old auth_get_user_by_email (no must_change_password)
    op.execute("DROP FUNCTION IF EXISTS auth_get_user_by_email(TEXT)")
    op.execute("""
        CREATE FUNCTION auth_get_user_by_email(p_email TEXT)
        RETURNS TABLE(id UUID, client_id UUID, password_hash TEXT, role TEXT, is_active BOOL)
        LANGUAGE SQL SECURITY DEFINER STABLE
        AS $$
            SELECT id, client_id, password_hash, role, is_active FROM users WHERE email = p_email LIMIT 1;
        $$;
    """)
    op.execute(f'GRANT EXECUTE ON FUNCTION auth_get_user_by_email(TEXT) TO "{_APP_USER}";')

    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS must_change_password")
    # Restore NOT NULL — delete superadmin rows first (they have NULL client_id)
    op.execute("DELETE FROM users WHERE role = 'superadmin'")
    op.execute("ALTER TABLE users ALTER COLUMN client_id SET NOT NULL")
    # Restore old role constraint
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role")
    op.execute("""
        ALTER TABLE users
        ADD CONSTRAINT ck_users_role
        CHECK (role IN ('owner', 'fleet_admin', 'viewer'))
    """)
