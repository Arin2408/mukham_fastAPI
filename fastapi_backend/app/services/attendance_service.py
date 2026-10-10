from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings

from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.location import Location
from app.models.user import User
from app.services.face_verification_service import (
    verify_attendance_face,
)
from app.services.employee_service import media_url
from app.services.geofence_service import calculate_distance_meters


# Shift times are stored in local (India) time, as in Django's TIME_ZONE.
LOCAL_TZ = ZoneInfo("Asia/Kolkata")


class AttendanceError(Exception):
    """Base attendance service error."""


class EmployeeNotFoundError(AttendanceError):
    pass


class LocationNotFoundError(AttendanceError):
    pass


class LocationValidationError(AttendanceError):
    pass


class OpenAttendanceError(AttendanceError):
    pass


class NoOpenAttendanceError(AttendanceError):
    pass


class GeofenceRejectedError(AttendanceError):
    def __init__(self, location: Location, distance_meters: float):
        super().__init__("You are outside the permitted attendance location.")
        self.location = location
        self.distance_meters = distance_meters



MAX_ATTENDANCE_PAGE_SIZE = 1000


def get_attendance_history(
    db: Session,
    org_id: int | None = None,
    employee_id: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[Attendance]:
    """
    Newest first. Organisation users pass org_id (optionally employee_id);
    employees pass only their own employee_id. from/to are local dates,
    inclusive - same as Django's attendance-history view.
    """
    query = (
        db.query(Attendance)
        .options(joinedload(Attendance.employee))
        .join(
            Employee,
            Attendance.employee_id == Employee.user_id,
        )
    )

    if org_id is not None:
        query = query.filter(Employee.organisation_id == org_id)

    if employee_id is not None:
        query = query.filter(Attendance.employee_id == employee_id)

    if from_date is not None:
        query = query.filter(
            Attendance.check_in
            >= datetime.combine(from_date, time.min, tzinfo=LOCAL_TZ)
        )

    if to_date is not None:
        query = query.filter(
            Attendance.check_in
            < datetime.combine(
                to_date + timedelta(days=1), time.min, tzinfo=LOCAL_TZ
            )
        )

    query = query.order_by(Attendance.check_in.desc())

    if offset:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    return query.all()


def get_employee_for_attendance(
    db: Session,
    user_id: int,
) -> Employee:
    employee = (
        db.query(Employee)
        .options(joinedload(Employee.office_location))
        .filter(Employee.user_id == user_id)
        .first()
    )

    if employee is None:
        raise EmployeeNotFoundError(
            "Employee profile not found."
        )

    return employee


def validate_coordinates(
    latitude: float,
    longitude: float,
    accuracy: float | None,
) -> None:
    if not -90 <= latitude <= 90:
        raise LocationValidationError(
            "Invalid latitude."
        )

    if not -180 <= longitude <= 180:
        raise LocationValidationError(
            "Invalid longitude."
        )

    if accuracy is not None and accuracy < 0:
        raise LocationValidationError(
            "Invalid GPS accuracy."
        )

def mark_manual_attendance(
    db: Session,
    employee: Employee,
    action: str,
    marked_by: User,
) -> Attendance:
    """
    Mark attendance manually by an organization/admin user.

    This mirrors the existing Django manual attendance behavior:

    - No GPS validation
    - No face verification
    - source = "manual"
    - location_status = "manual"
    - face_status = "skipped"
    - marked_by = organization user
    - repeated check-in returns the existing open attendance
    - checkout only closes an existing open attendance
    """

    if action not in {"checkin", "checkout"}:
        raise ValueError("Invalid attendance action.")

    active_attendance = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee.user_id,
            Attendance.check_out.is_(None),
        )
        .first()
    )

    # ---------------------------------------------------------
    # CHECK-IN
    # ---------------------------------------------------------
    if action == "checkin":

        # Django behavior:
        # A repeated check-in returns the already-open record.
        if active_attendance is not None:
            return active_attendance

        # Calculate attendance status using the employee shift.
        attendance_status = calculate_attendance_status(employee)

        attendance = Attendance(
            employee_id=employee.user_id,
            check_in=datetime.now(timezone.utc),
            check_out=None,
            status=attendance_status,
            location_status="manual",
            source="manual",
            marked_by_id=marked_by.org_id,
            check_in_latitude=None,
            check_in_longitude=None,
            check_in_accuracy=None,
            check_in_distance=None,
            check_in_location_id=None,
            face_status="skipped",
            hours_worked=None,
        )

        db.add(attendance)
        db.commit()
        db.refresh(attendance)

        return attendance

    # ---------------------------------------------------------
    # CHECK-OUT
    # ---------------------------------------------------------
    if active_attendance is None:
        raise LookupError(
            "No open check-in found. Please refresh and start the shift again."
        )

    check_out_time = datetime.now(timezone.utc)

    active_attendance.check_out = check_out_time

    # Manual checkout is never blocked by GPS.
    active_attendance.check_out_location_status = "manual"

    # Calculate worked hours.
    if active_attendance.check_in is not None:
        duration = (
            check_out_time - active_attendance.check_in
        ).total_seconds()

        active_attendance.hours_worked = round(
            duration / 3600,
            2,
        )

    db.commit()
    db.refresh(active_attendance)

    return active_attendance

