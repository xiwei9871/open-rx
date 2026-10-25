"""S1a-01/02: patient + treatment_case. Tenant-RLS scoped (migration 0003).

Patient rows belong to exactly one owning org (org_id). There is no lab-side
patient projection yet: sharing minimal patient fields to a lab requires an
authorized channel (Rx) that does not exist until S1b — see stage-s1a report.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.base import Base, CreatedAtMixin, IdMixin


class Patient(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "patient"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), index=True)
    patient_number: Mapped[str] = mapped_column(String(24))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    external_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)


class TreatmentCase(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "treatment_case"
    __table_args__ = (
        CheckConstraint("stage IN ('active','completed','cancelled')",
                        name="ck_case_stage"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patient.id"), index=True)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    stage: Mapped[str] = mapped_column(String(16), default="active",
                                       server_default="active")
    opened_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
