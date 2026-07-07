import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.message import MessageChannel, MessageStatus


class SendMessageRequest(BaseModel):
    """
        Sends a message to one or more recipients in a conversation.

        Accepts either a single `recipient_id` or multiple `recipient_ids` and
        processes them as a single recipient list.
    """
    recipient_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=1000)
    channel: MessageChannel
    content: str = Field(..., min_length=1, max_length=10_000)
    idempotency_key: str | None = Field(
        default=None,
        max_length=255,
        description=(
            "Client-supplied key to make retries safe. If omitted, one is generated "
            "server-side per recipient (retries of the whole request without a key may "
            "create duplicate messages)."
        ),
    )
    extra_metadata: dict = Field(default_factory=dict)

    @field_validator("recipient_ids")
    @classmethod
    def dedupe_recipients(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        deduped = list(dict.fromkeys(v))  # preserves order, removes dupes
        if not deduped:
            raise ValueError("recipient_ids must contain at least one recipient.")
        return deduped

    @field_validator("content")
    @classmethod
    def strip_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("content must not be blank.")
        return v


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    recipient_id: uuid.UUID
    channel: MessageChannel
    content: str
    status: MessageStatus
    provider_name: str | None
    provider_message_id: str | None
    error_code: str | None
    error_message: str | None
    attempt_count: int
    sent_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MessageStatusEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: MessageStatus
    reason: str | None
    created_at: datetime


class DeliveryWebhookPayload(BaseModel):
    """Inbound payload from a message provider reporting a status change."""
    provider_message_id: str = Field(..., min_length=1)
    status: MessageStatus
    reason: str | None = None
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def only_terminal_or_sent(self) -> "DeliveryWebhookPayload":
        allowed = {MessageStatus.SENT, MessageStatus.DELIVERED, MessageStatus.FAILED, MessageStatus.UNDELIVERED}
        if self.status not in allowed:
            raise ValueError(f"Webhook cannot report status '{self.status}'.")
        return self


class SendMessageResponse(BaseModel):
    conversation_id: uuid.UUID
    messages: list[MessageRead]
    accepted_count: int
    rejected_recipients: list[dict] = Field(default_factory=list)