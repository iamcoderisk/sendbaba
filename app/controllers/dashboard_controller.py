"""
Dashboard Controller - FIXED WITH CORRECT COLUMNS
"""
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from app import db
from datetime import datetime, timedelta
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)
dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


def get_dashboard_stats(org_id):
    """Get all dashboard statistics"""
    stats = {
        'emails_sent': 0,
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
        'growth_percent': 0
    }
    
    # EMAILS
    try:
        result = db.session.execute(text("""
            SELECT 
                COUNT(*) FILTER (WHERE status IN ('sent', 'delivered')) as sent,
                COUNT(*) FILTER (WHERE status = 'failed') as failed,
                COUNT(*) as total
            FROM emails WHERE organization_id = :org_id
        """), {'org_id': org_id}).fetchone()
        if result:
            stats['emails_sent'] = result[0] or 0
            stats['emails_failed'] = result[1] or 0
            stats['emails_total'] = result[2] or 0
            if stats['emails_total'] > 0:
                stats['delivery_rate'] = round((stats['emails_sent'] / stats['emails_total']) * 100, 1)
        logger.info(f"[Stats] Emails: {stats['emails_sent']}/{stats['emails_total']}")
    except Exception as e:
        logger.error(f"Emails error: {e}")
    
    # CONTACTS
    try:
        result = db.session.execute(text("SELECT COUNT(*) FROM contacts WHERE organization_id = :org_id"), {'org_id': org_id}).fetchone()
        if result:
            stats['contacts_total'] = result[0] or 0
            stats['contacts_active'] = result[0] or 0
        logger.info(f"[Stats] Contacts: {stats['contacts_total']}")
    except Exception as e:
        logger.error(f"Contacts error: {e}")
    
    # CAMPAIGNS
    try:
        result = db.session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status IN ('sent', 'completed')) as sent,
                COUNT(*) FILTER (WHERE status = 'draft') as draft
            FROM campaigns WHERE organization_id = :org_id
        """), {'org_id': org_id}).fetchone()
        if result:
            stats['campaigns_total'] = result[0] or 0
            stats['campaigns_sent'] = result[1] or 0
            stats['campaigns_draft'] = result[2] or 0
        logger.info(f"[Stats] Campaigns: {stats['campaigns_total']}")
    except Exception as e:
        logger.error(f"Campaigns error: {e}")
    
    # DOMAINS
    try:
        result = db.session.execute(text("""
            SELECT COUNT(*) as total,
                   COUNT(*) FILTER (WHERE is_verified = true) as verified
            FROM domains WHERE organization_id = :org_id
        """), {'org_id': org_id}).fetchone()
        if result:
            stats['domains_total'] = result[0] or 0
            stats['domains_verified'] = result[1] or 0
        logger.info(f"[Stats] Domains: {stats['domains_total']}")
    except Exception as e:
        logger.error(f"Domains error: {e}")
        try:
            result = db.session.execute(text("SELECT COUNT(*) FROM domains WHERE organization_id = :org_id"), {'org_id': org_id}).fetchone()
            if result:
                stats['domains_total'] = result[0] or 0
        except:
            pass
    
    return stats


def get_email_trends(org_id, days=30):
    """Get email activity for chart"""
    trends = []
    
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        result = db.session.execute(text("""
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status IN ('sent', 'delivered')) as delivered
            FROM emails 
            WHERE organization_id = :org_id AND created_at >= :start_date
            GROUP BY DATE(created_at)
            ORDER BY DATE(created_at)
        """), {'org_id': org_id, 'start_date': start_date}).fetchall()
        
        data_by_date = {str(row[0]): {'sent': row[1], 'delivered': row[2]} for row in result}
        
        for i in range(days - 1, -1, -1):
            date = datetime.utcnow() - timedelta(days=i)
            date_str = date.strftime('%Y-%m-%d')
            day_data = data_by_date.get(date_str, {'sent': 0, 'delivered': 0})
            trends.append({
                'date': date_str,
                'label': date.strftime('%b %d'),
                'sent': day_data['sent'],
                'delivered': day_data['delivered']
            })
    except Exception as e:
        logger.error(f"Email trends error: {e}")
        for i in range(days - 1, -1, -1):
            date = datetime.utcnow() - timedelta(days=i)
            trends.append({'date': date.strftime('%Y-%m-%d'), 'label': date.strftime('%b %d'), 'sent': 0, 'delivered': 0})
    
    return trends


def get_campaign_performance(org_id, limit=6):
    """Get campaign data for chart - FIXED COLUMN NAMES"""
    campaigns = []
    
    try:
        # Use correct column names: total_recipients, emails_sent, sent_count
        result = db.session.execute(text("""
            SELECT c.id, c.name, c.status,
                COALESCE(c.emails_sent, c.sent_count, 0) as sent,
                COALESCE(c.total_recipients, c.emails_sent, c.sent_count, 0) as recipients
            FROM campaigns c
            WHERE c.organization_id = :org_id AND c.status IN ('sent', 'completed', 'sending')
            ORDER BY c.created_at DESC LIMIT :limit
        """), {'org_id': org_id, 'limit': limit}).fetchall()
        
        for row in result:
            sent = row[3] or 0
            recipients = row[4] or sent or 0
            campaigns.append({
                'id': row[0],
                'name': row[1] or 'Untitled',
                'status': row[2] or 'draft',
                'sent': sent,
                'recipients': max(recipients, sent)
            })
        logger.info(f"[Chart] Campaign performance: {len(campaigns)} campaigns")
    except Exception as e:
        logger.error(f"Campaign performance error: {e}")
    
    return campaigns


def get_recent_campaigns(org_id, limit=5):
    """Get recent campaigns for list - FIXED COLUMN NAMES"""
    campaigns = []
    
    try:
        # Use correct column names: total_recipients, emails_sent, sent_count
        result = db.session.execute(text("""
            SELECT c.id, c.name, c.status, c.subject, c.created_at,
                COALESCE(c.emails_sent, c.sent_count, 0) as sent,
                COALESCE(c.total_recipients, c.emails_sent, 0) as recipients
            FROM campaigns c
            WHERE c.organization_id = :org_id
            ORDER BY c.created_at DESC LIMIT :limit
        """), {'org_id': org_id, 'limit': limit}).fetchall()
        
        for row in result:
            campaigns.append({
                'id': row[0],
                'name': row[1] or 'Untitled',
                'status': row[2] or 'draft',
                'subject': row[3] or '',
                'created_at': row[4].strftime('%b %d, %Y') if row[4] else '',
                'sent': row[5] or 0,
                'recipients': row[6] or row[5] or 0
            })
        logger.info(f"[List] Recent campaigns: {len(campaigns)}")
    except Exception as e:
        logger.error(f"Recent campaigns error: {e}")
    
    return campaigns


@dashboard_bp.route('/')
@login_required
def index():
    """Dashboard home"""
    org_id = current_user.organization_id
    logger.info(f"[Dashboard] Loading for org: {org_id}")
    
    stats = get_dashboard_stats(org_id)
    email_trends = get_email_trends(org_id, 30)
    campaign_performance = get_campaign_performance(org_id, 6)
    recent_campaigns = get_recent_campaigns(org_id, 5)
    
    logger.info(f"[Dashboard] Stats: emails={stats['emails_sent']}, campaigns={stats['campaigns_total']}, domains={stats['domains_total']}")
    logger.info(f"[Dashboard] Chart data: trends={len(email_trends)}, perf={len(campaign_performance)}, recent={len(recent_campaigns)}")
    
    return render_template('dashboard/index.html',
        user=current_user,
        stats=stats,
        email_trends=email_trends,
        campaign_performance=campaign_performance,
        recent_campaigns=recent_campaigns
    )


@dashboard_bp.route('/api/stats')
@login_required
def api_stats():
    stats = get_dashboard_stats(current_user.organization_id)
    return jsonify({'success': True, 'data': stats})


@dashboard_bp.route('/api/chart-data')
@login_required
def api_chart_data():
    days = request.args.get('days', 30, type=int)
    org_id = current_user.organization_id
    return jsonify({
        'success': True,
        'email_trends': get_email_trends(org_id, days),
        'campaign_performance': get_campaign_performance(org_id, 6)
    })
