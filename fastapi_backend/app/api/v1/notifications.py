from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services.notification_service import (
    get_preferences,
    register_device,
    set_preferences,
    unregister_device,
)


router = APIRouter()


class DeviceRequest(BaseModel):
    # An Expo push token, e.g. "ExponentPushToken[xxxx]"
    token: str = Field(min_length=10, max_length=255, pattern=r"^Expo(nent)?PushToken\[.+\]$")
    platform: Literal["android", "ios"] = "android"


class DeviceRemoveRequest(BaseModel):
    token: str = Field(min_length=10, max_length=255)


class Preferences(BaseModel):
    shift_start: bool | None = None
    check_out: bool | None = None
    new_task: bool | None = None


# POST /api/v1/devices: after sign-in, the phone registers its push token.
@router.post("/devices", status_code=status.HTTP_204_NO_CONTENT)
def add_device(
    data: DeviceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    register_device(db, current_user.org_id, data.token, data.platform)


# POST /api/v1/devices/remove: at sign-out, before the session ends.
@router.post("/devices/remove", status_code=status.HTTP_204_NO_CONTENT)
def remove_device(
    data: DeviceRemoveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    unregister_device(db, current_user.org_id, data.token)


# GET/PUT /api/v1/notifications/preferences: the on/off switches in Profile.
@router.get("/notifications/preferences", response_model=Preferences)
def read_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_preferences(db, current_user.org_id)


@router.put("/notifications/preferences", response_model=Preferences)
def update_preferences(
    data: Preferences,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return set_preferences(db, current_user.org_id, data.model_dump())
