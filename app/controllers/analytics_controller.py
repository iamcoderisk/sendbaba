"""
Analytics Controller - SendBaba Email Analytics Dashboard
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
    now = datetime.utcnow()
    periods = {'24h': timedelta(hours=24), '7d': timedelta(days=7), '30d': timedelta(days=30), '90d': timedelta(days=90), '12m': timedelta(days=365)}
    return now - periods.get(period, timedelta(days=30)), now

@analytics_bp.route('/')
@login_required
def index():
    try:
        org_id = current_user.organization_id
        period = request.args.get('period', '30d')
        start_date, end_date = get_date_range(period)
        
        overview = get_overview_stats(org_id, start_date, end_date)
        email_trends = get_email_trends(org_id, start_date, end_date)
        campaign_stats = get_campaign_stats(org_id, start_date, end_date)
        top_campaigns = get_top_campaigns(org_id, start_date, end_date)
        hourly_dist = get_hourly_distribution(org_id, start_date, end_date)
        domain_stats = get_domain_stats(org_id)
        engagement_funnel = get_engagement_funnel(org_id, start_date, end_date)
        queue_stats = get_queue_stats(org_id)
        status_breakdown = get_status_breakdown(org_id, start_date, end_date)
        
        return render_template('dashboard/analytics/index.html',
            overview=overview, email_trends=json.dumps(email_trends), campaign_stats=campaign_stats,
            top_campaigns=top_campaigns, hourly_dist=json.dumps(hourly_dist), domain_stats=domain_stats,
            engagement_funnel=engagement_funnel, queue_stats=queue_stats, status_breakdown=json.dumps(status_breakdown), period=period)
    except Exception as e:
        logger.error(f"Analytics error: {e}", exc_info=True)
        return render_template('dashboard/analytics/index.html',
            overview=get_empty_overview(), email_trends='[]', campaign_stats={'total': 0, 'sent': 0, 'drafts': 0, 'scheduled': 0},
            top_campaigns=[], hourly_dist='[]', domain_stats=[],
            engagement_funnel={'sent': 0, 'delivered': 0, 'opened': 0, 'clicked': 0, 'failed': 0},
            queue_stats={'pending': 0, 'processing': 0, 'completed_today': 0, 'failed_today': 0}, status_breakdown='[]', period='30d')

def get_empty_overview():
    return {'total_sent': 0, 'delivered': 0, 'opened': 0, 'clicked': 0, 'bounced': 0, 'unsubscribed': 0, 'delivery_rate': 0,
            'open_rate': 0, 'click_rate': 0, 'bounce_rate': 0, 'total_growth': 0, 'total_contacts': 0, 'active_contacts': 0,
            'avg_daily': 0, 'spam_rate': 0, 'delivery_growth': 0, 'open_growth': 0, 'spam': 0}

def get_overview_stats(org_id, start_date, end_date):
    try:
        result = db.session.execute(text("""
            SELECT COUNT(*) as total,
                COUNT(CASE WHEN status IN ('sent', 'delivered', 'opened', 'clicked') THEN 1 END) as delivered,
                COUNT(CASE WHEN status IN ('opened', 'clicked') THEN 1 END) as opened,
                COUNT(CASE WHEN status = 'clicked' THEN 1 END) as clicked,
                COUNT(CASE WHEN status IN ('bounced', 'failed', 'rejected', 'error') THEN 1 END) as bounced,
                COUNT(CASE WHEN status = 'unsubscribed' THEN 1 END) as unsubscribed,
                COUNT(CASE WHEN status = 'spam' OR status = 'complaint' THEN 1 END) as spam
            FROM emails WHERE organization_id = :org_id AND created_at >= :start_date
        """), {'org_id': org_id, 'start_date': start_date})
        row = result.fetchone()
        
        total, delivered, opened, clicked, bounced, unsubscribed, spam = row[0] or 0, row[1] or 0, row[2] or 0, row[3] or 0, row[4] or 0, row[5] or 0, row[6] or 0
        
        delivery_rate = round((delivered / total * 100), 1) if total > 0 else 0
        open_rate = round((opened / delivered * 100), 1) if delivered > 0 else 0
        click_rate = round((clicked / opened * 100), 1) if opened > 0 else 0
        bounce_rate = round((bounced / total * 100), 1) if total > 0 else 0
        spam_rate = round((spam / total * 100), 2) if total > 0 else 0
        
        days = max((end_date - start_date).days, 1)
        avg_daily = round(total / days, 0)
        
        period_length = end_date - start_date
        prev_start = start_date - period_length
        prev_result = db.session.execute(text("""
            SELECT COUNT(*) as total,
                COUNT(CASE WHEN status IN ('sent', 'delivered', 'opened', 'clicked') THEN 1 END) as delivered,
                COUNT(CASE WHEN status IN ('opened', 'clicked') THEN 1 END) as opened
            FROM emails WHERE organization_id = :org_id AND created_at >= :prev_start AND created_at < :start_date
        """), {'org_id': org_id, 'prev_start': prev_start, 'start_date': start_date})
        prev_row = prev_result.fetchone()
        prev_total, prev_delivered, prev_opened = prev_row[0] or 0, prev_row[1] or 0, prev_row[2] or 0
        
        total_growth = round(((total - prev_total) / prev_total * 100), 1) if prev_total > 0 else 0
        delivery_growth = round(((delivered - prev_delivered) / prev_delivered * 100), 1) if prev_delivered > 0 else 0
        open_growth = round(((opened - prev_opened) / prev_opened * 100), 1) if prev_opened > 0 else 0
        
        contacts_result = db.session.execute(text("""
            SELECT COUNT(*) as total,
                COUNT(CASE WHEN status = 'active' OR status IS NULL OR status = '' THEN 1 END) as active,
                COUNT(CASE WHEN status = 'unsubscribed' THEN 1 END) as unsubscribed
            FROM contacts WHERE organization_id = :org_id
        """), {'org_id': org_id})
        contact_row = contacts_result.fetchone()
        
        return {'total_sent': total, 'delivered': delivered, 'opened': opened, 'clicked': clicked, 'bounced': bounced,
                'unsubscribed': unsubscribed, 'spam': spam, 'delivery_rate': delivery_rate, 'open_rate': open_rate,
                'click_rate': click_rate, 'bounce_rate': bounce_rate, 'spam_rate': spam_rate, 'total_growth': total_growth,
                'delivery_growth': delivery_growth, 'open_growth': open_growth, 'avg_daily': avg_daily,
                'total_contacts': contact_row[0] or 0, 'active_contacts': contact_row[1] or 0, 'unsubscribed_contacts': contact_row[2] or 0}
    except Exception as e:
        logger.error(f"Overview stats error: {e}")
        return get_empty_overview()

def get_queue_stats(org_id):
    try:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        result = db.session.execute(text("""
            SELECT COUNT(CASE WHEN status = 'pending' OR status = 'queued' THEN 1 END) as pending,
                COUNT(CASE WHEN status = 'sending' OR status = 'processing' THEN 1 END) as processing,
                COUNT(CASE WHEN status IN ('sent', 'delivered', 'opened', 'clicked') AND created_at >= :today THEN 1 END) as completed_today,
                COUNT(CASE WHEN status IN ('failed', 'bounced', 'error', 'rejected') AND created_at >= :today THEN 1 END) as failed_today
            FROM emails WHERE organization_id = :org_id
        """), {'org_id': org_id, 'today': today_start})
        row = result.fetchone()
        return {'pending': row[0] or 0, 'processing': row[1] or 0, 'completed_today': row[2] or 0, 'failed_today': row[3] or 0}
    except Exception as e:
        logger.error(f"Queue stats error: {e}")
        return {'pending': 0, 'processing': 0, 'completed_today': 0, 'failed_today': 0}

def get_email_trends(org_id, start_date, end_date):
    try:
        result = db.session.execute(text("""
            SELECT DATE(created_at) as date, COUNT(*) as total,
                COUNT(CASE WHEN status IN ('sent', 'delivered', 'opened', 'clicked') THEN 1 END) as delivered,
                COUNT(CASE WHEN status IN ('opened', 'clicked') THEN 1 END) as opened,
                COUNT(CASE WHEN status = 'clicked' THEN 1 END) as clicked,
                COUNT(CASE WHEN status IN ('bounced', 'failed', 'error', 'rejected') THEN 1 END) as failed
            FROM emails WHERE organization_id = :org_id AND created_at >= :start_date
            GROUP BY DATE(created_at) ORDER BY date ASC
        """), {'org_id': org_id, 'start_date': start_date})
        return [{'date': row[0].strftime('%Y-%m-%d') if row[0] else '', 'label': row[0].strftime('%b %d') if row[0] else '',
                 'total': row[1] or 0, 'delivered': row[2] or 0, 'opened': row[3] or 0, 'clicked': row[4] or 0, 'failed': row[5] or 0} for row in result]
    except Exception as e:
        logger.error(f"Email trends error: {e}")
        return []

def get_campaign_stats(org_id, start_date, end_date):
    try:
        result = db.session.execute(text("""
            SELECT COUNT(*) as total, COUNT(CASE WHEN status IN ('sent', 'completed') THEN 1 END) as sent,
                COUNT(CASE WHEN status = 'draft' THEN 1 END) as drafts, COUNT(CASE WHEN status = 'scheduled' THEN 1 END) as scheduled,
                COUNT(CASE WHEN status = 'sending' THEN 1 END) as sending
            FROM campaigns WHERE organization_id = :org_id AND created_at >= :start_date
        """), {'org_id': org_id, 'start_date': start_date})
        row = result.fetchone()
        return {'total': row[0] or 0, 'sent': row[1] or 0, 'drafts': row[2] or 0, 'scheduled': row[3] or 0, 'sending': row[4] or 0}
    except Exception as e:
        logger.error(f"Campaign stats error: {e}")
        return {'total': 0, 'sent': 0, 'drafts': 0, 'scheduled': 0, 'sending': 0}

def get_top_campaigns(org_id, start_date, end_date, limit=5):
    try:
        result = db.session.execute(text("""
            SELECT c.id, c.name, c.subject, c.status, COALESCE(c.emails_sent, c.sent_count, 0) as sent,
                c.created_at, c.open_rate, c.click_rate
            FROM campaigns c WHERE c.organization_id = :org_id AND c.status IN ('sent', 'completed', 'sending')
            ORDER BY c.created_at DESC, COALESCE(c.emails_sent, c.sent_count, 0) DESC LIMIT :limit
        """), {'org_id': org_id, 'limit': limit})
        
        campaigns = []
        for row in result:
            sent = row[4] or 0
            delivery_rate = 95.0
            if sent > 0:
                try:
                    dr_result = db.session.execute(text("""
                        SELECT COUNT(CASE WHEN status IN ('sent', 'delivered', 'opened', 'clicked') THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0)
                        FROM emails WHERE campaign_id = :campaign_id
                    """), {'campaign_id': row[0]})
                    delivery_rate = round(dr_result.scalar() or 95.0, 1)
                except: pass
            campaigns.append({'id': row[0], 'name': row[1] or 'Untitled', 'subject': row[2] or '', 'status': row[3] or 'draft',
                            'sent': sent, 'created_at': row[5].strftime('%b %d, %Y') if row[5] else '',
                            'open_rate': row[6] or 0, 'click_rate': row[7] or 0, 'delivery_rate': delivery_rate})
        return campaigns
    except Exception as e:
        logger.error(f"Top campaigns error: {e}")
        return []

def get_hourly_distribution(org_id, start_date, end_date):
    try:
        result = db.session.execute(text("""
            SELECT EXTRACT(HOUR FROM created_at)::int as hour, COUNT(*) as count
            FROM emails WHERE organization_id = :org_id AND created_at >= :start_date
            GROUP BY EXTRACT(HOUR FROM created_at) ORDER BY hour
        """), {'org_id': org_id, 'start_date': start_date})
        hourly = {i: 0 for i in range(24)}
        for row in result:
            hourly[int(row[0])] = row[1] or 0
        return [{'hour': h, 'label': f'{h:02d}:00', 'count': c} for h, c in hourly.items()]
    except Exception as e:
        logger.error(f"Hourly distribution error: {e}")
        return [{'hour': i, 'label': f'{i:02d}:00', 'count': 0} for i in range(24)]

def get_domain_stats(org_id):
    try:
        result = db.session.execute(text("""
            SELECT domain, dns_verified, dkim_verified, spf_verified, created_at
            FROM domains WHERE organization_id = :org_id ORDER BY created_at DESC LIMIT 5
        """), {'org_id': org_id})
        domains = []
        for row in result:
            health = (34 if row[1] else 0) + (33 if row[2] else 0) + (33 if row[3] else 0)
            domains.append({'domain': row[0], 'dns_verified': row[1] or False, 'dkim_verified': row[2] or False,
                          'spf_verified': row[3] or False, 'health_score': health, 'created_at': row[4].strftime('%b %d, %Y') if row[4] else ''})
        return domains
    except Exception as e:
        logger.error(f"Domain stats error: {e}")
        return []

def get_engagement_funnel(org_id, start_date, end_date):
    try:
        result = db.session.execute(text("""
            SELECT COUNT(*) as sent,
                COUNT(CASE WHEN status IN ('sent', 'delivered', 'opened', 'clicked') THEN 1 END) as delivered,
                COUNT(CASE WHEN status IN ('opened', 'clicked') THEN 1 END) as opened,
                COUNT(CASE WHEN status = 'clicked' THEN 1 END) as clicked,
                COUNT(CASE WHEN status IN ('bounced', 'failed', 'error', 'rejected') THEN 1 END) as failed
            FROM emails WHERE organization_id = :org_id AND created_at >= :start_date
        """), {'org_id': org_id, 'start_date': start_date})
        row = result.fetchone()
        return {'sent': row[0] or 0, 'delivered': row[1] or 0, 'opened': row[2] or 0, 'clicked': row[3] or 0, 'failed': row[4] or 0}
    except Exception as e:
        logger.error(f"Engagement funnel error: {e}")
        return {'sent': 0, 'delivered': 0, 'opened': 0, 'clicked': 0, 'failed': 0}

def get_status_breakdown(org_id, start_date, end_date):
    try:
        result = db.session.execute(text("""
            SELECT status, COUNT(*) as count FROM emails WHERE organization_id = :org_id AND created_at >= :start_date
            GROUP BY status ORDER BY count DESC
        """), {'org_id': org_id, 'start_date': start_date})
        return [{'status': row[0] or 'unknown', 'count': row[1] or 0} for row in result]
    except Exception as e:
        logger.error(f"Status breakdown error: {e}")
        return []

@analytics_bp.route('/api/overview')
@login_required
def api_overview():
    try:
        period = request.args.get('period', '30d')
        start_date, end_date = get_date_range(period)
        return jsonify({'success': True, 'data': get_overview_stats(current_user.organization_id, start_date, end_date)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@analytics_bp.route('/api/realtime')
@login_required
def api_realtime():
    try:
        org_id = current_user.organization_id
        queue_stats = get_queue_stats(org_id)
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        result = db.session.execute(text("""
            SELECT COUNT(*) as total, COUNT(CASE WHEN status IN ('sent', 'delivered') THEN 1 END) as delivered,
                COUNT(CASE WHEN status = 'opened' THEN 1 END) as opened, COUNT(CASE WHEN status = 'clicked' THEN 1 END) as clicked,
                COUNT(CASE WHEN status IN ('failed', 'bounced') THEN 1 END) as failed
            FROM emails WHERE organization_id = :org_id AND created_at >= :start
        """), {'org_id': org_id, 'start': one_hour_ago})
        row = result.fetchone()
        return jsonify({'success': True, 'data': {
            'pending': queue_stats['pending'], 'processing': queue_stats['processing'],
            'completed': queue_stats['completed_today'], 'failed': queue_stats['failed_today'],
            'last_hour': {'sent': row[0] or 0, 'delivered': row[1] or 0, 'opened': row[2] or 0, 'clicked': row[3] or 0, 'failed': row[4] or 0},
            'timestamp': datetime.utcnow().isoformat()
        }})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@analytics_bp.route('/api/export')
@login_required
def api_export():
    try:
        period = request.args.get('period', '30d')
        start_date, end_date = get_date_range(period)
        org_id = current_user.organization_id
        result = db.session.execute(text("""
            SELECT DATE(created_at) as date, COUNT(*) as total,
                COUNT(CASE WHEN status IN ('sent', 'delivered', 'opened', 'clicked') THEN 1 END) as delivered,
                COUNT(CASE WHEN status IN ('opened', 'clicked') THEN 1 END) as opened,
                COUNT(CASE WHEN status = 'clicked' THEN 1 END) as clicked,
                COUNT(CASE WHEN status IN ('bounced', 'failed') THEN 1 END) as failed
            FROM emails WHERE organization_id = :org_id AND created_at >= :start_date
            GROUP BY DATE(created_at) ORDER BY date ASC
        """), {'org_id': org_id, 'start_date': start_date})
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Date', 'Total Sent', 'Delivered', 'Opened', 'Clicked', 'Failed', 'Delivery Rate', 'Open Rate'])
        for row in result:
            total, delivered, opened = row[1] or 0, row[2] or 0, row[3] or 0
            dr = round((delivered / total * 100), 1) if total > 0 else 0
            opr = round((opened / delivered * 100), 1) if delivered > 0 else 0
            writer.writerow([row[0].strftime('%Y-%m-%d') if row[0] else '', total, delivered, opened, row[4] or 0, row[5] or 0, f"{dr}%", f"{opr}%"])
        
        output.seek(0)
        return Response(output.getvalue(), mimetype='text/csv',
                       headers={'Content-Disposition': f'attachment; filename=sendbaba_analytics_{period}_{datetime.utcnow().strftime("%Y%m%d")}.csv'})
    except Exception as e:
        logger.error(f"Export error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
