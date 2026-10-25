import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.base import Base, CreatedAtMixin, IdMixin


class AuthSession(Base, IdMixin, CreatedAtMixin):
    """Opaque-token session. Only the token hash is stored (theft of the table
    does not yield usable cookies)."""

    __tablename__ = "auth_session"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"), index=True
    )
    active_org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    # Denormalized at login: lets the request path set app.tenant_id BEFORE any
    # RLS-scoped query (membership/org lookups would otherwise see zero rows).
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)


class AuthChallenge(Base, IdMixin, CreatedAtMixin):
    """Short-lived second-factor challenge issued after password check."""

    __tablename__ = "auth_challenge"
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"), index=True
    )
    purpose: Mapped[str] = mapped_column(Enum("totp_login", name="challenge_purpose"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
