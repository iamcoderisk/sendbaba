#!/bin/bash
# ============================================================
# SENDBABA CAMPAIGN MONITOR
# Usage: ./monitor_campaign.sh [org_id]
# ============================================================

ORG_ID="${1:-34101503-860d-427d-9344-6a00ed732bda}"

echo "============================================================"
echo "📊 SENDBABA LIVE CAMPAIGN MONITOR"
echo "============================================================"
echo "Time: $(date)"
echo ""

# Campaign status
echo "=== ACTIVE CAMPAIGNS ==="
sudo -u postgres psql -d emailer -c "
SELECT 
    name,
    status,
    total_recipients,
    COALESCE(emails_sent, 0) as sent,
    total_recipients - COALESCE(emails_sent, 0) as remaining,
    ROUND(COALESCE(emails_sent, 0) * 100.0 / NULLIF(total_recipients, 0), 1) as progress_pct
FROM campaigns 
WHERE organization_id = '$ORG_ID'
AND status IN ('sending', 'queued')
ORDER BY created_at DESC
LIMIT 5;"

echo ""
echo "=== EMAIL STATUS BREAKDOWN ==="
sudo -u postgres psql -d emailer -c "
SELECT 
    status, 
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) as pct
FROM emails 
WHERE organization_id = '$ORG_ID'
GROUP BY status
ORDER BY count DESC;"

echo ""
echo "=== SENDING SPEED ==="
sudo -u postgres psql -d emailer -c "
SELECT 
    COUNT(*) FILTER (WHERE sent_at > NOW() - INTERVAL '1 minute') as last_1_min,
    COUNT(*) FILTER (WHERE sent_at > NOW() - INTERVAL '5 minutes') as last_5_min,
    ROUND(COUNT(*) FILTER (WHERE sent_at > NOW() - INTERVAL '5 minutes') / 5.0, 0) as avg_per_min
FROM emails 
WHERE organization_id = '$ORG_ID'
AND status = 'sent';"

echo ""
echo "=== WORKER STATUS ==="
pm2 list

echo ""
echo "=== RECENT ACTIVITY (Last 5 sends) ==="
pm2 logs celery-worker --lines 20 --nostream 2>&1 | grep -E "✅ Sent|Batch done|✉️" | tail -5

echo ""
echo "============================================================"
echo "🔄 Run again: ./monitor_campaign.sh"
echo "============================================================"
