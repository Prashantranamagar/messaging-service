import csv
import io
from collections.abc import Iterator

import phonenumbers
from pydantic import BaseModel, EmailStr, ValidationError, field_validator

REQUIRED_COLUMNS = {"name", "phone_number", "email", "external_id"}


class CSVRecipientRow(BaseModel):
    name: str | None = None
    phone_number: str | None = None
    email: EmailStr | None = None
    external_id: str | None = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if not v:
            return None
        try:
            parsed = phonenumbers.parse(v, None)
        except phonenumbers.NumberParseException as exc:
            raise ValueError(f"invalid phone number: {exc}") from exc
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("phone number failed validity check")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

    def has_contact_method(self) -> bool:
        return bool(self.phone_number or self.email)


class RowValidationResult(BaseModel):
    row_number: int
    ok: bool
    data: dict | None = None
    error: str | None = None


def validate_headers(fieldnames: list[str] | None) -> None:
    if not fieldnames:
        raise ValueError("CSV file has no header row.")
    missing = REQUIRED_COLUMNS - {f.strip().lower() for f in fieldnames}
    # Only phone_number/email pair is truly "required" in the sense that at
    # least one must be present per row; we require the columns to exist
    # (may be blank per-row) so downstream code can rely on stable schema.
    if missing:
        raise ValueError(f"CSV is missing required columns: {sorted(missing)}")


def iter_csv_rows(file_bytes: bytes, max_rows: int) -> Iterator[RowValidationResult]:
    """Yields a validation result per row. Raises ValueError up-front if the
    header row is malformed (fail fast rather than processing garbage)."""
    text_stream = io.StringIO(file_bytes.decode("utf-8-sig", errors="replace"))
    reader = csv.DictReader(text_stream)
    validate_headers(reader.fieldnames)

    normalized_fields = {f: f.strip().lower() for f in reader.fieldnames}

    row_number = 0
    for raw_row in reader:
        row_number += 1
        if row_number > max_rows:
            yield RowValidationResult(
                row_number=row_number,
                ok=False,
                error=f"Row exceeds max allowed rows ({max_rows}); import truncated here.",
            )
            break

        normalized_row = {normalized_fields[k]: (v.strip() if v else v) for k, v in raw_row.items() if k in normalized_fields}

        try:
            parsed = CSVRecipientRow(**{k: v or None for k, v in normalized_row.items()})
        except ValidationError as exc:
            yield RowValidationResult(row_number=row_number, ok=False, error=str(exc.errors()))
            continue

        if not parsed.has_contact_method():
            yield RowValidationResult(
                row_number=row_number,
                ok=False,
                error="Row has neither phone_number nor email.",
            )
            continue

        yield RowValidationResult(row_number=row_number, ok=True, data=parsed.model_dump())