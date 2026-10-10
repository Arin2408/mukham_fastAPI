from pydantic import BaseModel


class DepartmentResponse(BaseModel):
    department_id: int
    org_id: int
    details: str
    location_id: int

    model_config = {"from_attributes": True}


class DepartmentCreateRequest(BaseModel):
    details: str
    location: int


class DepartmentUpdateRequest(BaseModel):
    details: str | None = None
    location: int | None = None


class DepartmentLeaderboardResponse(BaseModel):
    department_id: int
    department_name: str
    punctuality_score: float
    total_attendances: int