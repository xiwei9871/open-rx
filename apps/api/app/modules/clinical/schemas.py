"""S1a patient/case payloads — mirror docs/api/openapi.yaml."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class PatientCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    dob: date | None = None
    external_ref: str | None = Field(default=None, max_length=128)
    notes: str | None = None
    # Explicit confirmation after a 409 possible_duplicate — never implicit.
    confirm_duplicate: bool = False


class PatientUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    dob: date | None = None
    external_ref: str | None = Field(default=None, max_length=128)
    notes: str | None = None


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    org_id: uuid.UUID
    patient_number: str
    first_name: str
    last_name: str
    dob: date | None
    external_ref: str | None
    notes: str | None
    version: int
    deleted_at: datetime | None
    created_at: datetime


class DuplicateCandidate(BaseModel):
    patient_id: uuid.UUID
    last_name: str
    dob: date | None


class CaseCreate(BaseModel):
    label: str | None = Field(default=None, max_length=200)


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    patient_id: uuid.UUID
    label: str | None
    stage: str
    opened_at: datetime
    closed_at: datetime | None
