from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Attendance(Base):
    __tablename__ = "employees_attendance"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees_customuser.user_id"),
        nullable=False,
    )

    check_in: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    check_out: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    location_status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="inside",
    )

    source: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="self",
    )

    marked_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("organisation_customuser.org_id"),
        nullable=True,
    )

    check_in_latitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    check_in_longitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    check_in_accuracy: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    check_in_distance: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    check_in_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations_location.location_id"),
        nullable=True,
    )

    check_out_latitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    check_out_longitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    check_out_accuracy: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    check_out_distance: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    check_out_location_status: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    face_status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="skipped",
    )

    hours_worked: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    employee = relationship(
        "Employee",
        back_populates="attendances",
    )

    marked_by = relationship(
        "User",
        foreign_keys=[marked_by_id],
    )

    check_in_location = relationship(
        "Location",
        foreign_keys=[check_in_location_id],
    )