from datetime import time

from sqlalchemy import ForeignKey, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Shift(Base):
    __tablename__ = "shifts_shift"

    shift_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    shift_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    shift_start_time: Mapped[time] = mapped_column(
        Time,
        nullable=False,
    )

    shift_end_time: Mapped[time] = mapped_column(
        Time,
        nullable=False,
    )

    department_id: Mapped[int] = mapped_column(
        ForeignKey(
            "departments_department.department_id"
        ),
        nullable=False,
    )

    department = relationship(
        "Department",
        back_populates="shifts",
    )