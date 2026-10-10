from pydantic import BaseModel, Field


class OrgSignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    mobile_number: str = Field(min_length=1, max_length=20)
    email: str | None = None
    details: str | None = None


class OrgSignupResponse(BaseModel):
    mobile_number: str
    generated_password: str
    message: str


class MobileLoginRequest(BaseModel):
    mobile_number: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=1)


class OrgLoginResponse(BaseModel):
    access: str
    refresh: str
    org_id: int
    role: str


class MemberOrganisation(BaseModel):
    id: int
    name: str


class MemberProfile(BaseModel):
    user_type: str
    user_id: int
    first_name: str
    last_name: str
    department: int | None
    designation: int | None
    shift: int | None
    office_location: int | None
    organisation: MemberOrganisation | None


class MemberLoginResponse(BaseModel):
    message: str
    access_token: str
    refresh_token: str
    user_type: str
    user_id: int
    is_registered: bool
    profile: MemberProfile


class MobileNumberRequest(BaseModel):
    mobile_number: str = Field(min_length=1, max_length=20)


class RegistrationStatusResponse(BaseModel):
    is_registered: bool
    exists: bool


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    password: str = Field(min_length=8, max_length=128)


class MessageResponse(BaseModel):
    message: str


class RefreshRequest(BaseModel):
    refresh: str = Field(min_length=1)


class RefreshResponse(BaseModel):
    access: str
    token_type: str = "bearer"
