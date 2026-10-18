from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


TaskStatus = Literal["pending", "in_progress", "completed"]
TaskPriority = Literal["low", "medium", "high"]


def _clean_title(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Task title cannot be empty")
    return cleaned


class TaskCreateRequest(BaseModel):
    employee_id: int
    title: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    priority: TaskPriority = "medium"
    assigned_date: date
    due_date: date | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        return _clean_title(value)

    @model_validator(mode="after")
    def check_dates(self):
        if self.due_date is not None and self.due_date < self.assigned_date:
            raise ValueError("Due date cannot be before the assigned date")
        return self


class TaskUpdateRequest(BaseModel):
    employee_id: int | None = None
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    priority: TaskPriority | None = None
    assigned_date: date | None = None
    # Send null to clear the due date.
    due_date: date | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        return _clean_title(value)


class TaskStatusRequest(BaseModel):
    status: TaskStatus
    # Only used when status = completed; defaults to today.
    completed_date: date | None = None


class TaskResponse(BaseModel):
    task_id: int
    employee_id: int
    employee_name: str
    department_name: str | None = None
    title: str
    description: str | None = None
    priority: str
    status: str
    assigned_date: date
    due_date: date | None = None
    completed_date: date | None = None
    # Open and past its due date
    is_overdue: bool = False
    # Completed after its due date
    completed_late: bool = False
    created_by_id: int | None = None
    assigned_by_name: str | None = None
    # True when the employee's manager assigned it, not the admin.
    assigned_by_manager: bool = False
    created_at: datetime
    updated_at: datetime


class TeamMemberResponse(BaseModel):
    """Someone who reports to the signed-in manager."""
    employee_id: int
    first_name: str
    last_name: str
    designation_name: str | None = None
