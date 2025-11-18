from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from app import db
from sqlalchemy import text, func
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard/')
@dashboard_bp.route('/dashboard')
@login_required
def index():
    """Modern dashboard with advanced analytics"""
    try:
        org_id = current_user.organization_id
        
        # Get comprehensive stats
        stats = get_dashboard_stats(org_id)
        
        # Get chart data
        email_trends = get_email_trends(org_id)
        campaign_performance = get_campaign_performance(org_id)
        contact_growth = get_contact_growth(org_id)
        
        return render_template('dashboard/index.html',
                             stats=stats,
                             email_trends=email_trends,
                             campaign_performance=campaign_performance,
                             contact_growth=contact_growth)
    
    except Exception as e:
        logger.error(f"Dashboard error: {e}", exc_info=True)
        return render_template('dashboard/index.html',
                             stats={},
                             email_trends=[],
                             campaign_performance=[],
                             contact_growth=[])


def get_dashboard_stats(org_id):
    """Get comprehensive dashboard statistics"""
    try:
        # Emails sent (30 days)
        emails_result = db.session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'sent' THEN 1 END) as sent,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                COUNT(CASE WHEN status = 'queued' THEN 1 END) as queued
            FROM emails 
            WHERE organization_id = :org_id 
            AND created_at >= :date
        """), {
            'org_id': org_id,
            'date': datetime.utcnow() - timedelta(days=30)
        })
        emails = emails_result.fetchone()
        
        # Contacts
        contacts_result = db.session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active,
                COUNT(CASE WHEN status = 'unsubscribed' THEN 1 END) as unsubscribed
            FROM contacts 
            WHERE organization_id = :org_id
        """), {'org_id': org_id})
        contacts = contacts_result.fetchone()
        
        # Campaigns
        campaigns_result = db.session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'sent' THEN 1 END) as sent,
                COUNT(CASE WHEN status = 'draft' THEN 1 END) as drafts
            FROM campaigns 
            WHERE organization_id = :org_id
        """), {'org_id': org_id})
        campaigns = campaigns_result.fetchone()
        
        # Domains
        domains_result = db.session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN dns_verified = true THEN 1 END) as verified
            FROM domains 
            WHERE organization_id = :org_id
        """), {'org_id': org_id})
        domains = domains_result.fetchone()
        
        # Calculate growth rates
        prev_month_emails = db.session.execute(text("""
            SELECT COUNT(*) FROM emails 
            WHERE organization_id = :org_id 
            AND created_at >= :start AND created_at < :end
        """), {
            'org_id': org_id,
            'start': datetime.utcnow() - timedelta(days=60),
            'end': datetime.utcnow() - timedelta(days=30)
        }).scalar() or 1
        
        email_growth = ((emails[0] - prev_month_emails) / prev_month_emails * 100) if prev_month_emails > 0 else 0
        
        return {
            'emails_sent': emails[1] or 0,
            'emails_total': emails[0] or 0,
            'emails_failed': emails[2] or 0,
            'emails_queued': emails[3] or 0,
            'email_growth': round(email_growth, 1),
            'contacts_total': contacts[0] or 0,
            'contacts_active': contacts[1] or 0,
            'contacts_unsubscribed': contacts[2] or 0,
            'campaigns_total': campaigns[0] or 0,
            'campaigns_sent': campaigns[1] or 0,
            'campaigns_drafts': campaigns[2] or 0,
            'domains_total': domains[0] or 0,
            'domains_verified': domains[1] or 0,
            'delivery_rate': round((emails[1] / emails[0] * 100) if emails[0] > 0 else 0, 1)
        }
    
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return {}


def get_email_trends(org_id):
    """Get email sending trends for last 7 days"""
    try:
        result = db.session.execute(text("""
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'sent' THEN 1 END) as sent,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed
            FROM emails 
            WHERE organization_id = :org_id 
            AND created_at >= :date
            GROUP BY DATE(created_at)
            ORDER BY date ASC
        """), {
            'org_id': org_id,
            'date': datetime.utcnow() - timedelta(days=7)
        })
        
        return [dict(row._mapping) for row in result]
    
    except Exception as e:
        logger.error(f"Email trends error: {e}")
        return []


def get_campaign_performance(org_id):
    """Get top performing campaigns"""
    try:
        result = db.session.execute(text("""
            SELECT 
                name,
                COALESCE(emails_sent, sent_count, 0) as sent,
                COALESCE(total_recipients, 0) as recipients,
                status
            FROM campaigns 
            WHERE organization_id = :org_id 
            ORDER BY created_at DESC
            LIMIT 5
        """), {'org_id': org_id})
        
        return [dict(row._mapping) for row in result]
    
    except Exception as e:
        logger.error(f"Campaign performance error: {e}")
        return []


def get_contact_growth(org_id):
    """Get contact growth over last 30 days"""
    try:
        result = db.session.execute(text("""
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as new_contacts
            FROM contacts 
            WHERE organization_id = :org_id 
            AND created_at >= :date
            GROUP BY DATE(created_at)
            ORDER BY date ASC
        """), {
            'org_id': org_id,
            'date': datetime.utcnow() - timedelta(days=30)
        })
        
        return [dict(row._mapping) for row in result]
    
    except Exception as e:
        logger.error(f"Contact growth error: {e}")
        return []


@dashboard_bp.route('/dashboard/api/stats')
@login_required
def api_stats():
    """API endpoint for real-time stats"""
    try:
        stats = get_dashboard_stats(current_user.organization_id)
        return jsonify({'success': True, 'data': stats})
    except Exception as e:
        logger.error(f"API stats error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
