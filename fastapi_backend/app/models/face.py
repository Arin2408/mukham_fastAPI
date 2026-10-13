from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EmployeeFaceData(Base):
    __tablename__ = "face_auth_employeefacedata"

    mobile_number: Mapped[str] = mapped_column(
        String(15),
        ForeignKey(
            "organisation_customuser.mobile_number"
        ),
        primary_key=True,
    )

    # Key in face_store (app/services/storage.py).
    face_image_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
    )

    # Legacy rows only; new images go to face_store.
    face_image_base64: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    user = relationship(
        "User",
        foreign_keys=[mobile_number],
    )