# Mukham backend

FastAPI backend for Mukham, on PostgreSQL. The Django project in this repo
creates the base database tables; the API itself is served by FastAPI
(`fastapi_backend/`) on port 8002.

## Requirements

- Python 3.11 or newer
- PostgreSQL 16

## Setup

1. Create and activate a virtual environment, then install both
   dependency files (Django is needed for the base migrations):

   ```
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt -r requirements-fastapi.txt
   ```

2. Create `.env` in this folder:

   | Variable | Example | Notes |
   | --- | --- | --- |
   | `SECRET_KEY` | long random string | Signs JWTs; shared by Django and FastAPI |
   | `DEBUG` | `False` | `True` also enables the `/api/v1/debug/*` routes |
   | `POSTGRES_DB` | `mukham_db` | |
   | `POSTGRES_USER` | `postgres` | |
   | `POSTGRES_PASSWORD` | | |
   | `POSTGRES_HOST` | `localhost` | |
   | `POSTGRES_PORT` | `5432` | |
   | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | | Rekognition (face match, liveness) and S3 |
   | `AWS_DEFAULT_REGION` | `ap-south-1` | |
   | `MEDIA_S3_BUCKET` | | Optional. Private S3 bucket for photos and face images; unset = local folders |
   | `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated |
   | `EMAIL_HOST_PASSWORD` | | Resend SMTP, for password-reset emails |

3. Create the database user and database. With Homebrew PostgreSQL the
   default superuser is your macOS user, so `postgres` may not exist yet:

   ```
   psql -d postgres -c "CREATE ROLE postgres WITH LOGIN SUPERUSER PASSWORD '<POSTGRES_PASSWORD>'"
   createdb -O postgres mukham_db
   ```

4. Create the tables. Django migrations first, then Alembic:

   ```
   python manage.py migrate
   cd fastapi_backend
   alembic upgrade head
   ```

5. Start the API:

   ```
   cd fastapi_backend
   python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8002
   ```

   API docs: http://127.0.0.1:8002/docs. Database check:
   http://127.0.0.1:8002/api/v1/health/db

## File storage

Employee photos and enrolled face images are never stored in the database.

| | Local (no `MEDIA_S3_BUCKET`) | S3 (`MEDIA_S3_BUCKET` set) |
| --- | --- | --- |
| Employee photos | `media/`, served at `/media/...` | `s3://<bucket>/media/`, signed URLs valid 1 hour |
| Face images | `private_media/`, never served | `s3://<bucket>/faces/`, never served |

The bucket must block all public access. Objects are written with
server-side encryption. The AWS user in `.env` needs `s3:PutObject`,
`s3:GetObject` and `s3:DeleteObject` on `arn:aws:s3:::<bucket>/*`, in
addition to its Rekognition permissions.

After switching to S3, or to move face images left in the database by an
older version, run (from `fastapi_backend/`):

```
python -m scripts.move_files_to_storage --dry-run
python -m scripts.move_files_to_storage
```

## Docker

The image runs the FastAPI server on port 8002. Run migrations before
starting a new version:

```
docker build -t mukham-api .
docker run --rm --env-file .env mukham-api sh -c "python manage.py migrate && cd fastapi_backend && alembic upgrade head"
docker run --env-file .env -p 8002:8002 mukham-api
```

Use S3 storage (`MEDIA_S3_BUCKET`) in containers; local `media/` and
`private_media/` are not copied into the image.

## Database changes

Base tables come from the Django apps' migrations. Newer tables (tasks,
security tracking) are Alembic migrations in `fastapi_backend/migrations/`.
A change to a table a Django app defines goes in that app's migrations;
everything else goes in Alembic.
