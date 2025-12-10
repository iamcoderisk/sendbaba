"""
Team Management Controller
Complete department and member management with isolated contacts
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.team import Department, TeamMember
from sqlalchemy import text
from datetime import datetime
import secrets
import logging

logger = logging.getLogger(__name__)
team_bp = Blueprint('team', __name__, url_prefix='/dashboard/team')


def get_org_id():
    return str(current_user.organization_id)


@team_bp.route('/')
@login_required
def index():
    """Team overview with departments and members"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        
        # Get departments with member counts
        departments = db.session.execute(text("""
            SELECT d.id, d.name, d.description, d.color, d.email_quota,
                   COUNT(DISTINCT tm.id) as member_count,
                   COALESCE(SUM(des.emails_sent), 0) as total_emails
            FROM departments d
            LEFT JOIN team_members tm ON tm.department_id = d.id
            LEFT JOIN department_email_stats des ON des.department_id = d.id
            WHERE d.organization_id = :org_id
            GROUP BY d.id, d.name, d.description, d.color, d.email_quota
            ORDER BY d.name
        """), {'org_id': org_id}).fetchall()
        
        # Get all members
        members = db.session.execute(text("""
            SELECT tm.id, tm.email, tm.first_name, tm.last_name, tm.role,
                   tm.department_id, d.name as department_name, d.color as department_color,
                   tm.invitation_accepted, tm.is_active, tm.created_at
            FROM team_members tm
            LEFT JOIN departments d ON d.id = tm.department_id
            WHERE tm.organization_id = :org_id
            ORDER BY tm.first_name, tm.email
        """), {'org_id': org_id}).fetchall()
        
        # Stats
        stats = {
            'total_departments': len(departments),
            'total_members': len(members),
            'active_members': len([m for m in members if m.is_active]),
            'pending_invitations': len([m for m in members if not m.invitation_accepted])
        }
        
        # Format for template
        dept_list = [{
            'id': d[0], 'name': d[1], 'description': d[2], 'color': d[3] or '#6366F1',
            'email_quota': d[4] or 1000, 'member_count': d[5], 'total_emails': d[6]
        } for d in departments]
        
        member_list = [{
            'id': m[0], 'email': m[1], 'first_name': m[2] or '', 'last_name': m[3] or '',
            'full_name': f"{m[2] or ''} {m[3] or ''}".strip() or m[1].split('@')[0],
            'role': m[4] or 'member', 'department_id': m[5], 'department_name': m[6] or 'Unassigned',
            'department_color': m[7] or '#9CA3AF', 'invitation_accepted': m[8], 'is_active': m[9],
            'created_at': m[10]
        } for m in members]
        
        return render_template('dashboard/team/index.html',
                             departments=dept_list,
                             members=member_list,
                             stats=stats)
    except Exception as e:
        logger.error(f"Team index error: {e}")
        db.session.rollback()
        return render_template('dashboard/team/index.html',
                             departments=[], members=[],
                             stats={'total_departments': 0, 'total_members': 0, 'active_members': 0, 'pending_invitations': 0})


