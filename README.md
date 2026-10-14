# Mukham backend

FastAPI backend for Mukham, a workforce and attendance system that checks
attendance with GPS (inside the office's radius) and a live face check
(AWS Rekognition Face Liveness). It serves the web app (`../mukham_frontend`)
and the mobile app (`../mukham_mobile`).

The app lives in `fastapi_backend/` and serves the API on port 8002, on
PostgreSQL. Alembic owns the whole database schema.

## Requirements

- Python 3.11 or newer
- PostgreSQL 16

## Setup

1. Create and activate a virtual environment, then install dependencies:

   ```
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Create `.env` in this folder from the example, then fill it in:

   ```
   cp .env.example .env
   ```

   | Variable | Example | Notes |
   | --- | --- | --- |
   | `SECRET_KEY` | long random string | Signs JWTs and password-reset tokens |
   | `DEBUG` | `False` | `True` also enables the `/api/v1/debug/*` routes |
   | `POSTGRES_DB` | `mukham_db` | |
   | `POSTGRES_USER` | `postgres` | |
   | `POSTGRES_PASSWORD` | | |
   | `POSTGRES_HOST` | `localhost` | |
   | `POSTGRES_PORT` | `5432` | |
   | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | | Rekognition (face match, liveness) and S3 |
   | `AWS_DEFAULT_REGION` | `ap-south-1` | |
   | `AWS_IDENTITY_POOL_ID` | | Cognito identity pool; gives the mobile app short-lived credentials for its face check |
   | `MEDIA_S3_BUCKET` | | Optional. Private S3 bucket for photos and face images; unset = local folders |
   | `CORS_ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:8081` | Comma-separated: the web app, and the mobile dev server's web preview |
   | `FRONTEND_URL` | `http://localhost:3000` | Links in password-reset emails |
   | `EMAIL_HOST_PASSWORD` | | Resend API key (SMTP), for password-reset emails |
   | `DEFAULT_FROM_EMAIL` | `Mukham <no-reply@yourdomain.com>` | Sender of reset emails. Resend's test sender `onboarding@resend.dev` (the default) only delivers to the Resend account's own email; verify your domain in Resend to send to anyone |
   | `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | How long a signed-in device may stay idle |
   | `MIN_APP_VERSION` | `1.0.0` | Mobile app versions below this must update (`GET /app/config`) |
   | `GEOCODING_ENABLED` | `True` | Address search for office locations (`GET /geocode/search`). Set `False` to switch it off without an app update |
   | `GEOCODING_USER_AGENT` | `Mukham/1.0 (you@example.com)` | Sent to OpenStreetMap's Nominatim, whose policy requires the app's name and a contact |
   | `EXPO_ACCESS_TOKEN` | | Expo access token for sending push notifications (expo.dev › Access tokens). Required once enhanced push security is on |
   | `NOTIFICATIONS_ENABLED` | `True` | `False` stops all push notifications |
   | `SHIFT_REMINDER_MINUTES`, `CHECKOUT_REMINDER_MINUTES` | `15`, `60` | When "Your shift starts soon" and "You're still checked in" are sent |

3. Create the database user and database. With Homebrew PostgreSQL the
   default superuser is your macOS user, so `postgres` may not exist yet:

   ```
   psql -d postgres -c "CREATE ROLE postgres WITH LOGIN SUPERUSER PASSWORD '<POSTGRES_PASSWORD>'"
   createdb -O postgres mukham_db
   ```

4. Create the tables:

   ```
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

## Main routes

All under `/api/v1`; the full list is at `/docs`.

| Area | Routes |
| --- | --- |
| Sign-in | `POST /org/login` (admin), `POST /member/login` then `/member/login/complete` (employee, after the face check), `POST /auth/refresh`, `POST /auth/logout`, `POST /org/signup`, `/forgot-password` and `/reset-password` |
| Face check | `POST /face/liveness/create`, `POST /face/liveness/credentials` (mobile), `POST /face/liveness/result`, `POST /face/register` |
| Attendance | `POST /attendance/mark` (employee: GPS and face token), `GET /attendance/history`, `GET /attendance/list` and `POST /attendance/manual` (admin) |
| Admin | `GET /dashboard/summary`, `GET /geocode/search` (address search, at most one request per second to OpenStreetMap for all users), employees, departments (with `/departments/leaderboard`), designations, shifts, locations, tasks |
| Employee | `GET /employee-details`, `GET /tasks`, `PATCH /tasks/{id}/status` |
| Public | `GET /app/config` (minimum mobile app version), `GET /employees/{id}/card` (ID card page), `GET /health/db` |

## Push notifications

The mobile app registers each signed-in phone (`POST /devices`) and removes
it at sign-out (`POST /devices/remove`). People switch kinds on and off with
`GET`/`PUT /notifications/preferences`. "New task" is sent when a task is
created. Shift reminders come from a job that must run every 5 minutes; each
reminder is sent once however often it runs:

```
cd fastapi_backend
python -m scripts.send_notifications              # once (cron: */5 * * * *)
python -m scripts.send_notifications --every 300  # keep running (development)
```

## API conventions

**Versioning.** Every route lives under `/api/v1`. Changes to `/api/v1` are
additive only: new routes, new optional request fields, new response
fields. Anything that would break an existing client (renaming or removing
a field, changing a type or a status code) goes to `/api/v2` instead.

**Errors.** Every 4xx and 5xx response has two top-level fields:

```
{"code": "outside_geofence", "message": "You are outside the permitted attendance location.", "detail": {...}}
```

`code` is stable and meant for app logic; `message` is safe to show to the
user. Older fields (`detail`, and `error` on face routes) are kept for the
web app. Codes:

| Code | Status | When |
| --- | --- | --- |
| `bad_request` | 400 | Generic invalid request |
| `unauthorized` | 401 | Missing, invalid or expired token; wrong password |
| `forbidden` | 403 | Signed in, but not allowed |
| `not_found` | 404 | Record does not exist |
| `conflict` | 409 | E.g. a liveness session already used |
| `validation_error` | 422 | Request body or query failed validation; `detail` lists each field |
| `internal_error` | 500 | Unexpected server error; details are logged, never returned |
| `face_verification_required` | 428 | `/attendance/mark` check-in without a valid `face_token` |
| `outside_geofence` | 403 | Check-in too far from the office; `detail` has `distance_meters`, `allowed_radius_meters`, `office_location` |
| `no_open_attendance` | 404 | Check-out with no open check-in |
| `invalid_location` | 400 | Invalid GPS data or attendance action, or the organisation has no office location |
| `duplicate_face` | 400 | Face already enrolled for another employee |

**Sessions.** Each sign-in (`/org/login`, `/member/login/complete`,
`/auth/login`) starts a session for that device; send an optional
`device_name` to label it. The access token lasts 60 minutes. The refresh
token lasts `REFRESH_TOKEN_EXPIRE_DAYS` and works once:
`POST /auth/refresh` returns a new access and refresh token. Presenting an
already-used refresh token signs that device out (a copied token is
assumed), so a client must not refresh twice in parallel.
`POST /auth/logout` with `{"refresh": ...}` signs the device out.

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
docker run --rm --env-file .env mukham-api alembic upgrade head
docker run --env-file .env -p 8002:8002 mukham-api
```

Use S3 storage (`MEDIA_S3_BUCKET`) in containers; local `media/` and
`private_media/` are not copied into the image.

## Database changes

Every schema change is a hand-written Alembic migration in
`fastapi_backend/migrations/versions/`. `0000_baseline` creates the core
tables; their names (`organisation_customuser`, `employees_customuser`, …)
and constraint names come from the project's Django days and are kept as-is.
Do not use `--autogenerate`: it would try to rename them to match the models.

A database created before Django was removed upgrades in place:
`alembic upgrade head` drops the Django-only tables (`0003_drop_django_tables`).

## Sibling repositories

| Folder | What it is |
| --- | --- |
| `mukham_fastAPI` | This backend |
| `mukham_frontend` | Web app (Next.js) |
| `mukham_mobile` | Mobile app (Expo, React Native) |
