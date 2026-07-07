from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError, UnprocessableFileError
from app.models.bulk_import import BulkImportJob, BulkImportStatus
from app.repositories.bulk_import_repo import BulkImportJobRepository
from app.repositories.recipient_repo import RecipientRepository
from app.utils.csv_parser import iter_csv_rows

MAX_ERROR_REPORT_ENTRIES = 500  # cap stored error detail to avoid unbounded JSONB growth


class BulkImportService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.job_repo = BulkImportJobRepository(db)
        self.recipient_repo = RecipientRepository(db)

    async def create_job(self, *, filename: str, file_size_bytes: int, created_by: str | None) -> BulkImportJob:
        max_bytes = settings.BULK_IMPORT_MAX_FILE_SIZE_MB * 1024 * 1024
        if file_size_bytes > max_bytes:
            raise UnprocessableFileError(
                f"File exceeds max size of {settings.BULK_IMPORT_MAX_FILE_SIZE_MB}MB.",
            )
        if not filename.lower().endswith(".csv"):
            raise UnprocessableFileError("Only .csv files are supported.")

        job = BulkImportJob(filename=filename, status=BulkImportStatus.PENDING, created_by=created_by)
        job = await self.job_repo.create(job)
        await self.db.commit()
        return job

    async def get_job(self, job_id: uuid.UUID) -> BulkImportJob:
        job = await self.job_repo.get_by_id(job_id)
        if not job:
            raise NotFoundError(f"Bulk import job '{job_id}' not found.")
        return job

    async def process_job(self, job_id: uuid.UUID, file_bytes: bytes) -> None:
        """
            Processes a CSV import in a Celery worker.
            Validates each row, imports valid records in batches, and records errors
            for invalid rows without stopping the entire import.
        """
        
        job = await self.job_repo.get_by_id(job_id)
        if not job:
            raise NotFoundError(f"Bulk import job '{job_id}' not found.")

        job.status = BulkImportStatus.PROCESSING
        job.started_at = datetime.now(timezone.utc)
        await self.job_repo.save(job)
        await self.db.commit()

        batch: list[dict] = []
        error_report: list[dict] = []
        total = success = failure = 0

        try:
            for result in iter_csv_rows(file_bytes, max_rows=settings.BULK_IMPORT_MAX_ROWS):
                total += 1
                if not result.ok:
                    failure += 1
                    if len(error_report) < MAX_ERROR_REPORT_ENTRIES:
                        error_report.append({"row": result.row_number, "error": result.error})
                    continue

                row = result.data
                batch.append(
                    {
                        "id": uuid.uuid4(),
                        "name": row.get("name"),
                        "phone_number": row.get("phone_number"),
                        "email": row.get("email"),
                        "external_id": row.get("external_id") or f"csv-noid-{uuid.uuid4().hex[:12]}",
                        "attributes": {},
                    }
                )
                success += 1

                if len(batch) >= settings.BULK_IMPORT_BATCH_SIZE:
                    await self.recipient_repo.bulk_upsert(batch)
                    await self.db.commit()
                    batch.clear()
                    job.processed_rows = total
                    await self.job_repo.save(job)
                    await self.db.commit()

            if batch:
                await self.recipient_repo.bulk_upsert(batch)
                await self.db.commit()

            job.status = BulkImportStatus.COMPLETED
            job.total_rows = total
            job.processed_rows = total
            job.success_count = success
            job.failure_count = failure
            job.error_report = error_report
            job.finished_at = datetime.now(timezone.utc)
            await self.job_repo.save(job)
            await self.db.commit()

        except Exception as exc:  # noqa: BLE001 - we want to persist ANY failure onto the job
            await self.db.rollback()
            job = await self.job_repo.get_by_id(job_id)
            job.status = BulkImportStatus.FAILED
            job.error_report = error_report + [{"row": None, "error": f"Job aborted: {exc}"}]
            job.finished_at = datetime.now(timezone.utc)
            await self.job_repo.save(job)
            await self.db.commit()
            raise