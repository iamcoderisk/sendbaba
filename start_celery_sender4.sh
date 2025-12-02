#!/bin/bash
cd /opt/sendbaba-staging
source venv/bin/activate
exec celery -A celery_app worker --loglevel=warning --queues=default,high --concurrency=10 --hostname=sender4@%h -O fair
