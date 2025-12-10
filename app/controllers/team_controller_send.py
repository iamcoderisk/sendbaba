# Single Email Send Routes - to be merged into team_controller.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

def get_org_id():
    return str(current_user.organization_id)

# Route: /dashboard/team/send-email
def send_single_email_route():
    """Send a single email with template picker"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        
        # Get templates (system + user's org)
        templates = db.session.execute(text("""
            SELECT id, name, subject, html_content, category
            FROM email_templates 
            WHERE organization_id IN ('system', :org_id)
            ORDER BY 
                CASE WHEN name = 'Blank' THEN 0 ELSE 1 END,
                category, name
        """), {'org_id': org_id}).fetchall()
        
        template_list = [{
            'id': t[0], 'name': t[1], 'subject': t[2] or '', 
            'html_content': t[3] or '', 'category': t[4] or 'custom'
        } for t in templates]
        
        # Get verified domains for From email dropdown
        domains = db.session.execute(text("""
            SELECT id, domain FROM domains 
            WHERE organization_id = :org_id AND is_verified = true
            ORDER BY domain
        """), {'org_id': org_id}).fetchall()
        
        domain_list = [{'id': d[0], 'domain': d[1]} for d in domains]
        
        # Add default sendbaba.com option
        domain_list.insert(0, {'id': 'default', 'domain': 'sendbaba.com'})
        
        # Get recent sent emails
        recent = db.session.execute(text("""
            SELECT id, recipient_email, recipient_name, subject, status, sent_at, created_at
            FROM single_emails 
            WHERE organization_id = :org_id
            ORDER BY created_at DESC LIMIT 10
        """), {'org_id': org_id}).fetchall()
        
        recent_emails = [{
            'id': r[0], 'recipient_email': r[1], 'recipient_name': r[2],
            'subject': r[3], 'status': r[4], 'sent_at': r[5], 'created_at': r[6]
        } for r in recent]
        
        # Get contacts for autocomplete
        contacts = db.session.execute(text("""
            SELECT email, first_name, last_name FROM contacts 
            WHERE organization_id = :org_id 
            ORDER BY first_name, email LIMIT 200
        """), {'org_id': org_id}).fetchall()
        
        contact_list = [{
            'email': c[0], 
            'first_name': c[1] or '',
            'last_name': c[2] or '',
            'name': f"{c[1] or ''} {c[2] or ''}".strip() or c[0].split('@')[0]
        } for c in contacts]
        
        # Get user info for default from name
        user_name = current_user.name or current_user.email.split('@')[0] if hasattr(current_user, 'name') else ''
        
        return {
            'templates': template_list,
            'domains': domain_list,
            'recent_emails': recent_emails,
            'contacts': contact_list,
            'user_name': user_name,
            'user_email': current_user.email
        }
    except Exception as e:
        logger.error(f"Send email page error: {e}")
        db.session.rollback()
        return {
            'templates': [], 'domains': [{'id': 'default', 'domain': 'sendbaba.com'}],
            'recent_emails': [], 'contacts': [], 'user_name': '', 'user_email': ''
        }
