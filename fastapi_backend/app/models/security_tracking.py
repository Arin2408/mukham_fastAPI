
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


class RefreshTokenFamily(Base):
    """
    One signed-in device. Every refresh token issued for that device carries
    the family_id; signing out or a replayed refresh token revokes the
    whole family.
    """

    __tablename__ = "refresh_token_families"

    family_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )

    mobile_number: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
        index=True,
    )

    device_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # "sign_out" or "token_reuse"
    revoked_reason: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
