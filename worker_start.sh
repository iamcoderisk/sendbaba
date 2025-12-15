#!/bin/bash
cd /opt/sendbaba
source venv/bin/activate
source .env

WORKER_IP=$(hostname -I | awk '{print $1}')

exec celery -A celery_worker_config worker \
    --loglevel=info \
    --concurrency=${CELERY_CONCURRENCY:-25} \
    --hostname=worker@${WORKER_IP} \
    -Q email_queue,celery,default \
    --max-tasks-per-child=1000 \
    --prefetch-multiplier=4
