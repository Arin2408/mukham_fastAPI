
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "organisation_customuser"

    org_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    password: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(254),
        nullable=False,
        unique=True,
    )

    details: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    mobile_number: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
        unique=True,
    )

    date_joined: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    is_organization: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    is_staff: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Employee profile linked through employees_customuser.user_id
    employee = relationship(
        "Employee",
        foreign_keys="Employee.user_id",
        back_populates="user",
        uselist=False,
    )

    def __repr__(self) -> str:
        return (
            f"<User "
            f"org_id={self.org_id} "
            f"mobile={self.mobile_number}>"
        )
