from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Designation(Base):
    __tablename__ = "designations_designation"

    designation_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments_department.department_id"),
        nullable=False,
    )

    details: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    department = relationship(
        "Department",
        back_populates="designations",
    )