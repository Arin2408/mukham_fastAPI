from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.errors import error_response, register_error_handlers
from app.services.storage import media_store, uses_database, uses_s3

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
    # The API's map is for developers, not for the public internet.
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
)

# Bigger than any real request (a face photo is a few MB as base64).
MAX_BODY_BYTES = 12 * 1024 * 1024

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Cross-Origin-Resource-Policy": "cross-origin",
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        response = error_response(413, {"detail": "Request is too large."})
    else:
        response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response

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

# Uploaded employee photos at /media/..., from the database or local disk.
# With MEDIA_S3_BUCKET set, photos get signed S3 URLs instead.
if uses_database():
    @app.get("/media/{key:path}", include_in_schema=False)
    def media_file(key: str):
        stored = media_store.read_with_type(key)
        if stored is None:
            raise HTTPException(status_code=404, detail="Not found")
        data, content_type = stored
        # Every photo gets a new random name, so a name never changes content.
        return Response(
            content=data,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )
elif not uses_s3():
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


def _from_this_computer(request: Request) -> None:
    if not request.client or request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(status_code=404, detail="Not Found")


# Unauthenticated data dumps - never expose outside local development, and
# even with DEBUG on, only to requests from this computer.
if settings.debug:
    app.include_router(
        debug_router,
        prefix="/api/v1",
        tags=["Debug"],
        dependencies=[Depends(_from_this_computer)],
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
