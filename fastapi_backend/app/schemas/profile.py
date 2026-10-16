from datetime import time

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class OrganisationProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    email: EmailStr
    details: str | None = None
    mobile_number: str | None = None
    is_organization: bool | None = None


class OrganisationProfileUpdate(BaseModel):
    name: str = Field(max_length=255)
    email: EmailStr = Field(max_length=254)
    details: str | None = Field(default=None, max_length=5000)


class EmployeeOfficeLocation(BaseModel):
    location_id: int
    location_name: str
    latitude: float
    longitude: float
    radius_meters: int


class EmployeeProfileResponse(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    mobile_number: str

    department_id: int | None = None
    designation_id: int | None = None
    shift_id: int | None = None
    office_location_id: int | None = None

    photo: str | None = None

    organisation_id: int
    is_member_registered: bool

    department_name: str | None = None
    designation_name: str | None = None
    shift_name: str | None = None
    location_name: str | None = None

    # Also returned by Django's nested profile; the member portal uses the
    # shift times for display and the office for a client-side pre-check.
    email: str | None = None
    shift_start_time: time | None = None
    shift_end_time: time | None = None
    office_location: EmployeeOfficeLocation | None = None
