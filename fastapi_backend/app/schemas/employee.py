
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict


class EmployeeCreateRequest(BaseModel):
    mobile_number: str = Field(max_length=20)
    email: str = Field(max_length=254)
    first_name: str = Field(max_length=255)
    last_name: str = Field(max_length=255)
    department: int | None = None
    designation: int | None = None
    shift: int | None = None
    office_location: int | None = None

    # Required: who this employee reports to. null = reports directly to
    # the organisation admin (top of the reporting tree).
    manager: int | None


class EmployeeUpdateRequest(BaseModel):
    mobile_number: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=254)
    first_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    department: int | None = None
    designation: int | None = None
    shift: int | None = None
    office_location: int | None = None

    # Omit to keep the current manager; null = report to the organisation.
    manager: int | None = None


class EmployeeResponse(BaseModel):
    user_id: int
    employee_id: int
    first_name: str
    last_name: str
    mobile_number: str
    email: str

    department: int | None = None
    department_id: int | None = None
    department_name: str = "N/A"

    designation: int | None = None
    designation_id: int | None = None
    designation_name: str = "N/A"

    shift: int | None = None
    shift_id: int | None = None
    shift_name: str = "N/A"

    office_location: int | None = None
    office_location_id: int | None = None
    location_name: str = "N/A"

    photo: str | None = None
    organisation_id: int
    is_member_registered: bool
    # For the ID card's QR code: /verify/<card_code>
    card_code: str

    manager_id: int | None = None
    manager_name: str | None = None

    # The phone this employee checks in from: "none" until their first
    # check-in from the app, "registered", or "pending" when a different
    # phone is waiting for the admin's approval. None while the phone lock
    # is off (PHONE_LOCK_ENABLED).
    phone_status: Literal["none", "registered", "pending"] | None = None
    phone_registered_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class EmployeeCreateResponse(EmployeeResponse):
    member_password: str | None = None


class EmployeeCardResponse(BaseModel):
    employee_id: int
    first_name: str
    last_name: str
    designation_name: str | None = None
    department_name: str | None = None
    organisation_name: str | None = None
    photo: str | None = None
    card_code: str



class ManagerUpdateRequest(BaseModel):
    # null = report directly to the organisation admin
    manager_id: int | None


class HierarchyEmployee(BaseModel):
    employee_id: int
    first_name: str
    last_name: str
    designation_name: str | None = None
    department_id: int | None = None
    department_name: str | None = None
    photo: str | None = None
    manager_id: int | None = None
    direct_reports: int = 0


class HierarchyResponse(BaseModel):
    organisation_id: int
    organisation_name: str
    employees: list[HierarchyEmployee]
