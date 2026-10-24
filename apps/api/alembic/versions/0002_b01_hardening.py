"""B0.1 hardening: connection direction/decision fields, challenge attempts,
encrypted TOTP secret, scoped login-resolution function.

Replaces runtime admin-engine reads at the auth boundary with a
SECURITY DEFINER function exposing only the login projection — the runtime
role (easyrs_app, RLS-subject) can EXECUTE it but gains no table access.

Revision ID: 0002_b01_hardening
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_b01_hardening"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- org_connection: direction + decision audit + richer status set ------
    op.execute("ALTER TABLE org_connection ALTER COLUMN status DROP DEFAULT")
    op.alter_column("org_connection", "status", type_=sa.String(16))
    op.alter_column("org_connection", "status",
                    server_default=sa.text("'pending'"))
    op.drop_constraint("uq_connection", "org_connection", type_="unique")
    op.execute("DROP TYPE IF EXISTS connection_status")
    op.create_check_constraint(
        "ck_connection_status", "org_connection",
        "status IN ('pending','accepted','rejected','withdrawn','revoked')")
    op.create_unique_constraint(
        "uq_connection", "org_connection", ["practice_org_id", "lab_org_id"])
    op.add_column("org_connection",
                  sa.Column("initiated_by_org_id", sa.dialects.postgresql.UUID(as_uuid=True),
                            nullable=True))
    # Synthetic-data-only backfill: existing rows predated direction tracking;
    # practice side is the conventional initiator, so default to it.
    op.execute("UPDATE org_connection SET initiated_by_org_id = practice_org_id "
               "WHERE initiated_by_org_id IS NULL")
    op.alter_column("org_connection", "initiated_by_org_id", nullable=False)
    op.add_column("org_connection",
                  sa.Column("decided_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                            nullable=True))
    op.add_column("org_connection",
                  sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))

    # --- auth_challenge: brute-force cap ------------------------------------
    op.add_column("auth_challenge",
                  sa.Column("attempts", sa.Integer(), server_default="0",
                            nullable=False))

    # --- user_account: TOTP secret encrypted at rest -------------------------
    op.drop_column("user_account", "totp_secret")
    op.add_column("user_account",
                  sa.Column("totp_secret_enc", sa.LargeBinary(), nullable=True))

    # --- resolve_login: narrow pre-auth lookup without RLS bypass ------------
    # SECURITY DEFINER => runs as owner (admin, RLS-exempt) but only projects
    # the fields needed to bind tenant context + active org at login.
    op.execute("""
        CREATE OR REPLACE FUNCTION resolve_login(p_email text)
        RETURNS TABLE(user_id uuid, org_id uuid, tenant_id uuid,
                      org_status varchar, member_role varchar)
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public AS $$
            SELECT m.user_id, m.org_id, m.tenant_id,
                   o.status::varchar AS org_status, m.role::varchar AS member_role
            FROM membership m
            JOIN organization o ON o.id = m.org_id
            JOIN user_account u ON u.id = m.user_id
            WHERE u.email = lower(p_email) AND m.status = 'active'
            ORDER BY m.created_at
            LIMIT 1
        $$""")
    op.execute("ALTER FUNCTION resolve_login(text) OWNER TO easyrs_admin")
    op.execute("REVOKE ALL ON FUNCTION resolve_login(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION resolve_login(text) TO easyrs_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS resolve_login(text)")
    op.drop_column("user_account", "totp_secret_enc")
    op.add_column("user_account",
                  sa.Column("totp_secret", sa.String(64), nullable=True))
    op.drop_column("auth_challenge", "attempts")
    op.drop_column("org_connection", "decided_at")
    op.drop_column("org_connection", "decided_by_user_id")
    op.drop_column("org_connection", "initiated_by_org_id")
    op.drop_constraint("ck_connection_status", "org_connection", type_="check")
