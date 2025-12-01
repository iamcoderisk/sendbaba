#!/bin/bash
# Start Celery worker

cd /opt/sendbaba-staging
source venv/bin/activate

# Start worker with all queues
celery -A app.celery_config worker \
    --loglevel=info \
    --concurrency=8 \
    --queues=high,default,low,bulk,retry \
    --hostname=worker@%h \
    --pidfile=/var/run/celery/worker.pid \
    --logfile=/var/log/celery/worker.log
