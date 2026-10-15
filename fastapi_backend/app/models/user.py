
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base


class User(Base):
    __tablename__ = "organisation_customuser"
    # One account per mailbox: "Admin@Firm.com" and "admin@firm.com" are the same.
    __table_args__ = (Index("uq_customuser_email_lower", text("lower(email)"), unique=True),)

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

    @validates("email")
    def _lowercase_email(self, _key: str, value: str) -> str:
        """Emails are saved lowercase, however they are typed, wherever they are set."""
        return value.strip().lower() if value else value

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