@team_bp.route('/departments')
@login_required
def departments():
    """List all departments"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        
        departments = db.session.execute(text("""
            SELECT d.id, d.name, d.description, d.color, d.email_quota,
                   COUNT(DISTINCT tm.id) as member_count,
                   COUNT(DISTINCT c.id) as contact_count,
                   COALESCE(SUM(des.emails_sent), 0) as total_emails
            FROM departments d
            LEFT JOIN team_members tm ON tm.department_id = d.id
            LEFT JOIN contacts c ON c.department_id = d.id
            LEFT JOIN department_email_stats des ON des.department_id = d.id
            WHERE d.organization_id = :org_id
            GROUP BY d.id
            ORDER BY d.name
        """), {'org_id': org_id}).fetchall()
        
        dept_list = [{
            'id': d[0], 'name': d[1], 'description': d[2], 'color': d[3] or '#6366F1',
            'email_quota': d[4] or 1000, 'member_count': d[5], 'contact_count': d[6], 'total_emails': d[7]
        } for d in departments]
        
        return render_template('dashboard/team/departments.html', departments=dept_list)
    except Exception as e:
        logger.error(f"Departments error: {e}")
        db.session.rollback()
        return render_template('dashboard/team/departments.html', departments=[])


@team_bp.route('/departments/create', methods=['GET', 'POST'])
@login_required
def create_department():
    """Create new department"""
    if request.method == 'POST':
        try:
            db.session.rollback()
            org_id = get_org_id()
            
            db.session.execute(text("""
                INSERT INTO departments (organization_id, name, description, color, email_quota, created_at, updated_at)
                VALUES (:org_id, :name, :desc, :color, :quota, NOW(), NOW())
            """), {
                'org_id': org_id,
                'name': request.form.get('name'),
                'desc': request.form.get('description', ''),
                'color': request.form.get('color', '#6366F1'),
                'quota': int(request.form.get('email_quota', 1000))
            })
            db.session.commit()
            flash('Department created successfully!', 'success')
            return redirect(url_for('team.departments'))
        except Exception as e:
            logger.error(f"Create department error: {e}")
            db.session.rollback()
            flash('Error creating department', 'error')
    
    return render_template('dashboard/team/create_department.html')


@team_bp.route('/departments/<int:dept_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_department(dept_id):
    """Edit department"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        
        dept = db.session.execute(text("""
            SELECT id, name, description, color, email_quota 
            FROM departments WHERE id = :id AND organization_id = :org_id
        """), {'id': dept_id, 'org_id': org_id}).fetchone()
        
        if not dept:
            flash('Department not found', 'error')
            return redirect(url_for('team.departments'))
        
        department = {'id': dept[0], 'name': dept[1], 'description': dept[2], 'color': dept[3], 'email_quota': dept[4]}
        
        if request.method == 'POST':
            db.session.execute(text("""
                UPDATE departments SET name = :name, description = :desc, color = :color, 
                       email_quota = :quota, updated_at = NOW()
                WHERE id = :id AND organization_id = :org_id
            """), {
                'id': dept_id, 'org_id': org_id,
                'name': request.form.get('name'),
                'desc': request.form.get('description', ''),
                'color': request.form.get('color', '#6366F1'),
                'quota': int(request.form.get('email_quota', 1000))
            })
            db.session.commit()
            flash('Department updated successfully!', 'success')
            return redirect(url_for('team.departments'))
        
        return render_template('dashboard/team/edit_department.html', department=department)
    except Exception as e:
        logger.error(f"Edit department error: {e}")
        db.session.rollback()
        flash('Error editing department', 'error')
        return redirect(url_for('team.departments'))


@team_bp.route('/departments/<int:dept_id>/delete', methods=['POST'])
@login_required
def delete_department(dept_id):
    """Delete department"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        
        # Unassign members first
        db.session.execute(text("""
            UPDATE team_members SET department_id = NULL WHERE department_id = :id
        """), {'id': dept_id})
        
        # Delete department
        db.session.execute(text("""
            DELETE FROM departments WHERE id = :id AND organization_id = :org_id
        """), {'id': dept_id, 'org_id': org_id})
        
        db.session.commit()
        flash('Department deleted successfully!', 'success')
    except Exception as e:
        logger.error(f"Delete department error: {e}")
        db.session.rollback()
        flash('Error deleting department', 'error')
    
    return redirect(url_for('team.departments'))


@team_bp.route('/members')
@login_required
def members():
    """List all team members"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        
        members = db.session.execute(text("""
            SELECT tm.id, tm.email, tm.first_name, tm.last_name, tm.role,
                   tm.department_id, d.name as department_name, d.color as department_color,
                   tm.invitation_accepted, tm.is_active, tm.invitation_token,
                   COUNT(DISTINCT c.id) as contact_count
            FROM team_members tm
            LEFT JOIN departments d ON d.id = tm.department_id
            LEFT JOIN contacts c ON c.owner_user_id = tm.user_id
            WHERE tm.organization_id = :org_id
            GROUP BY tm.id, d.name, d.color
            ORDER BY tm.first_name, tm.email
        """), {'org_id': org_id}).fetchall()
        
        departments = db.session.execute(text("""
            SELECT id, name, color FROM departments WHERE organization_id = :org_id ORDER BY name
        """), {'org_id': org_id}).fetchall()
        
        member_list = [{
            'id': m[0], 'email': m[1], 'first_name': m[2] or '', 'last_name': m[3] or '',
            'full_name': f"{m[2] or ''} {m[3] or ''}".strip() or m[1].split('@')[0],
            'role': m[4] or 'member', 'department_id': m[5], 'department_name': m[6] or 'Unassigned',
            'department_color': m[7] or '#9CA3AF', 'invitation_accepted': m[8], 'is_active': m[9],
            'invitation_token': m[10], 'contact_count': m[11]
        } for m in members]
        
        dept_list = [{'id': d[0], 'name': d[1], 'color': d[2]} for d in departments]
        
        return render_template('dashboard/team/members.html', members=member_list, departments=dept_list)
    except Exception as e:
        logger.error(f"Members error: {e}")
        db.session.rollback()
        return render_template('dashboard/team/members.html', members=[], departments=[])


