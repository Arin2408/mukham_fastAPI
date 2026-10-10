from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.account import (
    ForgotPasswordRequest,
    MemberLoginResponse,
    MessageResponse,
    MobileLoginRequest,
    MobileNumberRequest,
    OrgLoginResponse,
    OrgSignupRequest,
    OrgSignupResponse,
    RefreshRequest,
    RefreshResponse,
    RegistrationStatusResponse,
    ResetPasswordRequest,
)
from app.services.account_service import (
    AccountError,
    check_registration_status,
    login_member,
    login_organisation,
    prepare_password_reset,
    refresh_access_token,
    register_organisation,
    reset_password,
    send_password_reset_email,
)


router = APIRouter()


def _raise(error: AccountError):
    headers = (
        {"WWW-Authenticate": "Bearer"}
        if error.status_code == status.HTTP_401_UNAUTHORIZED
        else None
    )
    raise HTTPException(
        status_code=error.status_code,
        detail=error.message,
        headers=headers,
    )


# --------------------------------------------------
# POST /api/v1/org/signup   (Django: /api/org/signup/)
# --------------------------------------------------

@router.post(
    "/org/signup",
    response_model=OrgSignupResponse,
    status_code=status.HTTP_201_CREATED,
)
def org_signup(
    data: OrgSignupRequest,
    db: Session = Depends(get_db),
):
    try:
        user, generated_password = register_organisation(
            db=db,
            name=data.name,
            mobile_number=data.mobile_number,
            email=data.email,
            details=data.details,
        )
    except AccountError as error:
        _raise(error)

    return {
        "mobile_number": user.mobile_number,
        "generated_password": generated_password,
        "message": "User created successfully",
    }


# --------------------------------------------------
# POST /api/v1/org/login   (Django: /api/org/login/)
# --------------------------------------------------

@router.post(
    "/org/login",
    response_model=OrgLoginResponse,
)
def org_login(
    data: MobileLoginRequest,
    db: Session = Depends(get_db),
):
    try:
        return login_organisation(db, data.mobile_number, data.password)
    except AccountError as error:
        _raise(error)


# --------------------------------------------------
# POST /api/v1/member/login   (Django: /api/member/login/)
# --------------------------------------------------

@router.post(
    "/member/login",
    response_model=MemberLoginResponse,
)
def member_login(
    data: MobileLoginRequest,
    db: Session = Depends(get_db),
):
    try:
        return login_member(db, data.mobile_number, data.password)
    except AccountError as error:
        _raise(error)


# --------------------------------------------------
# POST /api/v1/member/check-registration
# --------------------------------------------------

@router.post(
    "/member/check-registration",
    response_model=RegistrationStatusResponse,
)
def member_check_registration(
    data: MobileNumberRequest,
    db: Session = Depends(get_db),
):
    try:
        return check_registration_status(db, data.mobile_number)
    except AccountError as error:
        _raise(error)


# --------------------------------------------------
# POST /api/v1/forgot-password
# --------------------------------------------------

@router.post(
    "/forgot-password",
    response_model=MessageResponse,
)
def forgot_password(
    data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    email = prepare_password_reset(db, data.email)

    if email is not None:
        background_tasks.add_task(send_password_reset_email, *email)

    # Same response whether or not the email exists.
    return {
        "message": "If an account exists for this email, a reset link has been sent."
    }


# --------------------------------------------------
# POST /api/v1/reset-password
# --------------------------------------------------

@router.post(
    "/reset-password",
    response_model=MessageResponse,
)
def reset_password_endpoint(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    try:
        reset_password(db, data.token, data.password)
    except AccountError as error:
        _raise(error)

    return {"message": "Password reset successfully"}


# --------------------------------------------------
# POST /api/v1/auth/refresh   (Django: /api/token/refresh/)
# --------------------------------------------------

@router.post(
    "/auth/refresh",
    response_model=RefreshResponse,
)
def refresh_token(
    data: RefreshRequest,
    db: Session = Depends(get_db),
):
    try:
        return refresh_access_token(db, data.refresh)
    except AccountError as error:
        _raise(error)
