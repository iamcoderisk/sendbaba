"""
SendBaba Analytics Controller - Simplified & Fixed
"""
from flask import Blueprint, render_template, jsonify, request, Response
from flask_login import login_required, current_user
from app import db
from sqlalchemy import text
from datetime import datetime, timedelta
import logging
import json
import csv
import io

logger = logging.getLogger(__name__)
analytics_bp = Blueprint('analytics', __name__, url_prefix='/dashboard/analytics')


def get_date_range(period='30d'):
    """Get start and end dates for period"""
    now = datetime.utcnow()
    periods = {
        '24h': timedelta(hours=24),
        '7d': timedelta(days=7),
        '30d': timedelta(days=30),
        '90d': timedelta(days=90)
    }
    delta = periods.get(period, timedelta(days=30))
    return now - delta, now


def safe_query(query, params, default=None):
    """Execute query safely with error handling"""
    try:
        result = db.session.execute(text(query), params)
        return result.fetchone() if default is None else result.fetchall()
    except Exception as e:
        logger.error(f"[Analytics] Query error: {e}")
        return default


def get_overview_stats(org_id, start_date, end_date):
    """Get overview statistics"""
    stats = {
        'total_sent': 0, 'delivered': 0, 'opened': 0, 'clicked': 0,
        'bounced': 0, 'failed': 0, 'pending': 0, 'unsubscribed': 0,
        'delivery_rate': 0, 'open_rate': 0, 'click_rate': 0,
        'bounce_rate': 0, 'spam_rate': 0, 'avg_daily': 0,
        'total_contacts': 0, 'active_contacts': 0,
        'total_growth': 0, 'open_growth': 0,
    }
    
    if not org_id:
        return stats
    
    try:
        # Main email stats - simplified query
        result = safe_query("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'sent' THEN 1 END) as sent,
                COUNT(CASE WHEN status = 'delivered' THEN 1 END) as delivered,
                COUNT(CASE WHEN status = 'opened' THEN 1 END) as opened,
                COUNT(CASE WHEN status = 'clicked' THEN 1 END) as clicked,
                COUNT(CASE WHEN status = 'bounced' THEN 1 END) as bounced,
                COUNT(CASE WHEN status IN ('failed', 'error', 'rejected') THEN 1 END) as failed,
                COUNT(CASE WHEN status IN ('queued', 'pending') THEN 1 END) as pending
            FROM emails 
            WHERE organization_id = :org_id 
              AND created_at >= :start_date
        """, {'org_id': org_id, 'start_date': start_date})
        
        if result:
            total = result[0] or 0
            sent = (result[1] or 0) + (result[2] or 0) + (result[3] or 0) + (result[4] or 0)
            
            stats['total_sent'] = sent
            stats['delivered'] = (result[2] or 0) + (result[3] or 0) + (result[4] or 0)
            stats['opened'] = (result[3] or 0) + (result[4] or 0)
            stats['clicked'] = result[4] or 0
            stats['bounced'] = result[5] or 0
            stats['failed'] = result[6] or 0
            stats['pending'] = result[7] or 0
            
            if total > 0:
                stats['delivery_rate'] = round((stats['delivered'] / total) * 100, 1)
                stats['bounce_rate'] = round((stats['bounced'] / total) * 100, 1)
            
            if sent > 0:
                stats['open_rate'] = round((stats['opened'] / sent) * 100, 1)
                stats['click_rate'] = round((stats['clicked'] / sent) * 100, 1)
            
            days = max((end_date - start_date).days, 1)
            stats['avg_daily'] = int(total / days)
        
        # Contact stats
        contacts = safe_query("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'active' OR status IS NULL THEN 1 END) as active,
                COUNT(CASE WHEN status = 'unsubscribed' THEN 1 END) as unsub
            FROM contacts WHERE organization_id = :org_id
        """, {'org_id': org_id})
        
        if contacts:
            stats['total_contacts'] = contacts[0] or 0
            stats['active_contacts'] = contacts[1] or 0
            stats['unsubscribed'] = contacts[2] or 0
            
    except Exception as e:
        logger.error(f"[Analytics] Overview error: {e}")
    
    return stats


