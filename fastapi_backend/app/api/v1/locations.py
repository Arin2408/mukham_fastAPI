from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_organisation
from app.models.user import User
from app.schemas.location import (
    LocationCreateRequest,
    LocationResponse,
    LocationUpdateRequest,
)
from app.services.location_service import (
    create_location,
    delete_location,
    get_location,
    get_locations,
    update_location,
)

router = APIRouter()


@router.get(
    "/locations",
    response_model=list[LocationResponse],
)
def list_locations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_organisation),
):
    return get_locations(
        db=db,
        org_id=current_user.org_id,
    )


@router.post(
    "/locations",
    response_model=LocationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_location_endpoint(
    data: LocationCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_organisation),
):
    return create_location(
        db=db,
        org_id=current_user.org_id,
        location_name=data.location_name,
        latitude=data.latitude,
        longitude=data.longitude,
        radius_meters=data.radius_meters,
    )


@router.get(
    "/locations/{location_id}",
    response_model=LocationResponse,
)
def get_location_endpoint(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_organisation),
):
    location = get_location(
        db=db,
        location_id=location_id,
        org_id=current_user.org_id,
    )

    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found or not accessible",
        )

    return location


@router.put(
    "/locations/{location_id}",
    response_model=LocationResponse,
)
def update_location_endpoint(
    location_id: int,
    data: LocationUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_organisation),
):
    location = get_location(
        db=db,
        location_id=location_id,
        org_id=current_user.org_id,
    )

    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found or not accessible",
        )

    return update_location(
        db=db,
        location=location,
        location_name=data.location_name,
        latitude=data.latitude,
        longitude=data.longitude,
        radius_meters=data.radius_meters,
    )


@router.delete(
    "/locations/{location_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_location_endpoint(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_organisation),
):
    location = get_location(
        db=db,
        location_id=location_id,
        org_id=current_user.org_id,
    )

    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found or not accessible",
        )

    delete_location(db, location)

    return None