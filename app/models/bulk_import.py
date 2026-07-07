import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPkMixin


class BulkImportStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"       # finished, possibly with row-level errors
    FAILED = "failed"             # the job itself could not run (bad file, system error)


class BulkImportJob(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "bulk_import_jobs"

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[BulkImportStatus] = mapped_column(
        Enum(BulkImportStatus, name="bulk_import_status", native_enum=False),
        default=BulkImportStatus.PENDING,
        nullable=False,
    )
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Row-level errors, capped in size (see bulk_import_service for truncation policy)
    error_report: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<BulkImportJob {self.id} status={self.status}>"