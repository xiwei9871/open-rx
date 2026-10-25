"""S1b-Core: rx / rx_item / rx_transition / rx_comment / catalog_item.

Lifecycle (V1.1-verified, docs/research/v1.1-rx-rules.md):
  draft -> submitted -> checked_in -> completed -> shipped -> received
          ^    |                                            -> delivered
          +----+ unsubmit (allowed only while status=submitted)
Check-in is a lab-side act; a lab-side bundle download also checks in
(checked_in_via = button|download). in_progress/on_hold/reopened are
EasyRS-internal states with no confirmed EasyRx equivalent.

Revision ID: 0005_s1b_rx_core
Revises: 0004_s1a1_asset_format_status
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0005_s1b_rx_core"
down_revision = "0004_s1a1_asset_format_status"
branch_labels = None
depends_on = None

UUID = pg.UUID(as_uuid=True)
TENANT_SCOPED = ["catalog_item", "rx", "rx_item", "rx_transition",
                 "rx_comment"]


def upgrade() -> None:
    op.execute("CREATE SEQUENCE rx_number_seq")

    op.create_table(
        "catalog_item",
        sa.Column("id", UUID, primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", UUID, nullable=False, index=True),
        # NULL owner = universal library entry (V-04: universal + lab-owned
        # parts coexist; lab-owned rows scope to a lab org).
        sa.Column("owner_org_id", UUID, sa.ForeignKey("organization.id"),
                  nullable=True, index=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("option_schema", pg.JSONB(), nullable=True),
        sa.Column("arch_scope", sa.String(8), nullable=False,
                  server_default="both"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.CheckConstraint("kind IN ('part','appliance')",
                           name="ck_catalog_kind"),
        sa.CheckConstraint("arch_scope IN ('upper','lower','both')",
                           name="ck_catalog_arch"),
    )

    op.create_table(
        "rx",
        sa.Column("id", UUID, primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", UUID, nullable=False, index=True),
        sa.Column("practice_org_id", UUID, sa.ForeignKey("organization.id"),
                  nullable=False, index=True),
        sa.Column("rx_number", sa.String(24), nullable=False),
        sa.Column("patient_id", UUID, sa.ForeignKey("patient.id"),
                  nullable=False, index=True),
        sa.Column("case_id", UUID, sa.ForeignKey("treatment_case.id"),
                  nullable=True),
        sa.Column("lab_org_id", UUID, sa.ForeignKey("organization.id"),
                  nullable=True, index=True),
        sa.Column("location_id", UUID, sa.ForeignKey("location.id"),
                  nullable=True),
        sa.Column("doctor_id", UUID, sa.ForeignKey("roster_member.id"),
                  nullable=True),
        sa.Column("form_type", sa.String(16), nullable=False,
                  server_default="standard"),
        sa.Column("form_payload", pg.JSONB(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default="draft"),
        sa.Column("fulfillment_status", sa.String(16), nullable=False,
                  server_default="none"),
        sa.Column("checked_in_via", sa.String(16), nullable=True),
        sa.Column("created_by_user_id", UUID,
                  sa.ForeignKey("user_account.id"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_by_user_id", UUID,
                  sa.ForeignKey("user_account.id"), nullable=True),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_in_by_user_id", UUID,
                  sa.ForeignKey("user_account.id"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signature_name", sa.String(200), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("submit_idem_key", sa.String(128), nullable=True),
        sa.Column("submit_idem_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("rx_number", name="uq_rx_number"),
        sa.CheckConstraint(
            "status IN ('draft','submitted','checked_in','in_progress',"
            "'on_hold','completed','reopened','cancelled')",
            name="ck_rx_status"),
        sa.CheckConstraint(
            "fulfillment_status IN ('none','dispatched','in_transit',"
            "'received','delivered','exception')",
            name="ck_rx_fulfillment"),
        sa.CheckConstraint("form_type IN ('standard','aligner','idb')",
                           name="ck_rx_form_type"),
        sa.CheckConstraint("checked_in_via IS NULL OR checked_in_via IN "
                           "('button','download')", name="ck_rx_checkin_via"),
    )
    op.create_index("ix_rx_practice_status", "rx",
                    ["practice_org_id", "status"])
    op.create_index("ix_rx_lab_status", "rx", ["lab_org_id", "status"])

    op.create_table(
        "rx_item",
        sa.Column("id", UUID, primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", UUID, nullable=False, index=True),
        sa.Column("rx_id", UUID, sa.ForeignKey("rx.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("catalog_item_id", UUID,
                  sa.ForeignKey("catalog_item.id"), nullable=False),
        sa.Column("arch", sa.String(8), nullable=False),
        sa.Column("tooth_ops", pg.JSONB(), nullable=False,
                  server_default="[]"),
        sa.Column("options", pg.JSONB(), nullable=True),
        sa.Column("qty", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.CheckConstraint("arch IN ('upper','lower','both')",
                           name="ck_rxitem_arch"),
        sa.CheckConstraint("qty >= 1", name="ck_rxitem_qty"),
    )

    op.create_table(
        "rx_transition",
        sa.Column("id", UUID, primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", UUID, nullable=False, index=True),
        sa.Column("rx_id", UUID, sa.ForeignKey("rx.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("via", sa.String(16), nullable=False,
                  server_default="button"),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("user_account.id"),
                  nullable=False),
        sa.Column("actor_org_id", UUID, sa.ForeignKey("organization.id"),
                  nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    op.create_table(
        "rx_comment",
        sa.Column("id", UUID, primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", UUID, nullable=False, index=True),
        sa.Column("rx_id", UUID, sa.ForeignKey("rx.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("author_membership_id", UUID,
                  sa.ForeignKey("membership.id"), nullable=False),
        sa.Column("parent_id", UUID, sa.ForeignKey("rx_comment.id"),
                  nullable=True),
        sa.Column("body", sa.String(4000), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    op.execute("GRANT USAGE, SELECT ON SEQUENCE rx_number_seq TO easyrs_app")

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
    op.execute("DROP SEQUENCE rx_number_seq")
