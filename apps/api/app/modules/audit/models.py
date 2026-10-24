import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.base import Base, IdMixin


class AuditEvent(Base, IdMixin):
    """Append-only audit log. Written in the same transaction as the action it
    records. tenant_id nullable for pre-membership events (e.g. failed login of
    a user with no membership).

    Python-side defaults on id/ts: SQLAlchemy then supplies values and emits
    INSERT without RETURNING — important because RETURNING rows are checked
    against the tenant-scoped SELECT policy, which would reject NULL-tenant
    auth events. Server defaults remain as a DB-level backstop."""

    __tablename__ = "audit_event"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4, server_default=func.gen_random_uuid(),
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=True
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    action: Mapped[str] = mapped_column(String(80), index=True)
    object_type: Mapped[str] = mapped_column(String(80))
    object_id: Mapped[str] = mapped_column(String(80))
    before_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
        server_default=func.now(), index=True,
    )
