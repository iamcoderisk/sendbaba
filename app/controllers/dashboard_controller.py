from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.email import Email
from app.models.contact import Contact
from app.models.domain import Domain
from app.models.campaign import Campaign
from app.utils.permissions import can_see_all_org_data
from sqlalchemy import func, and_
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard/')
@dashboard_bp.route('/dashboard')
@login_required
def index():
    """Dashboard with role-based stats"""
    try:
        # Base filters
        org_filter = {'organization_id': current_user.organization_id}
        
        # Add user filter for non-admins
        if not can_see_all_org_data():
            user_filter = {'created_by_user_id': current_user.id}
        else:
            user_filter = {}
        
        # Combine filters
        email_filters = {**org_filter}
        contact_filters = {**org_filter, **user_filter}
        domain_filters = {**org_filter, **user_filter}
        campaign_filters = {**org_filter, **user_filter}
        
        # Get stats based on role
        emails_sent = Email.query.filter_by(**email_filters).filter(
            Email.created_at >= datetime.utcnow() - timedelta(days=30)
        ).count()
        
        total_contacts = Contact.query.filter_by(**contact_filters).filter_by(status='active').count()
        
        domains = Domain.query.filter_by(**domain_filters).count()
        
        queued = Email.query.filter_by(**email_filters).filter_by(status='queued').count()
        
        # Recent campaigns
        recent_campaigns = Campaign.query.filter_by(**campaign_filters).order_by(
            Campaign.created_at.desc()
        ).limit(5).all()
        
        stats = {
            'emails_sent': emails_sent,
            'total_contacts': total_contacts,
            'domains': domains,
            'queued': queued,
            'user_role': current_user.role,
            'is_admin': can_see_all_org_data()
        }
        
        logger.info(f"Dashboard stats for user {current_user.id} (role: {current_user.role}): {stats}")
        
        return render_template('dashboard/index.html', 
                             stats=stats, 
                             recent_campaigns=recent_campaigns)
    
    except Exception as e:
        logger.error(f"Dashboard error: {e}", exc_info=True)
        return render_template('dashboard/index.html', 
                             stats={
                                 'emails_sent': 0,
                                 'total_contacts': 0,
                                 'domains': 0,
                                 'queued': 0,
                                 'user_role': getattr(current_user, 'role', 'member'),
                                 'is_admin': False
                             },
                             recent_campaigns=[])


@dashboard_bp.route('/dashboard/stats')
@login_required
def stats():
    """API endpoint for dashboard stats"""
    try:
        org_filter = {'organization_id': current_user.organization_id}
        
        if not can_see_all_org_data():
            user_filter = {'created_by_user_id': current_user.id}
        else:
            user_filter = {}
        
        contact_filters = {**org_filter, **user_filter}
        
        stats = {
            'total_contacts': Contact.query.filter_by(**contact_filters).count(),
            'active_contacts': Contact.query.filter_by(**contact_filters).filter_by(status='active').count(),
            'emails_sent_today': Email.query.filter_by(**org_filter).filter(
                Email.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
            ).count(),
            'user_role': current_user.role,
            'viewing_scope': 'organization' if can_see_all_org_data() else 'personal'
        }
        
        return jsonify(stats)
    
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return jsonify({'error': str(e)}), 500

@dashboard_bp.route('/dashboard/send-email', methods=['GET', 'POST'])
@login_required
def send_single_email():
    """Send single email page"""
    try:
        domains_result = db.session.execute(
            text("SELECT id, domain_name, dns_verified FROM domains WHERE organization_id = :org_id"),
            {'org_id': current_user.organization_id}
        )
        domains = [dict(row._mapping) for row in domains_result]
        return render_template('dashboard/send_email.html', domains=domains)
    except Exception as e:
        logger.error(f"Send email page error: {e}", exc_info=True)
        return render_template('dashboard/send_email.html', domains=[])
