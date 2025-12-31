"""
Admin Templates & Campaigns Management Controller
Allows staff to create, edit, hide, delete templates and manage user campaigns/drafts
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from functools import wraps
from app import db
from sqlalchemy import text
import logging
import json
import uuid as uuid_lib
from datetime import datetime

logger = logging.getLogger(__name__)

admin_templates_bp = Blueprint('admin_templates', __name__, url_prefix='/admin')

def admin_required(f):
    """Decorator to require admin access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please login first', 'error')
            return redirect(url_for('auth.login'))
        # Check if user is admin (role = 'admin' or 'staff' or is_admin = True)
        is_admin = False
        try:
            result = db.session.execute(text("""
                SELECT role, is_admin FROM users WHERE id = :uid
            """), {'uid': current_user.id})
            row = result.fetchone()
            if row:
                is_admin = row[0] in ('admin', 'staff', 'superadmin') or row[1] == True
        except:
            pass
        
        if not is_admin:
            flash('Admin access required', 'error')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================
# TEMPLATE MANAGEMENT
# ============================================

@admin_templates_bp.route('/templates')
@login_required
@admin_required
def list_templates():
    """List all templates for admin management"""
    templates = []
    try:
        result = db.session.execute(text("""
            SELECT id, uuid, name, category, subject, description, 
                   organization_id, is_active, is_hidden, created_at, updated_at,
                   json_data IS NOT NULL as has_json
            FROM email_templates
            ORDER BY category, name
        """))
        for row in result:
            templates.append({
                'id': row[0],
                'uuid': row[1],
                'name': row[2],
                'category': row[3],
                'subject': row[4],
                'description': row[5],
                'organization_id': row[6],
                'is_active': row[7] if row[7] is not None else True,
                'is_hidden': row[8] if row[8] is not None else False,
                'created_at': row[9],
                'updated_at': row[10],
                'has_json': row[11]
            })
    except Exception as e:
        logger.error(f"Error loading templates: {e}")
        flash(f'Error loading templates: {e}', 'error')
    
    # Get categories for filter
    categories = list(set([t['category'] for t in templates if t['category']]))
    categories.sort()
    
    return render_template('admin/templates/list.html', 
                          templates=templates, 
                          categories=categories,
                          total=len(templates))


