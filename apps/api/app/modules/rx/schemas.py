"""S1b-Core request/response shapes — mirror docs/api/openapi.yaml."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class RxCreate(BaseModel):
    patient_id: uuid.UUID
    case_id: uuid.UUID | None = None
    lab_org_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    doctor_id: uuid.UUID | None = None
    form_type: str = Field(default="standard",
                           pattern="^(standard|aligner|idb)$")
    due_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)


class RxUpdate(BaseModel):
    lab_org_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    doctor_id: uuid.UUID | None = None
    due_date: date | None = None
    form_payload: dict | None = None
    notes: str | None = Field(default=None, max_length=4000)


class RxSubmit(BaseModel):
    note: str | None = Field(default=None, max_length=500)
    # S1b1-03: server-enforced signature confirmation — the typed name is
    # the business record of who signed; the authenticated user id, org,
    # UTC time and Rx version are stamped server-side.
    signature_name: str = Field(min_length=1, max_length=200)
    # Required — the client must explicitly send true; there is no default
    # that could silently confirm on the user's behalf (Final Gate F1).
    confirm_submit: bool


class RxUnsubmit(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class RxCheckIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class ToothOp(BaseModel):
    tooth: str = Field(pattern="^[1-4][1-8]$")
    op: str = Field(pattern="^(extraction|ipr|reset)$")
    detail: str | None = Field(default=None, max_length=200)


class RxItemIn(BaseModel):
    appliance_id: uuid.UUID
    arch: str = Field(pattern="^(upper|lower|both)$")
    tooth_ops: list[ToothOp] = []
    options: dict | None = None
    qty: int = Field(default=1, ge=1)


class RxItemsReplace(BaseModel):
    items: list[RxItemIn]


class RxItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    appliance_id: uuid.UUID
    arch: str
    tooth_ops: list
    options: dict | None
    qty: int


class RxOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    rx_number: str
    case_id: uuid.UUID | None
    patient_id: uuid.UUID
    status: str
    fulfillment_status: str
    form_type: str
    form_payload: dict | None
    due_date: date | None
    notes: str | None
    practice_org_id: uuid.UUID
    lab_org_id: uuid.UUID | None
    location_id: uuid.UUID | None
    doctor_id: uuid.UUID | None
    checked_in_via: str | None
    signature_name: str | None
    signed_rx_version: int | None
    version: int
    submitted_at: datetime | None
    checked_in_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class RxTransitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    from_status: str | None
    to_status: str
    via: str
    note: str | None
    created_at: datetime


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    parent_id: uuid.UUID | None = None
    file_reference_id: uuid.UUID | None = None


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    rx_id: uuid.UUID
    author_membership_id: uuid.UUID
    parent_id: uuid.UUID | None
    file_reference_id: uuid.UUID | None
    body: str
    created_at: datetime
    edited_at: datetime | None


class NotificationCreate(BaseModel):
    rx_id: uuid.UUID
    kind: str = Field(pattern="^(info|ack_required|approval_required)$")
    subject: str = Field(min_length=1, max_length=300)
    body: str | None = Field(default=None, max_length=4000)


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    rx_id: uuid.UUID
    created_by_org_id: uuid.UUID
    kind: str
    subject: str
    body: str | None
    rx_version_at_creation: int | None
    status: str
    resolved_at: datetime | None
    created_at: datetime


class DecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    # business signature record — required, non-blank
    signature_name: str = Field(min_length=1, max_length=200)
    comment: str | None = Field(default=None, max_length=2000)


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    notification_id: uuid.UUID
    rx_id: uuid.UUID
    rx_version: int
    decision: str
    signature_name: str
    comment: str | None
    decided_by_user_id: uuid.UUID
    decided_at: datetime


class CatalogItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    name: str
    kind: str
    category: str | None
    arch_scope: str
    option_schema: dict | None


class RxTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # items + optional defaults; ids re-validated server-side.
    payload: dict


class RxTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    payload: dict
    created_at: datetime


class AttachmentCreate(BaseModel):
    asset_id: uuid.UUID
    role: str = Field(pattern="^(original|attachment)$")


class RxBundleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    rx_id: uuid.UUID
    rx_version: int
    sha256: str
    bytes: int
    status: str
    created_at: datetime
