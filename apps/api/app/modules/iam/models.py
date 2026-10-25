"""TASK-0001 base: tenant/organization/location/user/membership/role/roster/
org_connection. RLS applies to all tenant-scoped tables (see migration 0001).

ADR-0006 V1 model: a tenant contains multiple practice/lab orgs; cross-tenant
access is denied at the RLS layer first, app layer second.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.base import Base, CreatedAtMixin, IdMixin


class Tenant(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "tenant"
    name: Mapped[str] = mapped_column(String(200))


class Organization(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "organization"
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id"), index=True
    )
    kind: Mapped[str] = mapped_column(
        Enum("practice", "lab", "hybrid", name="org_kind")
    )
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    status: Mapped[str] = mapped_column(
        Enum("active", "suspended", name="org_status"), default="active"
    )


class Location(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "location"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)


class UserAccount(Base, IdMixin, CreatedAtMixin):
    """Identity-domain table — intentionally NOT tenant-RLS-scoped.

    A user authenticates once, then acts inside a tenant through a membership.
    App layer only ever exposes users via tenant-scoped membership queries or
    the caller's own id.
    """

    __tablename__ = "user_account"
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(
        Enum("active", "disabled", name="user_status"), default="active"
    )
    # Fernet-encrypted TOTP seed (app/security.py). Never stored in clear.
    totp_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(default=False)


class Membership(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "membership"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_membership"),)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"), index=True
    )
    role: Mapped[str] = mapped_column(
        Enum(
            "practice_admin", "practice_doctor", "practice_staff",
            "lab_admin", "lab_technician",
            name="member_role",
        )
    )
    status: Mapped[str] = mapped_column(
        Enum("invited", "active", "disabled", name="member_status"), default="active"
    )
    user: Mapped[UserAccount] = relationship(lazy="joined")


class RosterMember(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "roster_member"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), index=True
    )
    kind: Mapped[str] = mapped_column(Enum("doctor", "staff", name="roster_kind"))
    display_name: Mapped[str] = mapped_column(String(200))
    credentials: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_default: Mapped[bool] = mapped_column(default=False)
    linked_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        Enum("active", "disabled", name="roster_status"), default="active"
    )


class OrgConnection(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "org_connection"
    __table_args__ = (
        UniqueConstraint("practice_org_id", "lab_org_id", name="uq_connection"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    practice_org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    lab_org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    # String + CHECK (migration 0002): pending/accepted/rejected/withdrawn/revoked
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # Which side opened the request — the counterparty must decide. (Our own
    # security design decision, NOT an EasyRx-derived rule — V-14 pending.)
    initiated_by_org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    granted_scopes: Mapped[list] = mapped_column(JSONB, default=list)
    version: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(), nullable=True
    )
