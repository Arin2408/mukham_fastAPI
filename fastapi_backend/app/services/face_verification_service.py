from app.core.security import face_token_mobile


class FaceVerificationRequired(Exception):
    """Raised when attendance requires face verification."""


def _digits(value: str | None) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[-10:]


def verify_attendance_face(
    face_token: str | None,
    mobile_number: str,
) -> None:
    """
    Attendance only continues when the server itself matched the face.

    POST /face/verify returns a short-lived `face_token` after a successful
    match. The token must belong to the logged-in employee; a client-sent
    face_status / face_verified flag is never trusted.
    """
    if not face_token:
        raise FaceVerificationRequired(
            "Face verification is required before attendance can be marked."
        )

    verified_mobile = face_token_mobile(face_token)

    if verified_mobile is None:
        raise FaceVerificationRequired(
            "Face verification has expired. Please verify your face again."
        )

    if _digits(verified_mobile) != _digits(mobile_number):
        raise FaceVerificationRequired(
            "Face verification does not match the logged-in employee."
        )
