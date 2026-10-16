
import logging
import secrets
import string

from fastapi import HTTPException
from passlib.context import CryptContext
from sqlalchemy.orm import Session, joinedload

from app.models.employee import Employee
from app.models.user import User
from app.models.department import Department
from app.models.designation import Designation
from app.models.shift import Shift
from app.models.location import Location
from app.services.storage import face_store, media_store


logger = logging.getLogger(__name__)


# Lowercase letters and digits without look-alikes (0/o, 1/l/i), since it
# is read out or typed in.
MEMBER_PASSWORD_ALPHABET = "".join(
    c for c in string.ascii_lowercase + string.digits if c not in "01ilo"
)


password_context = CryptContext(
    schemes=["django_pbkdf2_sha256"],
    deprecated="auto",
)


# --------------------------------------------------
# GET EMPLOYEES
# --------------------------------------------------

def get_employees(db: Session, org_id: int):
    return (
        db.query(Employee)
        .options(
            joinedload(Employee.user),
            joinedload(Employee.department),
            joinedload(Employee.designation),
            joinedload(Employee.shift),
            joinedload(Employee.office_location),
            joinedload(Employee.manager),
        )
        .filter(Employee.organisation_id == org_id)
        .order_by(Employee.user_id)
        .all()
    )


def get_employee(
    db: Session,
    employee_id: int,
    org_id: int,
):
    return (
        db.query(Employee)
        .options(
            joinedload(Employee.user),
            joinedload(Employee.department),
            joinedload(Employee.designation),
            joinedload(Employee.shift),
            joinedload(Employee.office_location),
            joinedload(Employee.manager),
        )
        .filter(
            Employee.user_id == employee_id,
            Employee.organisation_id == org_id,
        )
        .first()
    )


# --------------------------------------------------
# SERIALIZE EMPLOYEE
# --------------------------------------------------

def media_url(path: str | None) -> str | None:
    """Return the /media/... URL Django's ImageField used to return."""
    if not path:
        return None
    if path.startswith(("http://", "https://", "/")):
        return path
    return media_store.url(path)


def serialize_employee(employee: Employee) -> dict:
    user = employee.user

    return {
        "user_id": employee.user_id,
        "employee_id": employee.user_id,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "mobile_number": user.mobile_number if user else "",
        "email": user.email if user else "",
        "department": employee.department_id,
        "department_id": employee.department_id,
        "department_name": (
            employee.department.details
            if employee.department else "N/A"
        ),
        "designation": employee.designation_id,
        "designation_id": employee.designation_id,
        "designation_name": (
            employee.designation.details
            if employee.designation else "N/A"
        ),
        "shift": employee.shift_id,
        "shift_id": employee.shift_id,
        "shift_name": (
            employee.shift.shift_name
            if employee.shift else "N/A"
        ),
        "office_location": employee.office_location_id,
        "office_location_id": employee.office_location_id,
        "location_name": (
            employee.office_location.location_name
            if employee.office_location else "N/A"
        ),
        "photo": media_url(employee.photo),
        "organisation_id": employee.organisation_id,
        "is_member_registered": employee.is_member_registered,
        "manager_id": employee.manager_id,
        "manager_name": (
            f"{employee.manager.first_name} {employee.manager.last_name}".strip()
            if employee.manager else None
        ),
    }


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def normalize_mobile(value: str) -> str:
    return "".join(filter(str.isdigit, value))[-10:]


def validate_employee_relations(
    db: Session,
    org_id: int,
    department_id: int | None,
    designation_id: int | None,
    shift_id: int | None,
    location_id: int | None,
    same_department: bool = True,
) -> None:
    """
    Everything must be the organisation's own. With same_department, the
    designation and shift must also belong to the chosen department.
    """

    if department_id is not None:
        department = (
            db.query(Department)
            .filter(
                Department.department_id == department_id,
                Department.org_id == org_id,
            )
            .first()
        )

        if not department:
            raise HTTPException(
                status_code=400,
                detail="Invalid department selected",
            )

    if designation_id is not None:
        designation = (
            db.query(Designation)
            .join(Department)
            .filter(
                Designation.designation_id == designation_id,
                Department.org_id == org_id,
            )
            .first()
        )

        if not designation:
            raise HTTPException(
                status_code=400,
                detail="Invalid designation selected",
            )

        if same_department and designation.department_id != department_id:
            raise HTTPException(
                status_code=400,
                detail="This designation belongs to another department. Choose one from the employee's department.",
            )

    if shift_id is not None:
        shift = (
            db.query(Shift)
            .join(Department)
            .filter(
                Shift.shift_id == shift_id,
                Department.org_id == org_id,
            )
            .first()
        )

        if not shift:
            raise HTTPException(
                status_code=400,
                detail="Invalid shift selected",
            )

        if same_department and shift.department_id != department_id:
            raise HTTPException(
                status_code=400,
                detail="This shift belongs to another department. Choose one from the employee's department.",
            )

    if location_id is not None:
        location = (
            db.query(Location)
            .filter(
                Location.location_id == location_id,
                Location.org_id == org_id,
            )
            .first()
        )

        if not location:
            raise HTTPException(
                status_code=400,
                detail="Invalid office location selected",
            )


