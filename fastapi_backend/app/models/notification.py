from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PushDevice(Base):
    """A signed-in phone's Expo push token."""

    __tablename__ = "push_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("organisation_customuser.org_id", ondelete="CASCADE"),
        nullable=False,
    )
    token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    platform: Mapped[str] = mapped_column(String(10), nullable=False)
    # SHA-256 of the app install's secret (see register_device); None from older app builds.
    install_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationPreference(Base):
    """Which notifications a person wants. No row = all on."""

    __tablename__ = "notification_preferences"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("organisation_customuser.org_id", ondelete="CASCADE"),
        primary_key=True,
    )
    shift_start: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    check_out: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    new_task: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class NotificationSent(Base):
    """One row per reminder sent, so the same one is never sent twice."""

    __tablename__ = "notifications_sent"
    __table_args__ = (UniqueConstraint("user_id", "kind", "ref", name="uq_notifications_sent_once"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("organisation_customuser.org_id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    ref: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PushTicket(Base):
    """An Expo push ticket, kept until its receipt is checked."""

    __tablename__ = "push_tickets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    token: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
