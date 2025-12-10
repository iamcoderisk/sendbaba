"""
Single Email Controller
Separate from bulk campaigns - for one-to-one emails
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from sqlalchemy import text
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)
single_email_bp = Blueprint('single_email', __name__, url_prefix='/dashboard/send')


def get_org_id():
    return str(current_user.organization_id)


@single_email_bp.route('/')
@login_required
def index():
    """Single email compose page with template picker"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        
        # Get templates (system + user's org)
        templates = db.session.execute(text("""
            SELECT id, name, subject, html_content, category, thumbnail_url
            FROM email_templates 
            WHERE organization_id IN ('system', :org_id) AND is_default = true
            ORDER BY category, name
        """), {'org_id': org_id}).fetchall()
        
        template_list = [{
            'id': t[0], 'name': t[1], 'subject': t[2] or '', 
            'html_content': t[3] or '', 'category': t[4], 'thumbnail_url': t[5]
        } for t in templates]
        
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
            ORDER BY first_name, email LIMIT 100
        """), {'org_id': org_id}).fetchall()
        
        contact_list = [{
            'email': c[0], 'name': f"{c[1] or ''} {c[2] or ''}".strip() or c[0].split('@')[0]
        } for c in contacts]
        
        return render_template('dashboard/single_email/compose.html',
                             templates=template_list,
                             recent_emails=recent_emails,
                             contacts=contact_list)
    except Exception as e:
        logger.error(f"Single email index error: {e}")
        db.session.rollback()
        return render_template('dashboard/single_email/compose.html',
                             templates=[], recent_emails=[], contacts=[])


@single_email_bp.route('/compose')
@single_email_bp.route('/compose/<int:template_id>')
@login_required
def compose(template_id=None):
    """Email composer with visual editor"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        
        template = None
        if template_id:
            result = db.session.execute(text("""
                SELECT id, name, subject, html_content 
                FROM email_templates WHERE id = :id
            """), {'id': template_id})
            row = result.fetchone()
            if row:
                template = {'id': row[0], 'name': row[1], 'subject': row[2], 'html_content': row[3]}
        
        # Get contacts
        contacts = db.session.execute(text("""
            SELECT email, first_name, last_name FROM contacts 
            WHERE organization_id = :org_id 
            ORDER BY first_name, email LIMIT 200
        """), {'org_id': org_id}).fetchall()
        
        contact_list = [{
            'email': c[0], 
            'name': f"{c[1] or ''} {c[2] or ''}".strip() or c[0].split('@')[0],
            'first_name': c[1] or '',
            'last_name': c[2] or ''
        } for c in contacts]
        
        return render_template('dashboard/single_email/editor.html',
                             template=template,
                             contacts=contact_list)
    except Exception as e:
        logger.error(f"Compose error: {e}")
        db.session.rollback()
        return render_template('dashboard/single_email/editor.html',
                             template=None, contacts=[])


@single_email_bp.route('/send', methods=['POST'])
@login_required
def send():
    """Send the email"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        
        recipient_email = request.form.get('recipient_email', '').strip()
        recipient_name = request.form.get('recipient_name', '').strip()
        subject = request.form.get('subject', '').strip()
        html_body = request.form.get('html_body', '')
        text_body = request.form.get('text_body', '')
        
        if not recipient_email or not subject:
            flash('Recipient email and subject are required', 'error')
            return redirect(url_for('single_email.index'))
        
        # Replace merge tags
        html_body = html_body.replace('{{first_name}}', recipient_name.split()[0] if recipient_name else '')
        html_body = html_body.replace('{{name}}', recipient_name)
        html_body = html_body.replace('{{email}}', recipient_email)
        
        # Insert into single_emails
        result = db.session.execute(text("""
            INSERT INTO single_emails (organization_id, sender_user_id, recipient_email, recipient_name,
                subject, body, html_body, status, created_at, updated_at)
            VALUES (:org_id, :user_id, :email, :name, :subject, :text_body, :html_body, 'queued', NOW(), NOW())
            RETURNING id
        """), {
            'org_id': org_id, 
            'user_id': str(current_user.id),
            'email': recipient_email, 
            'name': recipient_name,
            'subject': subject, 
            'text_body': text_body,
            'html_body': html_body
        })
        new_email_id = result.fetchone()[0]
        db.session.commit()
        
        # Queue the email task
        try:
            from app.tasks.email_tasks import send_single_email_task
            send_single_email_task.delay(new_email_id)
        except Exception as task_error:
            logger.error(f"Task queue error: {task_error}")
        
        flash(f'Email queued for delivery to {recipient_email}!', 'success')
        return redirect(url_for('single_email.index'))
        
    except Exception as e:
        logger.error(f"Send error: {e}")
        db.session.rollback()
        flash('Error sending email', 'error')
        return redirect(url_for('single_email.index'))


@single_email_bp.route('/templates')
@login_required
def templates():
    """Manage email templates"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        
        templates = db.session.execute(text("""
            SELECT id, name, subject, category, created_at, 
                   CASE WHEN organization_id = 'system' THEN true ELSE false END as is_system
            FROM email_templates 
            WHERE organization_id IN ('system', :org_id)
            ORDER BY is_default DESC, name
        """), {'org_id': org_id}).fetchall()
        
        template_list = [{
            'id': t[0], 'name': t[1], 'subject': t[2], 'category': t[3], 
            'created_at': t[4], 'is_system': t[5]
        } for t in templates]
        
        return render_template('dashboard/single_email/templates.html', templates=template_list)
    except Exception as e:
        logger.error(f"Templates error: {e}")
        db.session.rollback()
        return render_template('dashboard/single_email/templates.html', templates=[])


