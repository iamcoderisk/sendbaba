#!/bin/bash
cd /opt/sendbaba-staging
source venv/bin/activate
export PYTHONPATH=/opt/sendbaba-staging
exec gunicorn -w 4 -b 0.0.0.0:8000 --timeout 120 wsgi:app
