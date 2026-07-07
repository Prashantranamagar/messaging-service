from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.recipient import Recipient, RecipientStatus
from app.repositories.recipient_repo import RecipientRepository
from app.schemas.recipient import RecipientCreate, RecipientUpdate


class RecipientService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = RecipientRepository(db)

    async def create(self, data: RecipientCreate) -> Recipient:
        print('hello')
        if data.external_id:
            existing = await self.repo.get_by_external_id(data.external_id)
            print(f'asdfasf {existing}')
            if existing:
                print(f"Recipient with external_id '{data.external_id}' already exists: {existing.id}")
                raise ConflictError(
                    f"Recipient with external_id '{data.external_id}' already exists.",
                    details={"recipient_id": str(existing.id)},
                )
        recipient = Recipient(
            name=data.name,
            phone_number=data.phone_number,
            email=data.email,
            external_id=data.external_id,
            attributes=data.attributes,
        )
        recipient = await self.repo.create(recipient)
        await self.db.commit()
        return recipient

    async def get(self, recipient_id: uuid.UUID) -> Recipient:
        recipient = await self.repo.get_by_id(recipient_id)
        if not recipient:
            raise NotFoundError(f"Recipient '{recipient_id}' not found.")
        return recipient

    async def list(
        self, *, limit: int, offset: int, status: RecipientStatus | None, search: str | None
    ) -> tuple[list[Recipient], int]:
        return await self.repo.list(limit=limit, offset=offset, status=status, search=search)

    async def update(self, recipient_id: uuid.UUID, data: RecipientUpdate) -> Recipient:
        recipient = await self.get(recipient_id)
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(recipient, field, value)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(recipient)
        return recipient

    async def delete(self, recipient_id: uuid.UUID) -> None:
        recipient = await self.get(recipient_id)
        await self.repo.soft_delete(recipient)
        await self.db.commit()