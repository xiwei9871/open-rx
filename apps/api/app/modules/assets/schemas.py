"""S1a asset payloads — mirror docs/api/openapi.yaml."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UploadDeclare(BaseModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(gt=0)
    kind: str = Field(pattern="^(stl|pdf|image|other)$")
    jaw: str = Field(default="na", pattern="^(upper|lower|na)$")
    filename_hint: str | None = None


class UploadSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: str
    upload_urls: list[str]
    expires_at: datetime
    resumed: bool = False


class UploadComplete(BaseModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    sha256: str
    kind: str
    jaw: str
    parent_asset_id: uuid.UUID | None
    scan_status: str
    bytes: int
    created_at: datetime


class ReferenceCreate(BaseModel):
    subject_type: str = Field(pattern="^(patient|case|rx|notification|order)$")
    subject_id: uuid.UUID
    role: str = Field(
        pattern="^(original|optimized|processed|print_ready|attachment)$")


class FileReferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    asset_id: uuid.UUID
    subject_type: str
    subject_id: uuid.UUID
    role: str
    revoked_at: datetime | None


class DownloadRequest(BaseModel):
    ttl_seconds: int = Field(default=900, ge=60, le=86400)


class SignedUrlOut(BaseModel):
    url: str
    expires_at: datetime
    grant_id: uuid.UUID
