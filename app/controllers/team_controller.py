"""Team Management Controller"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from datetime import datetime
import secrets
import logging

logger = logging.getLogger(__name__)
team_bp = Blueprint('team', __name__, url_prefix='/dashboard/team')


def get_models():
    from app.models.team import Department, TeamMember, AuditLog
    return Department, TeamMember, AuditLog


@team_bp.route('/')
@login_required
def index():
    """Team overview page"""
    try:
        Department, TeamMember, AuditLog = get_models()
        org_id = str(current_user.organization_id)
        
        departments = Department.query.filter_by(organization_id=org_id).all()
        members = TeamMember.query.filter_by(organization_id=org_id).all()
        
        stats = {
            'total_members': len(members),
            'total_departments': len(departments),
            'active_members': len([m for m in members if m.is_active]),
            'pending_invitations': len([m for m in members if not m.invitation_accepted])
        }
        
        return render_template('dashboard/team/index.html', 
                             departments=departments,
                             members=members,
                             stats=stats)
    except Exception as e:
        logger.error(f"Team index error: {e}")
        return render_template('dashboard/team/index.html', 
                             departments=[],
                             members=[],
                             stats={'total_members': 0, 'total_departments': 0, 'active_members': 0, 'pending_invitations': 0})


@team_bp.route('/members')
@login_required
def members():
    """List all team members"""
    try:
        Department, TeamMember, AuditLog = get_models()
        org_id = str(current_user.organization_id)
        members = TeamMember.query.filter_by(organization_id=org_id).all()
        departments = Department.query.filter_by(organization_id=org_id).all()
        return render_template('dashboard/team/members.html', members=members, departments=departments)
    except Exception as e:
        logger.error(f"Members error: {e}")
        return render_template('dashboard/team/members.html', members=[], departments=[])


@team_bp.route('/members/invite', methods=['GET', 'POST'])
@login_required
def invite_member():
    """Invite new team member"""
    try:
        Department, TeamMember, AuditLog = get_models()
        org_id = str(current_user.organization_id)
        departments = Department.query.filter_by(organization_id=org_id).all()
        
        if request.method == 'POST':
            email = request.form.get('email', '').lower().strip()
            
            existing = TeamMember.query.filter_by(email=email, organization_id=org_id).first()
            if existing:
                flash('A team member with this email already exists!', 'error')
                return redirect(url_for('team.invite_member'))
            
            invitation_token = secrets.token_urlsafe(32)
            
            member = TeamMember(
                organization_id=org_id,
                department_id=request.form.get('department_id') or None,
                email=email,
                first_name=request.form.get('first_name', ''),
                last_name=request.form.get('last_name', ''),
                role=request.form.get('role', 'member'),
                invitation_token=invitation_token,
                invitation_accepted=False,
                can_send_email=request.form.get('can_send_email') == 'on',
                can_manage_contacts=request.form.get('can_manage_contacts') == 'on',
                can_manage_campaigns=request.form.get('can_manage_campaigns') == 'on',
                can_view_analytics=request.form.get('can_view_analytics') == 'on',
                can_manage_team=request.form.get('can_manage_team') == 'on',
                can_manage_billing=request.form.get('can_manage_billing') == 'on'
            )
            
            db.session.add(member)
            db.session.commit()
            
            invitation_link = f"https://playmaster.sendbaba.com/team/accept-invite/{invitation_token}"
            flash(f'Invitation sent! Link: {invitation_link}', 'success')
            return redirect(url_for('team.members'))
        
        return render_template('dashboard/team/invite.html', departments=departments)
    except Exception as e:
        logger.error(f"Invite error: {e}")
        flash('Failed to send invitation', 'error')
        return redirect(url_for('team.index'))


@team_bp.route('/members/<int:member_id>/delete', methods=['POST'])
@login_required
def delete_member(member_id):
    """Delete team member"""
    try:
        Department, TeamMember, AuditLog = get_models()
        member = TeamMember.query.get_or_404(member_id)
        db.session.delete(member)
        db.session.commit()
        flash('Team member removed', 'success')
    except Exception as e:
        logger.error(f"Delete member error: {e}")
        flash('Failed to remove member', 'error')
    return redirect(url_for('team.members'))


@team_bp.route('/departments')
@login_required
def departments():
    """List departments"""
    try:
        Department, TeamMember, AuditLog = get_models()
        org_id = str(current_user.organization_id)
        departments = Department.query.filter_by(organization_id=org_id).all()
        return render_template('dashboard/team/departments.html', departments=departments)
    except Exception as e:
        logger.error(f"Departments error: {e}")
        return render_template('dashboard/team/departments.html', departments=[])


@team_bp.route('/departments/create', methods=['GET', 'POST'])
@login_required
def create_department():
    """Create department"""
    try:
        Department, TeamMember, AuditLog = get_models()
        
        if request.method == 'POST':
            org_id = str(current_user.organization_id)
            
            dept = Department(
                organization_id=org_id,
                name=request.form.get('name'),
                description=request.form.get('description', ''),
                color=request.form.get('color', '#6366F1'),
                email_quota=int(request.form.get('email_quota', 1000))
            )
            
            db.session.add(dept)
            db.session.commit()
            
            flash(f'Department "{dept.name}" created!', 'success')
            return redirect(url_for('team.departments'))
        
        return render_template('dashboard/team/create_department.html')
    except Exception as e:
        logger.error(f"Create dept error: {e}")
        flash('Failed to create department', 'error')
        return redirect(url_for('team.departments'))
