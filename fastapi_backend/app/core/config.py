from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Project root:
# C:\Users\Vikrant Malik\mukham-new\mukham_fastAPI
BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    # Database
    postgres_db: str = "mukham"
    postgres_user: str = "postgres"
    postgres_password: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Application
    secret_key: str

    # Refresh tokens rotate on every use; this is how long one signed-in
    # device can stay idle before it must sign in again.
    refresh_token_expire_days: int = 30

    # DEBUG=True enables the /debug/* routes (from this computer only) and
    # the API docs at /docs.
    debug: bool = False

    # Limits on repeated sign-in, sign-up, password-reset and face-check
    # requests (app/core/rate_limit.py). Turn off only for load tests.
    rate_limit_enabled: bool = True

    # AWS
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_default_region: str = "ap-south-1"
    # Cognito identity pool whose guest role may run face liveness checks
    # (the web app uses the same pool from the browser).
    aws_identity_pool_id: str | None = None
    # Lowest AWS liveness score (0-100) accepted as a live person. A photo
    # or screen held up to the camera finishes the check but scores low.
    liveness_min_confidence: float = 90
    # One phone per employee: check-in only from their registered phone,
    # a new phone needs the admin's approval. Off for now (on hold).
    phone_lock_enabled: bool = False

    # CORS
    cors_allowed_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000"
    )

    # Geofencing
    geofence_max_accuracy_meters: int = 100

    # Email (Resend SMTP)
    email_host: str = "smtp.resend.com"
    email_port: int = 587
    email_host_user: str = "resend"
    email_host_password: str | None = None
    default_from_email: str = "onboarding@resend.dev"

    # Frontend base URL used in password-reset links
    frontend_url: str = "http://localhost:3000"
    password_reset_token_minutes: int = 30

    # Mobile app: versions below this are told to update (GET /app/config)
    min_app_version: str = "1.0.0"

    # Address search for office locations (GET /geocode/search), through
    # OpenStreetMap's Nominatim. Switch it off here, with no app update,
    # if OpenStreetMap asks. Their policy wants a User-Agent naming the app,
    # with a contact address.
    geocoding_enabled: bool = True
    geocoding_url: str = "https://nominatim.openstreetmap.org/search"
    geocoding_user_agent: str = "Mukham/1.0"

    # Push notifications through Expo's push service. The access token
    # (expo.dev > Access tokens) stops anyone with a leaked push token from
    # messaging users as us; set it whenever enhanced push security is on.
    notifications_enabled: bool = True
    expo_access_token: str | None = None
    expo_push_url: str = "https://exp.host/--/api/v2/push/send"
    expo_receipts_url: str = "https://exp.host/--/api/v2/push/getReceipts"
    # "Your shift starts soon" this many minutes before shift start, and
    # "You're still checked in" this many minutes after shift end.
    shift_reminder_minutes: int = 15
    checkout_reminder_minutes: int = 60
    # No "Your shift starts soon" on these days: comma-separated, mon..sun
    # (empty for none). Shifts don't record their working days yet.
    reminder_days_off: str = "sat,sun"

    # Employee photos (local storage; served at /media)
    media_root: Path = BASE_DIR / "media"

    # Enrolled face images. Never mounted or served over HTTP.
    private_media_root: Path = BASE_DIR / "private_media"

    # Where photos and face images are kept when no S3 bucket is set:
    # "database" (the stored_files table; survives restarts on hosts whose
    # disk is wiped, such as Render's free plan) or "local" (the two
    # folders above).
    media_storage: str = "database"

    # When set, photos and face images go to this private S3 bucket
    # (under media/ and faces/) instead.
    media_s3_bucket: str | None = None
    media_url_expire_seconds: int = 3600

    # Logging
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()