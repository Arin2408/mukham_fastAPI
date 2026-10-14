from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_organisation
from app.models.department import Department
from app.models.shift import Shift
from app.models.user import User
from app.schemas.shift import (
    BulkAssignShiftRequest,
    BulkAssignShiftResponse,
    ShiftCreateRequest,
    ShiftDeleteResponse,
    ShiftResponse,
    ShiftUpdateRequest,
)
from app.services.shift_service import (
    ShiftValidationError,
    bulk_assign_shift,
    create_shift,
    delete_shift,
    employee_counts,
    get_shifts,
    is_overnight,
    shift_duration_minutes,
    update_shift,
    validate_shift,
)

router = APIRouter()


def _org_shift(db: Session, shift_id: int, org_id: int) -> Shift:
    shift = (
        db.query(Shift)
        .join(
            Department,
            Shift.department_id == Department.department_id,
        )
        .filter(
            Shift.shift_id == shift_id,
            Department.org_id == org_id,
        )
        .first()
    )

    if shift is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shift not found or not accessible",
        )

    return shift


def _org_department(db: Session, department_id: int, org_id: int) -> Department:
    department = (
        db.query(Department)
        .filter(
            Department.department_id == department_id,
            Department.org_id == org_id,
        )
        .first()
    )

    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found or not accessible",
        )

    return department


def _to_response(shift: Shift, employee_count: int = 0) -> ShiftResponse:
    return ShiftResponse(
        shift_id=shift.shift_id,
        shift_name=shift.shift_name,
        shift_start_time=shift.shift_start_time,
        shift_end_time=shift.shift_end_time,
        department_id=shift.department_id,
        is_overnight=is_overnight(shift.shift_start_time, shift.shift_end_time),
        duration_minutes=shift_duration_minutes(
            shift.shift_start_time, shift.shift_end_time
        ),
        employee_count=employee_count,
    )


def _validate(db: Session, **kwargs) -> None:
    try:
        validate_shift(db=db, **kwargs)
    except ShiftValidationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)


@router.get(
    "/shifts",
    response_model=list[ShiftResponse],
)
def list_shifts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_organisation),
):
    shifts = get_shifts(
        db=db,
        org_id=current_user.org_id,
    )
    counts = employee_counts(db, [shift.shift_id for shift in shifts])

    return [
        _to_response(shift, counts.get(shift.shift_id, 0))
        for shift in shifts
    ]


@router.post(
    "/add-shift",
    response_model=ShiftResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_shift(
    data: ShiftCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_organisation),
):
    if not current_user.is_organization:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization access required",
        )

    department = _org_department(db, data.department, current_user.org_id)

    _validate(
        db,
        org_id=current_user.org_id,
        department_id=department.department_id,
        shift_name=data.shift_name,
        start=data.shift_start_time,
        end=data.shift_end_time,
    )

    shift = create_shift(
        db=db,
        department=department,
        shift_name=data.shift_name,
        shift_start_time=data.shift_start_time,
        shift_end_time=data.shift_end_time,
    )

    return _to_response(shift)


@router.put(
    "/shifts/update/{shift_id}",
    response_model=ShiftResponse,
)
def update_shift_route(
    shift_id: int,
    data: ShiftUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_organisation),
):
    if not current_user.is_organization:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization access required",
        )

    shift = _org_shift(db, shift_id, current_user.org_id)

    department = (
        _org_department(db, data.department, current_user.org_id)
        if data.department is not None
        else None
    )

    # Validate the shift as it will look after the update.
    _validate(
        db,
        org_id=current_user.org_id,
        department_id=(
            department.department_id if department else shift.department_id
        ),
        shift_name=(
            data.shift_name if data.shift_name is not None else shift.shift_name
        ),
        start=(
            data.shift_start_time
            if data.shift_start_time is not None
            else shift.shift_start_time
        ),
        end=(
            data.shift_end_time
            if data.shift_end_time is not None
            else shift.shift_end_time
        ),
        exclude_shift_id=shift.shift_id,
    )

    shift = update_shift(
        db=db,
        shift=shift,
        shift_name=data.shift_name,
        shift_start_time=data.shift_start_time,
        shift_end_time=data.shift_end_time,
        department=department,
    )

    counts = employee_counts(db, [shift.shift_id])
    return _to_response(shift, counts.get(shift.shift_id, 0))


@router.delete(
    "/shifts/delete/{shift_id}",
    response_model=ShiftDeleteResponse,
)
def delete_shift_route(
    shift_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_organisation),
):
    if not current_user.is_organization:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization access required",
        )

    shift = _org_shift(db, shift_id, current_user.org_id)
    unassigned = delete_shift(db=db, shift=shift)

    return {
        "message": "Shift deleted successfully",
        "unassigned_employees": unassigned,
    }


@router.post(
    "/bulk-assign",
    response_model=BulkAssignShiftResponse,
)
def bulk_assign_shift_route(
    data: BulkAssignShiftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_organisation),
):
    department = (
        db.query(Department)
        .filter(
            Department.department_id == data.department_id,
            Department.org_id == current_user.org_id,
        )
        .first()
    )

    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department or Shift not found",
        )

    shift = (
        db.query(Shift)
        .filter(
            Shift.shift_id == data.shift_id,
            Shift.department_id == department.department_id,
        )
        .first()
    )

    if shift is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department or Shift not found",
        )

    updated_count = bulk_assign_shift(
        db=db,
        department=department,
        shift=shift,
    )

    return {
        "message": (
            f"Successfully assigned shift to "
            f"{updated_count} employees"
        ),
        "updated_count": updated_count,
    }