import logging
import uuid

from app.core.celery_app import celery_app
from app.core.database import db_session_ctx, run_worker_coroutine
from app.services.bulk_import_service import BulkImportService

logger = logging.getLogger("app.workers.import")


async def _process(job_id: str, file_bytes: bytes) -> None:
    async with db_session_ctx() as db:
        service = BulkImportService(db)
        await service.process_job(uuid.UUID(job_id), file_bytes)


@celery_app.task(
    name="app.workers.tasks_import.process_bulk_import",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def process_bulk_import(self, job_id: str, file_bytes_hex: str) -> None:
    """
    Runs the CSV import in the background so the API can respond 202
    immediately regardless of file size. `file_bytes_hex` is the file content
    hex-encoded for safe transport through the Celery/Redis broker (avoids
    binary-safety issues with some serializers); for very large files in
    production, prefer uploading to object storage (S3) and passing a
    reference key instead of the raw bytes.
    """
    try:
        file_bytes = bytes.fromhex(file_bytes_hex)
        logger.info("bulk_import_task_started", extra={"job_id": job_id})
        run_worker_coroutine(lambda: _process(job_id, file_bytes))
    except Exception as exc:
        logger.exception("bulk_import_task_failed", extra={"job_id": job_id})
        # Row-level errors are already handled inside process_job; retrying
        # here covers transient infra failures (DB connection blips etc).
        raise self.retry(exc=exc)