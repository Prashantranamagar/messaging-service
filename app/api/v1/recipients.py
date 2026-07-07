from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ClientIdentity, get_current_client
from app.models.recipient import RecipientStatus
from app.schemas.common import MessageResponse, Page
from app.schemas.recipient import BulkImportJobRead, RecipientCreate, RecipientRead, RecipientUpdate
from app.services.bulk_import_service import BulkImportService
from app.services.recipient_service import RecipientService
from app.workers.tasks_import import process_bulk_import

router = APIRouter(prefix="/recipients", tags=["recipients"])


@router.post("/import", response_model=BulkImportJobRead, status_code=status.HTTP_201_CREATED)
async def import_recipients_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: ClientIdentity = Depends(get_current_client),
):
    service = BulkImportService(db)
    file_bytes = await file.read()
    job = await service.create_job(
        filename=file.filename or "import.csv",
        file_size_bytes=len(file_bytes),
        created_by=_.client_id,
    )
    process_bulk_import.delay(str(job.id), file_bytes.hex())
    return BulkImportJobRead.model_validate(job)


@router.get("/import/{job_id}", response_model=BulkImportJobRead)
async def get_bulk_import_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: ClientIdentity = Depends(get_current_client),
):
    service = BulkImportService(db)
    job = await service.get_job(job_id)
    return BulkImportJobRead.model_validate(job)


@router.post("/", response_model=RecipientRead, status_code=status.HTTP_201_CREATED)
async def create_recipient(
    payload: RecipientCreate,
    db: AsyncSession = Depends(get_db),
    _: ClientIdentity = Depends(get_current_client),
):
    service = RecipientService(db)
    return await service.create(payload)


@router.get("/", response_model=Page[RecipientRead])
async def list_recipients(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: RecipientStatus | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: ClientIdentity = Depends(get_current_client),
):
    service = RecipientService(db)
    recipients, total = await service.list(limit=limit, offset=offset, status=status, search=search)
    return Page(
        items=[RecipientRead.model_validate(recipient) for recipient in recipients],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{recipient_id}", response_model=RecipientRead)
async def get_recipient(
    recipient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: ClientIdentity = Depends(get_current_client),
):
    service = RecipientService(db)
    return await service.get(recipient_id)


@router.patch("/{recipient_id}", response_model=RecipientRead)
async def update_recipient(
    recipient_id: uuid.UUID,
    payload: RecipientUpdate,
    db: AsyncSession = Depends(get_db),
    _: ClientIdentity = Depends(get_current_client),
):
    service = RecipientService(db)
    return await service.update(recipient_id, payload)


@router.delete("/{recipient_id}", response_model=MessageResponse)
async def delete_recipient(
    recipient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: ClientIdentity = Depends(get_current_client),
):
    service = RecipientService(db)
    await service.delete(recipient_id)
    return MessageResponse(message="Recipient deleted.")
