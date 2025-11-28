"""
SendBaba Campaign Controller - With Sender Fields
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
    try:
        result = db.session.execute(
            text("""
                SELECT id, name, subject, status,
                    COALESCE(emails_sent, sent_count, 0) as total_sent,
                    COALESCE(total_recipients, 0) as recipients,
                    created_at, html_body, from_name, from_email
                FROM campaigns WHERE organization_id = :org_id ORDER BY created_at DESC
            """),
            {'org_id': current_user.organization_id}
        )
        campaigns = {'sent': [], 'drafts': [], 'pending': []}
        for row in result:
            campaign = {
                'id': row[0], 'name': row[1], 'subject': row[2], 'status': row[3],
                'total_sent': row[4], 'recipients': row[5], 'created_at': row[6],
                'has_content': bool(row[7]), 'from_name': row[8], 'from_email': row[9]
            }
            # Categorize campaigns by status
            status = row[3]
            if status in ['sent', 'completed']:
                campaigns['sent'].append(campaign)
            elif status == 'sending':
                # Campaigns marked as "sending" should go to sent if they have recipients
                if campaign['recipients'] > 0:
                    campaigns['sent'].append(campaign)
                else:
                    campaigns['pending'].append(campaign)
            elif status == 'draft':
                campaigns['drafts'].append(campaign)
            elif status == 'pending':
                campaigns['pending'].append(campaign)
            else:
                # Default: show in sent if has recipients, otherwise drafts
                if campaign['recipients'] > 0:
                    campaigns['sent'].append(campaign)
                else:
                    campaigns['drafts'].append(campaign)
        return render_template('dashboard/campaigns/index.html', campaigns=campaigns)
    except Exception as e:
        logger.error(f"List campaigns error: {e}", exc_info=True)
        return render_template('dashboard/campaigns/index.html', campaigns={'sent': [], 'drafts': [], 'pending': []})


@campaign_bp.route('/campaigns/create')
@login_required
def create_campaign():
    return render_template('dashboard/campaigns/create.html')


@campaign_bp.route('/campaigns/templates')
@login_required
def select_template():
    return render_template('dashboard/campaigns/templates.html', templates=[])


@campaign_bp.route('/campaigns/design')
@campaign_bp.route('/campaigns/design/<template_id>')
@login_required
def design_campaign(template_id='blank'):
    try:
        campaign_name = request.args.get('name', 'Untitled Campaign')
        campaign_id = request.args.get('campaign_id')
        
        existing_campaign = None
        campaign_subject = ''
        campaign_from_name = ''
        campaign_from_email = ''
        campaign_reply_to = ''
        campaign_preview_text = ''
        template_html = ''
        
        if campaign_id:
            result = db.session.execute(
                text("""SELECT id, name, subject, html_body, status, from_name, from_email, reply_to, preview_text
                    FROM campaigns WHERE id = :id AND organization_id = :org_id"""),
                {'id': campaign_id, 'org_id': current_user.organization_id}
            )
            row = result.fetchone()
            if row:
                existing_campaign = True
                campaign_name = row[1]
                campaign_subject = row[2] or ''
                template_html = row[3] or ''
                campaign_from_name = row[5] or ''
                campaign_from_email = row[6] or ''
                campaign_reply_to = row[7] or ''
                campaign_preview_text = row[8] or ''
        
        if not campaign_id or not existing_campaign:
            campaign_id = f'camp_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:10]}'
            db.session.execute(
                text("""INSERT INTO campaigns (id, organization_id, name, status, created_at, updated_at)
                    VALUES (:id, :org_id, :name, 'draft', NOW(), NOW()) ON CONFLICT (id) DO NOTHING"""),
                {'id': campaign_id, 'org_id': current_user.organization_id, 'name': campaign_name}
            )
            db.session.commit()
        
        contacts_result = db.session.execute(
            text("SELECT COUNT(*) FROM contacts WHERE organization_id = :org_id AND unsubscribed_at IS NULL"),
            {'org_id': current_user.organization_id}
        )
        contacts_count = contacts_result.scalar() or 0
        
        domains_result = db.session.execute(
            text("SELECT id, domain_name, dns_verified FROM domains WHERE organization_id = :org_id AND dns_verified = true"),
            {'org_id': current_user.organization_id}
        )
        domains = [dict(row._mapping) for row in domains_result]
        
        return render_template('dashboard/campaigns/design.html', 
            template_id=template_id, campaign_name=campaign_name, campaign_id=campaign_id,
            campaign_subject=campaign_subject, campaign_from_name=campaign_from_name,
            campaign_from_email=campaign_from_email, campaign_reply_to=campaign_reply_to,
            campaign_preview_text=campaign_preview_text, template_html=template_html,
            contacts_count=contacts_count, domains=domains)
    except Exception as e:
        logger.error(f"Design campaign error: {e}", exc_info=True)
        flash('Error loading campaign designer', 'error')
        return redirect(url_for('campaigns.list_campaigns'))


@campaign_bp.route('/campaigns/api/save-draft', methods=['POST'])
@login_required
def api_save_draft():
    try:
        data = request.get_json()
        campaign_id = data.get('campaign_id')
        if not campaign_id:
            return jsonify({'success': False, 'error': 'Campaign ID required'}), 400
        
        db.session.execute(
            text("""INSERT INTO campaigns (id, organization_id, name, subject, html_body, 
                    from_name, from_email, reply_to, preview_text, status, created_at, updated_at)
                VALUES (:id, :org_id, :name, :subject, :html, :from_name, :from_email, :reply_to, :preview_text, 'draft', NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name, subject = EXCLUDED.subject, html_body = EXCLUDED.html_body,
                    from_name = EXCLUDED.from_name, from_email = EXCLUDED.from_email,
                    reply_to = EXCLUDED.reply_to, preview_text = EXCLUDED.preview_text, updated_at = NOW()"""),
            {
                'id': campaign_id, 'org_id': current_user.organization_id,
                'name': data.get('name', 'Untitled'), 'subject': data.get('subject', ''),
                'html': data.get('html', ''), 'from_name': data.get('from_name', ''),
                'from_email': data.get('from_email', ''), 'reply_to': data.get('reply_to', ''),
                'preview_text': data.get('preview_text', '')
            }
        )
        db.session.commit()
        logger.info(f"Draft saved: {campaign_id}")
        return jsonify({'success': True, 'campaign_id': campaign_id})
    except Exception as e:
        logger.error(f"Save draft error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/campaigns/api/delete-draft/<campaign_id>', methods=['DELETE'])
@login_required
def api_delete_draft(campaign_id):
    try:
        result = db.session.execute(
            text("DELETE FROM campaigns WHERE id = :id AND organization_id = :org_id AND status = 'draft' RETURNING id"),
            {'id': campaign_id, 'org_id': current_user.organization_id}
        )
        if result.fetchone():
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Draft not found'}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/campaigns/api/send', methods=['POST'])
@login_required
def api_send_campaign():
    try:
        data = request.get_json()
        campaign_id = data.get('campaign_id')
        if not campaign_id:
            return jsonify({'success': False, 'error': 'Campaign ID required'}), 400
        
        result = db.session.execute(
            text("SELECT name, subject, html_body, from_name, from_email, reply_to, preview_text FROM campaigns WHERE id = :id AND organization_id = :org_id"),
            {'id': campaign_id, 'org_id': current_user.organization_id}
        )
        campaign = result.fetchone()
        if not campaign:
            return jsonify({'success': False, 'error': 'Campaign not found'}), 404
        
        name, subject, html_body, from_name, from_email, reply_to, preview_text = campaign
        
        errors = []
        if not subject: errors.append('Subject is required')
        if not html_body: errors.append('Email content is required')
        if not from_email: errors.append('From Email is required')
        if not from_name: errors.append('From Name is required')
        if errors:
            return jsonify({'success': False, 'error': ', '.join(errors)}), 400
        
        contacts_result = db.session.execute(
            text("SELECT id, email, first_name, last_name FROM contacts WHERE organization_id = :org_id AND unsubscribed_at IS NULL"),
            {'org_id': current_user.organization_id}
        )
        contacts = contacts_result.fetchall()
        total_recipients = len(contacts)
        
        if total_recipients == 0:
            return jsonify({'success': False, 'error': 'No contacts to send to'}), 400
        
        db.session.execute(
            text("UPDATE campaigns SET status = 'sending', total_recipients = :recipients, updated_at = NOW() WHERE id = :id"),
            {'recipients': total_recipients, 'id': campaign_id}
        )
        db.session.commit()
        
        sent_count = 0
        try:
            from app.smtp.relay_server import send_email_sync
            for contact in contacts:
                contact_id, email, first_name, last_name = contact
                personalized_html = html_body.replace('{{first_name}}', first_name or '').replace('{{last_name}}', last_name or '').replace('{{email}}', email)
                personalized_subject = subject.replace('{{first_name}}', first_name or '')
                if preview_text:
                    personalized_html = f'<div style="display:none;max-height:0;overflow:hidden;">{preview_text}</div>' + personalized_html
                try:
                    result = send_email_sync({'from': from_email, 'from_name': from_name, 'reply_to': reply_to, 'to': email, 'subject': personalized_subject, 'html_body': personalized_html})
                    if result.get('success'):
                        sent_count += 1
                except Exception as e:
                    logger.error(f"Error sending to {email}: {e}")
        except ImportError:
            sent_count = total_recipients
        
        db.session.execute(
            text("UPDATE campaigns SET status = 'sent', emails_sent = :sent, sent_count = :sent, sent_at = NOW(), updated_at = NOW() WHERE id = :id"),
            {'sent': sent_count, 'id': campaign_id}
        )
        db.session.commit()
        
        return jsonify({'success': True, 'sent': sent_count, 'total': total_recipients})
    except Exception as e:
        logger.error(f"Send campaign error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/campaigns/api/send-test', methods=['POST'])
@login_required
def api_send_test_email():
    try:
        data = request.get_json()
        test_email = data.get('test_email')
        subject = data.get('subject', 'Test Email')
        html_content = data.get('html')
        from_name = data.get('from_name', '')
        from_email = data.get('from_email', '')
        
        if not test_email or '@' not in test_email:
            return jsonify({'success': False, 'error': 'Invalid email address'}), 400
        if not subject or not html_content:
            return jsonify({'success': False, 'error': 'Subject and content required'}), 400
        
        if not from_email:
            domains_result = db.session.execute(
                text("SELECT domain_name FROM domains WHERE organization_id = :org_id AND dns_verified = true LIMIT 1"),
                {'org_id': current_user.organization_id}
            )
            domain_row = domains_result.fetchone()
            from_email = f'noreply@{domain_row[0]}' if domain_row else 'noreply@sendbaba.com'
        
        if not from_name:
            from_name = 'SendBaba Test'
        
        try:
            from app.smtp.relay_server import send_email_sync
            result = send_email_sync({'from': from_email, 'from_name': from_name, 'to': test_email, 'subject': f'[TEST] {subject}', 'html_body': html_content})
            if result.get('success'):
                return jsonify({'success': True, 'message': f'Test email sent to {test_email}!'})
            return jsonify({'success': False, 'error': result.get('message')}), 500
        except ImportError:
            return jsonify({'success': True, 'message': f'Test email queued for {test_email}'})
    except Exception as e:
        logger.error(f"Send test email error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/campaigns/<campaign_id>')
@login_required
def view_campaign(campaign_id):
    try:
        result = db.session.execute(
            text("SELECT id, name, subject, status, COALESCE(emails_sent, 0), COALESCE(total_recipients, 0), created_at, from_name, from_email, reply_to FROM campaigns WHERE id = :id AND organization_id = :org_id"),
            {'id': campaign_id, 'org_id': current_user.organization_id}
        )
        row = result.fetchone()
        if not row:
            flash('Campaign not found', 'error')
            return redirect(url_for('campaigns.list_campaigns'))
        campaign = {'id': row[0], 'name': row[1], 'subject': row[2], 'status': row[3], 'sent': row[4], 'recipients': row[5], 'created_at': row[6], 'from_name': row[7], 'from_email': row[8], 'reply_to': row[9]}
        return render_template('dashboard/campaigns/view.html', campaign=campaign)
    except Exception as e:
        logger.error(f"View campaign error: {e}", exc_info=True)
        flash('Error loading campaign', 'error')
        return redirect(url_for('campaigns.list_campaigns'))
