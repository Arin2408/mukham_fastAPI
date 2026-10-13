# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Uvicorn workers (rule of thumb: 2 x CPU cores + 1)
ENV WEB_CONCURRENCY 4

# Set work directory
WORKDIR /app

# Install dependencies. Django (requirements.txt) is still needed for the
# base schema migrations; the API itself is FastAPI.
# (psycopg2-binary / psycopg[binary] ship their own libpq, no build tools needed)
COPY requirements.txt requirements-fastapi.txt /app/
RUN pip install --no-cache-dir -r requirements.txt -r requirements-fastapi.txt

# Copy project
COPY . /app/

# Expose port
EXPOSE 8002

# Database migrations are a separate step before starting a new version:
#   docker run --rm --env-file .env <image> sh -c \
#     "python manage.py migrate && cd fastapi_backend && alembic upgrade head"

# Start the FastAPI server
WORKDIR /app/fastapi_backend
CMD uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8002 \
    --workers ${WEB_CONCURRENCY} \
    --proxy-headers
