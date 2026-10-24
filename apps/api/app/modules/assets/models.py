"""S1a-03: content-addressed assets, upload sessions, file references and
access grants. Tenant-RLS scoped (migration 0003); S1a.1 renames
scan_status -> format_status (migration 0004): the check is structural
only — 'format_ok' means the bytes parse as a recognizable mesh, NOT that
any security or mesh-quality scan ran.

Immutability: storage_key is content-addressed per org —
assets/{tenant_id}/{org_id}/{sha256} for new uploads; rows minted before
S1a.1 keep flat assets/{sha256} keys and stay reachable verbatim. No API
mutates or deletes an asset row. Derived versions link via
parent_asset_id (reserved for the processing worker).
"""
import uuid
from datetime import datetime

from sqlalchemy import (BigInteger, CheckConstraint, DateTime, ForeignKey,
                        String)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.base import Base, CreatedAtMixin, IdMixin


class Asset(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "asset"
    __table_args__ = (
        CheckConstraint("kind IN ('stl','pdf','image','other')",
                        name="ck_asset_kind"),
        CheckConstraint("jaw IN ('upper','lower','na')", name="ck_asset_jaw"),
        CheckConstraint(
            "format_status IN ('unverified','format_ok','format_rejected')",
            name="ck_asset_format_status"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), index=True)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"))
    sha256: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    jaw: Mapped[str] = mapped_column(String(8), default="na", server_default="na")
    bytes: Mapped[int] = mapped_column(BigInteger)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    format_status: Mapped[str] = mapped_column(
        String(16), default="unverified", server_default="unverified")
    parent_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset.id"), nullable=True)


class UploadSession(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "upload_session"
    __table_args__ = (
        CheckConstraint("status IN ('open','completed','expired')",
                        name="ck_upload_session_status"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"))
    sha256: Mapped[str] = mapped_column(String(64))
    bytes: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(16))
    jaw: Mapped[str] = mapped_column(String(8), default="na", server_default="na")
    status: Mapped[str] = mapped_column(String(16), default="open",
                                        server_default="open")
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FileReference(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "file_reference"
    __table_args__ = (
        CheckConstraint(
            "subject_type IN ('patient','case','rx','notification','order')",
            name="ck_fileref_subject"),
        CheckConstraint(
            "role IN ('original','optimized','processed','print_ready','attachment')",
            name="ck_fileref_role"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset.id"), index=True)
    subject_type: Mapped[str] = mapped_column(String(16))
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    role: Mapped[str] = mapped_column(String(16))
    granted_by_org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"))
    granted_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)


class AccessGrant(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "access_grant"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset.id"), index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"))
    file_reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file_reference.id"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
