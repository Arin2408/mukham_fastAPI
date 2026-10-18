from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.employee import Employee
from app.models.task import Task


# Task dates are calendar dates in the organisation's local time.
LOCAL_TZ = ZoneInfo("Asia/Kolkata")
MAX_RANGE_DAYS = 400


def local_today() -> date:
    return datetime.now(LOCAL_TZ).date()


def serialize_task(task: Task, today: date | None = None) -> dict:
    today = today or local_today()
    employee = task.employee

    return {
        "task_id": task.task_id,
        "employee_id": task.employee_id,
        "employee_name": (
            f"{employee.first_name} {employee.last_name}".strip()
            if employee else "Unknown"
        ),
        "department_name": (
            employee.department.details
            if employee and employee.department else None
        ),
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "status": task.status,
        "assigned_date": task.assigned_date,
        "due_date": task.due_date,
        "completed_date": task.completed_date,
        "is_overdue": (
            task.status != "completed"
            and task.due_date is not None
            and task.due_date < today
        ),
        "completed_late": (
            task.status == "completed"
            and task.due_date is not None
            and task.completed_date is not None
            and task.completed_date > task.due_date
        ),
        "created_by_id": task.created_by_id,
        # "Assigned by": the admin (organisation) or the employee's manager.
        "assigned_by_name": task.created_by.name if task.created_by else None,
        "assigned_by_manager": bool(task.created_by and not task.created_by.is_organization),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _org_employee(db: Session, org_id: int, employee_id: int) -> Employee:
    employee = (
        db.query(Employee)
        .filter(
            Employee.user_id == employee_id,
            Employee.organisation_id == org_id,
        )
        .first()
    )
    if employee is None:
        raise HTTPException(status_code=400, detail="Invalid employee selected")
    return employee


def direct_reports(db: Session, manager_id: int) -> list[Employee]:
    """The employees whose manager is this employee (one level down)."""
    return (
        db.query(Employee)
        .options(joinedload(Employee.designation))
        .filter(Employee.manager_id == manager_id)
        .order_by(Employee.first_name, Employee.last_name)
        .all()
    )


def _team_employee(db: Session, manager_id: int, employee_id: int) -> Employee:
    employee = (
        db.query(Employee)
        .filter(
            Employee.user_id == employee_id,
            Employee.manager_id == manager_id,
        )
        .first()
    )
    if employee is None:
        raise HTTPException(
            status_code=400,
            detail="You can only assign tasks to people who report to you.",
        )
    return employee


def _assignable_employee(db: Session, org_id: int, employee_id: int, manager_id: int | None) -> Employee:
    """Admin: anyone in the organisation. Manager: their direct reports only."""
    if manager_id is not None:
        return _team_employee(db, manager_id, employee_id)
    return _org_employee(db, org_id, employee_id)


def _query(db: Session):
    return db.query(Task).options(
        joinedload(Task.employee).joinedload(Employee.department),
        joinedload(Task.created_by),
    )


def list_tasks(
    db: Session,
    org_id: int | None = None,
    employee_id: int | None = None,
    employee_ids: list[int] | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    status: str | None = None,
) -> list[Task]:
    """
    Tasks whose assigned -> completed span overlaps [from_date, to_date].
    Open tasks run until they are completed, so they overlap every range
    from their assigned date onwards.
    """
    if from_date and to_date:
        if to_date < from_date:
            raise HTTPException(status_code=400, detail="'to' must be on or after 'from'")
        if (to_date - from_date) > timedelta(days=MAX_RANGE_DAYS):
            raise HTTPException(
                status_code=400,
                detail=f"Date range cannot exceed {MAX_RANGE_DAYS} days",
            )

    query = _query(db)

    if org_id is not None:
        query = query.filter(Task.org_id == org_id)
    if employee_id is not None:
        query = query.filter(Task.employee_id == employee_id)
    if employee_ids is not None:
        query = query.filter(Task.employee_id.in_(employee_ids))
    if status is not None:
        query = query.filter(Task.status == status)
    if to_date is not None:
        query = query.filter(Task.assigned_date <= to_date)
    if from_date is not None:
        query = query.filter(
            or_(Task.completed_date.is_(None), Task.completed_date >= from_date)
        )

    return query.order_by(Task.assigned_date, Task.task_id).all()


def get_task(db: Session, task_id: int) -> Task | None:
    return _query(db).filter(Task.task_id == task_id).first()


def create_task(
    db: Session,
    org_id: int,
    created_by_id: int,
    data,
    manager_id: int | None = None,
) -> Task:
    _assignable_employee(db, org_id, data.employee_id, manager_id)

    task = Task(
        org_id=org_id,
        employee_id=data.employee_id,
        title=data.title,
        description=(data.description or "").strip() or None,
        priority=data.priority,
        status="pending",
        assigned_date=data.assigned_date,
        due_date=data.due_date,
        completed_date=None,
        created_by_id=created_by_id,
    )

    try:
        db.add(task)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return get_task(db, task.task_id)


def update_task(
    db: Session,
    task: Task,
    org_id: int,
    data,
    manager_id: int | None = None,
) -> Task:
    values = data.model_dump(exclude_unset=True)

    if values.get("employee_id") is not None:
        _assignable_employee(db, org_id, values["employee_id"], manager_id)
        task.employee_id = values["employee_id"]

    if values.get("title") is not None:
        task.title = values["title"]

    if "description" in values:
        task.description = (values["description"] or "").strip() or None

    if values.get("priority") is not None:
        task.priority = values["priority"]

    assigned = values.get("assigned_date") or task.assigned_date
    due = values["due_date"] if "due_date" in values else task.due_date

    if due is not None and due < assigned:
        raise HTTPException(status_code=400, detail="Due date cannot be before the assigned date")

    if task.completed_date is not None and task.completed_date < assigned:
        raise HTTPException(
            status_code=400,
            detail="Assigned date cannot be after the completed date",
        )

    task.assigned_date = assigned
    task.due_date = due

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return get_task(db, task.task_id)


def set_task_status(
    db: Session,
    task: Task,
    status: str,
    completed_date: date | None = None,
) -> Task:
    today = local_today()

    if status == "completed":
        completed = completed_date or today
        if completed < task.assigned_date:
            raise HTTPException(
                status_code=400,
                detail="Completed date cannot be before the assigned date",
            )
        if completed > today:
            raise HTTPException(
                status_code=400,
                detail="Completed date cannot be in the future",
            )
        task.completed_date = completed
    else:
        # Reopening a task clears its completion date.
        task.completed_date = None

    task.status = status

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return get_task(db, task.task_id)


def delete_task(db: Session, task: Task) -> None:
    try:
        db.delete(task)
        db.commit()
    except Exception:
        db.rollback()
        raise
