from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResult(BaseModel):
    requires_2fa: bool = False
    challenge_id: UUID | None = None


class TwoFAVerifyRequest(BaseModel):
    challenge_id: UUID
    code: str


class TwoFASetupResult(BaseModel):
    secret: str
    otpauth_url: str


class TwoFAEnableRequest(BaseModel):
    secret: str
    code: str


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: UUID
    email: str
    display_name: str
    org_id: UUID
    org_name: str
    org_kind: str
    tenant_id: UUID
    role: str
    permissions: list[str]
    session_expires_at: datetime
