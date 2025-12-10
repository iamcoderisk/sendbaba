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
    """Select template page"""
    return render_template('dashboard/campaigns/templates.html')


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
            domains=[]
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
    """Get pre-built template HTML"""
    templates = {
        'welcome': '''<div style="padding:40px 20px;background:#f0fdf4;"><div style="max-width:600px;margin:0 auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);"><div style="padding:40px;text-align:center;"><div style="font-size:48px;margin-bottom:20px;">👋</div><h1 style="color:#1e293b;font-size:28px;margin-bottom:15px;">Welcome, {{first_name}}!</h1><p style="color:#475569;line-height:1.6;margin-bottom:25px;">We're thrilled to have you join our community.</p><a href="#" style="display:inline-block;background:#22c55e;color:white;padding:14px 32px;text-decoration:none;border-radius:8px;font-weight:bold;">Get Started</a></div></div></div>''',
        'newsletter': '''<div style="padding:40px 20px;background:#f8fafc;"><div style="max-width:600px;margin:0 auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);"><div style="background:#3b82f6;padding:30px;text-align:center;"><h1 style="color:white;margin:0;font-size:28px;">Your Newsletter</h1></div><div style="padding:30px;"><h2 style="color:#1e293b;font-size:22px;margin-bottom:15px;">Hello {{first_name}},</h2><p style="color:#475569;line-height:1.6;margin-bottom:20px;">Welcome to our newsletter! Here are the latest updates.</p><a href="#" style="display:inline-block;background:#3b82f6;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;">Read More</a></div></div></div>''',
        'promotional': '''<div style="padding:40px 20px;background:#fff7ed;"><div style="max-width:600px;margin:0 auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);"><div style="background:linear-gradient(135deg,#f97316,#ef4444);padding:40px;text-align:center;"><h1 style="color:white;margin:0;font-size:42px;font-weight:bold;">50% OFF</h1><p style="color:rgba(255,255,255,0.9);font-size:18px;margin-top:10px;">Limited Time Offer!</p></div><div style="padding:30px;text-align:center;"><h2 style="color:#1e293b;font-size:24px;margin-bottom:15px;">Hey {{first_name}}!</h2><p style="color:#475569;line-height:1.6;margin-bottom:25px;">Dont miss our biggest sale. Use code <strong>SAVE50</strong> at checkout.</p><a href="#" style="display:inline-block;background:#f97316;color:white;padding:16px 40px;text-decoration:none;border-radius:8px;font-weight:bold;font-size:18px;">Shop Now</a></div></div></div>''',
        'simple': '''<div style="padding:40px 20px;"><div style="max-width:600px;margin:0 auto;"><p style="color:#1e293b;font-size:16px;line-height:1.8;margin-bottom:20px;">Hi {{first_name}},</p><p style="color:#475569;font-size:16px;line-height:1.8;margin-bottom:20px;">I wanted to reach out to share some thoughts with you.</p><p style="color:#475569;font-size:16px;line-height:1.8;margin-bottom:30px;">Best regards,<br>Your Name</p></div></div>'''
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
                'html': data.get('html', ''), 'from_name': data.get('from_name', ''),
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
        
        # Queue the campaign for async processing via Celery
        try:
            from app.tasks.email_tasks import send_campaign
            send_campaign.delay(campaign_id)
            logger.info(f"Campaign {campaign_id} queued for {total} contacts")
            
            return jsonify({
                'success': True, 
                'queued': True,
                'total': total,
                'message': f'Campaign queued! Sending to {total:,} contacts in background.'
            })
        except ImportError as e:
            logger.error(f"Celery import failed: {e}")
            # Fallback to sync for small lists
            if total <= 100:
                return send_campaign_sync(campaign_id, campaign, total)
            return jsonify({'success': False, 'error': 'Queue system unavailable'}), 500
            
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
