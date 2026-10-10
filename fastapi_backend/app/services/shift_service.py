from datetime import date, datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.employee import Employee
from app.models.shift import Shift


class ShiftValidationError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def is_overnight(start: time, end: time) -> bool:
    """A shift ending at or before its start time ends the next day."""
    return end < start


def shift_duration_minutes(start: time, end: time) -> int:
    today = date.today()
    start_dt = datetime.combine(today, start)
    end_dt = datetime.combine(today, end)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return int((end_dt - start_dt).total_seconds() // 60)


def normalize_shift_name(name: str) -> str:
    return " ".join(name.split())


def validate_shift(
    db: Session,
    org_id: int,
    department_id: int,
    shift_name: str,
    start: time,
    end: time,
    exclude_shift_id: int | None = None,
) -> None:
    """
    - start and end must differ (end before start = overnight shift)
    - within one department, no two shifts may share a name
      (case-insensitive) or the same start + end time
    """
    if start.replace(second=0, microsecond=0) == end.replace(second=0, microsecond=0):
        raise ShiftValidationError("Start time and end time cannot be the same.")

    others = (
        db.query(Shift)
        .join(Department, Shift.department_id == Department.department_id)
        .filter(
            Department.org_id == org_id,
            Shift.department_id == department_id,
        )
    )
    if exclude_shift_id is not None:
        others = others.filter(Shift.shift_id != exclude_shift_id)

    same_name = others.filter(
        func.lower(func.trim(Shift.shift_name)) == shift_name.lower()
    ).first()
    if same_name is not None:
        raise ShiftValidationError(
            f'A shift named "{same_name.shift_name}" already exists in this department.',
            status_code=409,
        )

    same_time = others.filter(
        Shift.shift_start_time == start,
        Shift.shift_end_time == end,
    ).first()
    if same_time is not None:
        raise ShiftValidationError(
            f'"{same_time.shift_name}" already uses '
            f'{start.strftime("%H:%M")}-{end.strftime("%H:%M")} in this department.',
            status_code=409,
        )


def get_shifts(
    db: Session,
    org_id: int,
) -> list[Shift]:
    return (
        db.query(Shift)
        .join(
            Department,
            Shift.department_id == Department.department_id,
        )
        .filter(
            Department.org_id == org_id,
        )
        .order_by(Shift.shift_start_time, Shift.shift_id)
        .all()
    )


def employee_counts(
    db: Session,
    shift_ids: list[int],
) -> dict[int, int]:
    if not shift_ids:
        return {}
    rows = (
        db.query(Employee.shift_id, func.count(Employee.user_id))
        .filter(Employee.shift_id.in_(shift_ids))
        .group_by(Employee.shift_id)
        .all()
    )
    return {shift_id: count for shift_id, count in rows}


def create_shift(
    db: Session,
    department: Department,
    shift_name: str,
    shift_start_time,
    shift_end_time,
) -> Shift:
    shift = Shift(
        shift_name=shift_name,
        shift_start_time=shift_start_time,
        shift_end_time=shift_end_time,
        department_id=department.department_id,
    )

    db.add(shift)
    db.commit()
    db.refresh(shift)

    return shift


def update_shift(
    db: Session,
    shift: Shift,
    shift_name: str | None = None,
    shift_start_time=None,
    shift_end_time=None,
    department: Department | None = None,
) -> Shift:

    if shift_name is not None:
        shift.shift_name = shift_name

    if shift_start_time is not None:
        shift.shift_start_time = shift_start_time

    if shift_end_time is not None:
        shift.shift_end_time = shift_end_time

    if department is not None:
        shift.department_id = department.department_id

    db.commit()
    db.refresh(shift)

    return shift


def delete_shift(
    db: Session,
    shift: Shift,
) -> int:
    """
    Delete a shift. Employees on it are left without a shift, as Django's
    on_delete=SET_NULL did (Django did this in Python, not in the database,
    so the foreign key would otherwise reject the delete).
    Returns how many employees were unassigned.
    """
    try:
        unassigned = (
            db.query(Employee)
            .filter(Employee.shift_id == shift.shift_id)
            .update({Employee.shift_id: None}, synchronize_session=False)
        )
        db.delete(shift)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return unassigned


def bulk_assign_shift(
    db: Session,
    department: Department,
    shift: Shift,
) -> int:
    updated_count = (
        db.query(Employee)
        .filter(
            Employee.department_id == department.department_id,
        )
        .update(
            {
                Employee.shift_id: shift.shift_id,
            },
            synchronize_session=False,
        )
    )

    db.commit()

    return updated_count
