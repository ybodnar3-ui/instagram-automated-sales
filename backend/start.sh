#!/bin/sh
set -e
echo "Running database migrations..."
alembic upgrade head
echo "Starting Celery worker+beat in background..."
celery -A workers.celery_app worker --beat --loglevel=info -c 1 &
echo "Starting server on port ${PORT:-8000}..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
