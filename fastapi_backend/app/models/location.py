from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Location(Base):
    __tablename__ = "locations_location"

    location_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    location_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    latitude: Mapped[Decimal] = mapped_column(
        Numeric(9, 6),
        nullable=False,
    )

    longitude: Mapped[Decimal] = mapped_column(
        Numeric(9, 6),
        nullable=False,
    )

    org_id: Mapped[int] = mapped_column(
        ForeignKey("organisation_customuser.org_id"),
        nullable=False,
    )

    radius_meters: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
    )

    organisation = relationship(
        "User",
        foreign_keys=[org_id],
    )