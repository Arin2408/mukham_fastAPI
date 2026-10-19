from datetime import datetime, timezone

from sqlalchemy import DateTime, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StoredFile(Base):
    """A photo or face image kept in the database (MEDIA_STORAGE=database)."""

    __tablename__ = "stored_files"

    # "media/<path>" for employee photos, "faces/<path>" for face images.
    key: Mapped[str] = mapped_column(String(255), primary_key=True)

    content_type: Mapped[str] = mapped_column(String(100), nullable=False)

    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
