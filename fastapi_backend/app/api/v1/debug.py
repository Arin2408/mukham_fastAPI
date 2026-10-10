from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.department import Department
from app.models.designation import Designation
from app.models.location import Location
from app.models.shift import Shift
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.models.face import EmployeeFaceData
from fastapi import Depends
from app.dependencies.auth import get_current_user
from app.models.user import User


router = APIRouter()

@router.get("/debug/me")
def debug_me(
    current_user: User = Depends(get_current_user),
):
    return {
        "authenticated": True,
        "mobile_number": current_user.mobile_number,
        "name": current_user.name,
        "is_organization": current_user.is_organization,
        "is_staff": current_user.is_staff,
        "is_superuser": current_user.is_superuser,
        "is_active": current_user.is_active,
    }

@router.get("/debug/users")
def debug_users(db: Session = Depends(get_db)):
    users = (
        db.query(User)
        .order_by(User.org_id)
        .limit(10)
        .all()
    )

    return [
        {
            "org_id": user.org_id,
            "name": user.name,
            "mobile_number": user.mobile_number,
            "email": user.email,
            "is_organization": user.is_organization,
        }
        for user in users
    ]


@router.get("/debug/departments")
def debug_departments(db: Session = Depends(get_db)):
    departments = (
        db.query(Department)
        .limit(10)
        .all()
    )

    return [
        {
            "department_id": item.department_id,
            "details": item.details,
            "org_id": item.org_id,
            "location_id": item.location_id,
        }
        for item in departments
    ]


@router.get("/debug/designations")
def debug_designations(db: Session = Depends(get_db)):
    designations = (
        db.query(Designation)
        .limit(10)
        .all()
    )

    return [
        {
            "designation_id": item.designation_id,
            "details": item.details,
            "department_id": item.department_id,
        }
        for item in designations
    ]


@router.get("/debug/locations")
def debug_locations(db: Session = Depends(get_db)):
    locations = (
        db.query(Location)
        .limit(10)
        .all()
    )

    return [
        {
            "location_id": item.location_id,
            "location_name": item.location_name,
            "latitude": float(item.latitude),
            "longitude": float(item.longitude),
            "org_id": item.org_id,
            "radius_meters": item.radius_meters,
        }
        for item in locations
    ]


@router.get("/debug/shifts")
def debug_shifts(db: Session = Depends(get_db)):
    shifts = (
        db.query(Shift)
        .limit(10)
        .all()
    )

    return [
        {
            "shift_id": item.shift_id,
            "shift_name": item.shift_name,
            "shift_start_time": item.shift_start_time,
            "shift_end_time": item.shift_end_time,
            "department_id": item.department_id,
        }
        for item in shifts
    ]


@router.get("/debug/employees")
def debug_employees(db: Session = Depends(get_db)):
    employees = (
        db.query(Employee)
        .limit(10)
        .all()
    )

    return [
        {
            "user_id": item.user_id,
            "first_name": item.first_name,
            "last_name": item.last_name,
            "department_id": item.department_id,
            "designation_id": item.designation_id,
            "shift_id": item.shift_id,
            "office_location_id": item.office_location_id,
            "organisation_id": item.organisation_id,
        }
        for item in employees
    ]


@router.get("/debug/attendance")
def debug_attendance(db: Session = Depends(get_db)):
    records = (
        db.query(Attendance)
        .limit(10)
        .all()
    )

    return [
        {
            "id": item.id,
            "employee_id": item.employee_id,
            "check_in": item.check_in,
            "check_out": item.check_out,
            "status": item.status,
            "face_status": item.face_status,
        }
        for item in records
    ]


@router.get("/debug/face-data")
def debug_face_data(db: Session = Depends(get_db)):
    records = (
        db.query(EmployeeFaceData)
        .limit(10)
        .all()
    )

    return [
        {
            "mobile_number": item.mobile_number,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        for item in records
    ]