"""S1b.1: monotonic seq on rx_transition — created_at ties made the
transition trail order nondeterministic.

Revision ID: 0007_s1b1_transition_seq
Revises: 0006_s1b1_bundle_idem
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_s1b1_transition_seq"
down_revision = "0006_s1b1_bundle_idem"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rx_transition",
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=False),
                  nullable=False),
    )
    op.create_index("ix_rx_transition_rx_seq", "rx_transition",
                    ["rx_id", "seq"])


def downgrade() -> None:
    op.drop_index("ix_rx_transition_rx_seq", table_name="rx_transition")
    op.drop_column("rx_transition", "seq")