def get_queue_stats(org_id):
    """Get current queue statistics"""
    stats = {'pending': 0, 'processing': 0, 'completed_today': 0, 'failed_today': 0}
    
    if not org_id:
        return stats
    
    try:
        result = safe_query("""
            SELECT 
                COUNT(CASE WHEN status = 'queued' THEN 1 END) as pending,
                COUNT(CASE WHEN status = 'sending' THEN 1 END) as processing,
                COUNT(CASE WHEN status IN ('sent', 'delivered') AND DATE(created_at) = CURRENT_DATE THEN 1 END) as completed,
                COUNT(CASE WHEN status IN ('failed', 'bounced') AND DATE(created_at) = CURRENT_DATE THEN 1 END) as failed
            FROM emails 
            WHERE organization_id = :org_id
        """, {'org_id': org_id})
        
        if result:
            stats = {
                'pending': result[0] or 0,
                'processing': result[1] or 0,
                'completed_today': result[2] or 0,
                'failed_today': result[3] or 0
            }
    except Exception as e:
        logger.error(f"[Analytics] Queue stats error: {e}")
    
    return stats


def get_email_trends(org_id, start_date, end_date):
    """Get email trends over time"""
    if not org_id:
        return []
    
    try:
        result = db.session.execute(text("""
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as total,
                COUNT(CASE WHEN status IN ('sent', 'delivered', 'opened', 'clicked') THEN 1 END) as sent,
                COUNT(CASE WHEN status IN ('failed', 'bounced') THEN 1 END) as failed
            FROM emails
            WHERE organization_id = :org_id 
              AND created_at >= :start_date
            GROUP BY DATE(created_at)
            ORDER BY date
        """), {'org_id': org_id, 'start_date': start_date}).fetchall()
        
        trends = []
        for row in result:
            trends.append({
                'label': row[0].strftime('%b %d') if row[0] else '',
                'date': row[0].strftime('%Y-%m-%d') if row[0] else '',
                'total': row[1] or 0,
                'sent': row[2] or 0,
                'delivered': row[2] or 0,
                'failed': row[3] or 0,
                'opened': 0
            })
        return trends
        
    except Exception as e:
        logger.error(f"[Analytics] Email trends error: {e}")
        return []


