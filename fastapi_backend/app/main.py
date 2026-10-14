from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.errors import register_error_handlers
from app.services.storage import uses_s3

from app.api.v1.health import router as health_router
from app.api.v1.app_config import router as app_config_router
from app.api.v1.debug import router as debug_router
from app.api.v1.auth import router as auth_router
from app.api.v1.accounts import router as accounts_router
from app.api.v1.departments import router as departments_router
from app.api.v1.designations import router as designations_router
from app.api.v1.shifts import router as shifts_router
from app.api.v1.locations import router as locations_router
from app.api.v1.employees import router as employees_router
from app.api.v1.profile import router as profile_router
from app.api.v1.attendance import router as attendance_router
from app.api.v1.geofence import router as geofence_router
from app.api.v1.face import router as face_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.geocode import router as geocode_router
from app.api.v1.notifications import router as notifications_router


app = FastAPI(
    title="Mukham API",
    version="1.0.0",
)

# Every error response carries `code` and `message` (app/core/errors.py).
register_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    # Comma-separated CORS_ALLOWED_ORIGINS from .env
    allow_origins=[
        origin.strip()
        for origin in settings.cors_allowed_origins.split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Uploaded employee photos at /media/... (local storage only).
# With MEDIA_S3_BUCKET set, photos get signed S3 URLs instead.
if not uses_s3():
    settings.media_root.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/media",
        StaticFiles(directory=settings.media_root),
        name="media",
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "fastapi",
    }


app.include_router(
    health_router,
    prefix="/api/v1",
    tags=["Health"],
)

app.include_router(
    app_config_router,
    prefix="/api/v1",
    tags=["App"],
)

app.include_router(
    shifts_router,
    prefix="/api/v1",
    tags=["Shifts"],
)

app.include_router(
    locations_router,
    prefix="/api/v1",
    tags=["Locations"],
)

app.include_router(
    employees_router,
    prefix="/api/v1",
    tags=["employees"],
)

app.include_router(
    profile_router,
    prefix="/api/v1",
    tags=["profile"],
)

app.include_router(
    designations_router,
    prefix="/api/v1",
    tags=["Designations"],
)

app.include_router(
    departments_router,
    prefix="/api/v1",
    tags=["Departments"],
)

app.include_router(
    attendance_router,
    prefix="/api/v1",
    tags=["Attendance"],
)

app.include_router(
    geofence_router,
    prefix="/api/v1",
    tags=["Geofence"],
)

app.include_router(
    face_router,
    prefix="/api/v1",
    tags=["Face"],
)

app.include_router(
    tasks_router,
    prefix="/api/v1",
    tags=["Tasks"],
)

app.include_router(
    dashboard_router,
    prefix="/api/v1",
    tags=["Dashboard"],
)

app.include_router(
    geocode_router,
    prefix="/api/v1",
    tags=["Geocoding"],
)

app.include_router(
    notifications_router,
    prefix="/api/v1",
    tags=["Notifications"],
)


# Unauthenticated data dumps - never expose outside local development.
if settings.debug:
    app.include_router(
        debug_router,
        prefix="/api/v1",
        tags=["Debug"],
    )


app.include_router(
    auth_router,
    prefix="/api/v1",
    tags=["Authentication"],
)

app.include_router(
    accounts_router,
    prefix="/api/v1",
    tags=["Accounts"],
)
