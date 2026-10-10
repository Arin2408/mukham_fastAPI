from datetime import datetime

from pydantic import BaseModel


class AttendanceHistoryResponse(BaseModel):
    id: int
    employee_id: int

    employee_name: str | None = None

    check_in: datetime
    check_out: datetime | None = None

    status: str
    location_status: str
    source: str
    face_status: str

    hours_worked: float | None = None

    check_in_latitude: float | None = None
    check_in_longitude: float | None = None
    check_in_accuracy: float | None = None
    check_in_distance: float | None = None

    check_out_latitude: float | None = None
    check_out_longitude: float | None = None
    check_out_accuracy: float | None = None
    check_out_distance: float | None = None
    check_out_location_status: str | None = None

    check_in_location_id: int | None = None

    model_config = {
        "from_attributes": True
    }

class AttendanceEmployeeListResponse(BaseModel):
    employee_id: int
    first_name: str
    last_name: str
    mobile_number: str
    email: str
    department: int | None = None
    designation: int | None = None
    shift: int | None = None
    office_location: int | None = None
    designation_name: str | None = None
    department_name: str | None = None
    shift_name: str | None = None
    location_name: str | None = None
    photo: str | None = None   