@single_email_bp.route('/templates/create', methods=['GET', 'POST'])
@login_required
def create_template():
    """Create new template"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        
        if request.method == 'POST':
            db.session.execute(text("""
                INSERT INTO email_templates (organization_id, name, subject, html_content, category, created_by)
                VALUES (:org_id, :name, :subject, :html, :category, :user_id)
            """), {
                'org_id': org_id,
                'name': request.form.get('name', 'Untitled'),
                'subject': request.form.get('subject', ''),
                'html': request.form.get('html_content', ''),
                'category': request.form.get('category', 'custom'),
                'user_id': str(current_user.id)
            })
            db.session.commit()
            flash('Template created!', 'success')
            return redirect(url_for('single_email.templates'))
        
        return render_template('dashboard/single_email/template_editor.html', template=None)
    except Exception as e:
        logger.error(f"Create template error: {e}")
        db.session.rollback()
        flash('Error creating template', 'error')
        return redirect(url_for('single_email.templates'))


@single_email_bp.route('/templates/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_template(template_id):
    """Edit template"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        
        template = db.session.execute(text("""
            SELECT id, name, subject, html_content, category, organization_id
            FROM email_templates WHERE id = :id
        """), {'id': template_id}).fetchone()
        
        if not template:
            flash('Template not found', 'error')
            return redirect(url_for('single_email.templates'))
        
        # Can't edit system templates
        if template[5] == 'system':
            flash('System templates cannot be edited. Create a copy instead.', 'info')
            return redirect(url_for('single_email.templates'))
        
        template_data = {
            'id': template[0], 'name': template[1], 'subject': template[2],
            'html_content': template[3], 'category': template[4]
        }
        
        if request.method == 'POST':
            db.session.execute(text("""
                UPDATE email_templates 
                SET name = :name, subject = :subject, html_content = :html, 
                    category = :category, updated_at = NOW()
                WHERE id = :id AND organization_id = :org_id
            """), {
                'id': template_id, 'org_id': org_id,
                'name': request.form.get('name'),
                'subject': request.form.get('subject'),
                'html': request.form.get('html_content'),
                'category': request.form.get('category', 'custom')
            })
            db.session.commit()
            flash('Template updated!', 'success')
            return redirect(url_for('single_email.templates'))
        
        return render_template('dashboard/single_email/template_editor.html', template=template_data)
    except Exception as e:
        logger.error(f"Edit template error: {e}")
        db.session.rollback()
        flash('Error editing template', 'error')
        return redirect(url_for('single_email.templates'))


@single_email_bp.route('/history')
@login_required
def history():
    """Email history"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        
        emails = db.session.execute(text("""
            SELECT id, recipient_email, recipient_name, subject, status, 
                   sent_at, opened_at, clicked_at, created_at
            FROM single_emails 
            WHERE organization_id = :org_id
            ORDER BY created_at DESC LIMIT 100
        """), {'org_id': org_id}).fetchall()
        
        email_list = [{
            'id': e[0], 'recipient_email': e[1], 'recipient_name': e[2],
            'subject': e[3], 'status': e[4], 'sent_at': e[5],
            'opened_at': e[6], 'clicked_at': e[7], 'created_at': e[8]
        } for e in emails]
        
        return render_template('dashboard/single_email/history.html', emails=email_list)
    except Exception as e:
        logger.error(f"History error: {e}")
        db.session.rollback()
        return render_template('dashboard/single_email/history.html', emails=[])


# API endpoints
@single_email_bp.route('/api/template/<int:template_id>')
@login_required
def api_get_template(template_id):
    """Get template content"""
    try:
        db.session.rollback()
        result = db.session.execute(text("""
            SELECT id, name, subject, html_content FROM email_templates WHERE id = :id
        """), {'id': template_id})
        row = result.fetchone()
        if row:
            return jsonify({
                'success': True,
                'template': {'id': row[0], 'name': row[1], 'subject': row[2], 'html_content': row[3]}
            })
        return jsonify({'success': False, 'error': 'Template not found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@single_email_bp.route('/api/contacts/search')
@login_required
def api_search_contacts():
    """Search contacts for autocomplete"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        query = request.args.get('q', '').lower()
        
        result = db.session.execute(text("""
            SELECT email, first_name, last_name FROM contacts 
            WHERE organization_id = :org_id 
            AND (LOWER(email) LIKE :q OR LOWER(first_name) LIKE :q OR LOWER(last_name) LIKE :q)
            ORDER BY first_name, email LIMIT 20
        """), {'org_id': org_id, 'q': f'%{query}%'})
        
        contacts = [{'email': r[0], 'name': f"{r[1] or ''} {r[2] or ''}".strip()} for r in result]
        return jsonify({'success': True, 'contacts': contacts})
    except Exception as e:
        return jsonify({'success': False, 'contacts': []})
