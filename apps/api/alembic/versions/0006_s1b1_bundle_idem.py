"""S1b.1: rx_bundle (prepared delivery packages) + idempotency_record
(persistent first-result snapshots for mutating POSTs).

Revision ID: 0006_s1b1_bundle_idem
Revises: 0005_s1b_rx_core
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0006_s1b1_bundle_idem"
down_revision = "0005_s1b_rx_core"
branch_labels = None
depends_on = None

UUID = pg.UUID(as_uuid=True)
TENANT_SCOPED = ["rx_bundle", "idempotency_record"]


def upgrade() -> None:
    op.create_table(
        "rx_bundle",
        sa.Column("id", UUID, primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", UUID, nullable=False, index=True),
        sa.Column("rx_id", UUID, sa.ForeignKey("rx.id"), nullable=False,
                  index=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organization.id"),
                  nullable=False),
        sa.Column("created_by_user_id", UUID,
                  sa.ForeignKey("user_account.id"), nullable=False),
        sa.Column("rx_version", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default="ready"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('ready','failed')",
                           name="ck_rxbundle_status"),
    )

    op.create_table(
        "idempotency_record",
        sa.Column("id", UUID, primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", UUID, nullable=False, index=True),
        sa.Column("org_id", UUID, nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("user_account.id"),
                  nullable=False),
        sa.Column("endpoint", sa.String(64), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_json", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("key", name="uq_idem_key"),
    )

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
