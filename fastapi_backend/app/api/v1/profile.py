
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.profile import (
    EmployeeOfficeLocation,
    EmployeeProfileResponse,
    OrganisationProfileResponse,
    OrganisationProfileUpdate,
)
from app.services.employee_service import media_url
from app.services.profile_service import get_employee_profile

router = APIRouter()


def require_own_organisation(
    org_id: int,
    current_user: User,
) -> None:
    if not current_user.is_organization:
        raise HTTPException(
            status_code=403,
            detail="Only organisation accounts can update organisation details",
        )

    if current_user.org_id != org_id:
        raise HTTPException(
            status_code=403,
            detail="You cannot access another organisation's profile",
        )


@router.get(
    "/organisations/{org_id}",
    response_model=OrganisationProfileResponse,
)
def get_organisation_profile(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_own_organisation(org_id, current_user)

    organisation = (
        db.query(User)
        .filter(User.org_id == org_id)
        .first()
    )

    if organisation is None:
        raise HTTPException(status_code=404, detail="Organisation not found")

    return organisation


@router.put(
    "/profile/{org_id}",
    response_model=OrganisationProfileResponse,
)
def update_organisation_profile(
    org_id: int,
    data: OrganisationProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_own_organisation(org_id, current_user)

    organisation = (
        db.query(User)
        .filter(User.org_id == org_id)
        .first()
    )

    if organisation is None:
        raise HTTPException(status_code=404, detail="Organisation not found")

    # Avoid updating another user's email address.
    existing_email = (
        db.query(User)
        .filter(
            User.email == str(data.email),
            User.org_id != org_id,
        )
        .first()
    )

    if existing_email:
        raise HTTPException(
            status_code=409,
            detail="This email address is already in use",
        )

    organisation.name = data.name
    organisation.email = str(data.email)
    organisation.details = data.details

    try:
        db.commit()
        db.refresh(organisation)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not update organisation profile",
        )

    return organisation


@router.get(
    "/employee-details",
    response_model=EmployeeProfileResponse,
)
def employee_details(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = get_employee_profile(
        db=db,
        user_id=current_user.org_id,
    )

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Employee profile not found",
        )

    return EmployeeProfileResponse(
        user_id=employee.user_id,
        first_name=employee.first_name,
        last_name=employee.last_name,
        mobile_number=current_user.mobile_number,
        department_id=employee.department_id,
        designation_id=employee.designation_id,
        shift_id=employee.shift_id,
        office_location_id=employee.office_location_id,
        photo=media_url(employee.photo),
        organisation_id=employee.organisation_id,
        is_member_registered=employee.is_member_registered,
        department_name=(
            employee.department.details if employee.department else None
        ),
        designation_name=(
            employee.designation.details if employee.designation else None
        ),
        shift_name=(
            employee.shift.shift_name if employee.shift else None
        ),
        location_name=(
            employee.office_location.location_name
            if employee.office_location
            else None
        ),
        email=current_user.email,
        shift_start_time=(
            employee.shift.shift_start_time if employee.shift else None
        ),
        shift_end_time=(
            employee.shift.shift_end_time if employee.shift else None
        ),
        office_location=(
            EmployeeOfficeLocation(
                location_id=employee.office_location.location_id,
                location_name=employee.office_location.location_name,
                latitude=float(employee.office_location.latitude),
                longitude=float(employee.office_location.longitude),
                radius_meters=employee.office_location.radius_meters,
            )
            if employee.office_location
            else None
        ),
    )
