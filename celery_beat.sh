#!/bin/bash
# Start Celery beat scheduler

cd /opt/sendbaba-staging
source venv/bin/activate

celery -A app.celery_config beat \
    --loglevel=info \
    --pidfile=/var/run/celery/beat.pid \
    --logfile=/var/log/celery/beat.log
