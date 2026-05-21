#!/bin/sh
set -e
echo "Running database migrations..."
python -m alembic upgrade head
echo "Starting Celery worker+beat in background..."
python -m celery -A workers.celery_app worker --beat --loglevel=info -c 1 &
echo "Starting server on port ${PORT:-8000}..."
exec python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
