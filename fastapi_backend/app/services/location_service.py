from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.attendance import Attendance
from app.models.department import Department
from app.models.employee import Employee
from app.models.location import Location
from app.services.in_use import refuse_if_in_use


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
    lid = location.location_id
    refuse_if_in_use(
        location.location_name,
        {
            "departments": db.query(Department).filter(Department.location_id == lid).count(),
            "employees": db.query(Employee).filter(Employee.office_location_id == lid).count(),
        },
        "Move them to another office first.",
    )
    # Past check-ins point at the office; keep that history.
    if db.query(Attendance).filter(Attendance.check_in_location_id == lid).first():
        raise HTTPException(
            status_code=409,
            detail=f"{location.location_name} has attendance history, so it can't be deleted. Rename it or move its pin instead.",
        )
    db.delete(location)
    db.commit()