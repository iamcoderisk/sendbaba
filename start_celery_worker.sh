#!/bin/bash
cd /opt/sendbaba-staging
source venv/bin/activate
exec celery -A celery_app.celery_app worker \
    --loglevel=info \
    --concurrency=20 \
    -Q high_priority,celery,bulk,retry \
    --max-tasks-per-child=1000
