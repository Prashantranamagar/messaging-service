import uuid
from datetime import datetime

import phonenumbers
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.recipient import RecipientStatus


def _validate_and_normalize_phone(value: str) -> str:
    try:
        parsed = phonenumbers.parse(value, None)  # requires E.164 (leading +) since region=None
    except phonenumbers.NumberParseException as exc:
        raise ValueError(f"Invalid phone number '{value}': {exc}") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError(f"Phone number '{value}' is not a valid number.")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


class RecipientBase(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    phone_number: str | None = Field(default=None, description="E.164 format, e.g. +9779800000000")
    email: EmailStr | None = None
    external_id: str | None = Field(default=None, max_length=128)
    attributes: dict = Field(default_factory=dict)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        return _validate_and_normalize_phone(v)

    @model_validator(mode="after")
    def require_contact_method(self) -> "RecipientBase":
        if not self.phone_number and not self.email:
            raise ValueError("At least one of phone_number or email must be provided.")
        return self


class RecipientCreate(RecipientBase):
    pass


class RecipientUpdate(BaseModel):
    """All fields optional for PATCH semantics."""
    name: str | None = Field(default=None, max_length=255)
    phone_number: str | None = None
    email: EmailStr | None = None
    external_id: str | None = Field(default=None, max_length=128)
    attributes: dict | None = None
    status: RecipientStatus | None = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v
        return _validate_and_normalize_phone(v)


class RecipientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str | None
    phone_number: str | None
    email: str | None
    external_id: str | None
    status: RecipientStatus
    attributes: dict
    created_at: datetime
    updated_at: datetime


class BulkImportJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    status: str
    total_rows: int
    processed_rows: int
    success_count: int
    failure_count: int
    error_report: list
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None