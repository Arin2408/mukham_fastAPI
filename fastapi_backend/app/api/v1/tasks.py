import logging
from datetime import date
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.dependencies.auth import get_current_user
from app.models.employee import Employee
from app.models.task import Task
from app.models.user import User
from app.schemas.task import (
    TaskCreateRequest,
    TaskResponse,
    TaskStatus,
    TaskStatusRequest,
    TaskUpdateRequest,
    TeamMemberResponse,
)
from app.services.notification_service import notify_new_task
from app.services.task_service import (
    create_task,
    delete_task,
    direct_reports,
    get_task,
    list_tasks,
    serialize_task,
    set_task_status,
    update_task,
)


router = APIRouter()


def _team_ids(db: Session, current_user: User) -> list[int]:
    """A manager's direct reports (empty for everyone else)."""
    # For an employee JWT, User.org_id == Employee.user_id
    return [e.user_id for e in direct_reports(db, current_user.org_id)]


def _accessible_task(
    db: Session,
    task_id: int,
    current_user: User,
) -> Task:
    """
    Organisation: any task in it. Employee: their own tasks, and as a
    manager, their direct reports' tasks.
    """
    task = get_task(db, task_id)

    if task is not None:
        if current_user.is_organization:
            if task.org_id == current_user.org_id:
                return task
        elif task.employee_id == current_user.org_id or task.employee_id in _team_ids(db, current_user):
            return task

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Task not found",
    )


def _manageable_task(db: Session, task_id: int, current_user: User) -> Task:
    """
    Edit or delete: the organisation, any task in it; a manager, only the
    tasks they assigned to someone who still reports to them.
    """
    task = _accessible_task(db, task_id, current_user)
    if current_user.is_organization:
        return task
    if task.created_by_id == current_user.org_id and task.employee_id in _team_ids(db, current_user):
        return task
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only the admin or the manager who assigned this task can change it.",
    )


def _manager(db: Session, current_user: User) -> Employee:
    """The signed-in employee, who must have at least one direct report."""
    employee = db.query(Employee).filter(Employee.user_id == current_user.org_id).first()
    if employee is None or not _team_ids(db, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only managers can assign tasks.",
        )
    return employee


# --------------------------------------------------
# GET /api/v1/team - a manager's direct reports, to assign tasks to
# --------------------------------------------------

@router.get(
    "/team",
    response_model=list[TeamMemberResponse],
)
def get_team(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.is_organization:
        return []
    return [
        {
            "employee_id": e.user_id,
            "first_name": e.first_name,
            "last_name": e.last_name,
            "designation_name": e.designation.details if e.designation else None,
        }
        for e in direct_reports(db, current_user.org_id)
    ]


# --------------------------------------------------
# GET /api/v1/tasks?from=YYYY-MM-DD&to=YYYY-MM-DD&employee_id=&status=
# Employees: their own tasks, or with scope=team (managers) their direct
# reports' tasks.
# --------------------------------------------------

@router.get(
    "/tasks",
    response_model=list[TaskResponse],
)
def get_tasks(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    employee_id: int | None = Query(default=None),
    task_status: TaskStatus | None = Query(default=None, alias="status"),
    scope: Literal["mine", "team"] = Query(default="mine"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.is_organization:
        tasks = list_tasks(
            db,
            org_id=current_user.org_id,
            employee_id=employee_id,
            from_date=from_date,
            to_date=to_date,
            status=task_status,
        )
    elif scope == "team":
        team = _team_ids(db, current_user)
        if employee_id is not None:
            team = [i for i in team if i == employee_id]
        tasks = list_tasks(
            db,
            employee_ids=team,
            from_date=from_date,
            to_date=to_date,
            status=task_status,
        ) if team else []
    else:
        tasks = list_tasks(
            db,
            employee_id=current_user.org_id,
            from_date=from_date,
            to_date=to_date,
            status=task_status,
        )

    return [serialize_task(task) for task in tasks]


@router.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
)
def get_one_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return serialize_task(_accessible_task(db, task_id, current_user))


@router.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_task(
    data: TaskCreateRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.is_organization:
        task = create_task(
            db,
            org_id=current_user.org_id,
            created_by_id=current_user.org_id,
            data=data,
        )
    else:
        # A manager, for one of their direct reports.
        manager = _manager(db, current_user)
        task = create_task(
            db,
            org_id=manager.organisation_id,
            created_by_id=current_user.org_id,
            data=data,
            manager_id=current_user.org_id,
        )
    # "New task: …" to the employee's phones, after the response is sent.
    background.add_task(_notify_new_task, task.employee_id, task.task_id, task.title)
    return serialize_task(task)


def _notify_new_task(employee_id: int, task_id: int, title: str) -> None:
    db = SessionLocal()
    try:
        notify_new_task(db, employee_id, task_id, title)
    except Exception:  # A failed push must never affect the task itself.
        logging.getLogger(__name__).exception("New-task notification failed")
    finally:
        db.close()


@router.put(
    "/tasks/{task_id}",
    response_model=TaskResponse,
)
def edit_task(
    task_id: int,
    data: TaskUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _manageable_task(db, task_id, current_user)
    return serialize_task(
        update_task(
            db,
            task,
            task.org_id,
            data,
            manager_id=None if current_user.is_organization else current_user.org_id,
        )
    )


# --------------------------------------------------
# PATCH /api/v1/tasks/{task_id}/status
# The organisation, the assigned employee, or the manager who assigned it
# can move a task between pending / in_progress / completed.
# --------------------------------------------------

@router.patch(
    "/tasks/{task_id}/status",
    response_model=TaskResponse,
)
def change_task_status(
    task_id: int,
    data: TaskStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _accessible_task(db, task_id, current_user)
    if (
        not current_user.is_organization
        and task.employee_id != current_user.org_id
        and task.created_by_id != current_user.org_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assignee or whoever assigned this task can change its status.",
        )
    return serialize_task(
        set_task_status(db, task, data.status, data.completed_date)
    )


@router.delete(
    "/tasks/{task_id}",
)
def remove_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _manageable_task(db, task_id, current_user)
    delete_task(db, task)

    return {"message": "Task deleted successfully"}
