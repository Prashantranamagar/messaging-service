import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPkMixin, utcnow


class MessageChannel(str, enum.Enum):
    SMS = "sms"
    EMAIL = "email"
    WHATSAPP = "whatsapp"


class MessageStatus(str, enum.Enum):
    QUEUED = "queued"         
    SENDING = "sending"       
    SENT = "sent"              
    DELIVERED = "delivered"   
    FAILED = "failed"         
    UNDELIVERED = "undelivered"  

    @classmethod
    def terminal_statuses(cls) -> set["MessageStatus"]:
        return {cls.DELIVERED, cls.FAILED, cls.UNDELIVERED}


class Message(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        # Prevents duplicate sends if a client retries the same send request.
        UniqueConstraint("idempotency_key", name="uq_messages_idempotency_key"),
        Index("ix_messages_conversation_id", "conversation_id"),
        Index("ix_messages_recipient_id", "recipient_id"),
        Index("ix_messages_status", "status"),
        Index("ix_messages_provider_message_id", "provider_message_id"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipients.id", ondelete="RESTRICT"), nullable=False
    )
    channel: Mapped[MessageChannel] = mapped_column(
        Enum(MessageChannel, name="message_channel", native_enum=False), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus, name="message_status", native_enum=False),
        default=MessageStatus.QUEUED,
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)

    provider_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    extra_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")  # noqa: F821
    recipient: Mapped["Recipient"] = relationship(back_populates="messages")  # noqa: F821
    status_events: Mapped[list["MessageStatusEvent"]] = relationship(
        back_populates="message", cascade="all, delete-orphan", order_by="MessageStatusEvent.created_at"
    )

    def __repr__(self) -> str:
        return f"<Message {self.id} status={self.status}>"


class MessageStatusEvent(UUIDPkMixin, Base):
    """Immutable audit trail of every status transition a message goes through.

    Kept separate from `Message` (which only stores current state) so we can
    answer "what happened and when" for support/debugging and reconcile
    out-of-order provider webhook deliveries.
    """
    __tablename__ = "message_status_events"
    __table_args__ = (Index("ix_message_status_events_message_id", "message_id"),)

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus, name="message_status_event_status", native_enum=False), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    message: Mapped["Message"] = relationship(back_populates="status_events")