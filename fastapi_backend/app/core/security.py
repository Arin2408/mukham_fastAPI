import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings


# Existing Django users use PBKDF2-SHA256 password hashes.
#
# Example Django hash format:
# pbkdf2_sha256$iterations$salt$hash
#
# FastAPI will verify these existing hashes directly.
pwd_context = CryptContext(
    schemes=["django_pbkdf2_sha256"],
    deprecated="auto",
)


JWT_ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 60


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """
    Verify a plain password against an existing
    Django PBKDF2-SHA256 password hash.
    """

    return pwd_context.verify(
        plain_password,
        hashed_password,
    )


def hash_password(plain_password: str) -> str:
    """Hash in Django's PBKDF2 format so Django can still verify it."""
    return pwd_context.hash(plain_password)


def create_access_token(
    mobile_number: str,
    extra_claims: dict | None = None,
) -> str:
    """
    Create an access JWT.
    """

    now = datetime.now(timezone.utc)

    expire = now + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        **(extra_claims or {}),
        "token_type": "access",
        "mobile_number": mobile_number,
        "iat": now,
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.secret_key,
        algorithm=JWT_ALGORITHM,
    )



def create_member_pre_auth_token(mobile_number: str) -> str:
    now = datetime.now(timezone.utc)

    payload = {
        "token_type": "member_pre_auth",
        "mobile_number": mobile_number,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }

    return jwt.encode(
        payload,
        settings.secret_key,
        algorithm=JWT_ALGORITHM,
    )
def create_refresh_token(
    mobile_number: str,
    family_id: str,
) -> str:
    """
    Create a refresh JWT. `jti` identifies this token for rotation;
    `fam` is the signed-in device's token family.
    """
    now = datetime.now(timezone.utc)

    payload = {
        "token_type": "refresh",
        "mobile_number": mobile_number,
        "jti": uuid.uuid4().hex,
        "fam": family_id,
        "iat": now,
        "exp": now + timedelta(
            days=settings.refresh_token_expire_days
        ),
    }

    return jwt.encode(
        payload,
        settings.secret_key,
        algorithm=JWT_ALGORITHM,
    )


def _password_fingerprint(hashed_password: str) -> str:
    # Changes whenever the password changes, which makes a reset token
    # single-use without storing anything in the database.
    return hashlib.sha256(hashed_password.encode("utf-8")).hexdigest()[:16]


def create_password_reset_token(
    org_id: int,
    hashed_password: str,
) -> str:
    now = datetime.now(timezone.utc)

    payload = {
        "token_type": "password_reset",
        "sub": str(org_id),
        "pwd": _password_fingerprint(hashed_password),
        "iat": now,
        "exp": now + timedelta(
            minutes=settings.password_reset_token_minutes
        ),
    }

    return jwt.encode(
        payload,
        settings.secret_key,
        algorithm=JWT_ALGORITHM,
    )


def decode_password_reset_token(token: str) -> dict | None:
    """Return the payload, or None if the token is invalid or expired."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[JWT_ALGORITHM],
        )
    except JWTError:
        return None

    if payload.get("token_type") != "password_reset":
        return None

    return payload


def password_reset_token_matches(
    payload: dict,
    hashed_password: str,
) -> bool:
    return hmac.compare_digest(
        payload.get("pwd", ""),
        _password_fingerprint(hashed_password),
    )



def decode_refresh_token(token: str) -> dict | None:
    """Validate a refresh JWT issued by this application."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[JWT_ALGORITHM],
        )
    except JWTError:
        return None

    if payload.get("token_type") != "refresh":
        return None

    if not payload.get("mobile_number"):
        return None

    if not payload.get("jti") or not payload.get("exp"):
        return None

    return payload



FACE_TOKEN_EXPIRE_MINUTES = 5


def create_face_token(mobile_number: str) -> str:
    """
    Short-lived proof that the server matched this mobile number's
    registered face. Attendance check-in requires it, so a client cannot
    simply claim face_status="verified".
    """
    now = datetime.now(timezone.utc)

    payload = {
        "token_type": "face_verified",
        "mobile_number": mobile_number,
        "iat": now,
        "exp": now + timedelta(minutes=FACE_TOKEN_EXPIRE_MINUTES),
    }

    return jwt.encode(
        payload,
        settings.secret_key,
        algorithm=JWT_ALGORITHM,
    )


def face_token_mobile(token: str) -> str | None:
    """Return the verified mobile number, or None if the token is invalid."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[JWT_ALGORITHM],
        )
    except JWTError:
        return None

    if payload.get("token_type") != "face_verified":
        return None

    return payload.get("mobile_number")
