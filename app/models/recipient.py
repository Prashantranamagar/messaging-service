import enum
import uuid

from sqlalchemy import Enum, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class RecipientStatus(str, enum.Enum):
    ACTIVE = "active"
    UNSUBSCRIBED = "unsubscribed"
    BLOCKED = "blocked"


class Recipient(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "recipients"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_recipients_external_id"),
        Index("ix_recipients_phone_number", "phone_number"),
        Index("ix_recipients_email", "email"),
    )

    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)  # E.164 format
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    status: Mapped[RecipientStatus] = mapped_column(
        Enum(RecipientStatus, name="recipient_status", native_enum=False),
        default=RecipientStatus.ACTIVE,
        nullable=False,
    )
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    messages: Mapped[list["Message"]] = relationship(back_populates="recipient")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Recipient {self.id} {self.phone_number or self.email}>"