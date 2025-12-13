"""
SendBaba Analytics Controller - COMPLETE FIX
All required template variables included
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
        '90d': timedelta(days=90),
        '12m': timedelta(days=365)
    }
    delta = periods.get(period, timedelta(days=30))
    return now - delta, now


def get_overview_stats(org_id, start_date, end_date):
    """Get overview statistics with ALL required fields"""
    stats = {
        'total_sent': 0,
        'delivered': 0,
        'opened': 0,
        'clicked': 0,
        'bounced': 0,
        'failed': 0,
        'pending': 0,
        'unsubscribed': 0,
        'delivery_rate': 0,
        'open_rate': 0,
        'click_rate': 0,
        'bounce_rate': 0,
        'spam_rate': 0,
        'avg_daily': 0,
        'total_contacts': 0,
        'active_contacts': 0,
        'total_growth': 0,
        'open_growth': 0,
    }
    
    if not org_id:
        return stats
    
    try:
        # Email stats for current period
        result = db.session.execute(text("""
            SELECT 
                COUNT(*) FILTER (WHERE status IN ('sent', 'delivered', 'opened', 'clicked')) as sent,
                COUNT(*) FILTER (WHERE status IN ('delivered', 'opened', 'clicked')) as delivered,
                COUNT(*) FILTER (WHERE status IN ('opened', 'clicked')) as opened,
                COUNT(*) FILTER (WHERE status = 'clicked') as clicked,
                COUNT(*) FILTER (WHERE status = 'bounced') as bounced,
                COUNT(*) FILTER (WHERE status IN ('failed', 'rejected', 'error')) as failed,
                COUNT(*) FILTER (WHERE status = 'queued' OR status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'spam' OR status = 'complaint') as spam,
                COUNT(*) as total
            FROM emails 
            WHERE organization_id = :org_id 
              AND created_at >= :start_date 
              AND created_at <= :end_date
        """), {'org_id': org_id, 'start_date': start_date, 'end_date': end_date}).fetchone()
        
        if result:
            sent = result[0] or 0
            stats['total_sent'] = sent
            stats['delivered'] = result[1] or 0
            stats['opened'] = result[2] or 0
            stats['clicked'] = result[3] or 0
            stats['bounced'] = result[4] or 0
            stats['failed'] = result[5] or 0
            stats['pending'] = result[6] or 0
            spam = result[7] or 0
            total = result[8] or 0
            
            if total > 0:
                stats['delivery_rate'] = round((sent / total) * 100, 1)
                stats['bounce_rate'] = round((stats['bounced'] / total) * 100, 1)
                stats['spam_rate'] = round((spam / total) * 100, 2)
            
            if sent > 0:
                stats['open_rate'] = round((stats['opened'] / sent) * 100, 1)
                stats['click_rate'] = round((stats['clicked'] / sent) * 100, 1)
            
            # Average daily
            days = max((end_date - start_date).days, 1)
            stats['avg_daily'] = round(total / days, 0)
        
        # Get unsubscribed count
        unsub_result = db.session.execute(text("""
            SELECT COUNT(*) FROM contacts 
            WHERE organization_id = :org_id AND status = 'unsubscribed'
        """), {'org_id': org_id}).fetchone()
        stats['unsubscribed'] = unsub_result[0] if unsub_result else 0
        
        # Contact stats
        contacts = db.session.execute(text("""
            SELECT COUNT(*), COUNT(*) FILTER (WHERE status = 'active' OR status IS NULL)
            FROM contacts WHERE organization_id = :org_id
        """), {'org_id': org_id}).fetchone()
        
        if contacts:
            stats['total_contacts'] = contacts[0] or 0
            stats['active_contacts'] = contacts[1] or 0
        
        # Calculate growth (compare to previous period)
        period_length = (end_date - start_date).days
        prev_start = start_date - timedelta(days=period_length)
        prev_end = start_date
        
        prev_result = db.session.execute(text("""
            SELECT 
                COUNT(*) FILTER (WHERE status IN ('sent', 'delivered', 'opened', 'clicked')) as sent,
                COUNT(*) FILTER (WHERE status IN ('opened', 'clicked')) as opened
            FROM emails 
            WHERE organization_id = :org_id 
              AND created_at >= :start_date 
              AND created_at < :end_date
        """), {'org_id': org_id, 'start_date': prev_start, 'end_date': prev_end}).fetchone()
        
        if prev_result:
            prev_sent = prev_result[0] or 0
            prev_opened = prev_result[1] or 0
            
            if prev_sent > 0:
                stats['total_growth'] = round(((stats['total_sent'] - prev_sent) / prev_sent) * 100, 1)
            elif stats['total_sent'] > 0:
                stats['total_growth'] = 100
            
            if prev_opened > 0:
                stats['open_growth'] = round(((stats['opened'] - prev_opened) / prev_opened) * 100, 1)
            elif stats['opened'] > 0:
                stats['open_growth'] = 100
            
    except Exception as e:
        logger.error(f"[Analytics] Overview error: {e}")
    
    return stats


def get_queue_stats(org_id):
    """Get current queue statistics"""
    stats = {
        'pending': 0,
        'processing': 0,
        'completed_today': 0,
        'failed_today': 0
    }
    
    if not org_id:
        return stats
    
    try:
        result = db.session.execute(text("""
            SELECT 
                COUNT(*) FILTER (WHERE status = 'queued') as pending,
                COUNT(*) FILTER (WHERE status = 'sending') as processing,
                COUNT(*) FILTER (WHERE status IN ('sent', 'delivered') AND DATE(sent_at) = CURRENT_DATE) as completed,
                COUNT(*) FILTER (WHERE status IN ('failed', 'bounced') AND DATE(created_at) = CURRENT_DATE) as failed
            FROM emails 
            WHERE organization_id = :org_id
        """), {'org_id': org_id}).fetchone()
        
        if result:
            stats['pending'] = result[0] or 0
            stats['processing'] = result[1] or 0
            stats['completed_today'] = result[2] or 0
            stats['failed_today'] = result[3] or 0
            
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
                COUNT(*) FILTER (WHERE status IN ('sent', 'delivered', 'opened', 'clicked')) as sent,
                COUNT(*) FILTER (WHERE status IN ('delivered', 'opened', 'clicked')) as delivered,
                COUNT(*) FILTER (WHERE status IN ('opened', 'clicked')) as opened,
                COUNT(*) FILTER (WHERE status IN ('failed', 'bounced')) as failed
            FROM emails
            WHERE organization_id = :org_id 
              AND created_at >= :start_date
            GROUP BY DATE(created_at)
            ORDER BY date
        """), {'org_id': org_id, 'start_date': start_date}).fetchall()
        
        return [{
            'date': row[0].strftime('%Y-%m-%d') if row[0] else '',
            'sent': row[1] or 0,
            'delivered': row[2] or 0,
            'opened': row[3] or 0,
            'failed': row[4] or 0
        } for row in result]
        
    except Exception as e:
        logger.error(f"[Analytics] Email trends error: {e}")
        return []


