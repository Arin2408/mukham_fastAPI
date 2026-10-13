from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    verify_password,
)
from app.models.user import User
from app.services.account_service import start_session


def authenticate_user(
    db: Session,
    mobile_number: str,
    password: str,
) -> User | None:
    """
    Authenticate a user by mobile number and password.
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
    db: Session,
    user: User,
    device_name: str | None = None,
) -> dict[str, str]:
    """
    Start a session for an authenticated user and return its tokens.
    """
    try:
        refresh = start_session(db, user, device_name)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "access": create_access_token(
            user.mobile_number
        ),
        "refresh": refresh,
        "token_type": "bearer",
    }