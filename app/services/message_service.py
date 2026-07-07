from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.conversation import ConversationStatus
from app.models.message import Message, MessageStatus, MessageStatusEvent
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.recipient_repo import RecipientRepository
from app.schemas.message import DeliveryWebhookPayload, SendMessageRequest


class MessageService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.message_repo = MessageRepository(db)
        self.conversation_repo = ConversationRepository(db)
        self.recipient_repo = RecipientRepository(db)

    async def send_to_recipients(
        self, conversation_id: uuid.UUID, data: SendMessageRequest
    ) -> tuple[list[Message], list[dict]]:
        """
        Creates one Message row per recipient (fan-out), validating each
        recipient exists and is contactable. Returns (created_messages,
        rejected_recipients) — a partial batch failure (e.g. one bad
        recipient ID among 500) does not abort the whole request.

        Actual provider dispatch happens asynchronously via Celery, enqueued
        by the caller (API route) after commit, so a DB failure never leaves
        an orphaned task.
        """
        conversation = await self.conversation_repo.get_by_id(conversation_id)
        if not conversation:
            raise NotFoundError(f"Conversation '{conversation_id}' not found.")
        if conversation.status in (ConversationStatus.COMPLETED, ConversationStatus.FAILED):
            raise BadRequestError(
                f"Cannot add messages to a conversation in terminal status '{conversation.status}'."
            )

        result_messages: list[Message] = []
        new_messages: list[Message] = []
        rejected: list[dict] = []

        for recipient_id in data.recipient_ids:
            recipient = await self.recipient_repo.get_by_id(recipient_id)
            if not recipient:
                rejected.append({"recipient_id": str(recipient_id), "reason": "recipient_not_found"})
                continue
            if recipient.status.value != "active":
                rejected.append(
                    {"recipient_id": str(recipient_id), "reason": f"recipient_status_{recipient.status.value}"}
                )
                continue

            address = recipient.phone_number if data.channel.value in ("sms", "whatsapp") else recipient.email
            print(f'your channel address is {address}')
            if not address:
                rejected.append(
                    {"recipient_id": str(recipient_id), "reason": f"no_address_for_channel_{data.channel.value}"}
                )
                continue

            idempotency_key = (
                f"{data.idempotency_key}:{recipient_id}" if data.idempotency_key else f"auto:{uuid.uuid4()}"
            )
            existing = await self.message_repo.get_by_idempotency_key(idempotency_key)
            if existing:
                # Idempotent replay: return the original message, don't duplicate the send.
                result_messages.append(existing)
                continue

            message = Message(
                conversation_id=conversation_id,
                recipient_id=recipient_id,
                channel=data.channel,
                content=data.content,
                idempotency_key=idempotency_key,
                extra_metadata=data.extra_metadata,
            )
            new_messages.append(message)
            result_messages.append(message)

        if new_messages:
            await self.message_repo.bulk_create(new_messages)

        # Conversation transitions to PROCESSING as soon as messages are queued.
        if new_messages and conversation.status == ConversationStatus.OPEN:
            await self.conversation_repo.update_status(conversation, ConversationStatus.PROCESSING)

        await self.db.commit()
        for m in result_messages:
            await self.db.refresh(m)
        return result_messages, rejected

    async def get(self, message_id: uuid.UUID) -> Message:
        message = await self.message_repo.get_by_id(message_id)
        if not message:
            raise NotFoundError(f"Message '{message_id}' not found.")
        return message

    async def list_by_conversation(
        self, conversation_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[Message], int]:
        return await self.message_repo.list_by_conversation(conversation_id, limit=limit, offset=offset)

    async def apply_status_update(
        self, message: Message, new_status: MessageStatus, *, reason: str | None, raw_payload: dict | None
    ) -> Message:
        """Applies a validated status transition, records an audit event, and
        stamps sent_at/delivered_at. Must be called with the message row
        locked (see get_locked_for_update) to avoid lost updates under
        concurrent webhook deliveries."""
        now = datetime.now(timezone.utc)
        message.status = new_status
        if new_status == MessageStatus.SENT and message.sent_at is None:
            message.sent_at = now
        if new_status == MessageStatus.DELIVERED:
            message.delivered_at = now
        if new_status in (MessageStatus.FAILED, MessageStatus.UNDELIVERED):
            message.error_message = reason or message.error_message

        await self.message_repo.add_status_event(
            MessageStatusEvent(message_id=message.id, status=new_status, reason=reason, raw_payload=raw_payload)
        )
        await self.db.flush()
        return message

    async def handle_delivery_webhook(self, payload: DeliveryWebhookPayload) -> Message:
        message = await self.message_repo.get_by_provider_message_id(payload.provider_message_id)
        if not message:
            raise NotFoundError(
                f"No message found for provider_message_id '{payload.provider_message_id}'."
            )
        # Re-fetch with row lock to serialize concurrent webhook deliveries for the same message.
        locked = await self.message_repo.get_locked_for_update(message.id)
        if locked.status in MessageStatus.terminal_statuses() and payload.status in MessageStatus.terminal_statuses():
            # Already terminal; ignore duplicate/late webhook rather than flip-flopping state.
            return locked
        await self.apply_status_update(
            locked, payload.status, reason=payload.reason, raw_payload=payload.model_dump(mode="json")
        )
        await self.db.commit()
        return locked