import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.recipients import router as recipients_router
from app.core.database import get_db
from app.core.security import get_current_client


def override_get_db():
    async def _dependency():
        yield None

    return _dependency


def override_get_current_client():
    return SimpleNamespace(client_id="tester")


def test_import_recipients_csv_creates_job_and_enqueues_worker():
    app = FastAPI()
    app.include_router(recipients_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db()
    app.dependency_overrides[get_current_client] = override_get_current_client

    fake_job = SimpleNamespace(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        filename="test.csv",
        status="pending",
        total_rows=0,
        processed_rows=0,
        success_count=0,
        failure_count=0,
        error_report=[],
        created_by="tester",
        started_at=None,
        finished_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    class FakeBulkImportService:
        def __init__(self, db):
            self.db = db

        async def create_job(self, *, filename: str, file_size_bytes: int, created_by: str | None):
            return fake_job

        async def get_job(self, job_id: uuid.UUID):
            return fake_job

    with patch("app.api.v1.recipients.BulkImportService", FakeBulkImportService), patch(
        "app.api.v1.recipients.process_bulk_import"
    ) as mock_task:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/recipients/import",
                files={"file": (
                    "test.csv", b"name,phone_number,email\nAlice,+15551234567,alice@example.com\n", "text/csv")},
            )

    assert response.status_code == 201
    assert response.json()["filename"] == "test.csv"
    mock_task.delay.assert_called_once()
