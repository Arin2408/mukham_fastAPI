
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LivenessSession(Base):
    __tablename__ = "liveness_sessions"

    session_id: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )

    mobile_number: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    face_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    login_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

class RevokedRefreshToken(Base):
    __tablename__ = "revoked_refresh_tokens"

    jti: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )

    mobile_number: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
        index=True,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
