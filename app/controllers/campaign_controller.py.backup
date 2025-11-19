"""
Modern Campaign Controller - Integrated with Templates
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from sqlalchemy import text
import logging
import uuid
from datetime import datetime
import os

logger = logging.getLogger(__name__)

campaign_bp = Blueprint('campaigns', __name__, url_prefix='/dashboard')


@campaign_bp.route('/campaigns')
@login_required
def list_campaigns():
    """Campaigns page with tabs: Sent, Drafts, Pending"""
    try:
        result = db.session.execute(
            text("""
                SELECT 
                    id, name, subject, status,
                    COALESCE(emails_sent, sent_count, 0) as total_sent,
                    COALESCE(total_recipients, 0) as recipients,
                    created_at
                FROM campaigns 
                WHERE organization_id = :org_id 
                ORDER BY created_at DESC
            """),
            {'org_id': current_user.organization_id}
        )
        
        campaigns = {'sent': [], 'drafts': [], 'pending': []}
        
        for row in result:
            campaign = {
                'id': row[0],
                'name': row[1],
                'subject': row[2],
                'status': row[3],
                'total_sent': row[4],
                'recipients': row[5],
                'created_at': row[6]
            }
            
            if row[3] in ['sent', 'completed']:
                campaigns['sent'].append(campaign)
            elif row[3] == 'draft':
                campaigns['drafts'].append(campaign)
            elif row[3] == 'pending':
                campaigns['pending'].append(campaign)
        
        return render_template('dashboard/campaigns/index.html', campaigns=campaigns)
        
    except Exception as e:
        logger.error(f"List campaigns error: {e}", exc_info=True)
        return render_template('dashboard/campaigns/index.html', campaigns={'sent': [], 'drafts': [], 'pending': []})


@campaign_bp.route('/campaigns/create')
@login_required
def create_campaign():
    """Step 1: Choose template source"""
    return render_template('dashboard/campaigns/create.html')


@campaign_bp.route('/campaigns/templates')
@login_required
def select_template():
    """Step 2: Template gallery - loads from email_templates folder"""
    try:
        templates_dir = os.path.join('app', 'templates', 'email_templates')
        templates = []
        
        # Read all .html files in email_templates directory
        if os.path.exists(templates_dir):
            for filename in os.listdir(templates_dir):
                if filename.endswith('.html'):
                    name = filename.replace('.html', '')
                    templates.append({
                        'id': name,
                        'name': name.replace('_', ' ').title(),
                        'category': 'Marketing',
                        'thumbnail': f'/api/templates/preview/{name}'
                    })
        
        logger.info(f"Found {len(templates)} templates")
        
        return render_template('dashboard/campaigns/templates.html', templates=templates)
        
    except Exception as e:
        logger.error(f"Select template error: {e}", exc_info=True)
        return render_template('dashboard/campaigns/templates.html', templates=[])


@campaign_bp.route('/campaigns/design')
@campaign_bp.route('/campaigns/design/<template_id>')
@login_required
def design_campaign(template_id='blank'):
    """Step 3: Visual editor"""
    try:
        # Get campaign name from query params
        campaign_name = request.args.get('name', 'Untitled Campaign')
        campaign_id = request.args.get('campaign_id', str(uuid.uuid4()))
        
        # Get contacts count
        contacts_result = db.session.execute(
            text("SELECT COUNT(*) FROM contacts WHERE organization_id = :org_id AND status = 'active'"),
            {'org_id': current_user.organization_id}
        )
        contacts_count = contacts_result.scalar() or 0
        
        # Get domains
        domains_result = db.session.execute(
            text("SELECT id, domain_name, dns_verified FROM domains WHERE organization_id = :org_id"),
            {'org_id': current_user.organization_id}
        )
        domains = [dict(row._mapping) for row in domains_result]
        
        # Load template HTML if not blank
        template_html = ''
        if template_id != 'blank':
            template_path = os.path.join('app', 'templates', 'email_templates', f'{template_id}.html')
            if os.path.exists(template_path):
                with open(template_path, 'r') as f:
                    template_html = f.read()
        
        return render_template('dashboard/campaigns/design.html', 
                             template_id=template_id,
                             campaign_name=campaign_name,
                             campaign_id=campaign_id,
                             template_html=template_html,
                             contacts_count=contacts_count,
                             domains=domains)
        
    except Exception as e:
        logger.error(f"Design campaign error: {e}", exc_info=True)
        flash('Error loading campaign designer', 'error')
        return redirect(url_for('campaigns.list_campaigns'))


@campaign_bp.route('/campaigns/api/save-draft', methods=['POST'])
@login_required
def api_save_draft():
    """API: Save campaign draft"""
    try:
        data = request.get_json()
        
        campaign_id = data.get('campaign_id')
        
        # Check if campaign exists
        existing = db.session.execute(
            text("SELECT id FROM campaigns WHERE id = :id"),
            {'id': campaign_id}
        ).fetchone()
        
        if existing:
            # Update existing draft
            db.session.execute(
                text("""
                    UPDATE campaigns 
                    SET name = :name, subject = :subject, html_body = :html, updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    'id': campaign_id,
                    'name': data.get('name'),
                    'subject': data.get('subject'),
                    'html': data.get('html')
                }
            )
        else:
            # Create new draft
            db.session.execute(
                text("""
                    INSERT INTO campaigns (id, organization_id, name, subject, html_body, status, created_at)
                    VALUES (:id, :org_id, :name, :subject, :html, 'draft', NOW())
                """),
                {
                    'id': campaign_id,
                    'org_id': current_user.organization_id,
                    'name': data.get('name'),
                    'subject': data.get('subject'),
                    'html': data.get('html')
                }
            )
        
        db.session.commit()
        
        logger.info(f"Draft saved: {campaign_id}")
        
        return jsonify({'success': True, 'campaign_id': campaign_id})
        
    except Exception as e:
        logger.error(f"Save draft error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/campaigns/api/send', methods=['POST'])
@login_required
def api_send_campaign():
    """API: Send campaign"""
    try:
        data = request.get_json()
        
        campaign_id = data.get('campaign_id')
        
        # Update campaign status
        db.session.execute(
            text("""
                UPDATE campaigns 
                SET status = 'sent', sent_at = NOW()
                WHERE id = :id
            """),
            {'id': campaign_id}
        )
        
        db.session.commit()
        
        # TODO: Queue emails for sending
        
        return jsonify({'success': True, 'message': 'Campaign sent successfully'})
        
    except Exception as e:
        logger.error(f"Send campaign error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500




@campaign_bp.route('/campaigns/api/send-test', methods=['POST'])
@login_required
def api_send_test_email():
    """API: Send test email"""
    try:
        data = request.get_json()
        
        test_email = data.get('test_email')
        subject = data.get('subject')
        html_content = data.get('html')
        
        if not test_email or '@' not in test_email:
            return jsonify({'success': False, 'error': 'Invalid email address'}), 400
        
        if not subject or not html_content:
            return jsonify({'success': False, 'error': 'Subject and content required'}), 400
        
        # Get sender domain
        domains_result = db.session.execute(
            text("SELECT domain_name FROM domains WHERE organization_id = :org_id LIMIT 1"),
            {'org_id': current_user.organization_id}
        )
        domain_row = domains_result.fetchone()
        sender_domain = domain_row[0] if domain_row else 'sendbaba.com'
        
        # Send test email
        email_id = str(uuid.uuid4())
        
        db.session.execute(
            text("""
                INSERT INTO emails (id, organization_id, sender, recipient, subject, html_body, status, created_at)
                VALUES (:id, :org_id, :sender, :recipient, :subject, :html, 'queued', NOW())
            """),
            {
                'id': email_id,
                'org_id': current_user.organization_id,
                'sender': f'noreply@{sender_domain}',
                'recipient': test_email,
                'subject': f'[TEST] {subject}',
                'html': html_content
            }
        )
        
        db.session.commit()
        
        logger.info(f"Test email queued: {email_id} to {test_email}")
        
        return jsonify({
            'success': True, 
            'message': f'Test email sent to {test_email}'
        })
        
    except Exception as e:
        logger.error(f"Send test email error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@campaign_bp.route('/campaigns/<campaign_id>')
@login_required
def view_campaign(campaign_id):
    """View campaign details"""
    try:
        result = db.session.execute(
            text("""
                SELECT id, name, subject, status, 
                       COALESCE(emails_sent, 0) as sent,
                       COALESCE(total_recipients, 0) as recipients,
                       created_at
                FROM campaigns 
                WHERE id = :id AND organization_id = :org_id
            """),
            {'id': campaign_id, 'org_id': current_user.organization_id}
        )
        
        row = result.fetchone()
        
        if not row:
            flash('Campaign not found', 'error')
            return redirect(url_for('campaigns.list_campaigns'))
        
        campaign = {
            'id': row[0],
            'name': row[1],
            'subject': row[2],
            'status': row[3],
            'sent': row[4],
            'recipients': row[5],
            'created_at': row[6]
        }
        
        return render_template('dashboard/campaigns/view.html', campaign=campaign)
        
    except Exception as e:
        logger.error(f"View campaign error: {e}", exc_info=True)
        flash('Error loading campaign', 'error')
        return redirect(url_for('campaigns.list_campaigns'))
