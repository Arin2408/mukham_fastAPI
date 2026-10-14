from collections import Counter
from datetime import datetime, time, timedelta

from sqlalchemy.orm import Session

from app.models.attendance import Attendance
from app.models.employee import Employee
from app.services.attendance_service import LOCAL_TZ
from app.services.department_service import get_department_leaderboard
from app.services.employee_service import get_employees
from app.services.location_service import get_locations
from app.services.shift_service import get_shifts
from app.services.task_service import local_today


WEEK_DAYS = 7


def _weekly_presence(db: Session, org_id: int, total_employees: int) -> list[dict]:
    """
    For each of the last 7 days (today included, India time): how many of
    the organisation's employees checked in at least once, and what share
    of today's headcount that is.
    """
    today = local_today()
    first_day = today - timedelta(days=WEEK_DAYS - 1)
    start = datetime.combine(first_day, time.min, tzinfo=LOCAL_TZ)

    rows = (
        db.query(Attendance.employee_id, Attendance.check_in)
        .join(Employee, Employee.user_id == Attendance.employee_id)
        .filter(
            Employee.organisation_id == org_id,
            Attendance.check_in >= start,
        )
        .all()
    )

    present_by_day: dict = {}
    for employee_id, check_in in rows:
        day = check_in.astimezone(LOCAL_TZ).date()
        present_by_day.setdefault(day, set()).add(employee_id)

    days = []
    for offset in range(WEEK_DAYS):
        day = first_day + timedelta(days=offset)
        present = len(present_by_day.get(day, ()))
        days.append(
            {
                "date": day,
                "present": present,
                "percent": (
                    round(present / total_employees * 100, 1)
                    if total_employees
                    else 0
                ),
            }
        )
    return days


def get_dashboard_summary(db: Session, org_id: int) -> dict:
    """Everything the admin dashboard shows, in one call."""
    employees = get_employees(db, org_id)
    leaderboard = get_department_leaderboard(db=db, org_id=org_id)

    # Same "attendance score" as the web dashboard always showed: the
    # average of the departments' punctuality scores.
    attendance_score = (
        round(
            sum(item["punctuality_score"] for item in leaderboard)
            / len(leaderboard)
        )
        if leaderboard
        else 0
    )

    roles = Counter(
        (employee.designation.details if employee.designation else None)
        or "Unassigned"
        for employee in employees
    )

    return {
        "total_employees": len(employees),
        "active_shifts": len(get_shifts(db, org_id)),
        "office_locations": len(get_locations(db, org_id)),
        "attendance_score": attendance_score,
        "roles": [
            {"name": name, "count": count}
            for name, count in roles.most_common()
        ],
        "weekly_attendance": _weekly_presence(db, org_id, len(employees)),
        "leaderboard": leaderboard,
    }
