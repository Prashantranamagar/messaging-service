from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message, MessageStatus, MessageStatusEvent


class MessageRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, message: Message) -> Message:
        self.db.add(message)
        await self.db.flush()
        return message

    async def bulk_create(self, messages: list[Message]) -> list[Message]:
        self.db.add_all(messages)
        await self.db.flush()
        return messages

    async def get_by_id(self, message_id: uuid.UUID) -> Message | None:
        result = await self.db.execute(select(Message).where(Message.id == message_id))
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, key: str) -> Message | None:
        result = await self.db.execute(select(Message).where(Message.idempotency_key == key))
        return result.scalar_one_or_none()

    async def get_by_provider_message_id(self, provider_message_id: str) -> Message | None:
        result = await self.db.execute(
            select(Message).where(Message.provider_message_id == provider_message_id)
        )
        return result.scalar_one_or_none()

    async def list_by_conversation(
        self, conversation_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[Message], int]:
        stmt = select(Message).where(Message.conversation_id == conversation_id)
        count_stmt = select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
        stmt = stmt.order_by(Message.created_at.asc()).limit(limit).offset(offset)

        total = (await self.db.execute(count_stmt)).scalar_one()
        items = (await self.db.execute(stmt)).scalars().all()
        return list(items), total

    async def get_locked_for_update(self, message_id: uuid.UUID) -> Message | None:
        """Row-level lock to serialize concurrent status updates to the same
        message (e.g. duplicate webhook deliveries arriving in parallel)."""
        stmt = select(Message).where(Message.id == message_id).with_for_update()
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def add_status_event(self, event: MessageStatusEvent) -> MessageStatusEvent:
        self.db.add(event)
        await self.db.flush()
        return event

    async def status_counts_for_conversation(self, conversation_id: uuid.UUID) -> dict[MessageStatus, int]:
        stmt = (
            select(Message.status, func.count(Message.id))
            .where(Message.conversation_id == conversation_id)
            .group_by(Message.status)
        )
        result = await self.db.execute(stmt)
        counts = {status: 0 for status in MessageStatus}
        for status, count in result.all():
            counts[status] = count
        return counts

    async def is_conversation_fully_terminal(self, conversation_id: uuid.UUID) -> bool:
        """True if the conversation has >=1 message and every message is in a
        terminal state (delivered/failed/undelivered)."""
        counts = await self.status_counts_for_conversation(conversation_id)
        total = sum(counts.values())
        if total == 0:
            return False
        terminal = sum(counts[s] for s in MessageStatus.terminal_statuses())
        return terminal == total