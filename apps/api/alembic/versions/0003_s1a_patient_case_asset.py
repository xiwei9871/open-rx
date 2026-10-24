"""S1a: patient / treatment_case / asset / upload_session / file_reference /
access_grant. All tenant-RLS scoped. Assets are content-addressed and have no
mutating API (immutability); patients soft-delete only.

Revision ID: 0003_s1a_patient_case_asset
Revises: 0002_b01_hardening
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0003_s1a_patient_case_asset"
down_revision = "0002_b01_hardening"
branch_labels = None
depends_on = None

UUID = pg.UUID(as_uuid=True)
TENANT_SCOPED = ["patient", "treatment_case", "asset", "upload_session",
                 "file_reference", "access_grant"]


def upgrade() -> None:
    op.execute("CREATE SEQUENCE patient_number_seq")

    op.create_table(
        "patient",
        sa.Column("id", UUID, primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", UUID, nullable=False, index=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organization.id"),
                  nullable=False, index=True),
        sa.Column("patient_number", sa.String(24), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("dob", sa.Date(), nullable=True),
        sa.Column("external_ref", sa.String(128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("patient_number", name="uq_patient_number"),
    )
    # external_ref unique per org among live rows only
    op.execute("""
        CREATE UNIQUE INDEX uq_patient_external_ref ON patient (org_id, external_ref)
        WHERE external_ref IS NOT NULL AND deleted_at IS NULL
    """)
    op.create_index("ix_patient_name", "patient",
                    ["org_id", "last_name", "first_name"])

    op.create_table(
        "treatment_case",
        sa.Column("id", UUID, primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", UUID, nullable=False, index=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organization.id"),
                  nullable=False, index=True),
        sa.Column("patient_id", UUID, sa.ForeignKey("patient.id"),
                  nullable=False, index=True),
        sa.Column("label", sa.String(200), nullable=True),
        sa.Column("stage", sa.String(16), nullable=False, server_default="active"),
        sa.Column("opened_by_user_id", UUID, sa.ForeignKey("user_account.id"),
                  nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.CheckConstraint("stage IN ('active','completed','cancelled')",
                           name="ck_case_stage"),
    )

    op.create_table(
        "asset",
        sa.Column("id", UUID, primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", UUID, nullable=False, index=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organization.id"),
                  nullable=False, index=True),
        sa.Column("uploaded_by_user_id", UUID, sa.ForeignKey("user_account.id"),
                  nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("jaw", sa.String(8), nullable=False, server_default="na"),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False, unique=True),
        sa.Column("scan_status", sa.String(16), nullable=False,
                  server_default="pending"),
        sa.Column("parent_asset_id", UUID, sa.ForeignKey("asset.id"),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "sha256", name="uq_asset_org_sha256"),
        sa.CheckConstraint("kind IN ('stl','pdf','image','other')",
                           name="ck_asset_kind"),
        sa.CheckConstraint("jaw IN ('upper','lower','na')", name="ck_asset_jaw"),
        sa.CheckConstraint(
            "scan_status IN ('pending','clean','infected','failed')",
            name="ck_asset_scan_status"),
    )

    op.create_table(
        "upload_session",
        sa.Column("id", UUID, primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", UUID, nullable=False, index=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organization.id"),
                  nullable=False, index=True),
        sa.Column("user_id", UUID, sa.ForeignKey("user_account.id"),
                  nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("jaw", sa.String(8), nullable=False, server_default="na"),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("storage_key", sa.String(512), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('open','completed','expired')",
                           name="ck_upload_session_status"),
    )

    op.create_table(
        "file_reference",
        sa.Column("id", UUID, primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", UUID, nullable=False, index=True),
        sa.Column("asset_id", UUID, sa.ForeignKey("asset.id"),
                  nullable=False, index=True),
        sa.Column("subject_type", sa.String(16), nullable=False),
        sa.Column("subject_id", UUID, nullable=False, index=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("granted_by_org_id", UUID, sa.ForeignKey("organization.id"),
                  nullable=False),
        sa.Column("granted_by_user_id", UUID, sa.ForeignKey("user_account.id"),
                  nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.CheckConstraint(
            "subject_type IN ('patient','case','rx','notification','order')",
            name="ck_fileref_subject"),
        sa.CheckConstraint(
            "role IN ('original','optimized','processed','print_ready','attachment')",
            name="ck_fileref_role"),
    )
    op.execute("""
        CREATE UNIQUE INDEX uq_fileref_live ON file_reference
        (asset_id, subject_type, subject_id, role) WHERE revoked_at IS NULL
    """)

    op.create_table(
        "access_grant",
        sa.Column("id", UUID, primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", UUID, nullable=False, index=True),
        sa.Column("asset_id", UUID, sa.ForeignKey("asset.id"),
                  nullable=False, index=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organization.id"),
                  nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("user_account.id"),
                  nullable=False),
        sa.Column("file_reference_id", UUID, sa.ForeignKey("file_reference.id"),
                  nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # least-privilege runtime role needs nextval() for patient_number
    op.execute("GRANT USAGE, SELECT ON SEQUENCE patient_number_seq TO easyrs_app")

    for table in TENANT_SCOPED:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            FOR ALL
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """)


def downgrade() -> None:
    for table in reversed(TENANT_SCOPED):
        op.drop_table(table)
    op.execute("DROP SEQUENCE patient_number_seq")
