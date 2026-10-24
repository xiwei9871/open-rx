"""0001 IAM + auth + audit baseline with tenant RLS

- tenant-scoped tables get ENABLE ROW LEVEL SECURITY + FOR ALL policy
  tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  (unset GUC -> NULL -> zero rows: deny by default)
- audit_event: SELECT restricted to tenant; INSERT CHECK(true); no UPDATE/
  DELETE policy -> append-only for the runtime user
- auth/identity tables (user_account, auth_session, auth_challenge, tenant)
  intentionally unscoped (identity domain, not business data)

Revision: 0001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TENANT_SCOPED = [
    "organization", "location", "membership", "roster_member", "org_connection",
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "tenant",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_table(
        "user_account",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(300), nullable=False),
        sa.Column("status", sa.Enum("active", "disabled", name="user_status"),
                  server_default="active"),
        sa.Column("totp_secret", sa.String(64)),
        sa.Column("totp_enabled", sa.Boolean(), server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("ix_user_account_email", "user_account", ["email"])

    op.create_table(
        "organization",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("kind", sa.Enum("practice", "lab", "hybrid", name="org_kind"),
                  nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("timezone", sa.String(64), server_default="UTC"),
        sa.Column("status", sa.Enum("active", "suspended", name="org_status"),
                  server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("ix_organization_tenant", "organization", ["tenant_id"])

    op.create_table(
        "location",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("organization.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("address", sa.String(500)),
        sa.Column("phone", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("ix_location_tenant", "location", ["tenant_id"])
    op.create_index("ix_location_org", "location", ["org_id"])

    op.create_table(
        "membership",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("organization.id"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("user_account.id"), nullable=False),
        sa.Column("role", sa.Enum(
            "practice_admin", "practice_doctor", "practice_staff",
            "lab_admin", "lab_technician", name="member_role"), nullable=False),
        sa.Column("status", sa.Enum("invited", "active", "disabled",
                                    name="member_status"),
                  server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "user_id", name="uq_membership"),
    )
    op.create_index("ix_membership_tenant", "membership", ["tenant_id"])
    op.create_index("ix_membership_org", "membership", ["org_id"])
    op.create_index("ix_membership_user", "membership", ["user_id"])

    op.create_table(
        "roster_member",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("organization.id"), nullable=False),
        sa.Column("kind", sa.Enum("doctor", "staff", name="roster_kind"),
                  nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("credentials", sa.String(300)),
        sa.Column("is_default", sa.Boolean(), server_default=sa.false()),
        sa.Column("linked_user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("user_account.id")),
        sa.Column("status", sa.Enum("active", "disabled", name="roster_status"),
                  server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("ix_roster_tenant", "roster_member", ["tenant_id"])
    op.create_index("ix_roster_org", "roster_member", ["org_id"])

    op.create_table(
        "org_connection",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("practice_org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("lab_org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Enum("pending", "accepted", "revoked",
                                    name="connection_status"),
                  server_default="pending"),
        sa.Column("granted_scopes", pg.JSONB(), server_default="[]"),
        sa.Column("version", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("practice_org_id", "lab_org_id",
                            name="uq_connection"),
    )
    op.create_index("ix_conn_tenant", "org_connection", ["tenant_id"])
    op.create_index("ix_conn_practice", "org_connection", ["practice_org_id"])
    op.create_index("ix_conn_lab", "org_connection", ["lab_org_id"])

    op.create_table(
        "auth_session",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("user_account.id"), nullable=False),
        sa.Column("active_org_id", pg.UUID(as_uuid=True)),
        sa.Column("tenant_id", pg.UUID(as_uuid=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.String(300)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("ix_session_token", "auth_session", ["token_hash"])
    op.create_index("ix_session_user", "auth_session", ["user_id"])

    op.create_table(
        "auth_challenge",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("user_account.id"), nullable=False),
        sa.Column("purpose", sa.Enum("totp_login", name="challenge_purpose"),
                  nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("ix_challenge_user", "auth_challenge", ["user_id"])

    op.create_table(
        "audit_event",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", pg.UUID(as_uuid=True)),
        sa.Column("org_id", pg.UUID(as_uuid=True)),
        sa.Column("actor_user_id", pg.UUID(as_uuid=True)),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("object_type", sa.String(80), nullable=False),
        sa.Column("object_id", sa.String(80), nullable=False),
        sa.Column("before_hash", sa.String(64)),
        sa.Column("after_hash", sa.String(64)),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.String(300)),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_tenant", "audit_event", ["tenant_id"])
    op.create_index("ix_audit_action", "audit_event", ["action"])
    op.create_index("ix_audit_ts", "audit_event", ["ts"])

    # ---------- row-level security ----------
    for table in TENANT_SCOPED:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            FOR ALL
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """)

    op.execute("ALTER TABLE audit_event ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY audit_tenant_select ON audit_event FOR SELECT
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    """)
    op.execute("""
        CREATE POLICY audit_tenant_insert ON audit_event FOR INSERT
        WITH CHECK (true)
    """)
    # No UPDATE/DELETE policy on audit_event -> append-only for the app user.


def downgrade() -> None:
    for table in reversed([
        "audit_event", "auth_challenge", "auth_session", "org_connection",
        "roster_member", "membership", "location", "organization",
        "user_account", "tenant",
    ]):
        op.drop_table(table)
    for enum in ["challenge_purpose", "connection_status", "roster_status",
                 "roster_kind", "member_status", "member_role", "org_status",
                 "org_kind", "user_status"]:
        op.execute(f"DROP TYPE IF EXISTS {enum}")
