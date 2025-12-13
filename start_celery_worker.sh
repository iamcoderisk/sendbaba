#!/bin/bash
cd /opt/sendbaba-staging
source venv/bin/activate
exec celery -A celery_app.celery_app worker --loglevel=info --concurrency=4 -Q celery
