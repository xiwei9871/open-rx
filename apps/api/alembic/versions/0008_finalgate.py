"""Final Gate fixes:
- rx.signed_rx_version — the exact Rx version the submit signature binds
  (persisted, not implied).
- rx_bundle.content_fingerprint — reuse key replacing the lossy
  "rx_version >= version - 1" heuristic; covers content, not status.
- idempotency_record — scope the key per tenant/org/user/endpoint
  instead of a database-global unique key.

Revision ID: 0008_finalgate
Revises: 0007_s1b1_transition_seq
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_finalgate"
down_revision = "0007_s1b1_transition_seq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rx", sa.Column("signed_rx_version", sa.Integer(),
                                  nullable=True))
    op.add_column(
        "rx_bundle",
        # '' marks pre-fingerprint rows: they can never match a computed
        # fingerprint, so they simply rebuild once.
        sa.Column("content_fingerprint", sa.String(64), nullable=False,
                  server_default=""),
    )
    op.drop_constraint("uq_idem_key", "idempotency_record", type_="unique")
    op.create_unique_constraint(
        "uq_idem_scope", "idempotency_record",
        ["tenant_id", "org_id", "user_id", "endpoint", "key"])


def downgrade() -> None:
    op.drop_constraint("uq_idem_scope", "idempotency_record", type_="unique")
    op.create_unique_constraint("uq_idem_key", "idempotency_record", ["key"])
    op.drop_column("rx_bundle", "content_fingerprint")
    op.drop_column("rx", "signed_rx_version")
