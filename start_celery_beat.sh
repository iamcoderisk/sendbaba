#!/bin/bash
cd /opt/sendbaba-staging
export PYTHONPATH=/opt/sendbaba-staging:$PYTHONPATH
source venv/bin/activate
exec celery -A celery_app beat "$@"
