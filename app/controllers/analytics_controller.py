"""
Analytics Controller - Enterprise Email Analytics Dashboard
Real-time metrics, interactive charts, and comprehensive insights
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
    """Get date range based on period"""
    now = datetime.utcnow()
    if period == '24h':
        start = now - timedelta(hours=24)
    elif period == '7d':
        start = now - timedelta(days=7)
    elif period == '30d':
        start = now - timedelta(days=30)
    elif period == '90d':
        start = now - timedelta(days=90)
    elif period == '12m':
        start = now - timedelta(days=365)
    else:
        start = now - timedelta(days=30)
    return start, now


@analytics_bp.route('/')
@login_required
def index():
    """Main analytics dashboard"""
    try:
        org_id = current_user.organization_id
        period = request.args.get('period', '30d')
        start_date, end_date = get_date_range(period)
        
        # Get all analytics data
        overview = get_overview_stats(org_id, start_date, end_date)
        email_trends = get_email_trends(org_id, start_date, end_date)
        campaign_stats = get_campaign_stats(org_id, start_date, end_date)
        contact_growth = get_contact_growth(org_id, start_date, end_date)
        top_campaigns = get_top_campaigns(org_id, start_date, end_date)
        hourly_dist = get_hourly_distribution(org_id, start_date, end_date)
        domain_stats = get_domain_stats(org_id)
        engagement_funnel = get_engagement_funnel(org_id, start_date, end_date)
        
        return render_template('dashboard/analytics/index.html',
            overview=overview,
            email_trends=json.dumps(email_trends),
            campaign_stats=campaign_stats,
            contact_growth=json.dumps(contact_growth),
            top_campaigns=top_campaigns,
            hourly_dist=json.dumps(hourly_dist),
            domain_stats=domain_stats,
            engagement_funnel=engagement_funnel,
            period=period
        )
        
    except Exception as e:
        logger.error(f"Analytics error: {e}", exc_info=True)
        return render_template('dashboard/analytics/index.html',
            overview=get_empty_overview(),
            email_trends='[]',
            campaign_stats={'total': 0, 'sent': 0, 'drafts': 0, 'scheduled': 0},
            contact_growth='[]',
            top_campaigns=[],
            hourly_dist='[]',
            domain_stats=[],
            engagement_funnel={'sent': 0, 'delivered': 0, 'opened': 0, 'clicked': 0},
            period='30d'
        )


def get_empty_overview():
    """Return empty overview stats"""
    return {
        'total_sent': 0, 'delivered': 0, 'opened': 0, 'clicked': 0,
        'bounced': 0, 'unsubscribed': 0, 'delivery_rate': 0,
        'open_rate': 0, 'click_rate': 0, 'bounce_rate': 0,
        'growth': 0, 'total_contacts': 0, 'active_contacts': 0,
        'avg_daily': 0, 'spam_rate': 0, 'total_growth': 0,
        'delivery_growth': 0, 'open_growth': 0, 'spam': 0,
        'unsubscribed_contacts': 0
    }


def get_overview_stats(org_id, start_date, end_date):
    """Get comprehensive overview statistics"""
    try:
        # Total emails sent
        emails_result = db.session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status IN ('sent', 'delivered') THEN 1 END) as delivered,
                COUNT(CASE WHEN status = 'opened' THEN 1 END) as opened,
                COUNT(CASE WHEN status = 'clicked' THEN 1 END) as clicked,
                COUNT(CASE WHEN status IN ('bounced', 'failed') THEN 1 END) as bounced,
                COUNT(CASE WHEN status = 'unsubscribed' THEN 1 END) as unsubscribed,
                COUNT(CASE WHEN status = 'spam' THEN 1 END) as spam
            FROM emails 
            WHERE organization_id = :org_id 
            AND created_at >= :start_date
        """), {'org_id': org_id, 'start_date': start_date})
        
        row = emails_result.fetchone()
        
        total = row[0] or 0
        delivered = row[1] or 0
        opened = row[2] or 0
        clicked = row[3] or 0
        bounced = row[4] or 0
        unsubscribed = row[5] or 0
        spam = row[6] or 0
        
        # Calculate rates
        delivery_rate = (delivered / total * 100) if total > 0 else 0
        open_rate = (opened / delivered * 100) if delivered > 0 else 0
        click_rate = (clicked / opened * 100) if opened > 0 else 0
        bounce_rate = (bounced / total * 100) if total > 0 else 0
        spam_rate = (spam / total * 100) if total > 0 else 0
        
        # Calculate days in range
        days = (end_date - start_date).days or 1
        avg_daily = total / days
        
        # Get previous period for comparison
        period_length = end_date - start_date
        prev_start = start_date - period_length
        
        prev_result = db.session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status IN ('sent', 'delivered') THEN 1 END) as delivered,
                COUNT(CASE WHEN status = 'opened' THEN 1 END) as opened
            FROM emails 
            WHERE organization_id = :org_id 
            AND created_at >= :prev_start AND created_at < :start_date
        """), {'org_id': org_id, 'prev_start': prev_start, 'start_date': start_date})
        
        prev_row = prev_result.fetchone()
        prev_total = prev_row[0] or 0
        prev_delivered = prev_row[1] or 0
        prev_opened = prev_row[2] or 0
        
        # Calculate growth percentages
        total_growth = ((total - prev_total) / prev_total * 100) if prev_total > 0 else 0
        delivery_growth = ((delivered - prev_delivered) / prev_delivered * 100) if prev_delivered > 0 else 0
        open_growth = ((opened - prev_opened) / prev_opened * 100) if prev_opened > 0 else 0
        
        # Contact stats
        contacts_result = db.session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'active' OR status IS NULL THEN 1 END) as active,
                COUNT(CASE WHEN status = 'unsubscribed' THEN 1 END) as unsubscribed
            FROM contacts 
            WHERE organization_id = :org_id
        """), {'org_id': org_id})
        
        contact_row = contacts_result.fetchone()
        
        return {
            'total_sent': total,
            'delivered': delivered,
            'opened': opened,
            'clicked': clicked,
            'bounced': bounced,
            'unsubscribed': unsubscribed,
            'spam': spam,
            'delivery_rate': round(delivery_rate, 1),
            'open_rate': round(open_rate, 1),
            'click_rate': round(click_rate, 1),
            'bounce_rate': round(bounce_rate, 1),
            'spam_rate': round(spam_rate, 2),
            'total_growth': round(total_growth, 1),
            'delivery_growth': round(delivery_growth, 1),
            'open_growth': round(open_growth, 1),
            'avg_daily': round(avg_daily, 0),
            'total_contacts': contact_row[0] or 0,
            'active_contacts': contact_row[1] or 0,
            'unsubscribed_contacts': contact_row[2] or 0
        }
        
    except Exception as e:
        logger.error(f"Overview stats error: {e}")
        return get_empty_overview()


