from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

OrgKind = Literal["practice", "lab", "hybrid"]
MemberRole = Literal[
    "practice_admin", "practice_doctor", "practice_staff",
    "lab_admin", "lab_technician",
]


class OrgCreate(BaseModel):
    kind: OrgKind
    name: str = Field(min_length=1, max_length=200)
    timezone: str = "UTC"


class OrgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    kind: OrgKind
    name: str
    status: str
    timezone: str
    created_at: datetime


class LocationCreate(BaseModel):
    name: str = Field(min_length=1)
    address: str | None = None
    phone: str | None = None


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    org_id: UUID
    name: str
    address: str | None
    phone: str | None


class MemberInvite(BaseModel):
    email: EmailStr
    role: MemberRole
    display_name: str | None = Field(default=None, max_length=200)
    # Dev-stage bootstrap convenience: when the email has no account yet the
    # invite creates one with this initial password (min 10). Absent → random.
    initial_password: str | None = Field(default=None, min_length=10)


class MembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    org_id: UUID
    user_id: UUID
    role: MemberRole
    status: str
    email: str | None = None

    @classmethod
    def from_row(cls, m) -> "MembershipOut":
        return cls(id=m.id, org_id=m.org_id, user_id=m.user_id, role=m.role,
                   status=m.status, email=m.user.email if m.user else None)


class RosterMemberCreate(BaseModel):
    kind: Literal["doctor", "staff"]
    display_name: str = Field(min_length=1)
    credentials: str | None = None
    is_default: bool = False
    linked_user_id: UUID | None = None


class RosterMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    org_id: UUID
    kind: str
    display_name: str
    credentials: str | None
    is_default: bool
    linked_user_id: UUID | None
    status: str


class OrgConnectionRequest(BaseModel):
    practice_org_id: UUID
    lab_org_id: UUID
    granted_scopes: list[str] = []


class OrgConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    practice_org_id: UUID
    lab_org_id: UUID
    status: str
    initiated_by_org_id: UUID
    decided_by_user_id: UUID | None
    decided_at: datetime | None
    granted_scopes: list
    version: int


class ConnectionTransition(BaseModel):
    # accept/reject: counterparty only. withdraw: initiator only.
    # revoke: either side, accepted rows only (ADR-0006 "no new access").
    action: Literal["accept", "reject", "withdraw", "revoke"]
    expected_version: int = Field(ge=0)
    # accept may NARROW scopes; expansion beyond requested is rejected.
    granted_scopes: list[str] | None = None


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    actor_user_id: UUID | None
    org_id: UUID | None
    action: str
    object_type: str
    object_id: str
    ts: datetime


class Page(BaseModel):
    items: list
    next_cursor: str | None = None
