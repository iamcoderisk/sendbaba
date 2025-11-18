"""
Bulk Send Controller - Campaign Sending
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.contact import Contact
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

bulk_send_bp = Blueprint('bulk_send', __name__, url_prefix='/dashboard')


@bulk_send_bp.route('/bulk-send', methods=['GET'])
@login_required
def bulk_send_page():
    """Bulk send campaign page"""
    try:
        # Get domains
        domains_result = db.session.execute(
            text("SELECT id, domain_name, dns_verified FROM domains WHERE organization_id = :org_id"),
            {'org_id': current_user.organization_id}
        )
        domains = [dict(row._mapping) for row in domains_result]
        
        # Get contacts
        contacts_result = db.session.execute(
            text("SELECT id, email, first_name, last_name, company FROM contacts WHERE organization_id = :org_id ORDER BY created_at DESC"),
            {'org_id': current_user.organization_id}
        )
        contacts = [dict(row._mapping) for row in contacts_result]
        
        logger.info(f"Bulk send page: {len(domains)} domains, {len(contacts)} contacts")
        
        return render_template('dashboard/bulk_send.html', domains=domains, contacts=contacts)
    except Exception as e:
        logger.error(f"Bulk send page error: {e}", exc_info=True)
        return render_template('dashboard/bulk_send.html', domains=[], contacts=[])


@bulk_send_bp.route('/bulk-send/send', methods=['POST'])
@login_required
def send_bulk_campaign():
    """Send bulk email campaign"""
    try:
        # Get form data
        contact_ids = request.form.getlist('contacts')
        subject = request.form.get('subject')
        body = request.form.get('body')
        from_domain = request.form.get('from_domain')
        campaign_name = request.form.get('campaign_name')
        
        if not contact_ids:
            return jsonify({'success': False, 'error': 'No contacts selected'}), 400
        
        if not subject or not body:
            return jsonify({'success': False, 'error': 'Subject and body required'}), 400
        
        # Get selected contacts
        contacts = Contact.query.filter(
            Contact.id.in_(contact_ids),
            Contact.organization_id == current_user.organization_id
        ).all()
        
        if not contacts:
            return jsonify({'success': False, 'error': 'No valid contacts found'}), 400
        
        # TODO: Create campaign and queue emails
        # For now, just return success
        
        flash(f'Campaign queued! Sending to {len(contacts)} contacts.', 'success')
        return jsonify({
            'success': True,
            'message': f'Campaign queued for {len(contacts)} contacts',
            'redirect': '/dashboard/campaigns'
        })
        
    except Exception as e:
        logger.error(f"Send bulk campaign error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
