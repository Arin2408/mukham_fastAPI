from datetime import time

from pydantic import BaseModel, Field, field_serializer, field_validator


def _clean_name(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Shift name cannot be empty")
    return cleaned


class ShiftResponse(BaseModel):
    shift_id: int
    shift_name: str
    shift_start_time: time
    shift_end_time: time
    department_id: int

    # End time before start time = the shift ends the next day.
    is_overnight: bool = False
    duration_minutes: int = 0
    employee_count: int = 0

    @field_serializer("shift_start_time", "shift_end_time")
    def serialize_time(self, value: time) -> str:
        return value.strftime("%H:%M")

    model_config = {
        "from_attributes": True
    }


class ShiftCreateRequest(BaseModel):
    shift_name: str = Field(max_length=255)
    shift_start_time: time
    shift_end_time: time
    department: int

    @field_validator("shift_name")
    @classmethod
    def clean_name(cls, value):
        return _clean_name(value)


class ShiftUpdateRequest(BaseModel):
    shift_name: str | None = Field(default=None, max_length=255)
    shift_start_time: time | None = None
    shift_end_time: time | None = None
    department: int | None = None

    @field_validator("shift_name")
    @classmethod
    def clean_name(cls, value):
        return _clean_name(value)


class ShiftDeleteResponse(BaseModel):
    message: str
    unassigned_employees: int


class BulkAssignShiftRequest(BaseModel):
    department_id: int
    shift_id: int


class BulkAssignShiftResponse(BaseModel):
    message: str
    updated_count: int
