from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation, ConversationStatus


class ConversationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, conversation: Conversation) -> Conversation:
        self.db.add(conversation)
        await self.db.flush()
        return conversation

    async def get_by_id(self, conversation_id: uuid.UUID, *, with_messages: bool = False) -> Conversation | None:
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        if with_messages:
            stmt = stmt.options(selectinload(Conversation.messages))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self, *, limit: int, offset: int, status: ConversationStatus | None = None
    ) -> tuple[list[Conversation], int]:
        stmt = select(Conversation)
        count_stmt = select(func.count(Conversation.id))
        if status:
            stmt = stmt.where(Conversation.status == status)
            count_stmt = count_stmt.where(Conversation.status == status)
        stmt = stmt.order_by(Conversation.created_at.desc()).limit(limit).offset(offset)

        total = (await self.db.execute(count_stmt)).scalar_one()
        items = (await self.db.execute(stmt)).scalars().all()
        return list(items), total

    async def update_status(self, conversation: Conversation, status: ConversationStatus) -> Conversation:
        conversation.status = status
        await self.db.flush()
        return conversation