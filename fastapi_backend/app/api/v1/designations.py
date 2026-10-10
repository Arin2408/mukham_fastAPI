from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.department import Department
from app.models.designation import Designation
from app.models.user import User
from app.schemas.designation import (
    DesignationCreateRequest,
    DesignationResponse,
    DesignationUpdateRequest,
)
from app.services.designation_service import (
    create_designation,
    delete_designation,
    get_designations,
    update_designation,
)

router = APIRouter()


@router.get(
    "/designations",
    response_model=list[DesignationResponse],
)
def list_designations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_designations(
        db=db,
        org_id=current_user.org_id,
    )


@router.post(
    "/designations/add",
    response_model=DesignationResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_designation(
    data: DesignationCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    department = (
        db.query(Department)
        .filter(
            Department.department_id == data.department,
            Department.org_id == current_user.org_id,
        )
        .first()
    )

    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found or not accessible",
        )

    return create_designation(
        db=db,
        department=department,
        details=data.details,
    )


@router.put(
    "/designations/update/{designation_id}",
    response_model=DesignationResponse,
)
def update_designation_route(
    designation_id: int,
    data: DesignationUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    designation = (
        db.query(Designation)
        .join(
            Department,
            Designation.department_id == Department.department_id,
        )
        .filter(
            Designation.designation_id == designation_id,
            Department.org_id == current_user.org_id,
        )
        .first()
    )

    if designation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Designation not found or not accessible",
        )

    department = None

    if data.department is not None:
        department = (
            db.query(Department)
            .filter(
                Department.department_id == data.department,
                Department.org_id == current_user.org_id,
            )
            .first()
        )

        if department is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found or not accessible",
            )

    return update_designation(
        db=db,
        designation=designation,
        department=department,
        details=data.details,
    )


@router.delete(
    "/designations/delete/{designation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_designation_route(
    designation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    designation = (
        db.query(Designation)
        .join(
            Department,
            Designation.department_id == Department.department_id,
        )
        .filter(
            Designation.designation_id == designation_id,
            Department.org_id == current_user.org_id,
        )
        .first()
    )

    if designation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Designation not found or not accessible",
        )

    delete_designation(
        db=db,
        designation=designation,
    )

    return None