import base64
import logging

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_face_token
from app.models.face import EmployeeFaceData

from datetime import datetime, timezone


logger = logging.getLogger(__name__)


aws_config = Config(
    connect_timeout=3,
    read_timeout=8,
    retries={
        "total_max_attempts": 2,
        "mode": "standard",
    },
    tcp_keepalive=True,
)


rekognition = boto3.client(
    "rekognition",
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=settings.aws_default_region,
    config=aws_config,
)


ATTENDANCE_FACE_MIN_SIMILARITY = 90


def normalize_mobile(mobile_number: str) -> str:
    """
    Keep only digits and return the last 10 digits.
    Matches the existing Django behavior.
    """
    return "".join(
        filter(str.isdigit, str(mobile_number))
    )[-10:]


def verify_face(
    db: Session,
    mobile_number: str,
    captured_image_base64: str,
) -> dict:

    normalized = normalize_mobile(mobile_number)

    try:
        face_record = (
            db.query(EmployeeFaceData)
            .filter(
                EmployeeFaceData.mobile_number == normalized
            )
            .first()
        )

        if face_record is None:
            logger.info(
                "Face verify: no registered face for %s",
                normalized,
            )

            return {
                "status_code": 404,
                "body": {
                    "error": (
                        "No reference face image found. "
                        "Please register first."
                    )
                },
            }

        try:
            stored_image_bytes = base64.b64decode(
                face_record.face_image_base64
            )

            captured_image_bytes = base64.b64decode(
                captured_image_base64
            )

        except Exception:
            return {
                "status_code": 400,
                "body": {
                    "error": "Invalid image data"
                },
            }

        try:
            aws_response = rekognition.compare_faces(
                SourceImage={
                    "Bytes": stored_image_bytes
                },
                TargetImage={
                    "Bytes": captured_image_bytes
                },
                SimilarityThreshold=80,
            )

        except ClientError as e:
            logger.warning(
                "Face verify: AWS ClientError: %s",
                e,
            )

            return {
                "status_code": 400,
                "body": {
                    "error": (
                        "Face verification failed: "
                        f"{e.response['Error']['Message']}"
                    )
                },
            }

        matches = aws_response.get("FaceMatches", [])

        if matches:
            similarity = matches[0]["Similarity"]

            logger.info(
                "Face verify: match for %s "
                "(similarity %.1f%%)",
                normalized,
                similarity,
            )

            body = {
                "verified": True,
                "confidence": similarity,
                "similarity": similarity,
                "message": "Face verified successfully",
            }

            # Attendance check-in requires this server-issued proof.
            # Same threshold the member portal applies.
            if similarity >= ATTENDANCE_FACE_MIN_SIMILARITY:
                body["face_token"] = create_face_token(normalized)

            return {
                "status_code": 200,
                "body": body,
            }

        logger.info(
            "Face verify: no match for %s",
            normalized,
        )

        return {
            "status_code": 400,
            "body": {
                "verified": False,
                "confidence": 0,
                "message": (
                    "Face verification failed. "
                    "No match found. "
                    "Please look directly at the camera."
                ),
            },
        }

    except Exception as e:
        logger.exception("Face verify failed")

        return {
            "status_code": 500,
            "body": {
                "error": f"Internal Error: {str(e)}"
            },
        }


def create_liveness_session() -> dict:
    try:
        response = rekognition.create_face_liveness_session()

        return {
            "status_code": 200,
            "body": {
                "session_id": response["SessionId"],
                "region": settings.aws_default_region,
            },
        }

    except ClientError as e:
        return {
            "status_code": 400,
            "body": {
                "error": e.response["Error"]["Message"]
            },
        }

    except Exception as e:
        return {
            "status_code": 500,
            "body": {
                "error": str(e)
            },
        }