def validate_manager(
    db: Session,
    org_id: int,
    manager_id: int | None,
    employee_id: int | None = None,
) -> None:
    """
    The manager must be an employee of the same organisation, not the
    employee themselves, and not someone who (directly or indirectly)
    reports to the employee - that would create a loop in the tree.
    manager_id None = reports directly to the organisation admin.
    """
    if manager_id is None:
        return

    if employee_id is not None and manager_id == employee_id:
        raise HTTPException(
            status_code=400,
            detail="An employee cannot report to themselves",
        )

    manager = (
        db.query(Employee)
        .filter(
            Employee.user_id == manager_id,
            Employee.organisation_id == org_id,
        )
        .first()
    )

    if manager is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid manager selected",
        )

    if employee_id is None:
        return

    # Walk up from the proposed manager; reaching the employee means loop.
    managers = dict(
        db.query(Employee.user_id, Employee.manager_id)
        .filter(Employee.organisation_id == org_id)
        .all()
    )
    current = manager_id
    seen = set()
    while current is not None and current not in seen:
        if current == employee_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "This would create a reporting loop: the selected "
                    "manager already reports to this employee"
                ),
            )
        seen.add(current)
        current = managers.get(current)


# --------------------------------------------------
# CREATE EMPLOYEE
# --------------------------------------------------

def create_employee(
    db: Session,
    org_id: int,
    data,
) -> tuple[Employee, str]:

    mobile = normalize_mobile(data.mobile_number)

    if len(mobile) != 10:
        raise HTTPException(
            status_code=400,
            detail="Enter a valid 10-digit mobile number",
        )

    if db.query(User).filter(
        User.mobile_number == mobile
    ).first():
        raise HTTPException(
            status_code=409,
            detail="Mobile number already exists",
        )

    if db.query(User).filter(
        User.email_is(data.email)
    ).first():
        raise HTTPException(
            status_code=409,
            detail="Email already exists",
        )

    validate_employee_relations(
        db=db,
        org_id=org_id,
        department_id=data.department,
        designation_id=data.designation,
        shift_id=data.shift,
        location_id=data.office_location,
    )

    validate_manager(
        db=db,
        org_id=org_id,
        manager_id=data.manager,
    )

    # Random, so nobody can work it out from the employee's number and
    # name. Shown to the admin once, to pass on.
    plain_member_password = "".join(
        secrets.choice(MEMBER_PASSWORD_ALPHABET) for _ in range(10)
    )

    try:
        user = User(
            mobile_number=mobile,
            email=data.email,
            name=f"{data.first_name} {data.last_name}".strip(),
            password=password_context.hash(
                secrets.token_urlsafe(32)
            ),
            is_organization=False,
        )

        db.add(user)
        db.flush()

        employee = Employee(
            user_id=user.org_id,
            first_name=data.first_name,
            last_name=data.last_name,
            department_id=data.department,
            designation_id=data.designation,
            shift_id=data.shift,
            office_location_id=data.office_location,
            organisation_id=org_id,
            manager_id=data.manager,
            member_password=password_context.hash(
                plain_member_password
            ),
            is_member_registered=False,
        )

        db.add(employee)
        db.commit()
        db.refresh(employee)

        # Return the generated member password only at creation.
        return employee, plain_member_password

    except Exception:
        db.rollback()
        raise


# --------------------------------------------------
# UPDATE EMPLOYEE
# --------------------------------------------------

