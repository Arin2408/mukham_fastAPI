"""
Account flows migrated from Django:

- organisation signup / login   (organisation/views.py)
- member login / registration   (employees/views.py)
- forgot / reset password       (organisation/views.py)
- token refresh                 (SimpleJWT TokenRefreshView)
"""

import logging
import secrets
import smtplib
import string
from app.models.security_tracking import LivenessSession, RevokedRefreshToken
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.models.security_tracking import RevokedRefreshToken
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_password_reset_token,
    decode_refresh_token,
    hash_password,
    password_reset_token_matches,
    verify_password,
    create_member_pre_auth_token,
)
from app.models.employee import Employee
from app.models.user import User


logger = logging.getLogger(__name__)


class AccountError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def normalize_mobile(mobile_number: str) -> str:
    """Digits only, last 10 — the format Django stores."""
    return "".join(filter(str.isdigit, str(mobile_number)))[-10:]


def _safe_verify(plain_password: str, hashed_password: str | None) -> bool:
    if not hashed_password:
        return False
    try:
        return verify_password(plain_password, hashed_password)
    except (ValueError, TypeError):
        # Unknown/unusable hash format (e.g. Django's "!" unusable password)
        return False


# --------------------------------------------------
# ORGANISATION SIGNUP
# --------------------------------------------------

