"""
SendBaba Dashboard Controller - COMPLETE FIX
"""
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from app import db
from sqlalchemy import text
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)
dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


def get_stats(org_id):
    """Get comprehensive dashboard statistics"""
    stats = {
        'emails_sent': 0,
        'emails_delivered': 0,
        'emails_failed': 0,
        'emails_total': 0,
        'delivery_rate': 0,
        'contacts_total': 0,
        'contacts_active': 0,
        'campaigns_total': 0,
        'campaigns_sent': 0,
        'campaigns_draft': 0,
        'domains_total': 0,
        'domains_verified': 0,
        'opens_total': 0,
        'clicks_total': 0,
        'bounces_total': 0,
        'open_rate': 0,
        'click_rate': 0,
        'bounce_rate': 0,
        'growth_percent': 0,
    }
    
    if not org_id:
        return stats
    
    # EMAILS
    try:
        result = db.session.execute(text("""
            SELECT 
                COUNT(*) FILTER (WHERE status IN ('sent', 'delivered', 'opened', 'clicked')) as sent,
                COUNT(*) FILTER (WHERE status IN ('delivered', 'opened', 'clicked')) as delivered,
                COUNT(*) FILTER (WHERE status IN ('failed', 'bounced', 'rejected', 'error')) as failed,
                COUNT(*) FILTER (WHERE status IN ('opened', 'clicked')) as opened,
                COUNT(*) FILTER (WHERE status = 'clicked') as clicked,
                COUNT(*) FILTER (WHERE status = 'bounced') as bounced,
                COUNT(*) as total
            FROM emails 
            WHERE organization_id = :org_id
        """), {'org_id': org_id}).fetchone()
        
        if result:
            stats['emails_sent'] = result[0] or 0
            stats['emails_delivered'] = result[1] or 0
            stats['emails_failed'] = result[2] or 0
            stats['opens_total'] = result[3] or 0
            stats['clicks_total'] = result[4] or 0
            stats['bounces_total'] = result[5] or 0
            stats['emails_total'] = result[6] or 0
            
            if stats['emails_total'] > 0:
                stats['delivery_rate'] = round((stats['emails_sent'] / stats['emails_total']) * 100, 1)
                stats['bounce_rate'] = round((stats['bounces_total'] / stats['emails_total']) * 100, 1)
            
            if stats['emails_sent'] > 0:
                stats['open_rate'] = round((stats['opens_total'] / stats['emails_sent']) * 100, 1)
                stats['click_rate'] = round((stats['clicks_total'] / stats['emails_sent']) * 100, 1)
        
        # Calculate growth (compare to previous period)
        prev_result = db.session.execute(text("""
            SELECT COUNT(*) FROM emails 
            WHERE organization_id = :org_id 
            AND created_at >= NOW() - INTERVAL '60 days'
            AND created_at < NOW() - INTERVAL '30 days'
        """), {'org_id': org_id}).fetchone()
        
        curr_result = db.session.execute(text("""
            SELECT COUNT(*) FROM emails 
            WHERE organization_id = :org_id 
            AND created_at >= NOW() - INTERVAL '30 days'
        """), {'org_id': org_id}).fetchone()
        
        prev_count = prev_result[0] if prev_result else 0
        curr_count = curr_result[0] if curr_result else 0
        
        if prev_count > 0:
            stats['growth_percent'] = round(((curr_count - prev_count) / prev_count) * 100, 1)
        elif curr_count > 0:
            stats['growth_percent'] = 100
        
        logger.info(f"[Dashboard] Emails: {stats['emails_sent']} sent / {stats['emails_total']} total, {stats['delivery_rate']}% delivery")
    except Exception as e:
        logger.error(f"[Dashboard] Emails query error: {e}")

    # CONTACTS
    try:
        result = db.session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'active' OR status IS NULL) as active
            FROM contacts 
            WHERE organization_id = :org_id
        """), {'org_id': org_id}).fetchone()
        
        if result:
            stats['contacts_total'] = result[0] or 0
            stats['contacts_active'] = result[1] or 0
        
        logger.info(f"[Dashboard] Contacts: {stats['contacts_total']}")
    except Exception as e:
        logger.error(f"[Dashboard] Contacts query error: {e}")

    # CAMPAIGNS
    try:
        result = db.session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status IN ('sent', 'completed', 'completed_with_errors', 'sending')) as sent,
                COUNT(*) FILTER (WHERE status = 'draft') as draft
            FROM campaigns 
            WHERE organization_id = :org_id
        """), {'org_id': org_id}).fetchone()
        
        if result:
            stats['campaigns_total'] = result[0] or 0
            stats['campaigns_sent'] = result[1] or 0
            stats['campaigns_draft'] = result[2] or 0
        
        logger.info(f"[Dashboard] Campaigns: {stats['campaigns_total']} total, {stats['campaigns_sent']} sent")
    except Exception as e:
        logger.error(f"[Dashboard] Campaigns query error: {e}")

    # DOMAINS
    try:
        result = db.session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE dns_verified = true OR is_verified = true) as verified
            FROM domains 
            WHERE organization_id = :org_id
        """), {'org_id': org_id}).fetchone()
        
        if result:
            stats['domains_total'] = result[0] or 0
            stats['domains_verified'] = result[1] or 0
        
        logger.info(f"[Dashboard] Domains: {stats['domains_total']} total, {stats['domains_verified']} verified")
    except Exception as e:
        logger.error(f"[Dashboard] Domains query error: {e}")

    return stats


def get_email_trends(org_id, days=30):
    """Get email trends for chart - SUPPORTS DIFFERENT PERIODS"""
    if not org_id:
        return []
    
    trends = []
    
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        result = db.session.execute(text("""
            SELECT 
                DATE(created_at) as date,
                COUNT(*) FILTER (WHERE status IN ('sent', 'delivered', 'opened', 'clicked')) as sent,
                COUNT(*) FILTER (WHERE status IN ('delivered', 'opened', 'clicked')) as delivered,
                COUNT(*) FILTER (WHERE status IN ('opened', 'clicked')) as opened,
                COUNT(*) FILTER (WHERE status = 'failed') as failed
            FROM emails
            WHERE organization_id = :org_id 
              AND created_at >= :start_date
            GROUP BY DATE(created_at)
            ORDER BY date
        """), {'org_id': org_id, 'start_date': start_date}).fetchall()
        
        # Create a dict for quick lookup
        data_by_date = {}
        for row in result:
            date_str = row[0].strftime('%Y-%m-%d') if row[0] else ''
            data_by_date[date_str] = {
                'sent': row[1] or 0,
                'delivered': row[2] or 0,
                'opened': row[3] or 0,
                'failed': row[4] or 0
            }
        
        # Fill in all days in range
        for i in range(days - 1, -1, -1):
            date = datetime.utcnow() - timedelta(days=i)
            date_str = date.strftime('%Y-%m-%d')
            day_data = data_by_date.get(date_str, {'sent': 0, 'delivered': 0, 'opened': 0, 'failed': 0})
            
            trends.append({
                'date': date_str,
                'label': date.strftime('%b %d'),
                'sent': day_data['sent'],
                'delivered': day_data['delivered'],
                'opened': day_data['opened'],
                'failed': day_data['failed']
            })
        
        return trends
        
    except Exception as e:
        logger.error(f"[Dashboard] Email trends error: {e}")
        # Return empty data for all days
        for i in range(days - 1, -1, -1):
            date = datetime.utcnow() - timedelta(days=i)
            trends.append({
                'date': date.strftime('%Y-%m-%d'),
                'label': date.strftime('%b %d'),
                'sent': 0, 'delivered': 0, 'opened': 0, 'failed': 0
            })
        return trends


def get_campaign_performance(org_id, limit=10):
    """Get campaign performance data for chart"""
    if not org_id:
        return []
    
    try:
        result = db.session.execute(text("""
            SELECT 
                c.name,
                COALESCE(c.emails_sent, c.sent_count, 0) as sent,
                (SELECT COUNT(*) FROM emails WHERE campaign_id = c.id AND status IN ('opened', 'clicked')) as opens,
                (SELECT COUNT(*) FROM emails WHERE campaign_id = c.id AND status = 'clicked') as clicks
            FROM campaigns c
            WHERE c.organization_id = :org_id
              AND c.status IN ('sent', 'completed', 'completed_with_errors', 'sending')
            ORDER BY c.created_at DESC
            LIMIT :limit
        """), {'org_id': org_id, 'limit': limit}).fetchall()
        
        campaigns = []
        for row in result:
            sent = row[1] or 0
            campaigns.append({
                'name': (row[0] or 'Untitled')[:20],
                'sent': sent,
                'opens': row[2] or 0,
                'clicks': row[3] or 0,
                'open_rate': round((row[2] / sent * 100), 1) if sent > 0 else 0,
                'click_rate': round((row[3] / sent * 100), 1) if sent > 0 else 0,
            })
        
        return campaigns
    except Exception as e:
        logger.error(f"[Dashboard] Campaign performance error: {e}")
        return []


def get_recent_campaigns(org_id, limit=5):
    """Get recent campaigns with stats"""
    if not org_id:
        return []
    
    try:
        result = db.session.execute(text("""
            SELECT 
                c.id, c.name, c.status, c.created_at,
                COALESCE(c.emails_sent, c.sent_count, 0) as sent,
                COALESCE(c.total_recipients, 0) as recipients,
                (SELECT COUNT(*) FROM emails WHERE campaign_id = c.id AND status IN ('opened', 'clicked')) as opens,
                (SELECT COUNT(*) FROM emails WHERE campaign_id = c.id AND status = 'clicked') as clicks
            FROM campaigns c
            WHERE c.organization_id = :org_id
            ORDER BY c.created_at DESC
            LIMIT :limit
        """), {'org_id': org_id, 'limit': limit}).fetchall()
        
        campaigns = []
        for row in result:
            sent = row[4] or 0
            campaigns.append({
                'id': str(row[0]),
                'name': row[1] or 'Untitled',
                'status': row[2] or 'draft',
                'created_at': row[3].strftime('%b %d, %Y') if row[3] else '',
                'sent': sent,
                'recipients': row[5] or 0,
                'opens': row[6] or 0,
                'clicks': row[7] or 0,
                'open_rate': round((row[6] / sent * 100), 1) if sent > 0 else 0,
                'click_rate': round((row[7] / sent * 100), 1) if sent > 0 else 0,
            })
        
        return campaigns
    except Exception as e:
        logger.error(f"[Dashboard] Recent campaigns error: {e}")
        return []



@dashboard_bp.route('/')
@login_required
def index():
    """Dashboard home with real usage data"""
    from app.services.usage_service import usage_service
    from sqlalchemy import text
    from app import db
    
    org_id = str(current_user.organization_id)
    
    # Get usage data
    usage = usage_service.get_organization_usage(org_id)
    
    # Get stats
    stats = {}
    try:
        result = db.session.execute(text("""
            SELECT 
                (SELECT COUNT(*) FROM contacts WHERE organization_id = :org_id) as total_contacts,
                (SELECT COUNT(*) FROM campaigns WHERE organization_id = :org_id) as total_campaigns,
                (SELECT COUNT(*) FROM emails WHERE organization_id = :org_id AND status = 'sent' AND created_at > NOW() - INTERVAL '30 days') as emails_30d,
                (SELECT COUNT(*) FROM emails WHERE organization_id = :org_id AND status = 'sent' AND created_at > NOW() - INTERVAL '24 hours') as emails_24h
        """), {'org_id': org_id})
        row = result.fetchone()
        if row:
            stats = {
                'total_contacts': row[0] or 0,
                'total_campaigns': row[1] or 0,
                'emails_30d': row[2] or 0,
                'emails_24h': row[3] or 0
            }
    except Exception as e:
        logger.error(f"Stats error: {e}")
        stats = {'total_contacts': 0, 'total_campaigns': 0, 'emails_30d': 0, 'emails_24h': 0}
    
    return render_template('dashboard/index.html', 
                          usage=usage, 
                          stats=stats,
                          plan=usage.get('plan', 'free') if usage else 'free')

@dashboard_bp.route('/api/stats')
@login_required
def api_stats():
    """API endpoint for dashboard stats"""
    try:
        org_id = current_user.organization_id
        stats = get_stats(org_id)
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        logger.error(f"[Dashboard API] Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@dashboard_bp.route('/api/trends')
@login_required
def api_trends():
    """API endpoint for email trends - SUPPORTS DIFFERENT PERIODS"""
    try:
        org_id = current_user.organization_id
        days = request.args.get('days', 30, type=int)
        
        # Validate days
        if days not in [7, 14, 30]:
            days = 30
        
        trends = get_email_trends(org_id, days)
        return jsonify({'success': True, 'trends': trends, 'days': days})
    except Exception as e:
        logger.error(f"[Dashboard API] Trends error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@dashboard_bp.route('/api/campaigns')
@login_required
def api_campaigns():
    """API endpoint for campaign performance"""
    try:
        org_id = current_user.organization_id
        campaigns = get_campaign_performance(org_id)
        return jsonify({'success': True, 'campaigns': campaigns})
    except Exception as e:
        logger.error(f"[Dashboard API] Campaigns error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
