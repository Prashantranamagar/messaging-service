import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPkMixin


class ConversationStatus(str, enum.Enum):
    OPEN = "open"         
    PROCESSING = "processing"  
    COMPLETED = "completed"    
    FAILED = "failed"          


class Conversation(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, name="conversation_status", native_enum=False),
        default=ConversationStatus.OPEN,
        nullable=False,
    )
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)  # client identifier
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Client-supplied webhook to notify when conversation completes (optional).
    notification_webhook_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    messages: Mapped[list["Message"]] = relationship(  # noqa: F821
        back_populates="conversation", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Conversation {self.id} status={self.status}>"