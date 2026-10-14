import logging
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.dependencies.auth import get_current_user
from app.models.task import Task
from app.models.user import User
from app.schemas.task import (
    TaskCreateRequest,
    TaskResponse,
    TaskStatus,
    TaskStatusRequest,
    TaskUpdateRequest,
)
from app.services.notification_service import notify_new_task
from app.services.task_service import (
    create_task,
    delete_task,
    get_task,
    list_tasks,
    serialize_task,
    set_task_status,
    update_task,
)


router = APIRouter()


def _require_org(current_user: User) -> None:
    if not current_user.is_organization:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization access required",
        )


def _accessible_task(
    db: Session,
    task_id: int,
    current_user: User,
) -> Task:
    """Organisation: any task in it. Employee: only their own tasks."""
    task = get_task(db, task_id)

    if task is not None:
        if current_user.is_organization and task.org_id == current_user.org_id:
            return task
        # For an employee JWT, User.org_id == Employee.user_id
        if not current_user.is_organization and task.employee_id == current_user.org_id:
            return task

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Task not found",
    )


# --------------------------------------------------
# GET /api/v1/tasks?from=YYYY-MM-DD&to=YYYY-MM-DD&employee_id=&status=
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
    else:
        # Employees only ever see their own tasks.
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
    _require_org(current_user)

    task = create_task(
        db,
        org_id=current_user.org_id,
        created_by_id=current_user.org_id,
        data=data,
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
    _require_org(current_user)

    task = _accessible_task(db, task_id, current_user)
    return serialize_task(update_task(db, task, current_user.org_id, data))


# --------------------------------------------------
# PATCH /api/v1/tasks/{task_id}/status
# The organisation or the assigned employee can move a task between
# pending / in_progress / completed.
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
    _require_org(current_user)

    task = _accessible_task(db, task_id, current_user)
    delete_task(db, task)

    return {"message": "Task deleted successfully"}
