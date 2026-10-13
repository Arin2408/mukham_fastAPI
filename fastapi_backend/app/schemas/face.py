from datetime import datetime

from pydantic import BaseModel, Field


class FaceVerifyRequest(BaseModel):
    mobile_number: str = Field(min_length=1, max_length=15)
    face_image_base64: str = Field(min_length=1)


class FaceVerifyResponse(BaseModel):
    verified: bool
    confidence: float | None = None
    similarity: float | None = None
    message: str
    face_token: str | None = None


class LivenessCreateResponse(BaseModel):
    session_id: str
    region: str


class LivenessResultRequest(BaseModel):
    session_id: str = Field(min_length=1)
    mobile_number: str = Field(min_length=1, max_length=15)
    mode: str = "verify"

class FaceStatusRequest(BaseModel):
    mobile_number: str = Field(min_length=1, max_length=20)


class FaceRegisterRequest(BaseModel):
    mobile_number: str = Field(min_length=1, max_length=20)
    face_image_base64: str = Field(min_length=1)



class FaceDetailsResponse(BaseModel):
    mobile_number: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
