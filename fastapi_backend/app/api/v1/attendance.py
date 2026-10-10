from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from datetime import date
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.employee import Employee
from app.models.user import User
from app.schemas.attendance import (
    AttendanceHistoryResponse,
    AttendanceEmployeeListResponse,
)
from app.schemas.attendance_manual import (
    ManualAttendanceRequest,
    ManualAttendanceResponse,
)
from app.schemas.attendance_mark import (
    AttendanceMarkRequest,
    AttendanceMarkResponse,
)
from app.services.attendance_service import (
    MAX_ATTENDANCE_PAGE_SIZE,
    GeofenceRejectedError,
    LocationNotFoundError,
    LocationValidationError,
    NoOpenAttendanceError,
    get_attendance_history,
    get_attendance_employee_list,
    mark_attendance,
    mark_manual_attendance,
)
from app.services.face_verification_service import (
    FaceVerificationRequired,
)

router = APIRouter()


@router.get(
    "/attendance/history",
    response_model=list[AttendanceHistoryResponse],
)
def attendance_history(
    from_date: date | None = Query(
        default=None,
        alias="from",
        description="Return attendance from this date onward.",
    ),
    to_date: date | None = Query(
        default=None,
        alias="to",
        description="Return attendance up to and including this date.",
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=MAX_ATTENDANCE_PAGE_SIZE,
    ),
    offset: int = Query(default=0, ge=0),
    employee_id: int | None = Query(
        default=None,
        description="Employee ID. Organization users may filter by employee.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Organization/admin user
    if current_user.is_organization:
        if employee_id is not None:
            employee = (
                db.query(Employee)
                .filter(
                    Employee.user_id == employee_id,
                    Employee.organisation_id == current_user.org_id,
                )
                .first()
            )

            if employee is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Employee not found",
                )

        records = get_attendance_history(
            db=db,
            org_id=current_user.org_id,
            employee_id=employee_id,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
        )

    # Employee/member user: only their own records. Their org_id is their
    # own account id, not the organisation's, so do not filter by it.
    else:
        records = get_attendance_history(
            db=db,
            employee_id=current_user.org_id,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
        )

    response = []

    for record in records:
        employee_name = None

        if record.employee is not None:
            employee_name = (
                f"{record.employee.first_name} "
                f"{record.employee.last_name}"
            ).strip()

        response.append(
            AttendanceHistoryResponse(
                id=record.id,
                employee_id=record.employee_id,
                employee_name=employee_name,
                check_in=record.check_in,
                check_out=record.check_out,
                status=record.status,
                location_status=record.location_status,
                source=record.source,
                face_status=record.face_status,
                hours_worked=record.hours_worked,
                check_in_latitude=record.check_in_latitude,
                check_in_longitude=record.check_in_longitude,
                check_in_accuracy=record.check_in_accuracy,
                check_in_distance=record.check_in_distance,
                check_out_latitude=record.check_out_latitude,
                check_out_longitude=record.check_out_longitude,
                check_out_accuracy=record.check_out_accuracy,
                check_out_distance=record.check_out_distance,
                check_out_location_status=record.check_out_location_status,
                check_in_location_id=record.check_in_location_id,
            )
        )

    return response


@router.post(
    "/attendance/mark",
    response_model=AttendanceMarkResponse,
)
def attendance_mark(
    request: AttendanceMarkRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Employee self check-in / check-out (Django: POST /api/mark-attendance/).
    Organisation admins use POST /attendance/manual instead.
    """
    if current_user.is_organization:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Attendance marking is only available for employees.",
        )

    # For an employee JWT: User.org_id == Employee.user_id
    employee = (
        db.query(Employee)
        .filter(Employee.user_id == current_user.org_id)
        .first()
    )

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee profile not found.",
        )

    try:
        attendance, action, office, distance = mark_attendance(
            db=db,
            employee=employee,
            mobile_number=current_user.mobile_number,
            action=request.action,
            latitude=request.latitude,
            longitude=request.longitude,
            accuracy=request.accuracy,
            face_token=request.face_token,
        )

    except FaceVerificationRequired as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail=str(exc),
        )

    except GeofenceRejectedError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": str(exc),
                "distance_meters": round(exc.distance_meters, 2),
                "allowed_radius_meters": exc.location.radius_meters,
                "office_location": exc.location.location_name,
            },
        )

    except NoOpenAttendanceError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    except (LocationValidationError, LocationNotFoundError, ValueError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return AttendanceMarkResponse(
        id=attendance.id,
        employee_id=attendance.employee_id,
        action=action,
        status=attendance.status,
        location_status=attendance.location_status,
        face_status=attendance.face_status,
        check_in=attendance.check_in,
        check_out=attendance.check_out,
        check_out_location_status=attendance.check_out_location_status,
        hours_worked=attendance.hours_worked,
        distance_meters=round(distance, 2) if distance is not None else None,
        allowed_radius_meters=office.radius_meters if office else None,
        location_id=office.location_id if office else None,
        location_name=office.location_name if office else None,
    )

@router.post(
    "/attendance/manual",
    response_model=ManualAttendanceResponse,
)
def attendance_manual(
    request: ManualAttendanceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manual attendance marking for organization/admin users.

    Mirrors Django's mark_attendance() manual behavior:
    - Admin only
    - Employee must belong to the logged-in organization
    - No GPS validation
    - No face verification
    - source = manual
    - location_status = manual
    - face_status = skipped
    """

    # ---------------------------------------------------------
    # ADMIN / ORGANIZATION CHECK
    # ---------------------------------------------------------

    if not current_user.is_organization:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manual attendance is only available for organization users.",
        )

    # ---------------------------------------------------------
    # FIND EMPLOYEE
    # ---------------------------------------------------------

    employee = (
        db.query(Employee)
        .filter(
            Employee.user_id == request.employee_id,
            Employee.organisation_id == current_user.org_id,
        )
        .first()
    )

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found in your organization",
        )

    # ---------------------------------------------------------
    # MARK ATTENDANCE
    # ---------------------------------------------------------

    try:
        attendance = mark_manual_attendance(
            db=db,
            employee=employee,
            action=request.action,
            marked_by=current_user,
        )

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    except LookupError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    # ---------------------------------------------------------
    # DETERMINE ACTION
    # ---------------------------------------------------------

    action = (
        "check_in"
        if request.action == "checkin"
        else "check_out"
    )

    return ManualAttendanceResponse(
        id=attendance.id,
        employee_id=attendance.employee_id,
        action=action,
        status=attendance.status,
        location_status=attendance.location_status,
        source=attendance.source,
        face_status=attendance.face_status,
        check_in=attendance.check_in,
        check_out=attendance.check_out,
        hours_worked=attendance.hours_worked,
        marked_by_id=attendance.marked_by_id,
    )

@router.get(
    "/attendance/list",
    response_model=list[AttendanceEmployeeListResponse],
)
def attendance_employee_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_attendance_employee_list(
        db=db,
        org_id=current_user.org_id,
    )
