from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# AWS takes face images up to 5 MB, which is under 7 million base64 characters.
MAX_IMAGE_BASE64 = 7_000_000


class LivenessCreateResponse(BaseModel):
    session_id: str
    region: str


class LivenessResultRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    mobile_number: str = Field(min_length=1, max_length=15)
    mode: Literal["register", "verify"] = "verify"

class FaceStatusRequest(BaseModel):
    mobile_number: str = Field(min_length=1, max_length=20)


class FaceRegisterRequest(BaseModel):
    mobile_number: str = Field(min_length=1, max_length=20)
    face_image_base64: str = Field(min_length=1, max_length=MAX_IMAGE_BASE64)



class FaceDetailsResponse(BaseModel):
    mobile_number: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
