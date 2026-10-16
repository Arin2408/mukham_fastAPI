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
from app.models.security_tracking import (
    LivenessSession,
    RefreshTokenFamily,
    RevokedRefreshToken,
)
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
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
from app.models.notification import PushDevice
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

    if db.query(User).filter(User.email_is(email)).first():
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
    device_name: str | None = None,
) -> dict:
    mobile = normalize_mobile(mobile_number)
    user = db.query(User).filter(User.mobile_number == mobile).first()

    # One answer for an unknown number and a wrong password, so this can't
    # be used to find out which numbers have accounts.
    if user is None or not user.is_active or not _safe_verify(password, user.password):
        raise AccountError(401, "Invalid mobile number or password")

    role = "organization" if user.is_organization else "employee"

    try:
        refresh = start_session(db, user, device_name)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "access": create_access_token(
            user.mobile_number,
            {"role": role, "org_id": user.org_id},
        ),
        "refresh": refresh,
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
    device_name: str | None = None,
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

        refresh = start_session(db, user, device_name)

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
        "refresh_token": refresh,
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
    user = db.query(User).filter(User.email_is(email)).first()

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

    # A reset signs the account out everywhere: if it was taken over, the
    # other sessions end now (access tokens already issued expire within
    # 60 minutes), and those phones stop getting notifications.
    now = datetime.now(timezone.utc)
    db.query(RefreshTokenFamily).filter(
        RefreshTokenFamily.mobile_number == user.mobile_number,
        RefreshTokenFamily.revoked_at.is_(None),
    ).update({"revoked_at": now, "revoked_reason": "password_reset"}, synchronize_session=False)
    db.query(PushDevice).filter(PushDevice.user_id == user.org_id).delete(synchronize_session=False)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


# --------------------------------------------------
# CHANGE PASSWORD (signed in)
# --------------------------------------------------

def change_password(
    db: Session,
    user: User,
    current_password: str,
    new_password: str,
    refresh_token: str | None = None,
    push_token: str | None = None,
) -> None:
    """
    Change the signed-in person's password: the admin's sign-in password, or
    the employee's member password. Every other signed-in device is signed
    out and stops getting notifications; this device (its refresh token and
    push token, when sent) stays signed in.
    """
    employee = None
    if user.is_organization:
        current_hash = user.password
    else:
        employee = db.query(Employee).filter(Employee.user_id == user.org_id).first()
        if employee is None:
            raise AccountError(404, "Employee profile not found")
        current_hash = employee.member_password

    if not _safe_verify(current_password, current_hash):
        raise AccountError(400, "Current password is incorrect.")

    if new_password == current_password:
        raise AccountError(400, "The new password must be different from the current one.")

    if employee is not None:
        employee.member_password = hash_password(new_password)
    else:
        user.password = hash_password(new_password)

    # This device's session, if it sent one that really is this person's.
    keep_family = None
    payload = decode_refresh_token(refresh_token) if refresh_token else None
    if payload and str(payload.get("mobile_number")) == user.mobile_number:
        keep_family = payload.get("fam")

    now = datetime.now(timezone.utc)
    others = db.query(RefreshTokenFamily).filter(
        RefreshTokenFamily.mobile_number == user.mobile_number,
        RefreshTokenFamily.revoked_at.is_(None),
    )
    if keep_family:
        others = others.filter(RefreshTokenFamily.family_id != keep_family)
    others.update(
        {"revoked_at": now, "revoked_reason": "password_change"},
        synchronize_session=False,
    )

    devices = db.query(PushDevice).filter(PushDevice.user_id == user.org_id)
    if push_token:
        devices = devices.filter(PushDevice.token != push_token)
    devices.delete(synchronize_session=False)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


# --------------------------------------------------
# SESSIONS: one refresh-token family per signed-in device
# --------------------------------------------------

INVALID_REFRESH_TOKEN = "Invalid or expired refresh token"


