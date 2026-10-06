# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Gunicorn settings (override at runtime if needed)
# Rule of thumb for workers: 2 x CPU cores + 1
ENV GUNICORN_WORKERS 4
ENV GUNICORN_THREADS 4
ENV GUNICORN_TIMEOUT 60

# Set work directory
WORKDIR /app

# Install dependencies (psycopg2-binary ships its own libpq, no build tools needed)
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /app/

# Expose port
EXPOSE 8001

# Start the production server (multi-process, threaded workers)
CMD gunicorn mukham.wsgi:application \
    --bind 0.0.0.0:8001 \
    --workers ${GUNICORN_WORKERS} \
    --worker-class gthread \
    --threads ${GUNICORN_THREADS} \
    --timeout ${GUNICORN_TIMEOUT} \
    --access-logfile -