@admin_templates_bp.route('/templates/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_template():
    """Create new template"""
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            category = request.form.get('category')
            subject = request.form.get('subject', '')
            description = request.form.get('description', '')
            
            new_uuid = str(uuid_lib.uuid4())
            
            db.session.execute(text("""
                INSERT INTO email_templates (uuid, name, category, subject, description, organization_id, is_active, is_hidden, created_at, updated_at)
                VALUES (:uuid, :name, :category, :subject, :description, 'system', TRUE, FALSE, NOW(), NOW())
            """), {
                'uuid': new_uuid,
                'name': name,
                'category': category,
                'subject': subject,
                'description': description
            })
            db.session.commit()
            
            flash(f'Template "{name}" created successfully', 'success')
            return redirect(url_for('admin_templates.edit_template', template_id=new_uuid))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating template: {e}")
            flash(f'Error creating template: {e}', 'error')
    
    categories = ['newsletter', 'welcome', 'transactional', 'marketing', 'event', 
                  'notification', 'survey', 'reengagement', 'holiday', 'basic', 'promotional']
    
    return render_template('admin/templates/create.html', categories=categories)


@admin_templates_bp.route('/templates/edit/<template_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_template(template_id):
    """Edit template - loads the visual editor"""
    template = None
    try:
        result = db.session.execute(text("""
            SELECT id, uuid, name, category, subject, description, html_content, json_data,
                   organization_id, is_active, is_hidden, icon, preheader
            FROM email_templates
            WHERE uuid = :id OR id::text = :id
            LIMIT 1
        """), {'id': template_id})
        row = result.fetchone()
        if row:
            template = {
                'id': row[0],
                'uuid': row[1],
                'name': row[2],
                'category': row[3],
                'subject': row[4],
                'description': row[5],
                'html_content': row[6],
                'json_data': row[7],
                'organization_id': row[8],
                'is_active': row[9] if row[9] is not None else True,
                'is_hidden': row[10] if row[10] is not None else False,
                'icon': row[11],
                'preheader': row[12]
            }
    except Exception as e:
        logger.error(f"Error loading template: {e}")
        flash(f'Error loading template: {e}', 'error')
        return redirect(url_for('admin_templates.list_templates'))
    
    if not template:
        flash('Template not found', 'error')
        return redirect(url_for('admin_templates.list_templates'))
    
    categories = ['newsletter', 'welcome', 'transactional', 'marketing', 'event', 
                  'notification', 'survey', 'reengagement', 'holiday', 'basic', 'promotional']
    
    return render_template('admin/templates/edit.html', template=template, categories=categories)


@admin_templates_bp.route('/templates/api/save', methods=['POST'])
@login_required
@admin_required
def api_save_template():
    """Save template via API"""
    try:
        data = request.get_json()
        template_id = data.get('template_id')
        
        # Check if updating or creating
        if template_id:
            db.session.execute(text("""
                UPDATE email_templates SET
                    name = :name,
                    category = :category,
                    subject = :subject,
                    description = :description,
                    html_content = :html_content,
                    json_data = :json_data,
                    icon = :icon,
                    preheader = :preheader,
                    is_active = :is_active,
                    is_hidden = :is_hidden,
                    updated_at = NOW()
                WHERE uuid = :id OR id::text = :id
            """), {
                'id': template_id,
                'name': data.get('name'),
                'category': data.get('category'),
                'subject': data.get('subject', ''),
                'description': data.get('description', ''),
                'html_content': data.get('html_content'),
                'json_data': json.dumps(data.get('json_data')) if data.get('json_data') else None,
                'icon': data.get('icon', 'fas fa-envelope'),
                'preheader': data.get('preheader', ''),
                'is_active': data.get('is_active', True),
                'is_hidden': data.get('is_hidden', False)
            })
        else:
            new_uuid = str(uuid_lib.uuid4())
            db.session.execute(text("""
                INSERT INTO email_templates (uuid, name, category, subject, description, html_content, json_data, icon, preheader, organization_id, is_active, is_hidden, created_at, updated_at)
                VALUES (:uuid, :name, :category, :subject, :description, :html_content, :json_data, :icon, :preheader, 'system', :is_active, :is_hidden, NOW(), NOW())
            """), {
                'uuid': new_uuid,
                'name': data.get('name'),
                'category': data.get('category'),
                'subject': data.get('subject', ''),
                'description': data.get('description', ''),
                'html_content': data.get('html_content'),
                'json_data': json.dumps(data.get('json_data')) if data.get('json_data') else None,
                'icon': data.get('icon', 'fas fa-envelope'),
                'preheader': data.get('preheader', ''),
                'is_active': data.get('is_active', True),
                'is_hidden': data.get('is_hidden', False)
            })
            template_id = new_uuid
        
        db.session.commit()
        return jsonify({'success': True, 'template_id': template_id})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving template: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_templates_bp.route('/templates/api/toggle-visibility', methods=['POST'])
@login_required
@admin_required
def api_toggle_template_visibility():
    """Toggle template visibility (hidden/shown)"""
    try:
        data = request.get_json()
        template_id = data.get('template_id')
        is_hidden = data.get('is_hidden', False)
        
        db.session.execute(text("""
            UPDATE email_templates SET is_hidden = :hidden, updated_at = NOW()
            WHERE uuid = :id OR id::text = :id
        """), {'id': template_id, 'hidden': is_hidden})
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_templates_bp.route('/templates/api/toggle-active', methods=['POST'])
@login_required
@admin_required
def api_toggle_template_active():
    """Toggle template active status"""
    try:
        data = request.get_json()
        template_id = data.get('template_id')
        is_active = data.get('is_active', True)
        
        db.session.execute(text("""
            UPDATE email_templates SET is_active = :active, updated_at = NOW()
            WHERE uuid = :id OR id::text = :id
        """), {'id': template_id, 'active': is_active})
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_templates_bp.route('/templates/api/delete', methods=['POST'])
@login_required
@admin_required
def api_delete_template():
    """Delete a template"""
    try:
        data = request.get_json()
        template_id = data.get('template_id')
        
        db.session.execute(text("""
            DELETE FROM email_templates WHERE uuid = :id OR id::text = :id
        """), {'id': template_id})
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_templates_bp.route('/templates/api/duplicate', methods=['POST'])
@login_required
@admin_required
def api_duplicate_template():
    """Duplicate a template"""
    try:
        data = request.get_json()
        template_id = data.get('template_id')
        
        # Get original template
        result = db.session.execute(text("""
            SELECT name, category, subject, description, html_content, json_data, icon, preheader
            FROM email_templates WHERE uuid = :id OR id::text = :id
        """), {'id': template_id})
        row = result.fetchone()
        
        if not row:
            return jsonify({'success': False, 'error': 'Template not found'}), 404
        
        new_uuid = str(uuid_lib.uuid4())
        db.session.execute(text("""
            INSERT INTO email_templates (uuid, name, category, subject, description, html_content, json_data, icon, preheader, organization_id, is_active, is_hidden, created_at, updated_at)
            VALUES (:uuid, :name, :category, :subject, :description, :html_content, :json_data, :icon, :preheader, 'system', TRUE, FALSE, NOW(), NOW())
        """), {
            'uuid': new_uuid,
            'name': f"{row[0]} (Copy)",
            'category': row[1],
            'subject': row[2],
            'description': row[3],
            'html_content': row[4],
            'json_data': row[5],
            'icon': row[6],
            'preheader': row[7]
        })
        db.session.commit()
        
        return jsonify({'success': True, 'new_id': new_uuid})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# CAMPAIGN & DRAFT MANAGEMENT
# ============================================

@admin_templates_bp.route('/campaigns')
@login_required
@admin_required
def list_all_campaigns():
    """List all campaigns across all users"""
    campaigns = []
    status_filter = request.args.get('status', 'all')
    user_filter = request.args.get('user_id', '')
    
    try:
        query = """
            SELECT c.id, c.name, c.subject, c.status, c.created_at, c.updated_at,
                   c.total_recipients, c.emails_sent, c.organization_id,
                   u.email as user_email, u.first_name, u.last_name,
                   o.name as org_name
            FROM campaigns c
            LEFT JOIN users u ON c.organization_id = u.organization_id
            LEFT JOIN organizations o ON c.organization_id = o.id
            WHERE 1=1
        """
        params = {}
        
        if status_filter and status_filter != 'all':
            query += " AND c.status = :status"
            params['status'] = status_filter
        
        if user_filter:
            query += " AND c.organization_id = :org_id"
            params['org_id'] = user_filter
        
        query += " ORDER BY c.updated_at DESC LIMIT 500"
        
        result = db.session.execute(text(query), params)
        for row in result:
            campaigns.append({
                'id': row[0],
                'name': row[1],
                'subject': row[2],
                'status': row[3],
                'created_at': row[4],
                'updated_at': row[5],
                'total_recipients': row[6] or 0,
                'emails_sent': row[7] or 0,
                'organization_id': row[8],
                'user_email': row[9],
                'user_name': f"{row[10] or ''} {row[11] or ''}".strip() or row[9],
                'org_name': row[12]
            })
    except Exception as e:
        logger.error(f"Error loading campaigns: {e}")
        flash(f'Error: {e}', 'error')
    
    # Get users for filter dropdown
    users = []
    try:
        result = db.session.execute(text("""
            SELECT DISTINCT u.organization_id, u.email, o.name as org_name
            FROM users u
            LEFT JOIN organizations o ON u.organization_id = o.id
            WHERE u.organization_id IS NOT NULL
            ORDER BY u.email
        """))
        for row in result:
            users.append({
                'organization_id': row[0],
                'email': row[1],
                'org_name': row[2]
            })
    except:
        pass
    
    # Stats
    stats = {'total': 0, 'draft': 0, 'sent': 0, 'sending': 0, 'completed': 0, 'cancelled': 0, 'paused': 0}
    try:
        result = db.session.execute(text("""
            SELECT status, COUNT(*) FROM campaigns GROUP BY status
        """))
        for row in result:
            stats[row[0]] = row[1]
            stats['total'] += row[1]
    except:
        pass
    
    return render_template('admin/campaigns/list.html',
                          campaigns=campaigns,
                          users=users,
                          stats=stats,
                          status_filter=status_filter,
                          user_filter=user_filter)


@admin_templates_bp.route('/campaigns/view/<campaign_id>')
@login_required
@admin_required
def view_campaign(campaign_id):
    """View campaign details"""
    campaign = None
    try:
        result = db.session.execute(text("""
            SELECT c.*, u.email as user_email, o.name as org_name
            FROM campaigns c
            LEFT JOIN users u ON c.organization_id = u.organization_id
            LEFT JOIN organizations o ON c.organization_id = o.id
            WHERE c.id = :id
        """), {'id': campaign_id})
        row = result.fetchone()
        if row:
            campaign = dict(row._mapping)
    except Exception as e:
        logger.error(f"Error loading campaign: {e}")
        flash(f'Error: {e}', 'error')
    
    if not campaign:
        flash('Campaign not found', 'error')
        return redirect(url_for('admin_templates.list_all_campaigns'))
    
    return render_template('admin/campaigns/view.html', campaign=campaign)


@admin_templates_bp.route('/campaigns/api/delete', methods=['POST'])
@login_required
@admin_required
def api_delete_campaign():
    """Delete a single campaign"""
    try:
        data = request.get_json()
        campaign_id = data.get('campaign_id')
        
        db.session.execute(text("DELETE FROM campaigns WHERE id = :id"), {'id': campaign_id})
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_templates_bp.route('/campaigns/api/delete-bulk', methods=['POST'])
@login_required
@admin_required
def api_delete_bulk_campaigns():
    """Delete multiple campaigns"""
    try:
        data = request.get_json()
        campaign_ids = data.get('campaign_ids', [])
        
        if campaign_ids:
            # Use parameterized query for safety
            placeholders = ','.join([f':id{i}' for i in range(len(campaign_ids))])
            params = {f'id{i}': cid for i, cid in enumerate(campaign_ids)}
            
            db.session.execute(text(f"DELETE FROM campaigns WHERE id IN ({placeholders})"), params)
            db.session.commit()
        
        return jsonify({'success': True, 'deleted': len(campaign_ids)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_templates_bp.route('/campaigns/api/clear-drafts', methods=['POST'])
@login_required
@admin_required
def api_clear_drafts():
    """Clear all drafts or drafts for specific user"""
    try:
        data = request.get_json()
        organization_id = data.get('organization_id')  # Optional - if provided, only clear for that org
        
        if organization_id:
            result = db.session.execute(text("""
                DELETE FROM campaigns WHERE status = 'draft' AND organization_id = :org_id
                RETURNING id
            """), {'org_id': organization_id})
        else:
            result = db.session.execute(text("""
                DELETE FROM campaigns WHERE status = 'draft'
                RETURNING id
            """))
        
        deleted = len(result.fetchall())
        db.session.commit()
        
        return jsonify({'success': True, 'deleted': deleted})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_templates_bp.route('/campaigns/api/update-status', methods=['POST'])
@login_required
@admin_required
def api_update_campaign_status():
    """Update campaign status"""
    try:
        data = request.get_json()
        campaign_id = data.get('campaign_id')
        new_status = data.get('status')
        
        valid_statuses = ['draft', 'queued', 'sending', 'paused', 'completed', 'cancelled', 'failed']
        if new_status not in valid_statuses:
            return jsonify({'success': False, 'error': 'Invalid status'}), 400
        
        db.session.execute(text("""
            UPDATE campaigns SET status = :status, updated_at = NOW() WHERE id = :id
        """), {'id': campaign_id, 'status': new_status})
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