def get_email_trends(org_id, start_date, end_date):
    """Get daily email statistics for trend charts"""
    try:
        result = db.session.execute(text("""
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as total,
                COUNT(CASE WHEN status IN ('sent', 'delivered') THEN 1 END) as delivered,
                COUNT(CASE WHEN status = 'opened' THEN 1 END) as opened,
                COUNT(CASE WHEN status = 'clicked' THEN 1 END) as clicked,
                COUNT(CASE WHEN status IN ('bounced', 'failed') THEN 1 END) as bounced
            FROM emails 
            WHERE organization_id = :org_id 
            AND created_at >= :start_date
            GROUP BY DATE(created_at)
            ORDER BY date ASC
        """), {'org_id': org_id, 'start_date': start_date})
        
        trends = []
        for row in result:
            trends.append({
                'date': row[0].strftime('%Y-%m-%d') if row[0] else '',
                'label': row[0].strftime('%b %d') if row[0] else '',
                'total': row[1] or 0,
                'delivered': row[2] or 0,
                'opened': row[3] or 0,
                'clicked': row[4] or 0,
                'bounced': row[5] or 0
            })
        
        return trends
        
    except Exception as e:
        logger.error(f"Email trends error: {e}")
        return []


def get_campaign_stats(org_id, start_date, end_date):
    """Get campaign statistics"""
    try:
        result = db.session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status IN ('sent', 'completed') THEN 1 END) as sent,
                COUNT(CASE WHEN status = 'draft' THEN 1 END) as drafts,
                COUNT(CASE WHEN status = 'scheduled' THEN 1 END) as scheduled,
                COUNT(CASE WHEN status = 'sending' THEN 1 END) as sending,
                SUM(COALESCE(emails_sent, sent_count, 0)) as total_emails
            FROM campaigns 
            WHERE organization_id = :org_id
            AND created_at >= :start_date
        """), {'org_id': org_id, 'start_date': start_date})
        
        row = result.fetchone()
        
        return {
            'total': row[0] or 0,
            'sent': row[1] or 0,
            'drafts': row[2] or 0,
            'scheduled': row[3] or 0,
            'sending': row[4] or 0,
            'total_emails': row[5] or 0
        }
        
    except Exception as e:
        logger.error(f"Campaign stats error: {e}")
        return {'total': 0, 'sent': 0, 'drafts': 0, 'scheduled': 0, 'sending': 0, 'total_emails': 0}


def get_contact_growth(org_id, start_date, end_date):
    """Get contact growth over time"""
    try:
        # Get total before period
        base_result = db.session.execute(text("""
            SELECT COUNT(*) FROM contacts 
            WHERE organization_id = :org_id 
            AND created_at < :start_date
        """), {'org_id': org_id, 'start_date': start_date})
        
        base_count = base_result.scalar() or 0
        
        result = db.session.execute(text("""
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as new_contacts
            FROM contacts 
            WHERE organization_id = :org_id 
            AND created_at >= :start_date
            GROUP BY DATE(created_at)
            ORDER BY date ASC
        """), {'org_id': org_id, 'start_date': start_date})
        
        growth = []
        cumulative = base_count
        for row in result:
            cumulative += row[1] or 0
            growth.append({
                'date': row[0].strftime('%Y-%m-%d') if row[0] else '',
                'label': row[0].strftime('%b %d') if row[0] else '',
                'new': row[1] or 0,
                'total': cumulative
            })
        
        return growth
        
    except Exception as e:
        logger.error(f"Contact growth error: {e}")
        return []


def get_top_campaigns(org_id, start_date, end_date, limit=5):
    """Get top performing campaigns"""
    try:
        result = db.session.execute(text("""
            SELECT 
                c.id, c.name, c.subject, c.status,
                COALESCE(c.emails_sent, c.sent_count, 0) as sent,
                COALESCE(c.total_recipients, 0) as recipients,
                c.created_at,
                c.open_rate,
                c.click_rate
            FROM campaigns c
            WHERE c.organization_id = :org_id
            AND c.status IN ('sent', 'completed', 'sending')
            ORDER BY COALESCE(c.emails_sent, c.sent_count, 0) DESC
            LIMIT :limit
        """), {'org_id': org_id, 'limit': limit})
        
        campaigns = []
        for row in result:
            campaigns.append({
                'id': row[0],
                'name': row[1] or 'Untitled',
                'subject': row[2] or '',
                'status': row[3],
                'sent': row[4] or 0,
                'recipients': row[5] or 0,
                'created_at': row[6].strftime('%b %d, %Y') if row[6] else '',
                'open_rate': row[7] or 0,
                'click_rate': row[8] or 0
            })
        
        return campaigns
        
    except Exception as e:
        logger.error(f"Top campaigns error: {e}")
        return []


def get_hourly_distribution(org_id, start_date, end_date):
    """Get email sending distribution by hour"""
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
        """), {'org_id': org_id, 'start_date': start_date})
        
        # Initialize all hours
        hourly = {i: 0 for i in range(24)}
        for row in result:
            hourly[int(row[0])] = row[1] or 0
        
        return [{'hour': h, 'label': f'{h:02d}:00', 'count': c} for h, c in hourly.items()]
        
    except Exception as e:
        logger.error(f"Hourly distribution error: {e}")
        return [{'hour': i, 'label': f'{i:02d}:00', 'count': 0} for i in range(24)]


