from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
)
from app.services.auth_service import (
    authenticate_user,
    create_tokens,
)
from app.dependencies.auth import get_current_user
from app.models.user import User


router = APIRouter()

@router.get("/auth/verify")
def verify_token(
    current_user: User = Depends(get_current_user),
):
    return {
        "valid": True,
        "mobile_number": current_user.mobile_number,
        "is_organization": current_user.is_organization,
        "role": "organization" if current_user.is_organization else "employee",
    }

@router.post(
    "/auth/login",
    response_model=TokenResponse,
)
def login(
    data: LoginRequest,
    db: Session = Depends(get_db),
):
    user = authenticate_user(
        db=db,
        mobile_number=data.mobile_number,
        password=data.password,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid mobile number or password",
        )

    return create_tokens(db, user, data.device_name)