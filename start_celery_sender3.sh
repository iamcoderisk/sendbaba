#!/bin/bash
cd /opt/sendbaba-staging
source venv/bin/activate
exec celery -A celery_app worker --loglevel=warning --queues=default,high --concurrency=4 --hostname=sender3@%h -O fair
