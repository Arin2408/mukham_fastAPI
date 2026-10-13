
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.errors import error_response
from app.db.session import get_db
from app.dependencies.auth import (
    get_current_member_pre_auth,
    get_current_user,
)
from app.models.employee import Employee
from app.models.security_tracking import LivenessSession
from app.models.user import User
from app.schemas.face import (
    FaceDetailsResponse,
    FaceRegisterRequest,
    FaceStatusRequest,
    FaceVerifyRequest,
    FaceVerifyResponse,
    LivenessCreateResponse,
    LivenessResultRequest,
)
from app.services.face_service import (
    check_face_status,
    create_liveness_session,
    get_face_details,
    get_liveness_result,
    normalize_mobile,
    register_face_image,
    verify_face,
)

router = APIRouter()


def _service_response(status_code: int, body: dict) -> JSONResponse:
    """Return a face-service result; errors get the shared `code`/`message`."""
    if status_code >= 400:
        return error_response(status_code, body)
    return JSONResponse(status_code=status_code, content=body)


def _require_employee(current_user: User) -> None:
    """Allow employee-only face operations."""
    if current_user.is_organization:
        raise HTTPException(
            status_code=403,
            detail="Employee account required",
        )


def _require_face_access(
    db: Session,
    current_user: User,
    mobile_number: str,
) -> None:
    """Allow an employee to access their own face data,
    or an organisation to access its own employee's data.
    """
    normalized = normalize_mobile(mobile_number)

    if not current_user.is_organization:
        if normalize_mobile(current_user.mobile_number) != normalized:
            raise HTTPException(
                status_code=403,
                detail="Not allowed",
            )
        return

    employee = (
        db.query(Employee)
        .join(User, User.org_id == Employee.user_id)
        .filter(
            User.mobile_number == normalized,
            Employee.organisation_id == current_user.org_id,
        )
        .first()
    )

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found",
        )


# POST /api/v1/face/verify
@router.post(
    "/face/verify",
    response_model=FaceVerifyResponse,
)
def verify_face_endpoint(
    request: FaceVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_employee(current_user)

    result = verify_face(
        db=db,
        mobile_number=current_user.mobile_number,
        captured_image_base64=request.face_image_base64,
    )

    status_code = result["status_code"]
    body = result["body"]

    if status_code != 200:
        raise HTTPException(
            status_code=status_code,
            detail=body,
        )

    return body


# POST /api/v1/face/liveness/create
@router.post(
    "/face/liveness/create",
    response_model=LivenessCreateResponse,
)
def create_liveness_session_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_member_pre_auth),
):
    _require_employee(current_user)

    result = create_liveness_session()

    if result["status_code"] != 200:
        return _service_response(result["status_code"], result["body"])

    session_id = result["body"]["session_id"]

    try:
        db.add(
            LivenessSession(
                session_id=session_id,
                mobile_number=normalize_mobile(
                    current_user.mobile_number
                ),
                created_at=datetime.now(timezone.utc),
                consumed_at=None,
            )
        )
        db.commit()

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not create liveness session",
        )

    return JSONResponse(
        status_code=200,
        content=result["body"],
    )


# POST /api/v1/face/liveness/result
@router.post("/face/liveness/result")
def get_liveness_result_endpoint(
    request: LivenessResultRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_member_pre_auth),
):
    _require_employee(current_user)

    normalized = normalize_mobile(current_user.mobile_number)

    # Lock and validate the session before consuming it.
    session_record = (
        db.query(LivenessSession)
        .filter(LivenessSession.session_id == request.session_id)
        .with_for_update()
        .first()
    )

    if (
        session_record is None
        or session_record.mobile_number != normalized
    ):
        db.rollback()
        raise HTTPException(
            status_code=404,
            detail="Liveness session not found",
        )

    if session_record.consumed_at is not None:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Liveness session has already been used",
        )

    # Consume the session before calling the service so it cannot
    # be replayed, including if the service commits its own changes.
    session_record.consumed_at = datetime.now(timezone.utc)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not process liveness session",
        )

    result = get_liveness_result(
        db=db,
        session_id=request.session_id,
        mobile_number=current_user.mobile_number,
        mode=request.mode,
    )

    status_code = result["status_code"]
    body = result["body"]

    # Only a positively verified result can authorize login completion.
    if status_code in (200, 201) and body.get("verified") is True:
        try:
            verified_session = (
                db.query(LivenessSession)
                .filter(
                    LivenessSession.session_id == request.session_id
                )
                .with_for_update()
                .first()
            )

            if (
                verified_session is None
                or verified_session.mobile_number != normalized
                or verified_session.consumed_at is None
            ):
                db.rollback()
                raise HTTPException(
                    status_code=409,
                    detail="Liveness session could not be verified",
                )

            verified_session.face_verified_at = datetime.now(timezone.utc)
            db.commit()

        except HTTPException:
            raise
        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail="Could not record face verification",
            )

    return _service_response(status_code, body)


# POST /api/v1/face/check-status
# Kept public for compatibility with the existing pre-login flow.
@router.post("/face/check-status")
def face_check_status_endpoint(
    request: FaceStatusRequest,
    db: Session = Depends(get_db),
):
    result = check_face_status(
        db=db,
        mobile_number=request.mobile_number,
    )

    return _service_response(result["status_code"], result["body"])


# POST /api/v1/face/register
@router.post("/face/register")
def face_register_endpoint(
    request: FaceRegisterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_face_access(
        db,
        current_user,
        request.mobile_number,
    )

    result = register_face_image(
        db=db,
        mobile_number=request.mobile_number,
        face_image_base64=request.face_image_base64,
    )

    return _service_response(result["status_code"], result["body"])


# GET /api/v1/face/details/{mobile_number}
@router.get(
    "/face/details/{mobile_number}",
    response_model=FaceDetailsResponse,
)
def face_details_endpoint(
    mobile_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_face_access(
        db,
        current_user,
        mobile_number,
    )

    face_data = get_face_details(
        db=db,
        mobile_number=mobile_number,
    )

    if face_data is None:
        raise HTTPException(
            status_code=404,
            detail="Face data not found",
        )

    # Never return the stored biometric image.
    return FaceDetailsResponse(
        mobile_number=face_data.mobile_number,
        created_at=face_data.created_at,
        updated_at=face_data.updated_at,
    )