def get_campaign_stats(org_id, start_date, end_date):
    """Get campaign statistics"""
    stats = {'total': 0, 'sent': 0, 'drafts': 0, 'scheduled': 0}
    
    if not org_id:
        return stats
    
    try:
        result = db.session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status IN ('sent', 'completed', 'completed_with_errors')) as sent,
                COUNT(*) FILTER (WHERE status = 'draft') as drafts,
                COUNT(*) FILTER (WHERE status = 'scheduled') as scheduled
            FROM campaigns
            WHERE organization_id = :org_id
        """), {'org_id': org_id}).fetchone()
        
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


def get_top_campaigns(org_id, start_date, end_date, limit=5):
    """Get top performing campaigns"""
    if not org_id:
        return []
    
    try:
        result = db.session.execute(text("""
            SELECT 
                c.id, c.name, c.status, c.created_at,
                COALESCE(c.emails_sent, c.sent_count, 0) as sent,
                (SELECT COUNT(*) FROM emails WHERE campaign_id = c.id AND status IN ('opened', 'clicked')) as opens,
                (SELECT COUNT(*) FROM emails WHERE campaign_id = c.id AND status = 'clicked') as clicks
            FROM campaigns c
            WHERE c.organization_id = :org_id
              AND c.status IN ('sent', 'completed', 'completed_with_errors')
            ORDER BY c.created_at DESC
            LIMIT :limit
        """), {'org_id': org_id, 'limit': limit}).fetchall()
        
        campaigns = []
        for row in result:
            sent = row[4] or 0
            opens = row[5] or 0
            clicks = row[6] or 0
            campaigns.append({
                'id': str(row[0]),
                'name': row[1] or 'Untitled',
                'status': row[2] or 'draft',
                'date': row[3].strftime('%Y-%m-%d') if row[3] else '',
                'sent': sent,
                'opens': opens,
                'clicks': clicks,
                'open_rate': round((opens / sent * 100), 1) if sent > 0 else 0,
                'click_rate': round((clicks / sent * 100), 1) if sent > 0 else 0
            })
        
        return campaigns
        
    except Exception as e:
        logger.error(f"[Analytics] Top campaigns error: {e}")
        return []


def get_hourly_distribution(org_id, start_date, end_date):
    """Get hourly email distribution"""
    if not org_id:
        return [{'hour': h, 'count': 0} for h in range(24)]
    
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
        
        # Fill in all 24 hours
        hourly = {i: 0 for i in range(24)}
        for row in result:
            hourly[row[0]] = row[1]
        
        return [{'hour': h, 'count': c} for h, c in hourly.items()]
        
    except Exception as e:
        logger.error(f"[Analytics] Hourly distribution error: {e}")
        return [{'hour': h, 'count': 0} for h in range(24)]


def get_domain_stats(org_id):
    """Get domain statistics"""
    if not org_id:
        return []
    
    try:
        result = db.session.execute(text("""
            SELECT 
                COALESCE(domain, domain_name, 'Unknown') as name,
                COALESCE(dns_verified, is_verified, false) as verified,
                COALESCE(emails_sent, 0) as sent,
                COALESCE(emails_delivered, 0) as delivered,
                COALESCE(emails_bounced, 0) as bounced
            FROM domains
            WHERE organization_id = :org_id
            ORDER BY emails_sent DESC NULLS LAST
        """), {'org_id': org_id}).fetchall()
        
        return [{
            'name': row[0] or 'Unknown',
            'verified': row[1] or False,
            'sent': row[2] or 0,
            'delivered': row[3] or 0,
            'bounced': row[4] or 0
        } for row in result]
        
    except Exception as e:
        logger.error(f"[Analytics] Domain stats error: {e}")
        return []


def get_engagement_funnel(org_id, start_date, end_date):
    """Get engagement funnel data"""
    funnel = {'sent': 0, 'delivered': 0, 'opened': 0, 'clicked': 0, 'failed': 0}
    
    if not org_id:
        return funnel
    
    try:
        result = db.session.execute(text("""
            SELECT 
                COUNT(*) FILTER (WHERE status IN ('sent', 'delivered', 'opened', 'clicked')) as sent,
                COUNT(*) FILTER (WHERE status IN ('delivered', 'opened', 'clicked')) as delivered,
                COUNT(*) FILTER (WHERE status IN ('opened', 'clicked')) as opened,
                COUNT(*) FILTER (WHERE status = 'clicked') as clicked,
                COUNT(*) FILTER (WHERE status IN ('failed', 'bounced')) as failed
            FROM emails
            WHERE organization_id = :org_id 
              AND created_at >= :start_date
        """), {'org_id': org_id, 'start_date': start_date}).fetchone()
        
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


def get_status_breakdown(org_id, start_date, end_date):
    """Get email status breakdown"""
    if not org_id:
        return []
    
    try:
        result = db.session.execute(text("""
            SELECT status, COUNT(*) as count
            FROM emails
            WHERE organization_id = :org_id 
              AND created_at >= :start_date
            GROUP BY status
            ORDER BY count DESC
        """), {'org_id': org_id, 'start_date': start_date}).fetchall()
        
        return [{'status': row[0] or 'unknown', 'count': row[1] or 0} for row in result]
        
    except Exception as e:
        logger.error(f"[Analytics] Status breakdown error: {e}")
        return []


@analytics_bp.route('/')
@login_required
def index():
    """Analytics dashboard"""
    try:
        org_id = current_user.organization_id
        period = request.args.get('period', '30d')
        start_date, end_date = get_date_range(period)
        
        overview = get_overview_stats(org_id, start_date, end_date)
        queue_stats = get_queue_stats(org_id)
        email_trends = get_email_trends(org_id, start_date, end_date)
        campaign_stats = get_campaign_stats(org_id, start_date, end_date)
        top_campaigns = get_top_campaigns(org_id, start_date, end_date)
        hourly_dist = get_hourly_distribution(org_id, start_date, end_date)
        domain_stats = get_domain_stats(org_id)
        engagement_funnel = get_engagement_funnel(org_id, start_date, end_date)
        status_breakdown = get_status_breakdown(org_id, start_date, end_date)
        
        return render_template('dashboard/analytics/index.html',
            overview=overview,
            queue_stats=queue_stats,
            email_trends=json.dumps(email_trends),
            campaign_stats=campaign_stats,
            top_campaigns=top_campaigns,
            hourly_dist=json.dumps(hourly_dist),
            domain_stats=domain_stats,
            engagement_funnel=engagement_funnel,
            status_breakdown=json.dumps(status_breakdown),
            period=period
        )
        
    except Exception as e:
        logger.error(f"[Analytics] Index error: {e}", exc_info=True)
        # Return with all default values
        return render_template('dashboard/analytics/index.html',
            overview={
                'total_sent': 0, 'delivered': 0, 'opened': 0, 'clicked': 0, 'bounced': 0, 
                'failed': 0, 'pending': 0, 'unsubscribed': 0,
                'delivery_rate': 0, 'open_rate': 0, 'click_rate': 0, 
                'bounce_rate': 0, 'spam_rate': 0, 'avg_daily': 0, 
                'total_contacts': 0, 'active_contacts': 0,
                'total_growth': 0, 'open_growth': 0
            },
            queue_stats={'pending': 0, 'processing': 0, 'completed_today': 0, 'failed_today': 0},
            email_trends='[]',
            campaign_stats={'total': 0, 'sent': 0, 'drafts': 0, 'scheduled': 0},
            top_campaigns=[],
            hourly_dist='[]',
            domain_stats=[],
            engagement_funnel={'sent': 0, 'delivered': 0, 'opened': 0, 'clicked': 0, 'failed': 0},
            status_breakdown='[]',
            period='30d'
        )


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


@analytics_bp.route('/api/realtime')
@login_required
def api_realtime():
    """Real-time queue statistics"""
    try:
        org_id = current_user.organization_id
        return jsonify({
            'success': True,
            'queue': get_queue_stats(org_id),
            'timestamp': datetime.utcnow().isoformat()
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
        
        # Get email data
        result = db.session.execute(text("""
            SELECT created_at, to_email, subject, status, sent_at, opened_at, clicked_at
            FROM emails
            WHERE organization_id = :org_id AND created_at >= :start_date
            ORDER BY created_at DESC
            LIMIT 10000
        """), {'org_id': org_id, 'start_date': start_date}).fetchall()
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Created', 'Recipient', 'Subject', 'Status', 'Sent At', 'Opened At', 'Clicked At'])
        
        for row in result:
            writer.writerow([
                row[0].isoformat() if row[0] else '',
                row[1] or '',
                row[2] or '',
                row[3] or '',
                row[4].isoformat() if row[4] else '',
                row[5].isoformat() if row[5] else '',
                row[6].isoformat() if row[6] else ''
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