def get_campaign_stats(org_id, start_date=None, end_date=None):
    """Get campaign statistics"""
    stats = {'total': 0, 'sent': 0, 'drafts': 0, 'scheduled': 0}
    
    if not org_id:
        return stats
    
    try:
        result = safe_query("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status IN ('sent', 'completed', 'completed_with_errors', 'sending') THEN 1 END) as sent,
                COUNT(CASE WHEN status = 'draft' THEN 1 END) as drafts,
                COUNT(CASE WHEN status = 'scheduled' THEN 1 END) as scheduled
            FROM campaigns
            WHERE organization_id = :org_id
        """, {'org_id': org_id})
        
        if result:
            stats = {
                'total': result[0] or 0,
                'sent': result[1] or 0,
                'drafts': result[2] or 0,
                'scheduled': result[3] or 0
            }
    except Exception as e:
        logger.error(f"[Analytics] Campaign stats error: {e}")
    
    return stats


def get_top_campaigns(org_id, start_date=None, end_date=None, limit=5):
    """Get top performing campaigns"""
    if not org_id:
        return []
    
    try:
        result = db.session.execute(text("""
            SELECT 
                id, name, status, created_at,
                COALESCE(emails_sent, 0) as sent,
                COALESCE(total_recipients, 0) as total
            FROM campaigns
            WHERE organization_id = :org_id
              AND status IN ('sent', 'completed', 'completed_with_errors', 'sending')
            ORDER BY created_at DESC
            LIMIT :limit
        """), {'org_id': org_id, 'limit': limit}).fetchall()
        
        campaigns = []
        for row in result:
            sent = row[4] or 0
            total = row[5] or sent or 1
            campaigns.append({
                'id': str(row[0]),
                'name': row[1] or 'Untitled',
                'status': row[2] or 'draft',
                'created_at': row[3].strftime('%b %d, %Y') if row[3] else '',
                'sent': sent,
                'total': total,
                'delivery_rate': round((sent / total) * 100, 1) if total > 0 else 0,
                'open_rate': 0
            })
        return campaigns
        
    except Exception as e:
        logger.error(f"[Analytics] Top campaigns error: {e}")
        return []


def get_hourly_distribution(org_id, start_date, end_date):
    """Get hourly email distribution"""
    hourly = [{'hour': f'{h:02d}:00', 'count': 0} for h in range(24)]
    
    if not org_id:
        return hourly
    
    try:
        result = db.session.execute(text("""
            SELECT 
                EXTRACT(HOUR FROM created_at)::int as hour,
                COUNT(*) as count
            FROM emails
            WHERE organization_id = :org_id 
              AND created_at >= :start_date
            GROUP BY EXTRACT(HOUR FROM created_at)
            ORDER BY hour
        """), {'org_id': org_id, 'start_date': start_date}).fetchall()
        
        for row in result:
            h = row[0] or 0
            if 0 <= h < 24:
                hourly[h]['count'] = row[1] or 0
        
        return hourly
        
    except Exception as e:
        logger.error(f"[Analytics] Hourly distribution error: {e}")
        return hourly


def get_domain_stats(org_id):
    """Get domain statistics"""
    if not org_id:
        return []
    
    try:
        result = db.session.execute(text("""
            SELECT 
                domain,
                dns_verified,
                dkim_verified,
                spf_verified
            FROM domains
            WHERE organization_id = :org_id
            ORDER BY created_at DESC
        """), {'org_id': org_id}).fetchall()
        
        domains = []
        for row in result:
            dns = row[1] or False
            dkim = row[2] or False
            spf = row[3] or False
            health = int((dns + dkim + spf) / 3 * 100)
            
            domains.append({
                'domain': row[0] or 'Unknown',
                'dns_verified': dns,
                'dkim_verified': dkim,
                'spf_verified': spf,
                'health_score': health
            })
        return domains
        
    except Exception as e:
        logger.error(f"[Analytics] Domain stats error: {e}")
        return []


def get_engagement_funnel(org_id, start_date, end_date):
    """Get engagement funnel data"""
    funnel = {'sent': 0, 'delivered': 0, 'opened': 0, 'clicked': 0, 'failed': 0}
    
    if not org_id:
        return funnel
    
    try:
        result = safe_query("""
            SELECT 
                COUNT(CASE WHEN status IN ('sent', 'delivered', 'opened', 'clicked') THEN 1 END) as sent,
                COUNT(CASE WHEN status IN ('delivered', 'opened', 'clicked') THEN 1 END) as delivered,
                COUNT(CASE WHEN status IN ('opened', 'clicked') THEN 1 END) as opened,
                COUNT(CASE WHEN status = 'clicked' THEN 1 END) as clicked,
                COUNT(CASE WHEN status IN ('failed', 'bounced') THEN 1 END) as failed
            FROM emails
            WHERE organization_id = :org_id 
              AND created_at >= :start_date
        """, {'org_id': org_id, 'start_date': start_date})
        
        if result:
            funnel = {
                'sent': result[0] or 0,
                'delivered': result[1] or 0,
                'opened': result[2] or 0,
                'clicked': result[3] or 0,
                'failed': result[4] or 0
            }
    except Exception as e:
        logger.error(f"[Analytics] Engagement funnel error: {e}")
    
    return funnel


@analytics_bp.route('/')
@login_required
def index():
    """Analytics dashboard"""
    try:
        org_id = current_user.organization_id
        period = request.args.get('period', '30d')
        start_date, end_date = get_date_range(period)
        
        logger.info(f"[Analytics] Loading for org_id={org_id}, period={period}")
        
        overview = get_overview_stats(org_id, start_date, end_date)
        queue_stats = get_queue_stats(org_id)
        email_trends = get_email_trends(org_id, start_date, end_date)
        campaign_stats = get_campaign_stats(org_id, start_date, end_date)
        top_campaigns = get_top_campaigns(org_id, start_date, end_date)
        hourly_dist = get_hourly_distribution(org_id, start_date, end_date)
        domain_stats = get_domain_stats(org_id)
        engagement_funnel = get_engagement_funnel(org_id, start_date, end_date)
        
        logger.info(f"[Analytics] Data: sent={overview['total_sent']}, contacts={overview['total_contacts']}, campaigns={campaign_stats['total']}")
        
        return render_template('dashboard/analytics/index.html',
            overview=overview,
            queue_stats=queue_stats,
            email_trends=json.dumps(email_trends),
            campaign_stats=campaign_stats,
            top_campaigns=top_campaigns,
            hourly_dist=json.dumps(hourly_dist),
            domain_stats=domain_stats,
            engagement_funnel=engagement_funnel,
            period=period
        )
        
    except Exception as e:
        logger.error(f"[Analytics] Index error: {e}", exc_info=True)
        return render_template('dashboard/analytics/index.html',
            overview={'total_sent': 0, 'delivered': 0, 'opened': 0, 'clicked': 0, 'bounced': 0, 
                      'failed': 0, 'pending': 0, 'unsubscribed': 0, 'delivery_rate': 0, 
                      'open_rate': 0, 'click_rate': 0, 'bounce_rate': 0, 'spam_rate': 0, 
                      'avg_daily': 0, 'total_contacts': 0, 'active_contacts': 0,
                      'total_growth': 0, 'open_growth': 0},
            queue_stats={'pending': 0, 'processing': 0, 'completed_today': 0, 'failed_today': 0},
            email_trends='[]',
            campaign_stats={'total': 0, 'sent': 0, 'drafts': 0, 'scheduled': 0},
            top_campaigns=[],
            hourly_dist='[]',
            domain_stats=[],
            engagement_funnel={'sent': 0, 'delivered': 0, 'opened': 0, 'clicked': 0, 'failed': 0},
            period='30d'
        )


@analytics_bp.route('/api/realtime')
@login_required
def api_realtime():
    """Real-time queue statistics"""
    try:
        org_id = current_user.organization_id
        queue = get_queue_stats(org_id)
        return jsonify({
            'success': True,
            'data': queue,
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@analytics_bp.route('/api/overview')
@login_required
def api_overview():
    """API endpoint for overview stats"""
    try:
        org_id = current_user.organization_id
        period = request.args.get('period', '30d')
        start_date, end_date = get_date_range(period)
        
        return jsonify({
            'success': True,
            'overview': get_overview_stats(org_id, start_date, end_date),
            'queue': get_queue_stats(org_id)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@analytics_bp.route('/api/export')
@login_required
def api_export():
    """Export analytics data as CSV"""
    try:
        org_id = current_user.organization_id
        period = request.args.get('period', '30d')
        start_date, end_date = get_date_range(period)
        
        result = db.session.execute(text("""
            SELECT created_at, to_email, subject, status
            FROM emails
            WHERE organization_id = :org_id AND created_at >= :start_date
            ORDER BY created_at DESC
            LIMIT 10000
        """), {'org_id': org_id, 'start_date': start_date}).fetchall()
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Created', 'Recipient', 'Subject', 'Status'])
        
        for row in result:
            writer.writerow([
                row[0].isoformat() if row[0] else '',
                row[1] or '',
                row[2] or '',
                row[3] or ''
            ])
        
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename=analytics_{period}.csv'}
        )
        
    except Exception as e:
        logger.error(f"[Analytics] Export error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
