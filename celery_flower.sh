#!/bin/bash
# Start Flower monitoring

cd /opt/sendbaba-staging
source venv/bin/activate

celery -A app.celery_config flower \
    --port=5555 \
    --broker=redis://localhost:6379/0
