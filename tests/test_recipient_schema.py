import pytest
from pydantic import ValidationError

from app.schemas.recipient import RecipientCreate


def test_recipient_requires_contact_method():
    with pytest.raises(ValidationError):
        RecipientCreate(name="No Contact")


def test_recipient_valid_phone_normalizes_to_e164():
    r = RecipientCreate(name="Hero", phone_number="+977 9800000000")
    assert r.phone_number == "+9779800000000"


def test_recipient_invalid_phone_rejected():
    with pytest.raises(ValidationError):
        RecipientCreate(name="Bad", phone_number="not-a-number")


def test_recipient_email_only_is_valid():
    r = RecipientCreate(name="Email Only", email="hero@example.com")
    assert r.email == "hero@example.com"