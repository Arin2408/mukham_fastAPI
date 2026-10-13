from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from app.models.employee import Employee
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import JWT_ALGORITHM
from app.db.session import get_db
from app.models.user import User

security = HTTPBearer(auto_error=True)


def _normalise_mobile(value: str) -> str:
    """Return digits only. Do not discard digits unless needed for fallback lookup."""
    return "".join(ch for ch in str(value) if ch.isdigit())


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Django SimpleJWT uses HS256 by default. The effective key configured
        # in FastAPI must match Django's effective SIMPLE_JWT SIGNING_KEY (or
        # Django SECRET_KEY when SIGNING_KEY is not overridden).
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[JWT_ALGORITHM],
            options={"verify_exp": True},
        )
    except JWTError:
        # Do not log token contents or unverified claims.
        raise credentials_exception

    if payload.get("token_type") != "access":
        raise credentials_exception

    mobile_claim = payload.get("mobile_number")
    if not mobile_claim:
        raise credentials_exception

    claim_digits = _normalise_mobile(mobile_claim)
    if not claim_digits:
        raise credentials_exception

    # Prefer exact matching. Django's login currently normalizes the submitted
    # number to its last 10 digits before querying CustomUser. The token's
    # mobile_number is the stored user's mobile_number, so exact match should
    # normally succeed. Use a last-10-digit fallback only if it identifies
    # exactly one database row, avoiding ambiguous account matches.
    user = (
        db.query(User)
        .filter(User.mobile_number == str(mobile_claim))
        .first()
    )

    if user is None and len(claim_digits) >= 10:
        suffix = claim_digits[-10:]
        candidates = db.query(User).all()
        matches = [
            candidate
            for candidate in candidates
            if _normalise_mobile(candidate.mobile_number)[-10:] == suffix
        ]
        if len(matches) == 1:
            user = matches[0]

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # If Django includes org_id, verify it for organization accounts rather
    # than trusting it as the source of identity. Identity comes from the DB.
    token_org_id = payload.get("org_id")
    if (
        user.is_organization
        and token_org_id is not None
        and str(token_org_id) != str(user.org_id)
    ):
        raise credentials_exception

    return user

def get_current_member_pre_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired member pre-authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[JWT_ALGORITHM],
            options={"verify_exp": True},
        )
    except JWTError:
        raise credentials_exception

    if payload.get("token_type") != "member_pre_auth":
        raise credentials_exception

    mobile_claim = payload.get("mobile_number")
    if not mobile_claim or not payload.get("jti"):
        raise credentials_exception

    claim_digits = _normalise_mobile(mobile_claim)
    if not claim_digits:
        raise credentials_exception

    user = (
        db.query(User)
        .filter(User.mobile_number == str(mobile_claim))
        .first()
    )

    # Support the existing last-10-digit mobile format only when unique.
    if user is None and len(claim_digits) >= 10:
        suffix = claim_digits[-10:]
        candidates = db.query(User).all()

        matches = [
            candidate
            for candidate in candidates
            if _normalise_mobile(candidate.mobile_number)[-10:] == suffix
        ]

        if len(matches) == 1:
            user = matches[0]

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise credentials_exception

    if user.is_organization:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Member account required",
        )

    employee = (
        db.query(Employee)
        .filter(Employee.user_id == user.org_id)
        .first()
    )

    if employee is None:
        raise credentials_exception

    return user
