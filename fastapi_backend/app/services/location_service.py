from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.location import Location


def get_locations(db: Session, org_id: int):
    return (
        db.query(Location)
        .filter(Location.org_id == org_id)
        .order_by(Location.location_id)
        .all()
    )


def get_location(
    db: Session,
    location_id: int,
    org_id: int,
):
    return (
        db.query(Location)
        .filter(
            Location.location_id == location_id,
            Location.org_id == org_id,
        )
        .first()
    )


def create_location(
    db: Session,
    org_id: int,
    location_name: str,
    latitude: Decimal,
    longitude: Decimal,
    radius_meters: int,
):
    location = Location(
        location_name=location_name,
        latitude=latitude,
        longitude=longitude,
        org_id=org_id,
        radius_meters=radius_meters,
    )

    db.add(location)
    db.commit()
    db.refresh(location)

    return location


def update_location(
    db: Session,
    location: Location,
    location_name: str | None = None,
    latitude: Decimal | None = None,
    longitude: Decimal | None = None,
    radius_meters: int | None = None,
):
    if location_name is not None:
        location.location_name = location_name

    if latitude is not None:
        location.latitude = latitude

    if longitude is not None:
        location.longitude = longitude

    if radius_meters is not None:
        location.radius_meters = radius_meters

    db.commit()
    db.refresh(location)

    return location


def delete_location(db: Session, location: Location):
    db.delete(location)
    db.commit()