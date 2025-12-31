"""
SendBaba Campaign Controller - Production Version
URL: /dashboard/campaigns
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from sqlalchemy import text
import logging
import uuid
from datetime import datetime
import threading

logger = logging.getLogger(__name__)

# IMPORTANT: url_prefix='/dashboard' so routes are /dashboard/campaigns
campaign_bp = Blueprint('campaigns', __name__, url_prefix='/dashboard')


def get_html_column():
    """Check which column name is used for HTML content"""
    try:
        result = db.session.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'campaigns' AND column_name = 'html_content'"
        ))
        if result.fetchone():
            return 'html_content'
    except:
        pass
    return 'html_body'


# ============================================
# PAGE ROUTES - /dashboard/campaigns/*
# ============================================

@campaign_bp.route('/campaigns')
@login_required
def list_campaigns():
    """List all campaigns - /dashboard/campaigns"""
    try:
        html_col = get_html_column()
        result = db.session.execute(
            text(f"""
                SELECT id, name, subject, status,
                    COALESCE(emails_sent, sent_count, 0) as emails_sent,
                    COALESCE(total_recipients, 0) as recipients,
                    created_at, from_name, from_email
                FROM campaigns WHERE organization_id = :org_id ORDER BY created_at DESC
            """),
            {'org_id': current_user.organization_id}
        )
        
        campaigns = {'sent': [], 'drafts': [], 'pending': []}
        
        for row in result:
            campaign = {
                'id': row[0],
                'name': row[1] or 'Untitled',
                'subject': row[2] or '',
                'status': row[3] or 'draft',
                'emails_sent': row[4] or 0,
                'recipients': row[5] or 0,
                'created_at': row[6],
                'from_name': row[7],
                'from_email': row[8]
            }
            
            status = (row[3] or 'draft').lower()
            if status in ['sent', 'completed']:
                campaigns['sent'].append(campaign)
            elif status == 'sending' and campaign['recipients'] > 0:
                campaigns['sent'].append(campaign)
            elif status in ['pending', 'queued', 'scheduled', 'sending']:
                campaigns['pending'].append(campaign)
            else:
                campaigns['drafts'].append(campaign)
        
        return render_template('dashboard/campaigns/index.html', campaigns=campaigns)
    except Exception as e:
        logger.error(f"List campaigns error: {e}", exc_info=True)
        return render_template('dashboard/campaigns/index.html', campaigns={'sent': [], 'drafts': [], 'pending': []})


@campaign_bp.route('/campaigns/create')
@login_required
def create_campaign():
    """Create new campaign page"""
    return render_template('dashboard/campaigns/create.html')


@campaign_bp.route('/campaigns/templates')
@login_required
def select_template():
    """Select template page - loads templates from database"""
    from sqlalchemy import text
    
    templates = []
    try:
        result = db.session.execute(text("""
            SELECT COALESCE(uuid, id::text) as id, name, category, subject, description, icon, html_content
            FROM email_templates 
            WHERE organization_id = 'system' OR organization_id = :org_id
            ORDER BY category, name
        """), {'org_id': current_user.organization_id})
        
        for row in result:
            templates.append({
                'id': row[0],
                'name': row[1],
                'category': row[2],
                'subject': row[3],
                'description': row[4] or '',
                'icon': row[5] or 'fas fa-envelope',
                'html_content': row[6]
            })
    except Exception as e:
        print(f"Error loading templates: {e}")
    
    categories = list(set([t['category'] for t in templates]))
    categories.sort()
    
    return render_template('dashboard/campaigns/templates.html', templates=templates, categories=categories)
@campaign_bp.route('/campaigns/design')
@campaign_bp.route('/campaigns/design/<template_id>')
@login_required
def design_campaign(template_id='blank'):
    """Design campaign page"""
    try:
        campaign_name = request.args.get('name', 'Untitled Campaign')
        campaign_id = request.args.get('campaign_id')
        html_col = get_html_column()
        
        campaign_subject = ''
        campaign_from_name = ''
        campaign_from_email = ''
        campaign_reply_to = ''
        campaign_preview_text = ''
        template_html = ''
        
        if campaign_id:
            try:
                result = db.session.execute(
                    text(f"""SELECT id, name, subject, {html_col}, status, 
                            from_name, from_email, reply_to, preview_text
                        FROM campaigns WHERE id = :id AND organization_id = :org_id"""),
                    {'id': campaign_id, 'org_id': current_user.organization_id}
                )
                row = result.fetchone()
                if row:
                    campaign_id = row[0]
                    campaign_name = row[1] or campaign_name
                    campaign_subject = row[2] or ''
                    template_html = row[3] or ''
                    campaign_from_name = row[5] or ''
                    campaign_from_email = row[6] or ''
                    campaign_reply_to = row[7] or ''
                    campaign_preview_text = row[8] or ''
            except Exception as e:
                logger.error(f"Error loading campaign: {e}")
        
        if not campaign_id:
            campaign_id = f'camp_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:10]}'
            try:
                db.session.execute(
                    text("""INSERT INTO campaigns (id, organization_id, name, status, created_at, updated_at)
                        VALUES (:id, :org_id, :name, 'draft', NOW(), NOW())"""),
                    {'id': campaign_id, 'org_id': current_user.organization_id, 'name': campaign_name}
                )
                db.session.commit()
            except Exception as e:
                logger.error(f"Error creating campaign: {e}")
                db.session.rollback()
        
        if not template_html and template_id != 'blank':
            template_html = get_template_html(template_id)
        
        contacts_count = 0
        try:
            result = db.session.execute(
                text("SELECT COUNT(*) FROM contacts WHERE organization_id = :org_id"),
                {'org_id': current_user.organization_id}
            )
            contacts_count = result.scalar() or 0
        except Exception as e:
            logger.warning(f"Error getting contacts: {e}")
        
        # Get all templates from database for template picker
        all_templates = []
        try:
            tmpl_result = db.session.execute(text("""
                SELECT COALESCE(uuid, id::text) as id, name, category, subject, description, icon, html_content
                FROM email_templates 
                WHERE organization_id = 'system' OR organization_id = :org_id
                ORDER BY category, name
            """), {'org_id': current_user.organization_id})
            
            for row in tmpl_result:
                all_templates.append({
                    'id': row[0],
                    'name': row[1],
                    'category': row[2],
                    'subject': row[3],
                    'description': row[4] or '',
                    'icon': row[5] or 'fas fa-envelope',
                    'html_content': row[6]
                })
        except Exception as e:
            logger.warning(f"Error loading domains: {e}")
        except Exception as e:
            logger.warning(f"Error loading templates: {e}")

        # Get verified domains for the organization
        verified_domains = []
        try:
            domains_result = db.session.execute(text("""
                SELECT COALESCE(domain, domain_name) as domain, COALESCE(is_verified, dns_verified, false), COALESCE(dns_verified, false), COALESCE(dns_verified, false)
                FROM domains
                WHERE organization_id = :org_id AND (is_verified = TRUE OR dns_verified = TRUE)
                ORDER BY domain
            """), {'org_id': current_user.organization_id})
            for row in domains_result:
                verified_domains.append({
                    'domain': row[0],
                    'verified': row[1],
                    'dkim_verified': row[2],
                    'spf_verified': row[3]
                })
        except Exception as e:
            logger.warning(f"Error loading domains: {e}")
        
        template_categories = list(set([t['category'] for t in all_templates]))
        template_categories.sort()
        
        return render_template('dashboard/campaigns/design.html',
            template_id=template_id,
            campaign_name=campaign_name,
            campaign_id=campaign_id,
            campaign_subject=campaign_subject,
            campaign_from_name=campaign_from_name,
            campaign_from_email=campaign_from_email,
            campaign_reply_to=campaign_reply_to,
            campaign_preview_text=campaign_preview_text,
            template_html=template_html,
            contacts_count=contacts_count,
            domains=verified_domains,
            all_templates=all_templates,
            template_categories=template_categories
        )
        
    except Exception as e:
        logger.error(f"Design campaign error: {e}", exc_info=True)
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('campaigns.list_campaigns'))


@campaign_bp.route('/campaigns/view/<campaign_id>')
@campaign_bp.route('/campaigns/<campaign_id>')
@login_required
def view_campaign(campaign_id):
    """View campaign details"""
    try:
        result = db.session.execute(
            text("""SELECT id, name, subject, status, 
                    COALESCE(emails_sent, sent_count, 0), 
                    COALESCE(total_recipients, 0), 
                    created_at, from_name, from_email, sent_at
                FROM campaigns WHERE id = :id AND organization_id = :org_id"""),
            {'id': campaign_id, 'org_id': current_user.organization_id}
        )
        row = result.fetchone()
        if not row:
            flash('Campaign not found', 'error')
            return redirect(url_for('campaigns.list_campaigns'))
        
        campaign = {
            'id': row[0], 'name': row[1], 'subject': row[2], 'status': row[3],
            'emails_sent': row[4], 'total_recipients': row[5], 'created_at': row[6],
            'from_name': row[7], 'from_email': row[8], 'sent_at': row[9]
        }
        
        stats = {'total': campaign['total_recipients'], 'sent': campaign['emails_sent'], 
                'delivered': campaign['emails_sent'], 'failed': 0, 'bounced': 0, 
                'opens': 0, 'clicks': 0, 'open_rate': 0, 'click_rate': 0, 'delivery_rate': 100}
        
        return render_template('dashboard/campaigns/view.html', campaign=campaign, stats=stats, recipients=[])
    except Exception as e:
        logger.error(f"View campaign error: {e}", exc_info=True)
        flash('Error loading campaign', 'error')
        return redirect(url_for('campaigns.list_campaigns'))


def get_template_html(template_id):
    """Get template HTML from database"""
    from sqlalchemy import text
    try:
        # Try to load from database first
        result = db.session.execute(text("""
            SELECT html_content FROM email_templates WHERE id::text = :id OR uuid = :id
        """), {'id': template_id})
        row = result.fetchone()
        if row and row[0]:
            return row[0]
    except Exception as e:
        logger.warning(f"Error loading template {template_id}: {e}")
    
    # Fallback to basic templates
    templates = {
        'blank': '',
        'welcome': '<div style="padding:40px 20px;background:#f0fdf4;"><div style="max-width:600px;margin:0 auto;background:white;border-radius:8px;padding:40px;text-align:center;"><h1 style="color:#1e293b;">Welcome!</h1><p style="color:#475569;">Thanks for joining us.</p></div></div>',
        'newsletter': '<div style="padding:40px 20px;background:#f8fafc;"><div style="max-width:600px;margin:0 auto;background:white;border-radius:8px;"><div style="background:#3b82f6;padding:30px;text-align:center;"><h1 style="color:white;margin:0;">Newsletter</h1></div><div style="padding:30px;"><p style="color:#475569;">Your content here.</p></div></div></div>'
    }
    return templates.get(template_id, '')


# ============================================
# API ROUTES
# ============================================

@campaign_bp.route('/campaigns/api/save-draft', methods=['POST'])
@login_required
def api_save_draft():
    """Save campaign as draft"""
    try:
        data = request.get_json()
        campaign_id = data.get('campaign_id')
        if not campaign_id:
            return jsonify({'success': False, 'error': 'Campaign ID required'}), 400
        
        html_col = get_html_column()
        
        db.session.execute(
            text(f"""INSERT INTO campaigns (id, organization_id, name, subject, {html_col}, 
                    from_name, from_email, reply_to, preview_text, status, created_at, updated_at)
                VALUES (:id, :org_id, :name, :subject, :html, :from_name, :from_email, :reply_to, :preview_text, 'draft', NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name, subject = EXCLUDED.subject, {html_col} = EXCLUDED.{html_col},
                    from_name = EXCLUDED.from_name, from_email = EXCLUDED.from_email,
                    reply_to = EXCLUDED.reply_to, preview_text = EXCLUDED.preview_text, updated_at = NOW()"""),
            {
                'id': campaign_id, 'org_id': current_user.organization_id,
                'name': data.get('name', 'Untitled'), 'subject': data.get('subject', ''),
                'html': data.get('html_content', data.get('html', '')), 'from_name': data.get('from_name', ''),
                'from_email': data.get('from_email', ''), 'reply_to': data.get('reply_to', ''),
                'preview_text': data.get('preview_text', '')
            }
        )
        db.session.commit()
        return jsonify({'success': True, 'campaign_id': campaign_id})
    except Exception as e:
        logger.error(f"Save draft error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/campaigns/api/delete-draft/<campaign_id>', methods=['DELETE'])
@login_required
def api_delete_draft(campaign_id):
    """Delete draft campaign"""
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


@campaign_bp.route('/campaigns/api/stats')
@login_required
def api_stats():
    """Get campaign stats"""
    try:
        result = db.session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'sent' THEN 1 END) as sent,
                COUNT(CASE WHEN status = 'draft' THEN 1 END) as drafts,
                COUNT(CASE WHEN status = 'sending' THEN 1 END) as sending,
                COALESCE(SUM(emails_sent), 0) as total_emails
            FROM campaigns WHERE organization_id = :org_id
        """), {'org_id': current_user.organization_id})
        row = result.fetchone()
        
        return jsonify({
            'success': True,
            'total': row[0] or 0,
            'sent': row[1] or 0,
            'drafts': row[2] or 0,
            'sending': row[3] or 0,
            'total_emails': row[4] or 0
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/campaigns/api/send', methods=['POST'])
@login_required
def api_send_campaign():
    """Send campaign using Celery async queue"""
    try:
        data = request.get_json()
        campaign_id = data.get('campaign_id')
        html_col = get_html_column()
        
        # Validate campaign exists and belongs to user
        result = db.session.execute(
            text(f"SELECT name, subject, {html_col}, from_name, from_email, reply_to, preview_text FROM campaigns WHERE id = :id AND organization_id = :org_id"),
            {'id': campaign_id, 'org_id': current_user.organization_id}
        )
        campaign = result.fetchone()
        if not campaign:
            return jsonify({'success': False, 'error': 'Campaign not found'}), 404
        
        name, subject, html_body, from_name, from_email, reply_to, preview_text = campaign
        
        # Validate required fields
        if not subject: return jsonify({'success': False, 'error': 'Subject is required'}), 400
        if not html_body: return jsonify({'success': False, 'error': 'Email content is required'}), 400
        if not from_email: return jsonify({'success': False, 'error': 'From Email is required'}), 400
        if not from_name: return jsonify({'success': False, 'error': 'From Name is required'}), 400
        
        # Count contacts
        contacts_result = db.session.execute(
            text("SELECT COUNT(*) FROM contacts WHERE organization_id = :org_id AND status = 'active'"),
            {'org_id': current_user.organization_id}
        )
        total = contacts_result.scalar() or 0
        
        if total == 0:
            return jsonify({'success': False, 'error': 'No contacts to send to'}), 400
        
        # Update campaign status to queued
        db.session.execute(
            text("UPDATE campaigns SET status = 'queued', total_recipients = :total, updated_at = NOW() WHERE id = :id"),
            {'total': total, 'id': campaign_id}
        )
        db.session.commit()
        
        # Campaign is now queued - process_queued_campaigns task will pick it up automatically
        # The Celery beat scheduler runs process_queued_campaigns every 3 seconds
        logger.info(f"Campaign {campaign_id} queued for {total} contacts - will be processed by scheduler")
        
        return jsonify({
            'success': True,
            'queued': True,
            'total': total,
            'message': f'Campaign queued! Sending to {total:,} contacts. Processing will start shortly.'
        })
            
    except Exception as e:
        logger.error(f"Send error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


def send_campaign_sync(campaign_id, campaign, total):
    """Fallback sync sending for small campaigns"""
    name, subject, html_body, from_name, from_email, reply_to, preview_text = campaign
    
    db.session.execute(
        text("UPDATE campaigns SET status = 'sending', updated_at = NOW() WHERE id = :id"),
        {'id': campaign_id}
    )
    db.session.commit()
    
    contacts_result = db.session.execute(
        text("SELECT id, email, first_name, last_name FROM contacts WHERE organization_id = :org_id AND status = 'active' LIMIT 100"),
        {'org_id': current_user.organization_id}
    )
    contacts = contacts_result.fetchall()
    
    sent = 0
    from app.smtp.relay_server import send_email_sync
    for contact in contacts:
        contact_id, email, first_name, last_name = contact
        html = html_body.replace('{{first_name}}', first_name or '').replace('{{last_name}}', last_name or '').replace('{{email}}', email)
        subj = subject.replace('{{first_name}}', first_name or '')
        try:
            result = send_email_sync({'from': from_email, 'from_name': from_name, 'reply_to': reply_to, 'to': email, 'subject': subj, 'html_body': html})
            if result.get('success'): sent += 1
        except Exception as e:
            logger.error(f"Send to {email} failed: {e}")
    
    db.session.execute(
        text("UPDATE campaigns SET status = 'sent', emails_sent = :sent, sent_count = :sent, sent_at = NOW(), updated_at = NOW() WHERE id = :id"),
        {'sent': sent, 'id': campaign_id}
    )
    db.session.commit()
    
    return jsonify({'success': True, 'sent': sent, 'total': total})


@campaign_bp.route('/campaigns/api/send-test', methods=['POST'])
@login_required
def api_send_test_email():
    """Send test email"""
    try:
        data = request.get_json()
        test_email = data.get('test_email')
        if not test_email or '@' not in test_email:
            return jsonify({'success': False, 'error': 'Invalid email'}), 400
        
        try:
            from app.smtp.relay_server import send_email_sync
            result = send_email_sync({
                'from': data.get('from_email', 'test@sendbaba.com'),
                'from_name': data.get('from_name', 'SendBaba'),
                'to': test_email,
                'subject': f"[TEST] {data.get('subject', 'Test')}",
                'html_body': data.get('html', '<p>Test email</p>')
            })
            if result.get('success'):
                return jsonify({'success': True, 'message': f'Test sent to {test_email}'})
            return jsonify({'success': False, 'error': 'Send failed'}), 500
        except ImportError:
            return jsonify({'success': True, 'message': f'Test queued for {test_email}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# CAMPAIGN CONTROL APIs - Pause/Resume/Resend
# ============================================

@campaign_bp.route('/campaigns/api/pause/<campaign_id>', methods=['POST'])
@login_required
def api_pause_campaign(campaign_id):
    """Pause a running campaign"""
    try:
        result = db.session.execute(
            text("""
                UPDATE campaigns 
                SET status = 'paused', updated_at = NOW()
                WHERE id = :id AND organization_id = :org_id 
                AND status IN ('sending', 'queued', 'processing')
                RETURNING id, name
            """),
            {'id': campaign_id, 'org_id': current_user.organization_id}
        )
        row = result.fetchone()
        if row:
            db.session.commit()
            logger.info(f"Campaign {row[1]} paused by user")
            return jsonify({'success': True, 'message': f'Campaign "{row[1]}" paused'})
        return jsonify({'success': False, 'error': 'Campaign not found or cannot be paused'}), 404
    except Exception as e:
        db.session.rollback()
        logger.error(f"Pause campaign error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/campaigns/api/resume/<campaign_id>', methods=['POST'])
@login_required
def api_resume_campaign(campaign_id):
    """Resume a paused campaign"""
    try:
        result = db.session.execute(
            text("""
                UPDATE campaigns 
                SET status = 'queued', updated_at = NOW()
                WHERE id = :id AND organization_id = :org_id 
                AND status = 'paused'
                RETURNING id, name
            """),
            {'id': campaign_id, 'org_id': current_user.organization_id}
        )
        row = result.fetchone()
        if row:
            db.session.commit()
            logger.info(f"Campaign {row[1]} resumed, queued for processing")
            return jsonify({'success': True, 'message': f'Campaign "{row[1]}" resumed and queued'})
        return jsonify({'success': False, 'error': 'Campaign not found or not paused'}), 404
    except Exception as e:
        db.session.rollback()
        logger.error(f"Resume campaign error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/campaigns/api/resend/<campaign_id>', methods=['POST'])
@login_required
def api_resend_campaign(campaign_id):
    """Resend a failed or completed campaign (to unsent contacts only)"""
    try:
        result = db.session.execute(
            text("""
                SELECT id, name, status FROM campaigns 
                WHERE id = :id AND organization_id = :org_id
            """),
            {'id': campaign_id, 'org_id': current_user.organization_id}
        )
        row = result.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Campaign not found'}), 404
        
        campaign_name = row[1]
        current_status = row[2]
        
        allowed_statuses = ['failed', 'completed', 'completed_with_errors', 'paused', 'sending']
        if current_status not in allowed_statuses:
            return jsonify({'success': False, 'error': f'Cannot resend campaign with status: {current_status}'}), 400
        
        db.session.execute(
            text("UPDATE campaigns SET status = 'queued', updated_at = NOW() WHERE id = :id"),
            {'id': campaign_id}
        )
        db.session.commit()
        
        logger.info(f"Campaign {campaign_name} queued for resend")
        return jsonify({
            'success': True, 
            'message': f'Campaign "{campaign_name}" queued for resend. Will send to remaining contacts.'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Resend campaign error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/campaigns/api/cancel/<campaign_id>', methods=['POST'])
@login_required
def api_cancel_campaign(campaign_id):
    """Cancel a campaign completely"""
    try:
        result = db.session.execute(
            text("""
                UPDATE campaigns 
                SET status = 'cancelled', updated_at = NOW()
                WHERE id = :id AND organization_id = :org_id 
                AND status IN ('sending', 'queued', 'paused', 'processing')
                RETURNING id, name
            """),
            {'id': campaign_id, 'org_id': current_user.organization_id}
        )
        row = result.fetchone()
        if row:
            db.session.commit()
            logger.info(f"Campaign {row[1]} cancelled")
            return jsonify({'success': True, 'message': f'Campaign "{row[1]}" cancelled'})
        return jsonify({'success': False, 'error': 'Campaign not found or cannot be cancelled'}), 404
    except Exception as e:
        db.session.rollback()
        logger.error(f"Cancel campaign error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/campaigns/api/progress/<campaign_id>')
@login_required
def api_campaign_progress(campaign_id):
    """Get real-time campaign progress"""
    try:
        result = db.session.execute(
            text("""
                SELECT c.id, c.name, c.status, c.total_recipients,
                       COALESCE(c.sent_count, 0) as sent_count,
                       (SELECT COUNT(*) FROM emails WHERE campaign_id = c.id AND status = 'sent') as actual_sent,
                       (SELECT COUNT(*) FROM emails WHERE campaign_id = c.id AND status = 'failed') as failed
                FROM campaigns c
                WHERE c.id = :id AND c.organization_id = :org_id
            """),
            {'id': campaign_id, 'org_id': current_user.organization_id}
        )
        row = result.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Campaign not found'}), 404
        
        total = row[3] or 0
        sent = row[5] or 0
        failed = row[6] or 0
        percent = int((sent + failed) / total * 100) if total > 0 else 0
        
        return jsonify({
            'success': True,
            'campaign_id': row[0],
            'name': row[1],
            'status': row[2],
            'total': total,
            'sent': sent,
            'failed': failed,
            'percent': percent,
            'remaining': total - sent - failed
        })
    except Exception as e:
        logger.error(f"Campaign progress error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@campaign_bp.route('/campaigns/api/template/<template_id>')
@login_required
def get_template_json(template_id):
    """Get template JSON data"""
    from flask import jsonify
    try:
        result = db.session.execute(text("""
            SELECT uuid, name, subject, html_content, json_data, preheader
            FROM email_templates 
            WHERE uuid = :id OR id::text = :id
            LIMIT 1
        """), {'id': template_id})
        row = result.fetchone()
        
        if row:
            return jsonify({
                'uuid': row[0],
                'name': row[1],
                'subject': row[2],
                'html_content': row[3],
                'json_data': row[4],
                'preheader': row[5]
            })
        return jsonify({'error': 'Template not found'}), 404
    except Exception as e:
        logger.error(f"Error getting template: {e}")
        return jsonify({'error': str(e)}), 500




@campaign_bp.route('/api/upload-image', methods=['POST'])
@login_required
def api_upload_image():
    """Upload image for email campaigns"""
    import os
    import uuid
    from werkzeug.utils import secure_filename
    
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': 'No image file provided'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    # Check allowed extensions
    allowed = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed:
        return jsonify({'success': False, 'error': f'Invalid file type. Allowed: {", ".join(allowed)}'}), 400
    
    # Check file size (max 5MB)
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > 5 * 1024 * 1024:
        return jsonify({'success': False, 'error': 'File too large. Max 5MB'}), 400
    
    # Create upload directory
    upload_dir = os.path.join(current_app.root_path, '..', 'static', 'uploads', 'campaigns')
    os.makedirs(upload_dir, exist_ok=True)
    
    # Generate unique filename
    filename = f"{uuid.uuid4().hex[:12]}_{secure_filename(file.filename)}"
    filepath = os.path.join(upload_dir, filename)
    
    try:
        file.save(filepath)
        # Return URL
        url = f"/static/uploads/campaigns/{filename}"
        return jsonify({'success': True, 'url': url, 'filename': filename})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/campaigns/recipients')
@login_required
def campaign_recipients():
    """Select recipients page before sending"""
    campaign_id = request.args.get('campaign_id')
    if not campaign_id:
        flash('Campaign ID required', 'error')
        return redirect(url_for('campaigns.list_campaigns'))
    
    try:
        html_col = get_html_column()
        result = db.session.execute(
            text(f"""SELECT id, name, subject, {html_col}, from_name, from_email, reply_to, preview_text, status
                FROM campaigns WHERE id = :id AND organization_id = :org_id"""),
            {'id': campaign_id, 'org_id': current_user.organization_id}
        )
        row = result.fetchone()
        if not row:
            flash('Campaign not found', 'error')
            return redirect(url_for('campaigns.list_campaigns'))
        
        campaign = {
            'id': row[0], 'name': row[1], 'subject': row[2], 'html_body': row[3],
            'from_name': row[4], 'from_email': row[5], 'reply_to': row[6],
            'preview_text': row[7], 'status': row[8]
        }
        
        # Get contacts count
        contacts_result = db.session.execute(
            text("SELECT COUNT(*) FROM contacts WHERE organization_id = :org_id AND status = 'active'"),
            {'org_id': current_user.organization_id}
        )
        contacts_count = contacts_result.scalar() or 0
        
        # Get segments
        segments = []
        try:
            seg_result = db.session.execute(
                text("SELECT id, name, contact_count FROM segments WHERE organization_id = :org_id ORDER BY name"),
                {'org_id': current_user.organization_id}
            )
            for s in seg_result:
                segments.append({'id': s[0], 'name': s[1], 'count': s[2] or 0})
        except:
            pass
        
        return render_template('dashboard/campaigns/recipients.html',
            campaign=campaign,
            contacts_count=contacts_count,
            segments=segments
        )
    except Exception as e:
        logger.error(f"Recipients page error: {e}", exc_info=True)
        flash('Error loading campaign', 'error')
        return redirect(url_for('campaigns.list_campaigns'))
