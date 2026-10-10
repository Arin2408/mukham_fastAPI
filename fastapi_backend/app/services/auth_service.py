from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
)
from app.models.user import User


def authenticate_user(
    db: Session,
    mobile_number: str,
    password: str,
) -> User | None:
    """
    Authenticate an existing user using the same database
    used by Django.
    """

    user = (
        db.query(User)
        .filter(
            User.mobile_number == mobile_number
        )
        .first()
    )

    if user is None:
        return None

    if not user.is_active:
        return None

    if not verify_password(
        password,
        user.password,
    ):
        return None

    return user


def create_tokens(
    user: User,
) -> dict[str, str]:
    """
    Generate access and refresh tokens for an authenticated user.
    """

    return {
        "access": create_access_token(
            user.mobile_number
        ),
        "refresh": create_refresh_token(
            user.mobile_number
        ),
        "token_type": "bearer",
    }