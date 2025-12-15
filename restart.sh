#!/bin/bash
# SendBaba Quick Restart Script
# Usage: ./restart.sh [option]
# Options:
#   all     - Restart all services (default)
#   web     - Restart web server only
#   workers - Restart celery workers only
#   status  - Show status only

cd /opt/sendbaba-staging
source venv/bin/activate

case "${1:-all}" in
    web)
        echo "🔄 Restarting web server..."
        pm2 restart sendbaba-web
        ;;
    workers)
        echo "🔄 Restarting Celery workers..."
        pm2 restart celery-worker celery-beat
        ;;
    status)
        echo "📊 Current Status:"
        pm2 list
        ;;
    all|*)
        echo "🔄 Restarting all services..."
        pm2 restart all
        ;;
esac

sleep 3
echo ""
echo "✅ Done!"
pm2 list
echo ""
echo "🌐 Dashboard: https://playmaster.sendbaba.com/dashboard/"