def get_domain_stats(org_id):
    """Get domain performance statistics"""
    try:
        result = db.session.execute(text("""
            SELECT 
                d.domain,
                d.dns_verified,
                d.dkim_verified,
                d.spf_verified,
                d.created_at
            FROM domains d
            WHERE d.organization_id = :org_id
            ORDER BY d.created_at DESC
            LIMIT 5
        """), {'org_id': org_id})
        
        domains = []
        for row in result:
            # Calculate health score based on verification status
            health = 0
            if row[1]: health += 34
            if row[2]: health += 33
            if row[3]: health += 33
            
            domains.append({
                'domain': row[0],
                'dns_verified': row[1] or False,
                'dkim_verified': row[2] or False,
                'spf_verified': row[3] or False,
                'health_score': health,
                'created_at': row[4].strftime('%b %d, %Y') if row[4] else ''
            })
        
        return domains
        
    except Exception as e:
        logger.error(f"Domain stats error: {e}")
        return []


def get_engagement_funnel(org_id, start_date, end_date):
    """Get engagement funnel data"""
    try:
        result = db.session.execute(text("""
            SELECT 
                COUNT(*) as sent,
                COUNT(CASE WHEN status IN ('sent', 'delivered', 'opened', 'clicked') THEN 1 END) as delivered,
                COUNT(CASE WHEN status IN ('opened', 'clicked') THEN 1 END) as opened,
                COUNT(CASE WHEN status = 'clicked' THEN 1 END) as clicked
            FROM emails 
            WHERE organization_id = :org_id 
            AND created_at >= :start_date
        """), {'org_id': org_id, 'start_date': start_date})
        
        row = result.fetchone()
        
        return {
            'sent': row[0] or 0,
            'delivered': row[1] or 0,
            'opened': row[2] or 0,
            'clicked': row[3] or 0
        }
        
    except Exception as e:
        logger.error(f"Engagement funnel error: {e}")
        return {'sent': 0, 'delivered': 0, 'opened': 0, 'clicked': 0}