def get_liveness_result(
    db: Session,
    session_id: str,
    mobile_number: str,
    mode: str = "verify",
) -> dict:

    if mode not in ("register", "verify"):
        return {
            "status_code": 400,
            "body": {
                "error": (
                    "Invalid mode. "
                    "Must be 'register' or 'verify'."
                )
            },
        }

    normalized = normalize_mobile(mobile_number)

    try:
        response = rekognition.get_face_liveness_session_results(
            SessionId=session_id
        )

        confidence = response.get("Confidence")
        session_status = response.get("Status")

        if session_status != "SUCCEEDED":
            return {
                "status_code": 400,
                "body": {
                    "verified": False,
                    "status": session_status,
                    "confidence": confidence,
                    "message": (
                        "Face liveness verification failed."
                    ),
                },
            }

        reference_image = response.get("ReferenceImage")

        if not reference_image:
            return {
                "status_code": 400,
                "body": {
                    "verified": False,
                    "status": session_status,
                    "confidence": confidence,
                    "message": (
                        "Reference image not found."
                    ),
                },
            }

        reference_bytes = reference_image.get("Bytes")

        if not reference_bytes:
            return {
                "status_code": 400,
                "body": {
                    "verified": False,
                    "status": session_status,
                    "confidence": confidence,
                    "message": (
                        "Reference image bytes not found."
                    ),
                },
            }

        # ---------------------------------------------------------
        # REGISTER MODE
        # ---------------------------------------------------------

        if mode == "register":

            from app.models.user import User

            user = (
                db.query(User)
                .filter(
                    User.mobile_number == normalized
                )
                .first()
            )

            if user is None:
                return {
                    "status_code": 404,
                    "body": {
                        "error": "Employee not found."
                    },
                }

            existing_face = (
                db.query(EmployeeFaceData)
                .filter(
                    EmployeeFaceData.mobile_number == normalized
                )
                .first()
            )

            if existing_face is not None:
                return {
                    "status_code": 400,
                    "body": {
                        "error": (
                            "Face is already registered "
                            "for this employee."
                        )
                    },
                }

            # Check whether this face already belongs
            # to another employee.
            other_faces = (
                db.query(EmployeeFaceData)
                .filter(
                    EmployeeFaceData.mobile_number != normalized
                )
                .all()
            )

            for other in other_faces:
                try:
                    stored_bytes = base64.b64decode(
                        other.face_image_base64
                    )

                    comparison = rekognition.compare_faces(
                        SourceImage={
                            "Bytes": stored_bytes
                        },
                        TargetImage={
                            "Bytes": reference_bytes
                        },
                        SimilarityThreshold=90,
                    )

                    if comparison.get("FaceMatches"):
                        return {
                            "status_code": 400,
                            "body": {
                                "error": (
                                    "This face is already registered "
                                    "to another employee account."
                                ),
                                "code": "DUPLICATE_FACE",
                            },
                        }

                except Exception as e:
                    logger.warning(
                        "Duplicate-face check failed for %s: %s",
                        other.mobile_number,
                        e,
                    )
                    continue

            face_base64 = base64.b64encode(
                reference_bytes
            ).decode("utf-8")

            # Django automatically populated these timestamps
            # using auto_now_add / auto_now.
            # FastAPI/SQLAlchemy must supply them explicitly.
            now = datetime.now(timezone.utc)

            face_record = EmployeeFaceData(
                mobile_number=normalized,
                face_image_base64=face_base64,
                created_at=now,
                updated_at=now,
            )

            db.add(face_record)
            db.commit()

            sync_employee_photo(db, normalized, reference_bytes)

            return {
                "status_code": 201,
                "body": {
                    "registered": True,
                    "verified": True,
                    "status": session_status,
                    "confidence": confidence,
                    "message": (
                        "Face registered successfully."
                    ),
                },
            }

        # ---------------------------------------------------------
        # VERIFY MODE
        # ---------------------------------------------------------

        face_record = (
            db.query(EmployeeFaceData)
            .filter(
                EmployeeFaceData.mobile_number == normalized
            )
            .first()
        )

        if face_record is None:
            return {
                "status_code": 404,
                "body": {
                    "error": (
                        "No registered face found "
                        "for this employee."
                    )
                },
            }

        stored_image_bytes = base64.b64decode(
            face_record.face_image_base64
        )

        try:
            aws_response = rekognition.compare_faces(
                SourceImage={
                    "Bytes": stored_image_bytes
                },
                TargetImage={
                    "Bytes": reference_bytes
                },
                SimilarityThreshold=80,
            )

        except ClientError as e:
            return {
                "status_code": 400,
                "body": {
                    "error": e.response["Error"]["Message"]
                },
            }

        matches = aws_response.get("FaceMatches", [])

        if matches:
            similarity = matches[0]["Similarity"]

            return {
                "status_code": 200,
                "body": {
                    "verified": True,
                    "status": session_status,
                    "liveness_confidence": confidence,
                    "similarity": similarity,
                    "message": (
                        "Liveness and face verification "
                        "successful."
                    ),
                },
            }

        return {
            "status_code": 400,
            "body": {
                "verified": False,
                "status": session_status,
                "liveness_confidence": confidence,
                "similarity": 0,
                "message": (
                    "Face does not match "
                    "the registered employee."
                ),
            },
        }

    except ClientError as e:
        return {
            "status_code": 400,
            "body": {
                "error": e.response["Error"]["Message"]
            },
        }

    except Exception as e:
        logger.exception("Liveness result error")

        return {
            "status_code": 500,
            "body": {
                "error": str(e)
            },
        }

