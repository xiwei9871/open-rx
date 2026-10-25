"""M1: organization defaults (doctor/location) + rx_template.

- organization.default_doctor_id / default_location_id: prefill values for
  Rx create (IAM-001/003/010 scope — org-level defaults only).
- rx_template: practice-owned reusable Rx item/field payloads (RX-010).
  Templates reference catalog_item ids inside payload JSONB; applying a
  template re-validates those ids at write time (no FK inside JSONB).

Revision ID: 0009_m1_studio
Revises: 0008_finalgate
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0009_m1_studio"
down_revision = "0008_finalgate"
branch_labels = None
depends_on = None

UUID = pg.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("organization", sa.Column(
        "default_doctor_id", UUID,
        sa.ForeignKey("roster_member.id"), nullable=True))
    op.add_column("organization", sa.Column(
        "default_location_id", UUID,
        sa.ForeignKey("location.id"), nullable=True))

    op.create_table(
        "rx_template",
        sa.Column("id", UUID, primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", UUID, nullable=False, index=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organization.id"),
                  nullable=False, index=True),
        sa.Column("created_by_user_id", UUID,
                  sa.ForeignKey("user_account.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        # {items: [{catalog_item_id, arch, tooth_ops, options, qty}],
        #  notes?, due_days_offset?, form_type?}
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.execute("ALTER TABLE rx_template ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON rx_template
        FOR ALL
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    """)


def downgrade() -> None:
    op.drop_table("rx_template")
    op.drop_column("organization", "default_location_id")
    op.drop_column("organization", "default_doctor_id")
