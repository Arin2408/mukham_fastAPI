from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Employee(Base):
    __tablename__ = "employees_customuser"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("organisation_customuser.org_id"),
        primary_key=True,
    )

    first_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    last_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments_department.department_id"),
        nullable=True,
    )

    designation_id: Mapped[int | None] = mapped_column(
        ForeignKey("designations_designation.designation_id"),
        nullable=True,
    )

    shift_id: Mapped[int | None] = mapped_column(
        ForeignKey("shifts_shift.shift_id"),
        nullable=True,
    )

    office_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations_location.location_id"),
        nullable=True,
    )

    photo: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    organisation_id: Mapped[int] = mapped_column(
        ForeignKey("organisation_customuser.org_id"),
        nullable=False,
    )

    # Employee this employee reports to. NULL = reports directly to the
    # organisation admin (top of the reporting tree).
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees_customuser.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    member_password: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    is_member_registered: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="employee",
        uselist=False,
    )

    organisation = relationship(
        "User",
        foreign_keys=[organisation_id],
    )

    department = relationship(
        "Department",
        foreign_keys=[department_id],
    )

    designation = relationship(
        "Designation",
        foreign_keys=[designation_id],
    )

    shift = relationship(
        "Shift",
        foreign_keys=[shift_id],
    )

    office_location = relationship(
        "Location",
        foreign_keys=[office_location_id],
    )

    attendances = relationship(
        "Attendance",
        back_populates="employee",
        passive_deletes=True,
    )

    manager = relationship(
        "Employee",
        remote_side=[user_id],
        foreign_keys=[manager_id],
        back_populates="direct_reports",
    )

    direct_reports = relationship(
        "Employee",
        foreign_keys=[manager_id],
        back_populates="manager",
        passive_deletes=True,
    )