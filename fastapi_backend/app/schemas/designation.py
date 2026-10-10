from pydantic import BaseModel


class DesignationResponse(BaseModel):
    designation_id: int
    department_id: int
    details: str

    model_config = {
        "from_attributes": True
    }


class DesignationCreateRequest(BaseModel):
    department: int
    details: str


class DesignationUpdateRequest(BaseModel):
    department: int | None = None
    details: str | None = None