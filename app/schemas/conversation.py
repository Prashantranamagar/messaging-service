import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.conversation import ConversationStatus


class ConversationCreate(BaseModel):
    subject: str | None = Field(default=None, max_length=255)
    metadata: dict = Field(default_factory=dict)
    notification_webhook_url: HttpUrl | None = Field(
        default=None,
        description="Optional URL called when all messages in the conversation reach a terminal state.",
    )


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject: str | None
    status: ConversationStatus
    created_by: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ConversationStatusSummary(BaseModel):
    conversation_id: uuid.UUID
    status: ConversationStatus
    total_messages: int
    queued: int
    sending: int
    sent: int
    delivered: int
    failed: int
    undelivered: int
    is_complete: bool