#!/bin/bash
cd /opt/sendbaba-staging
source venv/bin/activate
python3 monitor_ips.py >> /var/log/sendbaba-monitor.log 2>&1
echo "---" >> /var/log/sendbaba-monitor.log
