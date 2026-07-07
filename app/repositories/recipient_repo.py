from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert


from app.models.recipient import Recipient, RecipientStatus


class RecipientRepository:
    """
    Handles all database operations for Recipient, 
    keeping database logic separate from business logic.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, recipient: Recipient) -> Recipient:
        self.db.add(recipient)
        await self.db.flush()
        return recipient

    async def get_by_id(self, recipient_id: uuid.UUID, include_deleted: bool = False) -> Recipient | None:
        stmt = select(Recipient).where(Recipient.id == recipient_id)
        if not include_deleted:
            stmt = stmt.where(Recipient.deleted_at.is_(None))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_external_id(self, external_id: str) -> Recipient | None:
        print('hello2')
        stmt = select(Recipient).where(
            Recipient.external_id == external_id, Recipient.deleted_at.is_(None)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_phone_or_email(self, phone_number: str | None, email: str | None) -> Recipient | None:
        if not phone_number and not email:
            return None
        conditions = []
        if phone_number:
            conditions.append(Recipient.phone_number == phone_number)
        if email:
            conditions.append(Recipient.email == email)
        stmt = select(Recipient).where(or_(*conditions), Recipient.deleted_at.is_(None))
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        status: RecipientStatus | None = None,
        search: str | None = None,
    ) -> tuple[list[Recipient], int]:
        stmt = select(Recipient).where(Recipient.deleted_at.is_(None))
        count_stmt = select(func.count(Recipient.id)).where(Recipient.deleted_at.is_(None))

        if status:
            stmt = stmt.where(Recipient.status == status)
            count_stmt = count_stmt.where(Recipient.status == status)
        if search:
            like = f"%{search}%"
            search_cond = or_(
                Recipient.name.ilike(like),
                Recipient.email.ilike(like),
                Recipient.phone_number.ilike(like),
            )
            stmt = stmt.where(search_cond)
            count_stmt = count_stmt.where(search_cond)

        stmt = stmt.order_by(Recipient.created_at.desc()).limit(limit).offset(offset)

        total = (await self.db.execute(count_stmt)).scalar_one()
        items = (await self.db.execute(stmt)).scalars().all()
        return list(items), total

    async def soft_delete(self, recipient: Recipient) -> None:
        recipient.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def bulk_upsert(self, rows: list[dict]) -> tuple[int, int]:
        """
            Bulk creates or updates recipients using PostgreSQL's `ON CONFLICT` for
            efficient imports. Returns the number of created and updated records.
        """

        if not rows:
            return 0, 0

        stmt = pg_insert(Recipient).values(rows)
        update_cols = {
            "name": stmt.excluded.name,
            "phone_number": stmt.excluded.phone_number,
            "email": stmt.excluded.email,
            "attributes": stmt.excluded.attributes,
            "updated_at": func.now(),
        }
        upsert_stmt = stmt.on_conflict_do_update(
            constraint="uq_recipients_external_id",
            set_=update_cols,
        ).returning(Recipient.id, (Recipient.created_at == Recipient.updated_at).label("was_insert"))

        result = await self.db.execute(upsert_stmt)
        rows_result = result.all()
        created = sum(1 for r in rows_result if r.was_insert)
        updated = len(rows_result) - created
        return created, updated