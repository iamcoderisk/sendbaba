#!/bin/bash
cd /opt/sendbaba-staging
source venv/bin/activate
exec celery -A celery_app worker --loglevel=info --queues=bulk --concurrency=10 --hostname=bulk@%h
