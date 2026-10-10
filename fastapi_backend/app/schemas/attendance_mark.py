from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AttendanceMarkRequest(BaseModel):
    # "checkin" never checks out, "checkout" only checks out; omitted keeps
    # Django's legacy toggle behaviour.
    action: Literal["checkin", "checkout"] | None = None

    # Required for check-in; optional for check-out (never blocked).
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    accuracy: float | None = Field(default=None, ge=0)

    # Returned by POST /face/verify after a successful server-side match.
    face_token: str | None = None

    # Sent by older clients; ignored - the server decides these.
    location_status: str | None = None
    face_status: str | None = None


class AttendanceMarkResponse(BaseModel):
    id: int
    employee_id: int
    action: str
    status: str
    location_status: str
    face_status: str
    check_in: datetime
    check_out: datetime | None = None
    check_out_location_status: str | None = None
    hours_worked: float | None = None
    distance_meters: float | None = None
    allowed_radius_meters: int | None = None
    location_id: int | None = None
    location_name: str | None = None
