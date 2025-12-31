#!/bin/bash
cd /opt/sendbaba-staging
source venv/bin/activate
export PYTHONPATH=/opt/sendbaba-staging
exec celery -A celery_app worker --loglevel=INFO --concurrency=170 -n worker@main
