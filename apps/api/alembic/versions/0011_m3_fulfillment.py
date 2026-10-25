"""M3: fulfillment & delivery — separate logistics track.

- rx: carrier/tracking + shipped/received/delivered stamps + qc_status.
  rx.fulfillment_status is the logistics track: none -> qc_pending (set at
  clinical complete) -> qc_passed -> shipped -> received -> delivered.
  Clinical status stays 'completed' — the two tracks never alias.
- qc_record: append-only manual QC confirmations (lab side).
- fulfillment_event: append-only logistics trail, seq-ordered.

Revision ID: 0011_m3_fulfillment
Revises: 0010_m2_collaboration
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0011_m3_fulfillment"
down_revision = "0010_m2_collaboration"
branch_labels = None
depends_on = None

UUID = pg.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("rx", sa.Column("carrier", sa.String(120), nullable=True))
    op.add_column("rx", sa.Column(
        "tracking_number", sa.String(120), nullable=True))
    op.add_column("rx", sa.Column(
        "shipped_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("rx", sa.Column(
        "shipped_by_user_id", UUID,
        sa.ForeignKey("user_account.id"), nullable=True))
    op.add_column("rx", sa.Column(
        "received_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("rx", sa.Column(
        "received_by_user_id", UUID,
        sa.ForeignKey("user_account.id"), nullable=True))
    op.add_column("rx", sa.Column(
        "delivered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("rx", sa.Column(
        "delivered_by_user_id", UUID,
        sa.ForeignKey("user_account.id"), nullable=True))
    op.add_column("rx", sa.Column("qc_status", sa.String(16),
                                  nullable=False, server_default="none"))

    # widen the fulfillment vocabulary: the 0005 values stay valid, the M3
    # chain adds the QC gate + shipped.
    op.drop_constraint("ck_rx_fulfillment", "rx", type_="check")
    op.create_check_constraint(
        "ck_rx_fulfillment", "rx",
        "fulfillment_status IN ('none','qc_pending','qc_passed','shipped',"
        "'dispatched','in_transit','received','delivered','exception')")

    op.create_table(
        "qc_record",
        sa.Column("id", UUID, primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", UUID, nullable=False, index=True),
        sa.Column("rx_id", UUID, sa.ForeignKey("rx.id"), nullable=False,
                  index=True),
        sa.Column("result", sa.String(8), nullable=False),
        sa.Column("note", sa.String(2000), nullable=True),
        sa.Column("checked_by_user_id", UUID,
                  sa.ForeignKey("user_account.id"), nullable=False),
        sa.Column("checked_by_org_id", UUID,
                  sa.ForeignKey("organization.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.CheckConstraint("result IN ('pass','fail')",
                           name="ck_qc_record_result"),
    )

    op.create_table(
        "fulfillment_event",
        sa.Column("id", UUID, primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", UUID, nullable=False, index=True),
        sa.Column("rx_id", UUID, sa.ForeignKey("rx.id"), nullable=False,
                  index=True),
        sa.Column("seq", sa.Integer(), sa.Identity(always=False),
                  nullable=False),
        sa.Column("event", sa.String(24), nullable=False),
        sa.Column("actor_user_id", UUID,
                  sa.ForeignKey("user_account.id"), nullable=False),
        sa.Column("actor_org_id", UUID,
                  sa.ForeignKey("organization.id"), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("ix_fulfillment_event_rx_seq", "fulfillment_event",
                    ["rx_id", "seq"])

    for table in ("qc_record", "fulfillment_event"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            FOR ALL
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """)


def downgrade() -> None:
    op.drop_table("fulfillment_event")
    op.drop_table("qc_record")
    op.drop_constraint("ck_rx_fulfillment", "rx", type_="check")
    op.create_check_constraint(
        "ck_rx_fulfillment", "rx",
        "fulfillment_status IN ('none','dispatched','in_transit',"
        "'received','delivered','exception')")
    for col in ("qc_status", "delivered_by_user_id", "delivered_at",
                "received_by_user_id", "received_at", "shipped_by_user_id",
                "shipped_at", "tracking_number", "carrier"):
        op.drop_column("rx", col)
