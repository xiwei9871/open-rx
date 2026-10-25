"""S1b-Core: catalog_item / rx / rx_item / rx_transition / rx_comment.

Tenant-RLS scoped (migration 0005). Ownership model (docs/api/openapi.yaml,
docs/research/v1.1-rx-rules.md):
- `practice_org_id` is the issuing org; the Rx is addressable to `lab_org_id`.
- Practice members see rows where practice_org_id = their org.
- Lab members see rows addressed to their org once status >= submitted;
  Saved/draft rows are never lab-visible (SRC03's draft tag visibility is
  an org-config flag we default OFF — EasyRS policy).
"""
import uuid
from datetime import date, datetime

from sqlalchemy import (BigInteger, CheckConstraint, Date, DateTime,
                        ForeignKey, Identity, Integer, String, Text)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.base import Base, CreatedAtMixin, IdMixin


class CatalogItem(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "catalog_item"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    owner_org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=True,
        index=True)
    kind: Mapped[str] = mapped_column(String(16))  # part | appliance
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    option_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    arch_scope: Mapped[str] = mapped_column(String(8), default="both",
                                            server_default="both")
    active: Mapped[bool] = mapped_column(default=True, server_default="true")


class Rx(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "rx"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    practice_org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), index=True)
    rx_number: Mapped[str] = mapped_column(String(24))
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patient.id"), index=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("treatment_case.id"), nullable=True)
    lab_org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=True,
        index=True)
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("location.id"), nullable=True)
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_member.id"), nullable=True)
    form_type: Mapped[str] = mapped_column(String(16), default="standard",
                                           server_default="standard")
    form_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft",
                                        server_default="draft")
    fulfillment_status: Mapped[str] = mapped_column(
        String(16), default="none", server_default="none")
    checked_in_via: Mapped[str | None] = mapped_column(String(16),
                                                       nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"), nullable=True)
    checked_in_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    checked_in_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"), nullable=True)
    # M3 fulfillment (logistics track — separate from clinical status)
    carrier: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(120),
                                                      nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    shipped_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    received_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    delivered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"), nullable=True)
    qc_status: Mapped[str] = mapped_column(String(16), default="none",
                                           server_default="none")
    signature_name: Mapped[str | None] = mapped_column(String(200),
                                                       nullable=True)
    # exact version the submit signature binds (persisted — Final Gate F1)
    signed_rx_version: Mapped[int | None] = mapped_column(Integer,
                                                        nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # Submit idempotency: (key, payload-hash) pair; replay -> first result,
    # same key + different payload -> 409 (contract x-idempotent).
    submit_idem_key: Mapped[str | None] = mapped_column(String(128),
                                                      nullable=True)
    submit_idem_hash: Mapped[str | None] = mapped_column(String(64),
                                                         nullable=True)


class RxItem(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "rx_item"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    rx_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rx.id", ondelete="CASCADE"),
        index=True)
    catalog_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("catalog_item.id"))
    arch: Mapped[str] = mapped_column(String(8))
    tooth_ops: Mapped[list] = mapped_column(JSONB, default=list,
                                            server_default="[]")
    options: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    qty: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class RxTransition(Base, IdMixin, CreatedAtMixin):
    """Append-only status history — auditable transition trail."""
    __tablename__ = "rx_transition"
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    rx_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rx.id", ondelete="CASCADE"),
        index=True)
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str] = mapped_column(String(16))
    via: Mapped[str] = mapped_column(String(16), default="button",
                                     server_default="button")
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"))
    actor_org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class RxBundle(Base, IdMixin, CreatedAtMixin):
    """A prepared delivery package (S1b.1): ZIP in object storage plus a
    content hash recorded at build time."""
    __tablename__ = "rx_bundle"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
                                                 index=True)
    rx_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rx.id"), index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"))
    rx_version: Mapped[int] = mapped_column(Integer)
    # sha256 over the deliverable content (fields + items + live refs);
    # reuse requires an exact match — status-only bumps never invalidate.
    content_fingerprint: Mapped[str] = mapped_column(
        String(64), default="", server_default="")
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    bytes: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default="ready",
                                        server_default="ready")


class IdempotencyRecord(Base, IdMixin, CreatedAtMixin):
    """First-result snapshot for keyed mutating POSTs (S1b1-04)."""
    __tablename__ = "idempotency_record"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
                                                 index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"))
    endpoint: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int] = mapped_column(Integer)
    response_json: Mapped[dict] = mapped_column(JSONB)


class RxTemplate(Base, IdMixin, CreatedAtMixin):
    """RX-010: practice-owned reusable Rx payload (items + defaults).

    Template sharing between orgs is DEFER (IAM-008/RX-011): rows are
    org-scoped only; apply re-validates catalog ids at write time."""
    __tablename__ = "rx_template"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), index=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"))
    name: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict] = mapped_column(JSONB)


class RxComment(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "rx_comment"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    rx_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rx.id", ondelete="CASCADE"),
        index=True)
    author_membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("membership.id"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rx_comment.id"), nullable=True)
    # COM-001: optional anchor to a specific attachment reference.
    file_reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file_reference.id"), nullable=True)
    body: Mapped[str] = mapped_column(String(4000))
    edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)


class Notification(Base, IdMixin, CreatedAtMixin):
    """COM-002/004/007: structured clinical/issue message to a recipient org
    inbox. approval_required binds rx_version_at_creation — a mutated Rx
    makes the request stale (decide -> 409 version_drift)."""
    __tablename__ = "notification"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), index=True)
    rx_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rx.id"), index=True)
    created_by_org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"))
    kind: Mapped[str] = mapped_column(String(24))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    rx_version_at_creation: Mapped[int | None] = mapped_column(
        Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="unread",
                                        server_default="unread")
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"), nullable=True)


class Approval(Base, IdMixin, CreatedAtMixin):
    """COM-004/E2E-09: one signed decision per approval notification,
    bound to the Rx version at request time (business record — no claim
    of jurisdiction-specific legal e-signature compliance)."""
    __tablename__ = "approval"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notification.id"), unique=True)
    rx_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rx.id"), index=True)
    rx_version: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(16))
    signature_name: Mapped[str] = mapped_column(String(200))
    comment: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    decided_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QcRecord(Base, IdMixin, CreatedAtMixin):
    """FLOW-016: append-only manual QC confirmations (production quality
    check before dispatch). result: pass|fail."""
    __tablename__ = "qc_record"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    rx_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rx.id"), index=True)
    result: Mapped[str] = mapped_column(String(8))
    note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    checked_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"))
    checked_by_org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"))


class FulfillmentEvent(Base, IdMixin, CreatedAtMixin):
    """Logistics trail — seq-ordered like rx_transition (FLOW-016)."""
    __tablename__ = "fulfillment_event"
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    rx_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rx.id"), index=True)
    event: Mapped[str] = mapped_column(String(24))
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"))
    actor_org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
