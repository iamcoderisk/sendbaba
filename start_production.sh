#!/bin/bash
# Start SendBaba Production Environment

cd /opt/sendbaba-staging

echo "Starting SendBaba Production..."

# Stop old processes
pm2 delete all 2>/dev/null || true

# Clear Python cache
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true

# Start with new ecosystem
pm2 start ecosystem.config.js

# Show status
sleep 3
pm2 status

echo ""
echo "============================================"
echo "SendBaba Production Started!"
echo "============================================"
echo ""
echo "Web UI:      http://156.67.29.186:5001"
echo "Flower:      http://156.67.29.186:5555"
echo "Metrics:     http://156.67.29.186:5001/metrics"
echo ""
echo "Commands:"
echo "  pm2 status              - Check status"
echo "  pm2 logs               - View logs"
echo "  pm2 logs celery-default - View worker logs"
echo ""
