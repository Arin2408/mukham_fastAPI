from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Project root:
# C:\Users\Vikrant Malik\mukham-new\mukham_fastAPI
BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    # Django-compatible database variables
    postgres_db: str = "mukham"
    postgres_user: str = "postgres"
    postgres_password: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Application
    secret_key: str

    # DEBUG=True (as in Django's .env) enables the /debug/* routes.
    debug: bool = False

    # AWS
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_default_region: str = "ap-south-1"

    # CORS
    cors_allowed_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000"
    )

    # Geofencing
    geofence_max_accuracy_meters: int = 100

    # Email (same Resend SMTP account Django uses)
    email_host: str = "smtp.resend.com"
    email_port: int = 587
    email_host_user: str = "resend"
    email_host_password: str | None = None
    default_from_email: str = "onboarding@resend.dev"

    # Frontend base URL used in password-reset links
    frontend_url: str = "http://localhost:3000"
    password_reset_token_minutes: int = 30

    # Uploaded files (shared with Django's MEDIA_ROOT)
    media_root: Path = BASE_DIR / "media"

    # Logging
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()