from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Department(Base):
    __tablename__ = "departments_department"

    department_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    org_id: Mapped[int] = mapped_column(
        ForeignKey("organisation_customuser.org_id"),
        nullable=False,
    )

    details: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations_location.location_id"),
        nullable=False,
    )

    organisation = relationship(
        "User",
        foreign_keys=[org_id],
    )

    location = relationship(
        "Location",
        foreign_keys=[location_id],
    )

    designations = relationship(
        "Designation",
        back_populates="department",
    )

    shifts = relationship(
        "Shift",
        back_populates="department",
    )