def start_session(
    db: Session,
    user: User,
    device_name: str | None = None,
) -> str:
    """
    Start a token family for a newly signed-in device and return its first
    refresh token. The caller commits.
    """
    now = datetime.now(timezone.utc)
    family_id = secrets.token_hex(16)

    db.add(
        RefreshTokenFamily(
            family_id=family_id,
            mobile_number=user.mobile_number,
            device_name=(device_name or "").strip()[:100] or None,
            created_at=now,
            last_used_at=now,
        )
    )

    return create_refresh_token(user.mobile_number, family_id)


def _record_used_token(db: Session, payload: dict, now: datetime) -> None:
    db.add(
        RevokedRefreshToken(
            jti=str(payload["jti"]),
            mobile_number=str(payload["mobile_number"]),
            expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc),
            revoked_at=now,
        )
    )


def _revoke_family(
    db: Session,
    family_id: str,
    reason: str,
    now: datetime,
) -> None:
    family = db.get(RefreshTokenFamily, family_id)
    if family is not None and family.revoked_at is None:
        family.revoked_at = now
        family.revoked_reason = reason


def refresh_access_token(db: Session, refresh_token: str) -> dict:
    payload = decode_refresh_token(refresh_token)

    if payload is None:
        raise AccountError(401, INVALID_REFRESH_TOKEN)

    user = (
        db.query(User)
        .filter(User.mobile_number == str(payload["mobile_number"]))
        .first()
    )

    if user is None or not user.is_active:
        raise AccountError(401, INVALID_REFRESH_TOKEN)

    family_id = payload.get("fam")
    now = datetime.now(timezone.utc)

    already_used = (
        db.query(RevokedRefreshToken)
        .filter(RevokedRefreshToken.jti == str(payload["jti"]))
        .first()
    )

    if already_used is not None:
        # Each refresh token works once. Seeing one again means a copy is
        # in someone else's hands, so sign that device out entirely.
        if family_id:
            _revoke_family(db, family_id, "token_reuse", now)
            db.commit()
            logger.warning(
                "Refresh token reused; revoked token family %s for %s",
                family_id,
                user.mobile_number,
            )
        raise AccountError(401, INVALID_REFRESH_TOKEN)

    family = None
    if family_id:
        family = (
            db.query(RefreshTokenFamily)
            .filter(RefreshTokenFamily.family_id == family_id)
            .with_for_update()
            .first()
        )
        if (
            family is None
            or family.revoked_at is not None
            or family.mobile_number != user.mobile_number
        ):
            db.rollback()
            raise AccountError(401, INVALID_REFRESH_TOKEN)

    try:
        # The primary key on jti stops the same refresh token from being
        # rotated twice, including by concurrent requests.
        _record_used_token(db, payload, now)

        if family is None:
            # Issued before token families existed: give it a family now.
            new_refresh = start_session(db, user)
        else:
            family.last_used_at = now
            new_refresh = create_refresh_token(user.mobile_number, family.family_id)

        role = "organization" if user.is_organization else "employee"
        claims = {"role": role}

        if user.is_organization:
            claims["org_id"] = user.org_id

        new_access = create_access_token(
            user.mobile_number,
            claims,
        )

        db.commit()

    except IntegrityError:
        db.rollback()
        raise AccountError(401, INVALID_REFRESH_TOKEN)

    except Exception:
        db.rollback()
        raise

    return {
        "access": new_access,
        "refresh": new_refresh,
        "token_type": "bearer",
    }


def end_session(db: Session, refresh_token: str) -> None:
    """
    Sign a device out: revoke its token family, so none of its refresh
    tokens work again. Invalid or expired tokens are ignored, so signing
    out always succeeds. Access tokens already issued stay valid until
    they expire (at most 60 minutes).
    """
    payload = decode_refresh_token(refresh_token)

    if payload is None:
        return

    now = datetime.now(timezone.utc)

    try:
        if payload.get("fam"):
            _revoke_family(db, str(payload["fam"]), "sign_out", now)

        already_used = (
            db.query(RevokedRefreshToken)
            .filter(RevokedRefreshToken.jti == str(payload["jti"]))
            .first()
        )
        if already_used is None:
            _record_used_token(db, payload, now)

        db.commit()

    except IntegrityError:
        # Revoked by a concurrent request; the outcome is the same.
        db.rollback()

    except Exception:
        db.rollback()
        raise