# API Endpoints
@analytics_bp.route('/api/overview')
@login_required
def api_overview():
    """API endpoint for overview stats"""
    try:
        period = request.args.get('period', '30d')
        start_date, end_date = get_date_range(period)
        overview = get_overview_stats(current_user.organization_id, start_date, end_date)
        return jsonify({'success': True, 'data': overview})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@analytics_bp.route('/api/trends')
@login_required
def api_trends():
    """API endpoint for email trends"""
    try:
        period = request.args.get('period', '30d')
        start_date, end_date = get_date_range(period)
        trends = get_email_trends(current_user.organization_id, start_date, end_date)
        return jsonify({'success': True, 'data': trends})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@analytics_bp.route('/api/realtime')
@login_required
def api_realtime():
    """API endpoint for real-time stats"""
    try:
        org_id = current_user.organization_id
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        result = db.session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status IN ('sent', 'delivered') THEN 1 END) as delivered,
                COUNT(CASE WHEN status = 'opened' THEN 1 END) as opened,
                COUNT(CASE WHEN status = 'clicked' THEN 1 END) as clicked
            FROM emails 
            WHERE organization_id = :org_id 
            AND created_at >= :start
        """), {'org_id': org_id, 'start': one_hour_ago})
        
        row = result.fetchone()
        
        return jsonify({
            'success': True,
            'data': {
                'sent': row[0] or 0,
                'delivered': row[1] or 0,
                'opened': row[2] or 0,
                'clicked': row[3] or 0,
                'timestamp': datetime.utcnow().isoformat()
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@analytics_bp.route('/api/export')
@login_required
def api_export():
    """Export analytics data as CSV"""
    try:
        period = request.args.get('period', '30d')
        start_date, end_date = get_date_range(period)
        org_id = current_user.organization_id
        
        result = db.session.execute(text("""
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as total,
                COUNT(CASE WHEN status IN ('sent', 'delivered') THEN 1 END) as delivered,
                COUNT(CASE WHEN status = 'opened' THEN 1 END) as opened,
                COUNT(CASE WHEN status = 'clicked' THEN 1 END) as clicked,
                COUNT(CASE WHEN status IN ('bounced', 'failed') THEN 1 END) as bounced
            FROM emails 
            WHERE organization_id = :org_id 
            AND created_at >= :start_date
            GROUP BY DATE(created_at)
            ORDER BY date ASC
        """), {'org_id': org_id, 'start_date': start_date})
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Date', 'Total Sent', 'Delivered', 'Opened', 'Clicked', 'Bounced'])
        
        for row in result:
            writer.writerow([
                row[0].strftime('%Y-%m-%d') if row[0] else '',
                row[1] or 0,
                row[2] or 0,
                row[3] or 0,
                row[4] or 0,
                row[5] or 0
            ])
        
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename=analytics_{period}.csv'}
        )
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
