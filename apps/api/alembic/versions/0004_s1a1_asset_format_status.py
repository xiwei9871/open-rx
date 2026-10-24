"""S1a.1: honest naming for asset content checks + storage-key namespacing.

1) scan_status -> format_status. The value only ever meant "the bytes match a
   recognizable mesh/document structure". 'clean' implied a malware/quality
   scan that does not exist; the rename keeps reviewers honest. Values:
   unverified (default), format_ok, format_rejected. Legacy values remap:
   pending->unverified, clean->format_ok, infected/failed->format_rejected.

2) Storage keys are now minted as assets/{tenant_id}/{org_id}/{sha256}.
   No DDL for that — storage_key is a plain unique column — but existing rows
   keep their legacy flat key assets/{sha256}; readers resolve the stored
   key verbatim, so previously-uploaded objects stay reachable. The
   (org_id, sha256) dedup constraint is unchanged.

3) TOTP migration-history note (S1a1-04): databases that ran the ORIGINAL
   0002 revision lost their plaintext totp_secret values when that column
   was dropped. Those secrets are unrecoverable by any schema migration.
   This stage intentionally adds NO repair column or flag: affected
   accounts keep totp_enabled=true with totp_secret_enc NULL and hit the
   fail-closed recovery path (login -> totp_recovery_required -> TOTP
   re-enrollment). We do not silently clear totp_enabled — that would
   downgrade accounts to single-factor without notice.

Revision ID: 0004_s1a1_asset_format_status
Revises: 0003_s1a_patient_case_asset
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_s1a1_asset_format_status"
down_revision = "0003_s1a_patient_case_asset"
branch_labels = None
depends_on = None

_NEW = "('unverified','format_ok','format_rejected')"
_OLD = "('pending','clean','infected','failed')"


def upgrade() -> None:
    op.drop_constraint("ck_asset_scan_status", "asset", type_="check")
    op.execute("""
        UPDATE asset SET scan_status = CASE scan_status
            WHEN 'pending'  THEN 'unverified'
            WHEN 'clean'    THEN 'format_ok'
            ELSE 'format_rejected'  -- infected / failed
        END""")
    op.alter_column("asset", "scan_status", new_column_name="format_status",
                    server_default="unverified")
    op.create_check_constraint("ck_asset_format_status", "asset",
                               f"format_status IN {_NEW}")


def downgrade() -> None:
    op.drop_constraint("ck_asset_format_status", "asset", type_="check")
    op.execute("""
        UPDATE asset SET format_status = CASE format_status
            WHEN 'unverified' THEN 'pending'
            WHEN 'format_ok'  THEN 'clean'
            ELSE 'failed'  -- format_rejected
        END""")
    op.alter_column("asset", "format_status", new_column_name="scan_status",
                    server_default="pending")
    op.create_check_constraint("ck_asset_scan_status", "asset",
                               f"scan_status IN {_OLD}")
