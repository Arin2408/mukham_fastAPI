from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.employee import Employee
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


@router.post(
    "/face/verify",
    response_model=FaceVerifyResponse,
)
def verify_face_endpoint(
    request: FaceVerifyRequest,
    db: Session = Depends(get_db),
):
    result = verify_face(
        db=db,
        mobile_number=request.mobile_number,
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

@router.post(
    "/face/liveness/create",
    response_model=LivenessCreateResponse,
)
def create_liveness_session_endpoint():

    result = create_liveness_session()

    return JSONResponse(
        status_code=result["status_code"],
        content=result["body"],
    )

@router.post(
    "/face/liveness/result",
)
def get_liveness_result_endpoint(
    request: LivenessResultRequest,
    db: Session = Depends(get_db),
):

    result = get_liveness_result(
        db=db,
        session_id=request.session_id,
        mobile_number=request.mobile_number,
        mode=request.mode,
    )

    return JSONResponse(
        status_code=result["status_code"],
        content=result["body"],
    )

def _require_face_access(
    db: Session,
    current_user: User,
    mobile_number: str,
) -> None:
    """Allow the employee themselves, or the organisation they belong to."""
    normalized = normalize_mobile(mobile_number)

    if not current_user.is_organization:
        if normalize_mobile(current_user.mobile_number) != normalized:
            raise HTTPException(status_code=403, detail="Not allowed")
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
        raise HTTPException(status_code=404, detail="Employee not found")


# POST /api/v1/face/check-status   (Django: /api/face/check-status/)
# Public: the member login screen calls it before a token exists.
@router.post("/face/check-status")
def face_check_status_endpoint(
    request: FaceStatusRequest,
    db: Session = Depends(get_db),
):
    result = check_face_status(db=db, mobile_number=request.mobile_number)
    return JSONResponse(status_code=result["status_code"], content=result["body"])


# POST /api/v1/face/register   (Django: /api/face/register/)
@router.post("/face/register")
def face_register_endpoint(
    request: FaceRegisterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_face_access(db, current_user, request.mobile_number)

    result = register_face_image(
        db=db,
        mobile_number=request.mobile_number,
        face_image_base64=request.face_image_base64,
    )
    return JSONResponse(status_code=result["status_code"], content=result["body"])


# GET /api/v1/face/details/{mobile_number}   (Django: /api/face/details/<m>/)
@router.get(
    "/face/details/{mobile_number}",
    response_model=FaceDetailsResponse,
)
def face_details_endpoint(
    mobile_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_face_access(db, current_user, mobile_number)

    face_data = get_face_details(db=db, mobile_number=mobile_number)
    if face_data is None:
        raise HTTPException(status_code=404, detail="Face data not found")

    return face_data
