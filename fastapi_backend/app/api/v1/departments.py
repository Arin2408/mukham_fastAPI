from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_organisation
from app.models.department import Department
from app.models.user import User
from app.schemas.department import (
    DepartmentCreateRequest,
    DepartmentLeaderboardResponse,
    DepartmentResponse,
    DepartmentUpdateRequest,
)
from app.services.department_service import (
    create_department,
    delete_department,
    get_department_leaderboard,
    get_departments,
    update_department,
)

router = APIRouter()


@router.get(
    "/departments",
    response_model=list[DepartmentResponse],
)
def list_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_organisation),
):
    return get_departments(
        db=db,
        org_id=current_user.org_id,
    )


@router.post(
    "/departments/add",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_department(
    data: DepartmentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_organisation),
):
    return create_department(
        db=db,
        org_id=current_user.org_id,
        details=data.details,
        location_id=data.location,
    )


@router.put(
    "/departments/update/{department_id}",
    response_model=DepartmentResponse,
)
def update_department_route(
    department_id: int,
    data: DepartmentUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_organisation),
):
    department = (
        db.query(Department)
        .filter(
            Department.department_id == department_id,
            Department.org_id == current_user.org_id,
        )
        .first()
    )

    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found",
        )

    return update_department(
        db=db,
        department=department,
        details=data.details,
        location_id=data.location,
    )


@router.delete(
    "/departments/delete/{department_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_department_route(
    department_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_organisation),
):
    department = (
        db.query(Department)
        .filter(
            Department.department_id == department_id,
            Department.org_id == current_user.org_id,
        )
        .first()
    )

    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found",
        )

    delete_department(
        db=db,
        department=department,
    )

    return None


@router.get(
    "/departments/leaderboard",
    response_model=list[DepartmentLeaderboardResponse],
)
def department_leaderboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_organisation),
):
    return get_department_leaderboard(
        db=db,
        org_id=current_user.org_id,
    )