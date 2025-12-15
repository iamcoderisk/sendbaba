#!/bin/bash
cd /opt/sendbaba-staging
source venv/bin/activate

export PYTHONPATH=/opt/sendbaba-staging
export REDIS_URL="redis://:SendBabaRedis2024!@localhost:6379/0"
export DATABASE_URL="postgresql://emailer:SecurePassword123@localhost:5432/emailer"

exec celery -A celery_app.celery_app beat --loglevel=info