def register_organisation(
    db: Session,
    name: str,
    mobile_number: str,
    email: str | None,
    details: str | None,
) -> tuple[User, str]:
    mobile = normalize_mobile(mobile_number)

    if len(mobile) != 10:
        raise AccountError(400, "Enter a valid 10-digit mobile number.")

    # Django used a placeholder when email was omitted
    email = (email or "").strip() or f"{mobile}@placeholder.com"

    if db.query(User).filter(User.mobile_number == mobile).first():
        raise AccountError(400, "A user with this mobile number already exists.")

    if db.query(User).filter(User.email == email).first():
        raise AccountError(400, "A user with this email already exists.")

    alphabet = string.ascii_letters + string.digits
    generated_password = "".join(secrets.choice(alphabet) for _ in range(8))

    user = User(
        name=name.strip(),
        mobile_number=mobile,
        email=email,
        details=details,
        password=hash_password(generated_password),
        is_organization=True,
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise

    return user, generated_password


# --------------------------------------------------
# ORGANISATION LOGIN
# --------------------------------------------------

def login_organisation(
    db: Session,
    mobile_number: str,
    password: str,
) -> dict:
    mobile = normalize_mobile(mobile_number)
    user = db.query(User).filter(User.mobile_number == mobile).first()

    if user is None:
        raise AccountError(404, "User not found")

    if not user.is_active or not _safe_verify(password, user.password):
        raise AccountError(401, "Invalid password")

    role = "organization" if user.is_organization else "employee"

    return {
        "access": create_access_token(
            user.mobile_number,
            {"role": role, "org_id": user.org_id},
        ),
        "refresh": create_refresh_token(user.mobile_number),
        "org_id": user.org_id,
        "role": role,
    }


# --------------------------------------------------
# MEMBER LOGIN
# --------------------------------------------------

def _get_member(db: Session, mobile_number: str) -> tuple[User, Employee]:
    mobile = normalize_mobile(mobile_number)
    user = db.query(User).filter(User.mobile_number == mobile).first()

    if user is None:
        raise AccountError(404, "Member not found")

    employee = db.query(Employee).filter(Employee.user_id == user.org_id).first()

    if employee is None:
        raise AccountError(
            404,
            "This number belongs to an organization admin, not a member.",
        )

    return user, employee


def serialize_member_profile(user: User, employee: Employee) -> dict:
    organisation = employee.organisation

    return {
        "user_type": "organization" if user.is_organization else "employee",
        "user_id": user.org_id,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "department": employee.department_id,
        "designation": employee.designation_id,
        "shift": employee.shift_id,
        "office_location": employee.office_location_id,
        "organisation": (
            {"id": organisation.org_id, "name": organisation.name}
            if organisation
            else None
        ),
    }



def login_member(
    db: Session,
    mobile_number: str,
    password: str,
) -> dict:
    user, employee = _get_member(db, mobile_number)

    if not user.is_active:
        raise AccountError(401, "User account is inactive")

    if not employee.member_password:
        raise AccountError(400, "Member access not configured")

    if not _safe_verify(password, employee.member_password):
        raise AccountError(400, "Invalid mobile number or password.")

    return {
        "message": "Credentials verified. Face verification required.",
        "pre_auth_token": create_member_pre_auth_token(user.mobile_number),
        "user_type": "employee",
    }

def complete_member_login(
    db: Session,
    mobile_number: str,
    session_id: str,
) -> dict:
    user, employee = _get_member(db, mobile_number)

    if not user.is_active:
        raise AccountError(401, "User account is inactive")

    normalized_mobile = normalize_mobile(user.mobile_number)

    try:
        liveness = (
            db.query(LivenessSession)
            .filter(LivenessSession.session_id == session_id)
            .with_for_update()
            .first()
        )

        if (
            liveness is None
            or liveness.mobile_number != normalized_mobile
            or liveness.consumed_at is None
            or liveness.face_verified_at is None
        ):
            db.rollback()
            raise AccountError(
                401,
                "A successful face verification is required.",
            )

        if liveness.login_completed_at is not None:
            db.rollback()
            raise AccountError(
                409,
                "This face verification session has already been used.",
            )

        liveness.login_completed_at = datetime.now(timezone.utc)

        if not employee.is_member_registered:
            employee.is_member_registered = True

        db.commit()

    except AccountError:
        raise
    except Exception:
        db.rollback()
        raise

    return {
        "message": "Login successful",
        "access_token": create_access_token(
            user.mobile_number,
            {"role": "employee"},
        ),
        "refresh_token": create_refresh_token(user.mobile_number),
        "user_type": "employee",
        "user_id": employee.user_id,
        "is_registered": employee.is_member_registered,
        "profile": serialize_member_profile(user, employee),
    }



def check_registration_status(db: Session, mobile_number: str) -> dict:
    _, employee = _get_member(db, mobile_number)

    return {
        "is_registered": employee.is_member_registered,
        "exists": True,
    }


# --------------------------------------------------
# PASSWORD RESET
# --------------------------------------------------

def _send_email(to_address: str, subject: str, body: str) -> None:
    if not settings.email_host_password:
        logger.error("EMAIL_HOST_PASSWORD is not set; cannot send email.")
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.default_from_email
    message["To"] = to_address
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.email_host, settings.email_port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(settings.email_host_user, settings.email_host_password)
            smtp.send_message(message)
    except Exception:
        logger.exception("Failed to send email to %s", to_address)


def prepare_password_reset(db: Session, email: str) -> tuple[str, str, str] | None:
    """
    Return (to_address, subject, body) for the reset email, or None when no
    account matches. The caller responds the same way in both cases so the
    endpoint cannot be used to discover registered emails.
    """
    user = db.query(User).filter(User.email == email.strip()).first()

    if user is None or not user.is_active:
        return None

    token = create_password_reset_token(user.org_id, user.password)
    link = f"{settings.frontend_url.rstrip('/')}/reset-password?token={token}"

    body = (
        f"Hi {user.name},\n\n"
        "You requested a password reset. Use the link below to set a new "
        f"password. It expires in {settings.password_reset_token_minutes} "
        "minutes and can be used once:\n\n"
        f"{link}\n\n"
        "If you did not request this, please ignore this email."
    )

    return user.email, "Password Reset Request", body


def send_password_reset_email(to_address: str, subject: str, body: str) -> None:
    _send_email(to_address, subject, body)


def reset_password(db: Session, token: str, new_password: str) -> None:
    payload = decode_password_reset_token(token)

    if payload is None:
        raise AccountError(400, "This reset link is invalid or has expired.")

    user = db.query(User).filter(User.org_id == int(payload["sub"])).first()

    if user is None or not password_reset_token_matches(payload, user.password):
        raise AccountError(400, "This reset link is invalid or has expired.")

    user.password = hash_password(new_password)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


# --------------------------------------------------
# TOKEN REFRESH
# --------------------------------------------------


def refresh_access_token(db: Session, refresh_token: str) -> dict:
    payload = decode_refresh_token(refresh_token)

    if payload is None:
        raise AccountError(401, "Invalid or expired refresh token")

    mobile_number = str(payload["mobile_number"])
    token_jti = str(payload["jti"])

    user = (
        db.query(User)
        .filter(User.mobile_number == mobile_number)
        .first()
    )

    if user is None or not user.is_active:
        raise AccountError(401, "Invalid or expired refresh token")

    already_revoked = (
        db.query(RevokedRefreshToken)
        .filter(RevokedRefreshToken.jti == token_jti)
        .first()
    )

    if already_revoked is not None:
        raise AccountError(401, "Invalid or expired refresh token")

    now = datetime.now(timezone.utc)

    try:
        # The primary key on jti prevents the same refresh token
        # from being successfully rotated twice, including concurrent
        # requests.
        db.add(
            RevokedRefreshToken(
                jti=token_jti,
                mobile_number=user.mobile_number,
                expires_at=datetime.fromtimestamp(
                    int(payload["exp"]),
                    tz=timezone.utc,
                ),
                revoked_at=now,
            )
        )

        role = "organization" if user.is_organization else "employee"
        claims = {"role": role}

        if user.is_organization:
            claims["org_id"] = user.org_id

        new_access = create_access_token(
            user.mobile_number,
            claims,
        )
        new_refresh = create_refresh_token(user.mobile_number)

        db.commit()

    except IntegrityError:
        db.rollback()
        raise AccountError(401, "Invalid or expired refresh token")

    except Exception:
        db.rollback()
        raise

    return {
        "access": new_access,
        "refresh": new_refresh,
        "token_type": "bearer",
    }
