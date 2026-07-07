import pytest

from app.core.exceptions import UnprocessableFileError
from app.providers.mock_provider import get_provider
from app.utils.csv_parser import iter_csv_rows


def test_valid_rows_parsed():
    csv_content = (
        "name,phone_number,email,external_id\n"
        "Alice,+9779800000001,alice@example.com,ext-1\n"
        "Bob,+9779800000002,,ext-2\n"
    ).encode()

    results = list(iter_csv_rows(csv_content, max_rows=1000))
    assert len(results) == 2
    assert all(r.ok for r in results)
    assert results[0].data["phone_number"] == "+9779800000001"


def test_row_without_contact_method_flagged_invalid():
    csv_content = "name,phone_number,email,external_id\nNoContact,,,ext-3\n".encode()
    results = list(iter_csv_rows(csv_content, max_rows=1000))
    assert len(results) == 1
    assert results[0].ok is False
    assert "neither phone_number nor email" in results[0].error


def test_invalid_phone_flagged_but_does_not_abort_import():
    csv_content = (
        "name,phone_number,email,external_id\n"
        "BadPhone,not-a-number,,ext-4\n"
        "GoodOne,+9779800000003,,ext-5\n"
    ).encode()
    results = list(iter_csv_rows(csv_content, max_rows=1000))
    assert len(results) == 2
    assert results[0].ok is False
    assert results[1].ok is True


def test_missing_required_columns_raises():
    csv_content = "foo,bar\n1,2\n".encode()
    try:
        list(iter_csv_rows(csv_content, max_rows=1000))
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "missing required columns" in str(exc).lower()
