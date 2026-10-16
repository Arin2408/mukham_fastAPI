from pydantic import BaseModel, Field


class DesignationResponse(BaseModel):
    designation_id: int
    department_id: int
    details: str

    model_config = {
        "from_attributes": True
    }


class DesignationCreateRequest(BaseModel):
    department: int
    details: str = Field(max_length=255)


class DesignationUpdateRequest(BaseModel):
    department: int | None = None
    details: str | None = Field(default=None, max_length=255)