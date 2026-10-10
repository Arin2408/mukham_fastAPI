from typing import Literal

from pydantic import BaseModel


class ManualAttendanceRequest(BaseModel):
    employee_id: int
    action: Literal["checkin", "checkout"]


class ManualAttendanceResponse(BaseModel):
    id: int
    employee_id: int
    action: str
    status: str
    location_status: str
    source: str
    face_status: str
    check_in: object
    check_out: object | None = None
    hours_worked: float | None = None
    marked_by_id: int | None = None