def calculate_attendance_status(
    employee: Employee,
    now: datetime | None = None,
) -> str:
    """
    Early / On Time / Late against the shift start (local time).

    A check-in belongs to the shift occurrence it is closest to: the day
    is split at the midpoint of the off-hours between shifts. So for a
    20:00-04:00 night shift, 00:30 is "Late" (tonight's shift) and 19:30 is
    "Early"; for 09:00-18:00, 23:00 is still "Late", as in Django.
    """
    if employee.shift is None:
        return "On Time"

    local_now = (now or datetime.now(timezone.utc)).astimezone(LOCAL_TZ)

    shift_start = local_now.replace(
        hour=employee.shift.shift_start_time.hour,
        minute=employee.shift.shift_start_time.minute,
        second=0,
        microsecond=0,
    )

    start_t = employee.shift.shift_start_time
    end_t = employee.shift.shift_end_time
    duration = (
        datetime.combine(date.min, end_t) - datetime.combine(date.min, start_t)
    ) % timedelta(days=1)
    half_gap = (timedelta(days=1) - duration) / 2

    # Shift the difference into the window [-half_gap, 24h - half_gap).
    difference = (
        (local_now - shift_start + half_gap) % timedelta(days=1)
    ) - half_gap

    if difference < timedelta(minutes=-15):
        return "Early"

    if difference > timedelta(minutes=15):
        return "Late"

    return "On Time"


def find_office(
    db: Session,
    employee: Employee,
    latitude: float,
    longitude: float,
) -> tuple[Location | None, float | None]:
    """
    The employee's assigned office; if none is assigned, the organisation
    location the position is most inside of. Mirrors Django find_office().
    """
    if employee.office_location is not None:
        candidates = [employee.office_location]
    else:
        candidates = (
            db.query(Location)
            .filter(Location.org_id == employee.organisation_id)
            .all()
        )

    best_location, best_distance = None, None

    for location in candidates:
        distance = calculate_distance_meters(
            latitude,
            longitude,
            float(location.latitude),
            float(location.longitude),
        )

        if (
            best_location is None
            or distance - location.radius_meters
            < best_distance - best_location.radius_meters
        ):
            best_location, best_distance = location, distance

    return best_location, best_distance


def _usable_gps(
    latitude: float | None,
    longitude: float | None,
) -> bool:
    return (
        latitude is not None
        and longitude is not None
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
        and not (latitude == 0 and longitude == 0)
    )


def _record_check_out_location(
    db: Session,
    attendance: Attendance,
    employee: Employee,
    latitude: float | None,
    longitude: float | None,
    accuracy: float | None,
) -> None:
    """
    Store the check-out GPS and flag it inside / outside.
    Check-out is never blocked: missing or unusable GPS is 'unknown'.
    """
    if not _usable_gps(latitude, longitude):
        attendance.check_out_location_status = "unknown"
        return

    attendance.check_out_latitude = latitude
    attendance.check_out_longitude = longitude
    attendance.check_out_accuracy = accuracy

    office = (
        db.get(Location, attendance.check_in_location_id)
        if attendance.check_in_location_id
        else None
    )

    if office is not None:
        distance = calculate_distance_meters(
            latitude,
            longitude,
            float(office.latitude),
            float(office.longitude),
        )
    else:
        office, distance = find_office(db, employee, latitude, longitude)

    if office is None:
        attendance.check_out_location_status = "unknown"
        return

    attendance.check_out_distance = distance

    if accuracy is not None and accuracy > settings.geofence_max_accuracy_meters:
        attendance.check_out_location_status = "unknown"
    elif distance <= office.radius_meters:
        attendance.check_out_location_status = "inside"
    else:
        attendance.check_out_location_status = "outside"


