from pydantic import BaseModel, Field


class DepartmentResponse(BaseModel):
    department_id: int
    org_id: int
    details: str
    location_id: int

    model_config = {"from_attributes": True}


class DepartmentCreateRequest(BaseModel):
    details: str = Field(max_length=255)
    location: int


class DepartmentUpdateRequest(BaseModel):
    details: str | None = Field(default=None, max_length=255)
    location: int | None = None


class DepartmentLeaderboardResponse(BaseModel):
    department_id: int
    department_name: str
    punctuality_score: float
    total_attendances: int