@team_bp.route('/members/invite', methods=['GET', 'POST'])
@login_required
def invite_member():
    """Invite new team member"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        
        departments = db.session.execute(text("""
            SELECT id, name, color FROM departments WHERE organization_id = :org_id ORDER BY name
        """), {'org_id': org_id}).fetchall()
        dept_list = [{'id': d[0], 'name': d[1], 'color': d[2]} for d in departments]
        
        if request.method == 'POST':
            email = request.form.get('email', '').lower().strip()
            
            # Check if exists
            existing = db.session.execute(text("""
                SELECT id FROM team_members WHERE email = :email AND organization_id = :org_id
            """), {'email': email, 'org_id': org_id}).fetchone()
            
            if existing:
                flash('A member with this email already exists!', 'error')
                return render_template('dashboard/team/invite_member.html', departments=dept_list)
            
            invitation_token = secrets.token_urlsafe(32)
            dept_id = request.form.get('department_id') or None
            
            db.session.execute(text("""
                INSERT INTO team_members (organization_id, department_id, email, first_name, last_name, role,
                    invitation_token, invitation_accepted, is_active, invited_at,
                    can_send_email, can_manage_contacts, can_manage_campaigns, can_view_analytics,
                    can_manage_team, can_manage_billing, created_at, updated_at)
                VALUES (:org_id, :dept_id, :email, :fname, :lname, :role, :token, false, true, NOW(),
                    :can_email, :can_contacts, :can_campaigns, :can_analytics, :can_team, :can_billing, NOW(), NOW())
            """), {
                'org_id': org_id, 'dept_id': dept_id, 'email': email,
                'fname': request.form.get('first_name', ''),
                'lname': request.form.get('last_name', ''),
                'role': request.form.get('role', 'member'),
                'token': invitation_token,
                'can_email': request.form.get('can_send_email') == 'on',
                'can_contacts': request.form.get('can_manage_contacts') == 'on',
                'can_campaigns': request.form.get('can_manage_campaigns') == 'on',
                'can_analytics': request.form.get('can_view_analytics') == 'on',
                'can_team': request.form.get('can_manage_team') == 'on',
                'can_billing': request.form.get('can_manage_billing') == 'on'
            })
            db.session.commit()
            
            invitation_link = f"https://playmaster.sendbaba.com/team/accept-invite/{invitation_token}"
            
            return render_template('dashboard/team/invite_member.html',
                                 departments=dept_list,
                                 invitation_link=invitation_link,
                                 invited_email=email)
        
        return render_template('dashboard/team/invite_member.html', departments=dept_list)
    except Exception as e:
        logger.error(f"Invite member error: {e}")
        db.session.rollback()
        flash('Error inviting member', 'error')
        return redirect(url_for('team.members'))


@team_bp.route('/members/<int:member_id>/change-department', methods=['POST'])
@login_required
def change_department(member_id):
    """Change member's department"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        new_dept_id = request.form.get('department_id') or None
        
        db.session.execute(text("""
            UPDATE team_members SET department_id = :dept_id, updated_at = NOW()
            WHERE id = :id AND organization_id = :org_id
        """), {'id': member_id, 'org_id': org_id, 'dept_id': new_dept_id})
        db.session.commit()
        
        flash('Member department updated!', 'success')
    except Exception as e:
        logger.error(f"Change department error: {e}")
        db.session.rollback()
        flash('Error updating department', 'error')
    
    return redirect(url_for('team.members'))


