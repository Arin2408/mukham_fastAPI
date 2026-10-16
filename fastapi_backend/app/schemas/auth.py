from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    mobile_number: str = Field(
        min_length=1,
        max_length=15,
    )

    password: str = Field(
        min_length=1,
        max_length=128,
    )

    # Optional label for the signed-in device, e.g. "Pixel 8" (mobile app).
    device_name: str | None = Field(default=None, max_length=100)


class TokenResponse(BaseModel):
    access: str
    refresh: str
    token_type: str = "bearer"