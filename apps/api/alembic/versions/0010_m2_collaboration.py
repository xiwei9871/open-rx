"""M2: notification + approval + attachment-level comments.

- notification: structured clinical/issue messages between the Rx parties.
  kind=approval_required carries rx_version_at_creation — the version the
  request binds. If the Rx mutates afterwards the request is stale and a
  decision is rejected 409 (no silent carry-over of old conclusions).
- approval: decision record bound to notification + rx_version + signer.
  One decision per notification (UK).
- rx_comment.file_reference_id: optional link to an attachment reference so
  discussion can be anchored to a specific file (COM-001 gap closure).

Revision ID: 0010_m2_collaboration
Revises: 0009_m1_studio
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0010_m2_collaboration"
down_revision = "0009_m1_studio"
branch_labels = None
depends_on = None

UUID = pg.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "notification",
        sa.Column("id", UUID, primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", UUID, nullable=False, index=True),
        # recipient org inbox
        sa.Column("org_id", UUID, sa.ForeignKey("organization.id"),
                  nullable=False, index=True),
        sa.Column("rx_id", UUID, sa.ForeignKey("rx.id"), nullable=False,
                  index=True),
        sa.Column("created_by_org_id", UUID, sa.ForeignKey("organization.id"),
                  nullable=False),
        sa.Column("created_by_user_id", UUID,
                  sa.ForeignKey("user_account.id"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("body", sa.String(4000), nullable=True),
        # version the request binds at creation (approval_required only)
        sa.Column("rx_version_at_creation", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default="unread"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", UUID,
                  sa.ForeignKey("user_account.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.CheckConstraint(
            "kind IN ('info','ack_required','approval_required')",
            name="ck_notification_kind"),
        sa.CheckConstraint("status IN ('unread','read','resolved')",
                           name="ck_notification_status"),
    )

    op.create_table(
        "approval",
        sa.Column("id", UUID, primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", UUID, nullable=False, index=True),
        sa.Column("notification_id", UUID,
                  sa.ForeignKey("notification.id"), nullable=False,
                  unique=True),
        sa.Column("rx_id", UUID, sa.ForeignKey("rx.id"), nullable=False,
                  index=True),
        sa.Column("rx_version", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("signature_name", sa.String(200), nullable=False),
        sa.Column("comment", sa.String(2000), nullable=True),
        sa.Column("decided_by_user_id", UUID,
                  sa.ForeignKey("user_account.id"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.CheckConstraint("decision IN ('approved','rejected')",
                           name="ck_approval_decision"),
    )

    op.add_column("rx_comment", sa.Column(
        "file_reference_id", UUID,
        sa.ForeignKey("file_reference.id"), nullable=True))
    # LAB-019: who completed the order (attribution for the Complete act).
    op.add_column("rx", sa.Column(
        "completed_by_user_id", UUID,
        sa.ForeignKey("user_account.id"), nullable=True))

    for table in ("notification", "approval"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            FOR ALL
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """)


def downgrade() -> None:
    op.drop_column("rx", "completed_by_user_id")
    op.drop_column("rx_comment", "file_reference_id")
    op.drop_table("approval")
    op.drop_table("notification")
