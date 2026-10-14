from fastapi import APIRouter

from app.core.config import settings


router = APIRouter()


# GET /api/v1/app/config
# Public: the mobile app calls it at start-up, before anyone signs in.
@router.get("/app/config")
def app_config():
    return {
        # The app shows "Update required" when its version is lower.
        "min_app_version": settings.min_app_version,
    }
