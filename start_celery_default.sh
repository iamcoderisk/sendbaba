#!/bin/bash
cd /opt/sendbaba-staging
source venv/bin/activate
exec celery -A celery_app worker --loglevel=info --queues=default --concurrency=4 --hostname=default@%h