def update_employee(
    db: Session,
    employee: Employee,
    org_id: int,
    data,
) -> Employee:

    values = data.model_dump(exclude_unset=True)
    user = employee.user

    try:
        new_mobile = values.get("mobile_number")
        new_email = values.get("email")

        if new_mobile is not None:
            new_mobile = normalize_mobile(new_mobile)

            if len(new_mobile) != 10:
                raise HTTPException(
                    status_code=400,
                    detail="Enter a valid 10-digit mobile number",
                )

            duplicate = (
                db.query(User)
                .filter(
                    User.mobile_number == new_mobile,
                    User.org_id != user.org_id,
                )
                .first()
            )

            if duplicate:
                raise HTTPException(
                    status_code=409,
                    detail="Mobile number already exists",
                )

            user.mobile_number = new_mobile

        if new_email is not None:
            duplicate = (
                db.query(User)
                .filter(
                    User.email_is(new_email),
                    User.org_id != user.org_id,
                )
                .first()
            )

            if duplicate:
                raise HTTPException(
                    status_code=409,
                    detail="Email already exists",
                )

            user.email = new_email

        if (
            "first_name" in values
            and values["first_name"] is not None
        ):
            employee.first_name = values["first_name"]

        if (
            "last_name" in values
            and values["last_name"] is not None
        ):
            employee.last_name = values["last_name"]

        user.name = (
            f"{employee.first_name} {employee.last_name}"
        ).strip()

        department_id = values.get(
            "department", employee.department_id
        )
        designation_id = values.get(
            "designation", employee.designation_id
        )
        shift_id = values.get("shift", employee.shift_id)
        location_id = values.get(
            "office_location", employee.office_location_id
        )

        validate_employee_relations(
            db=db,
            org_id=org_id,
            department_id=department_id,
            designation_id=designation_id,
            shift_id=shift_id,
            location_id=location_id,
            # Only when one of them changes, so an employee saved before
            # this check can still have their name or number edited.
            same_department=bool({"department", "designation", "shift"} & values.keys()),
        )

        employee.department_id = department_id
        employee.designation_id = designation_id
        employee.shift_id = shift_id
        employee.office_location_id = location_id

        if "manager" in values:
            validate_manager(
                db=db,
                org_id=org_id,
                manager_id=values["manager"],
                employee_id=employee.user_id,
            )
            employee.manager_id = values["manager"]

        db.commit()
        db.refresh(employee)

        return employee

    except Exception:
        db.rollback()
        raise


# --------------------------------------------------
# DELETE EMPLOYEE
# --------------------------------------------------

def set_manager(
    db: Session,
    employee: Employee,
    org_id: int,
    manager_id: int | None,
) -> Employee:
    validate_manager(
        db=db,
        org_id=org_id,
        manager_id=manager_id,
        employee_id=employee.user_id,
    )

    try:
        employee.manager_id = manager_id
        db.commit()
        db.refresh(employee)
    except Exception:
        db.rollback()
        raise

    return employee


def get_hierarchy(
    db: Session,
    org_id: int,
) -> list[dict]:
    employees = (
        db.query(Employee)
        .options(
            joinedload(Employee.department),
            joinedload(Employee.designation),
        )
        .filter(Employee.organisation_id == org_id)
        .order_by(Employee.first_name, Employee.last_name)
        .all()
    )

    report_counts: dict[int, int] = {}
    for employee in employees:
        if employee.manager_id is not None:
            report_counts[employee.manager_id] = (
                report_counts.get(employee.manager_id, 0) + 1
            )

    return [
        {
            "employee_id": employee.user_id,
            "first_name": employee.first_name,
            "last_name": employee.last_name,
            "designation_name": (
                employee.designation.details if employee.designation else None
            ),
            "department_id": employee.department_id,
            "department_name": (
                employee.department.details if employee.department else None
            ),
            "photo": media_url(employee.photo),
            "manager_id": employee.manager_id,
            "direct_reports": report_counts.get(employee.user_id, 0),
        }
        for employee in employees
    ]


def delete_employee(
    db: Session,
    employee: Employee,
) -> None:
    """
    Delete an employee with their attendance and face data. The database
    foreign keys have no delete rule, so these rows are removed explicitly.
    Direct reports move up to the deleted employee's own manager so nobody
    is left without one. Tasks are removed by the database (ON DELETE CASCADE).
    """
    from app.models.attendance import Attendance
    from app.models.face import EmployeeFaceData

    try:
        user = employee.user

        (
            db.query(Employee)
            .filter(Employee.manager_id == employee.user_id)
            .update(
                {Employee.manager_id: employee.manager_id},
                synchronize_session=False,
            )
        )

        (
            db.query(Attendance)
            .filter(Attendance.employee_id == employee.user_id)
            .delete(synchronize_session=False)
        )

        # Files are removed only after the rows are gone (below).
        employee_id = employee.user_id
        photo_path = employee.photo
        face_key = None

        if user is not None:
            face_record = (
                db.query(EmployeeFaceData)
                .filter(EmployeeFaceData.mobile_number == user.mobile_number)
                .first()
            )
            if face_record is not None:
                face_key = face_record.face_image_key or None
                db.delete(face_record)

        db.delete(employee)
        db.flush()

        if user is not None:
            db.delete(user)

        db.commit()

    except Exception:
        db.rollback()
        raise

    # Biometric data must not outlive the employee record.
    try:
        if face_key:
            face_store.delete(face_key)
        if photo_path and not photo_path.startswith(("http://", "https://", "/")):
            media_store.delete(photo_path)
    except Exception:
        logger.exception(
            "Employee %s deleted but stored files were not removed",
            employee_id,
        )
