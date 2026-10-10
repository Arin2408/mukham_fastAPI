from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.geofence import (
    GeofenceCheckRequest,
    GeofenceCheckResponse,
)
from app.services.employee_location_service import (
    get_employee_with_location,
)
from app.services.geofence_service import check_geofence


router = APIRouter()


@router.post(
    "/geofence/check",
    response_model=GeofenceCheckResponse,
)
def check_employee_geofence(
    data: GeofenceCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = get_employee_with_location(
        db=db,
        employee_id=current_user.org_id,
    )

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee profile not found",
        )

    if employee.office_location is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No office location assigned to employee",
        )

    is_inside, distance = check_geofence(
        latitude=data.latitude,
        longitude=data.longitude,
        location=employee.office_location,
    )

    return GeofenceCheckResponse(
        inside=is_inside,
        distance_meters=round(distance, 2),
        allowed_radius_meters=employee.office_location.radius_meters,
        location_id=employee.office_location.location_id,
        location_name=employee.office_location.location_name,
    )