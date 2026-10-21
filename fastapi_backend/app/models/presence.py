from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PresenceEvent(Base):
    """
    What the phone's background geofence reported during an open check-in:
    "exit" / "enter" the office area, and "on" / "off" when tracking
    started or could not run (location "Allow all the time" refused).
    """

    __tablename__ = "presence_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    attendance_id: Mapped[int] = mapped_column(
        ForeignKey("employees_attendance.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    event: Mapped[str] = mapped_column(String(10), nullable=False)

    # When it happened on the phone (it may be sent later, after a signal gap).
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