@team_bp.route('/members/<int:member_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_member(member_id):
    """Edit team member"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        
        member = db.session.execute(text("""
            SELECT id, email, first_name, last_name, role, department_id, is_active,
                   can_send_email, can_manage_contacts, can_manage_campaigns,
                   can_view_analytics, can_manage_team, can_manage_billing
            FROM team_members WHERE id = :id AND organization_id = :org_id
        """), {'id': member_id, 'org_id': org_id}).fetchone()
        
        if not member:
            flash('Member not found', 'error')
            return redirect(url_for('team.members'))
        
        departments = db.session.execute(text("""
            SELECT id, name FROM departments WHERE organization_id = :org_id ORDER BY name
        """), {'org_id': org_id}).fetchall()
        
        member_data = {
            'id': member[0], 'email': member[1], 'first_name': member[2], 'last_name': member[3],
            'role': member[4], 'department_id': member[5], 'is_active': member[6],
            'can_send_email': member[7], 'can_manage_contacts': member[8], 'can_manage_campaigns': member[9],
            'can_view_analytics': member[10], 'can_manage_team': member[11], 'can_manage_billing': member[12]
        }
        dept_list = [{'id': d[0], 'name': d[1]} for d in departments]
        
        if request.method == 'POST':
            db.session.execute(text("""
                UPDATE team_members SET first_name = :fname, last_name = :lname, role = :role,
                       department_id = :dept_id, is_active = :active,
                       can_send_email = :can_email, can_manage_contacts = :can_contacts,
                       can_manage_campaigns = :can_campaigns, can_view_analytics = :can_analytics,
                       can_manage_team = :can_team, can_manage_billing = :can_billing, updated_at = NOW()
                WHERE id = :id AND organization_id = :org_id
            """), {
                'id': member_id, 'org_id': org_id,
                'fname': request.form.get('first_name', ''),
                'lname': request.form.get('last_name', ''),
                'role': request.form.get('role', 'member'),
                'dept_id': request.form.get('department_id') or None,
                'active': request.form.get('is_active') == 'on',
                'can_email': request.form.get('can_send_email') == 'on',
                'can_contacts': request.form.get('can_manage_contacts') == 'on',
                'can_campaigns': request.form.get('can_manage_campaigns') == 'on',
                'can_analytics': request.form.get('can_view_analytics') == 'on',
                'can_team': request.form.get('can_manage_team') == 'on',
                'can_billing': request.form.get('can_manage_billing') == 'on'
            })
            db.session.commit()
            flash('Member updated successfully!', 'success')
            return redirect(url_for('team.members'))
        
        return render_template('dashboard/team/edit_member.html', member=member_data, departments=dept_list)
    except Exception as e:
        logger.error(f"Edit member error: {e}")
        db.session.rollback()
        flash('Error editing member', 'error')
        return redirect(url_for('team.members'))


@team_bp.route('/members/<int:member_id>/delete', methods=['POST'])
@login_required
def delete_member(member_id):
    """Delete team member"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        
        db.session.execute(text("""
            DELETE FROM team_members WHERE id = :id AND organization_id = :org_id
        """), {'id': member_id, 'org_id': org_id})
        db.session.commit()
        
        flash('Member removed successfully!', 'success')
    except Exception as e:
        logger.error(f"Delete member error: {e}")
        db.session.rollback()
        flash('Error removing member', 'error')
    
    return redirect(url_for('team.members'))


@team_bp.route('/members/<int:member_id>/resend-invite', methods=['POST'])
@login_required
def resend_invite(member_id):
    """Get invitation link"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        
        member = db.session.execute(text("""
            SELECT email, invitation_token FROM team_members 
            WHERE id = :id AND organization_id = :org_id
        """), {'id': member_id, 'org_id': org_id}).fetchone()
        
        if member and member[1]:
            invitation_link = f"https://playmaster.sendbaba.com/team/accept-invite/{member[1]}"
            flash(f'Invitation link: {invitation_link}', 'success')
        else:
            flash('No invitation token found', 'error')
    except Exception as e:
        logger.error(f"Resend invite error: {e}")
        db.session.rollback()
        flash('Error getting invitation link', 'error')
    
    return redirect(url_for('team.members'))


# Single Email Send Routes
@team_bp.route('/send-email')
@login_required
def send_single_email():
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
        
        # Get verified domains for this organization - NO DEFAULT DOMAIN
        domains = db.session.execute(text("""
            SELECT id, domain_name FROM domains 
            WHERE organization_id = :org_id 
            AND dns_verified = true
            AND domain_name IS NOT NULL AND domain_name != ''
            ORDER BY domain_name
        """), {'org_id': org_id}).fetchall()
        
        domain_list = [{'id': str(d[0]), 'domain': d[1]} for d in domains if d[1]]
        
        # Get recent sent emails
        recent = db.session.execute(text("""
            SELECT id, recipient_email, recipient_name, subject, status, sent_at, created_at,
                   from_name, from_email
            FROM single_emails 
            WHERE organization_id = :org_id
            ORDER BY created_at DESC LIMIT 10
        """), {'org_id': org_id}).fetchall()
        
        recent_emails = [{
            'id': r[0], 'recipient_email': r[1], 'recipient_name': r[2],
            'subject': r[3], 'status': r[4], 'sent_at': r[5], 'created_at': r[6],
            'from_name': r[7], 'from_email': r[8]
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
        user_name = getattr(current_user, 'name', '') or current_user.email.split('@')[0]
        
        return render_template('dashboard/team/send_email.html',
                             templates=template_list,
                             domains=domain_list,
                             recent_emails=recent_emails,
                             contacts=contact_list,
                             user_name=user_name,
                             user_email=current_user.email)
    except Exception as e:
        logger.error(f"Send email page error: {e}")
        db.session.rollback()
        return render_template('dashboard/team/send_email.html',
                             templates=[], 
                             domains=[],
                             recent_emails=[], contacts=[],
                             user_name='', user_email='')


@team_bp.route('/send-email/send', methods=['POST'])
@login_required
def send_email_action():
    """Process and send the email with full sender options"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        
        data = request.get_json() if request.is_json else request.form
        
        # Sender fields
        from_name = data.get('from_name', '').strip()
        from_email = data.get('from_email', '').strip()
        reply_to = data.get('reply_to', '').strip()
        
        # Recipient fields
        recipient_email = data.get('recipient_email', '').strip()
        recipient_name = data.get('recipient_name', '').strip()
        
        # Content fields
        subject = data.get('subject', '').strip()
        html_body = data.get('html_body', '')
        text_body = data.get('text_body', '')
        
        # Validation
        if not recipient_email:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Recipient email is required'})
            flash('Recipient email is required', 'error')
            return redirect(url_for('team.send_single_email'))
        
        if not subject:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Subject is required'})
            flash('Subject is required', 'error')
            return redirect(url_for('team.send_single_email'))
        
        if not from_email:
            from_email = 'noreply@sendbaba.com'
        
        if not from_name:
            from_name = 'SendBaba'
        
        if not reply_to:
            reply_to = from_email
        
        # Replace merge tags
        first_name = recipient_name.split()[0] if recipient_name else ''
        replacements = {
            '{{first_name}}': first_name,
            '{{name}}': recipient_name,
            '{{email}}': recipient_email,
            '{{company}}': from_name,
        }
        for tag, value in replacements.items():
            html_body = html_body.replace(tag, value)
            subject = subject.replace(tag, value)
        
        # Insert into single_emails
        result = db.session.execute(text("""
            INSERT INTO single_emails (
                organization_id, sender_user_id, 
                from_name, from_email, reply_to,
                recipient_email, recipient_name,
                subject, body, html_body, 
                status, created_at, updated_at
            )
            VALUES (
                :org_id, :user_id,
                :from_name, :from_email, :reply_to,
                :to_email, :to_name,
                :subject, :text_body, :html_body,
                'queued', NOW(), NOW()
            )
            RETURNING id
        """), {
            'org_id': org_id, 
            'user_id': str(current_user.id),
            'from_name': from_name,
            'from_email': from_email,
            'reply_to': reply_to,
            'to_email': recipient_email, 
            'to_name': recipient_name,
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
        
        if request.is_json:
            return jsonify({'success': True, 'message': f'Email queued for {recipient_email}', 'id': new_email_id})
        
        flash(f'Email queued for delivery to {recipient_email}!', 'success')
        return redirect(url_for('team.send_single_email'))
        
    except Exception as e:
        logger.error(f"Send email error: {e}")
        db.session.rollback()
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)})
        flash('Error sending email', 'error')
        return redirect(url_for('team.send_single_email'))


@team_bp.route('/api/template/<int:template_id>')
@login_required
def api_get_template(template_id):
    """Get template content via API"""
    try:
        db.session.rollback()
        result = db.session.execute(text("""
            SELECT id, name, subject, html_content FROM email_templates WHERE id = :id
        """), {'id': template_id})
        row = result.fetchone()
        if row:
            return jsonify({
                'success': True,
                'template': {'id': row[0], 'name': row[1], 'subject': row[2] or '', 'html_content': row[3] or ''}
            })
        return jsonify({'success': False, 'error': 'Template not found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# API endpoints for AJAX
@team_bp.route('/api/members/<int:member_id>/department', methods=['POST'])
@login_required
def api_change_department(member_id):
    """API to change member department"""
    try:
        db.session.rollback()
        org_id = get_org_id()
        data = request.get_json()
        new_dept_id = data.get('department_id') or None
        
        db.session.execute(text("""
            UPDATE team_members SET department_id = :dept_id, updated_at = NOW()
            WHERE id = :id AND organization_id = :org_id
        """), {'id': member_id, 'org_id': org_id, 'dept_id': new_dept_id})
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"API change department error: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})
