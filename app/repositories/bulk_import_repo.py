from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bulk_import import BulkImportJob


class BulkImportJobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, job: BulkImportJob) -> BulkImportJob:
        self.db.add(job)
        await self.db.flush()
        return job

    async def get_by_id(self, job_id: uuid.UUID) -> BulkImportJob | None:
        result = await self.db.execute(select(BulkImportJob).where(BulkImportJob.id == job_id))
        return result.scalar_one_or_none()

    async def save(self, job: BulkImportJob) -> BulkImportJob:
        await self.db.flush()
        return job