# ---------------------------------------------------------
# HELPERS SHARED BY FACE REGISTRATION
# ---------------------------------------------------------

def find_duplicate_face(
    db: Session,
    normalized: str,
    image_bytes: bytes,
) -> bool:
    """True if this face already matches another employee's face."""
    other_faces = (
        db.query(EmployeeFaceData)
        .filter(EmployeeFaceData.mobile_number != normalized)
        .all()
    )

    for other in other_faces:
        try:
            comparison = rekognition.compare_faces(
                SourceImage={"Bytes": base64.b64decode(other.face_image_base64)},
                TargetImage={"Bytes": image_bytes},
                SimilarityThreshold=90,
            )
            if comparison.get("FaceMatches"):
                return True
        except Exception as e:
            logger.warning(
                "Duplicate-face check failed for %s: %s",
                other.mobile_number,
                e,
            )

    return False


def sync_employee_photo(
    db: Session,
    normalized: str,
    image_bytes: bytes,
) -> None:
    """Keep the employee profile photo in sync with the registered face."""
    from app.models.employee import Employee
    from app.models.user import User

    try:
        employee = (
            db.query(Employee)
            .join(User, User.org_id == Employee.user_id)
            .filter(User.mobile_number == normalized)
            .first()
        )
        if employee is None:
            return

        # Same location and naming Django's ImageField used.
        relative_path = f"employee_photos/face_{normalized}.jpg"
        target = settings.media_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(image_bytes)

        employee.photo = relative_path
        db.commit()

    except Exception as e:
        db.rollback()
        logger.warning(
            "Failed to sync face photo to employee profile for %s: %s",
            normalized,
            e,
        )


# ---------------------------------------------------------
# CHECK FACE REGISTRATION STATUS
# ---------------------------------------------------------

def check_face_status(
    db: Session,
    mobile_number: str,
) -> dict:
    from app.models.user import User

    normalized = normalize_mobile(mobile_number)

    if not db.query(User).filter(User.mobile_number == normalized).first():
        return {
            "status_code": 404,
            "body": {"error": "User not found in records", "exists": False},
        }

    face_exists = (
        db.query(EmployeeFaceData)
        .filter(EmployeeFaceData.mobile_number == normalized)
        .first()
        is not None
    )

    return {
        "status_code": 200,
        "body": {
            "mobile_number": normalized,
            "is_face_registered": face_exists,
            "exists": True,
        },
    }


# ---------------------------------------------------------
# REGISTER FACE (DIRECT IMAGE UPLOAD)
# ---------------------------------------------------------

def register_face_image(
    db: Session,
    mobile_number: str,
    face_image_base64: str,
) -> dict:
    from app.models.user import User

    normalized = normalize_mobile(mobile_number)

    if not db.query(User).filter(User.mobile_number == normalized).first():
        return {"status_code": 404, "body": {"error": "Employee not found."}}

    try:
        image_bytes = base64.b64decode(face_image_base64, validate=True)
    except Exception:
        return {"status_code": 400, "body": {"error": "Invalid image data"}}

    if find_duplicate_face(db, normalized, image_bytes):
        return {
            "status_code": 400,
            "body": {
                "error": "This face is already registered to another employee account.",
                "code": "DUPLICATE_FACE",
            },
        }

    now = datetime.now(timezone.utc)
    face_record = (
        db.query(EmployeeFaceData)
        .filter(EmployeeFaceData.mobile_number == normalized)
        .first()
    )

    # Django's serializer created or replaced the record.
    if face_record is None:
        face_record = EmployeeFaceData(
            mobile_number=normalized,
            face_image_base64=face_image_base64,
            created_at=now,
            updated_at=now,
        )
        db.add(face_record)
    else:
        face_record.face_image_base64 = face_image_base64
        face_record.updated_at = now

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    sync_employee_photo(db, normalized, image_bytes)

    return {
        "status_code": 201,
        "body": {"message": "Face data registered successfully"},
    }


# ---------------------------------------------------------
# FACE DETAILS
# ---------------------------------------------------------

def get_face_details(
    db: Session,
    mobile_number: str,
) -> EmployeeFaceData | None:
    return (
        db.query(EmployeeFaceData)
        .filter(EmployeeFaceData.mobile_number == normalize_mobile(mobile_number))
        .first()
    )
