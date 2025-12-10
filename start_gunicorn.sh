#!/bin/bash
cd /opt/sendbaba-staging
export PYTHONPATH=/opt/sendbaba-staging:$PYTHONPATH
export FLASK_ENV=production
source venv/bin/activate
exec gunicorn --workers 4 --bind 0.0.0.0:5000 --timeout 120 --access-logfile - --error-logfile - "app:create_app()"