def mark_attendance(
    db: Session,
    employee: Employee,
    mobile_number: str,
    action: str | None,
    latitude: float | None,
    longitude: float | None,
    accuracy: float | None,
    face_token: str | None,
) -> tuple[Attendance, str, Location | None, float | None]:
    """
    Employee self check-in / check-out. Mirrors Django mark_attendance():

    action="checkin"  -> never checks out; a repeated check-in returns the
                         open record
    action="checkout" -> only checks out (404 when nothing is open)
    no action         -> legacy toggle

    Check-in requires a server face match (face_token) and a GPS position
    inside the office radius. Check-out is never blocked, only flagged.

    Returns (attendance, "check_in" | "check_out", office, distance).
    """
    if action not in (None, "checkin", "checkout"):
        raise ValueError("Invalid attendance action.")

    open_attendance = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee.user_id,
            Attendance.check_out.is_(None),
        )
        .order_by(Attendance.check_in.desc())
        .with_for_update()
        .first()
    )

    # ---------------------------------------------------------
    # CHECK-OUT (or repeated check-in)
    # ---------------------------------------------------------
    if open_attendance is not None:
        if action == "checkin":
            db.commit()  # release the row lock
            return open_attendance, "check_in", None, None

        now = datetime.now(timezone.utc)
        check_in = open_attendance.check_in
        if check_in.tzinfo is None:
            check_in = check_in.replace(tzinfo=timezone.utc)

        open_attendance.check_out = now
        open_attendance.hours_worked = max(
            0.0,
            round((now - check_in).total_seconds() / 3600, 2),
        )
        _record_check_out_location(
            db, open_attendance, employee, latitude, longitude, accuracy
        )

        db.commit()
        db.refresh(open_attendance)

        return (
            open_attendance,
            "check_out",
            None,
            open_attendance.check_out_distance,
        )

    db.commit()  # nothing to lock; end the read transaction

    if action == "checkout":
        raise NoOpenAttendanceError(
            "No open check-in found. Please refresh and start the shift again."
        )

    # ---------------------------------------------------------
    # CHECK-IN
    # ---------------------------------------------------------
    verify_attendance_face(face_token=face_token, mobile_number=mobile_number)

    if not _usable_gps(latitude, longitude):
        raise LocationValidationError(
            "Current location is required. Please enable location and try again."
        )

    max_accuracy = settings.geofence_max_accuracy_meters
    if accuracy is not None and accuracy > max_accuracy:
        raise LocationValidationError(
            f"Your location is only accurate to about {int(accuracy)}m "
            f"(needs {max_accuracy}m or better). Turn on precise location, "
            "move near a window or outdoors, and try again."
        )

    office, distance = find_office(db, employee, latitude, longitude)

    if office is None:
        raise LocationNotFoundError(
            "Office location not configured. Admin must add an office "
            "location for your organisation."
        )

    if distance > office.radius_meters:
        raise GeofenceRejectedError(office, distance)

    attendance = Attendance(
        employee_id=employee.user_id,
        check_in=datetime.now(timezone.utc),
        check_out=None,
        status=calculate_attendance_status(employee),
        location_status="inside",
        source="self",
        marked_by_id=None,
        check_in_latitude=latitude,
        check_in_longitude=longitude,
        check_in_accuracy=accuracy,
        check_in_distance=distance,
        check_in_location_id=office.location_id,
        face_status="verified",
        hours_worked=None,
    )

    try:
        db.add(attendance)
        db.commit()
    except IntegrityError:
        # A parallel request already checked this employee in
        # (one open attendance per employee) - return that record.
        db.rollback()
        existing = (
            db.query(Attendance)
            .filter(
                Attendance.employee_id == employee.user_id,
                Attendance.check_out.is_(None),
            )
            .first()
        )
        if existing is None:
            raise
        return existing, "check_in", office, distance

    db.refresh(attendance)

    return attendance, "check_in", office, distance


def get_attendance_employee_list(
    db: Session,
    org_id: int,
) -> list[dict]:
    employees = (
        db.query(Employee)
        .options(
            joinedload(Employee.user),
            joinedload(Employee.department),
            joinedload(Employee.designation),
            joinedload(Employee.shift),
            joinedload(Employee.office_location),
        )
        .filter(Employee.organisation_id == org_id)
        .order_by(Employee.user_id)
        .all()
    )

    result = []

    for employee in employees:
        result.append(
            {
                "employee_id": employee.user_id,
                "first_name": employee.first_name,
                "last_name": employee.last_name,
                "mobile_number": (
                    employee.user.mobile_number
                    if employee.user
                    else ""
                ),
                "email": (
                    employee.user.email
                    if employee.user
                    else ""
                ),
                "department": employee.department_id,
                "designation": employee.designation_id,
                "shift": employee.shift_id,
                "office_location": employee.office_location_id,
                "designation_name": (
                    employee.designation.details
                    if employee.designation
                    else None
                ),
                "department_name": (
                    employee.department.details
                    if employee.department
                    else None
                ),
                "shift_name": (
                    employee.shift.shift_name
                    if employee.shift
                    else None
                ),
                "location_name": (
                    employee.office_location.location_name
                    if employee.office_location
                    else None
                ),
                "photo": media_url(employee.photo),
            }
        )

    return result
