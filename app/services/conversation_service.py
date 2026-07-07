from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import MessageStatus
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from app.schemas.conversation import ConversationCreate, ConversationStatusSummary


class ConversationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ConversationRepository(db)
        self.message_repo = MessageRepository(db)

    async def create(self, data: ConversationCreate, created_by: str | None) -> Conversation:
        conversation = Conversation(
            subject=data.subject,
            metadata_=data.metadata,
            notification_webhook_url=str(data.notification_webhook_url) if data.notification_webhook_url else None,
            created_by=created_by,
        )
        conversation = await self.repo.create(conversation)
        await self.db.commit()
        return conversation

    async def get(self, conversation_id: uuid.UUID) -> Conversation:
        conversation = await self.repo.get_by_id(conversation_id)
        if not conversation:
            raise NotFoundError(f"Conversation '{conversation_id}' not found.")
        return conversation

    async def list(
        self, *, limit: int, offset: int, status: ConversationStatus | None
    ) -> tuple[list[Conversation], int]:
        return await self.repo.list(limit=limit, offset=offset, status=status)

    async def get_status_summary(self, conversation_id: uuid.UUID) -> ConversationStatusSummary:
        conversation = await self.get(conversation_id)
        counts = await self.message_repo.status_counts_for_conversation(conversation_id)
        total = sum(counts.values())
        is_complete = conversation.status in (ConversationStatus.COMPLETED, ConversationStatus.FAILED)
        return ConversationStatusSummary(
            conversation_id=conversation.id,
            status=conversation.status,
            total_messages=total,
            queued=counts.get(MessageStatus.QUEUED, 0),
            sending=counts.get(MessageStatus.SENDING, 0),
            sent=counts.get(MessageStatus.SENT, 0),
            delivered=counts.get(MessageStatus.DELIVERED, 0),
            failed=counts.get(MessageStatus.FAILED, 0),
            undelivered=counts.get(MessageStatus.UNDELIVERED, 0),
            is_complete=is_complete,
        )