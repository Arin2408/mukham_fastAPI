from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.attendance import Attendance
from app.models.department import Department
from app.models.designation import Designation
from app.models.employee import Employee
from app.models.shift import Shift
from app.services.in_use import refuse_if_in_use


def get_departments(
    db: Session,
    org_id: int,
) -> list[Department]:
    return (
        db.query(Department)
        .filter(Department.org_id == org_id)
        .order_by(Department.department_id)
        .all()
    )


def create_department(
    db: Session,
    org_id: int,
    details: str,
    location_id: int,
) -> Department:
    department = Department(
        org_id=org_id,
        details=details,
        location_id=location_id,
    )

    db.add(department)
    db.commit()
    db.refresh(department)

    return department


def update_department(
    db: Session,
    department: Department,
    details: str | None = None,
    location_id: int | None = None,
) -> Department:
    if details is not None:
        department.details = details

    if location_id is not None:
        department.location_id = location_id

    db.commit()
    db.refresh(department)

    return department


def delete_department(
    db: Session,
    department: Department,
) -> None:
    refuse_if_in_use(
        department.details,
        {
            "employees": db.query(Employee).filter(Employee.department_id == department.department_id).count(),
            "designations": db.query(Designation).filter(Designation.department_id == department.department_id).count(),
            "shifts": db.query(Shift).filter(Shift.department_id == department.department_id).count(),
        },
        "Move or remove them first.",
    )
    db.delete(department)
    db.commit()


def get_department_leaderboard(
    db: Session,
    org_id: int,
) -> list[dict]:
    rows = (
        db.query(
            Department.department_id.label("department_id"),
            Department.details.label("department_name"),
            func.count(Attendance.id).label("total_attendances"),
            func.sum(
                case(
                    (
                        Attendance.status.in_(["Early", "On Time"]),
                        1,
                    ),
                    else_=0,
                )
            ).label("on_time_count"),
        )
        .outerjoin(
            Employee,
            Employee.department_id == Department.department_id,
        )
        .outerjoin(
            Attendance,
            Attendance.employee_id == Employee.user_id,
        )
        .filter(Department.org_id == org_id)
        .group_by(
            Department.department_id,
            Department.details,
        )
        .all()
    )

    leaderboard = []

    for row in rows:
        total_attendances = int(row.total_attendances or 0)
        on_time_count = int(row.on_time_count or 0)

        punctuality_score = (
            on_time_count / total_attendances * 100
            if total_attendances > 0
            else 0
        )

        leaderboard.append(
            {
                "department_id": row.department_id,
                "department_name": row.department_name,
                "punctuality_score": round(punctuality_score, 1),
                "total_attendances": total_attendances,
            }
        )

    leaderboard.sort(
        key=lambda item: item["punctuality_score"],
        reverse=True,
    )

    return leaderboard