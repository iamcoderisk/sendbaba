"""
Team Management Controller
Handles departments and team members
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app import db
from app.models.team import Department, TeamMember, AuditLog
from datetime import datetime
import secrets
import logging

logger = logging.getLogger(__name__)
team_bp = Blueprint('team', __name__, url_prefix='/dashboard/team')


@team_bp.route('/')
@login_required
def index():
    """Team overview page"""
    org_id = current_user.organization_id
    
    departments = Department.query.filter_by(organization_id=org_id).all()
    members = TeamMember.query.filter_by(organization_id=org_id).all()
    
    stats = {
        'total_members': len(members),
        'total_departments': len(departments),
        'active_members': len([m for m in members if m.is_active]),
        'pending_invitations': len([m for m in members if not m.invitation_accepted])
    }
    
    return render_template('team/index.html', 
                         departments=departments,
                         members=members,
                         stats=stats)


@team_bp.route('/departments')
@login_required
def departments():
    """List all departments"""
    org_id = current_user.organization_id
    departments = Department.query.filter_by(organization_id=org_id).all()
    return render_template('team/departments.html', departments=departments)


@team_bp.route('/departments/create', methods=['GET', 'POST'])
@login_required
def create_department():
    """Create new department"""
    if request.method == 'POST':
        org_id = current_user.organization_id
        
        department = Department(
            organization_id=org_id,
            name=request.form.get('name'),
            description=request.form.get('description'),
            color=request.form.get('color', '#6366F1'),
            email_quota=int(request.form.get('email_quota', 1000))
        )
        
        db.session.add(department)
        db.session.commit()
        
        flash(f'Department "{department.name}" created successfully!', 'success')
        return redirect(url_for('team.departments'))
    
    return render_template('team/create_department.html')


@team_bp.route('/departments/<int:dept_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_department(dept_id):
    """Edit department"""
    department = Department.query.get_or_404(dept_id)
    
    if request.method == 'POST':
        department.name = request.form.get('name')
        department.description = request.form.get('description')
        department.color = request.form.get('color')
        department.email_quota = int(request.form.get('email_quota', 1000))
        
        db.session.commit()
        flash(f'Department "{department.name}" updated successfully!', 'success')
        return redirect(url_for('team.departments'))
    
    return render_template('team/edit_department.html', department=department)


@team_bp.route('/departments/<int:dept_id>/delete', methods=['POST'])
@login_required
def delete_department(dept_id):
    """Delete department"""
    department = Department.query.get_or_404(dept_id)
    name = department.name
    
    db.session.delete(department)
    db.session.commit()
    
    flash(f'Department "{name}" deleted successfully!', 'success')
    return redirect(url_for('team.departments'))


@team_bp.route('/members')
@login_required
def members():
    """List all team members"""
    org_id = current_user.organization_id
    members = TeamMember.query.filter_by(organization_id=org_id).all()
    departments = Department.query.filter_by(organization_id=org_id).all()
    return render_template('team/members.html', members=members, departments=departments)


@team_bp.route('/members/invite', methods=['GET', 'POST'])
@login_required
def invite_member():
    """Invite new team member"""
    org_id = current_user.organization_id
    departments = Department.query.filter_by(organization_id=org_id).all()
    
    if request.method == 'POST':
        email = request.form.get('email')
        
        # Check if email already exists
        existing = TeamMember.query.filter_by(email=email).first()
        if existing:
            flash('A team member with this email already exists!', 'error')
            return redirect(url_for('team.invite_member'))
        
        # Generate invitation token
        invitation_token = secrets.token_urlsafe(32)
        
        member = TeamMember(
            organization_id=org_id,
            department_id=request.form.get('department_id') or None,
            email=email,
            first_name=request.form.get('first_name'),
            last_name=request.form.get('last_name'),
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
        
        # Generate invitation link
        invitation_link = f"https://playmaster.sendbaba.com/team/accept-invite/{invitation_token}"
        
        logger.info(f"Created invitation for {email}: {invitation_link}")
        
        # Return to same page with invitation link displayed
        return render_template('team/invite_member.html', 
                             departments=departments,
                             invitation_link=invitation_link,
                             invited_email=email)
    
    return render_template('team/invite_member.html', departments=departments)


@team_bp.route('/members/<int:member_id>/resend-invite', methods=['POST'])
@login_required
def resend_invite(member_id):
    """Resend invitation link"""
    member = TeamMember.query.get_or_404(member_id)
    
    if member.invitation_accepted:
        flash('This member has already accepted their invitation!', 'info')
        return redirect(url_for('team.members'))
    
    if not member.invitation_token:
        # Generate new token if missing
        member.invitation_token = secrets.token_urlsafe(32)
        db.session.commit()
    
    invitation_link = f"https://playmaster.sendbaba.com/team/accept-invite/{member.invitation_token}"
    
    flash(f'Invitation link for {member.email}: {invitation_link}', 'success')
    return redirect(url_for('team.members'))


@team_bp.route('/members/<int:member_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_member(member_id):
    """Edit team member"""
    member = TeamMember.query.get_or_404(member_id)
    
    if request.method == 'POST':
        member.first_name = request.form.get('first_name')
        member.last_name = request.form.get('last_name')
        member.department_id = request.form.get('department_id') or None
        member.role = request.form.get('role')
        member.is_active = request.form.get('is_active') == 'on'
        
        member.can_send_email = request.form.get('can_send_email') == 'on'
        member.can_manage_contacts = request.form.get('can_manage_contacts') == 'on'
        member.can_manage_campaigns = request.form.get('can_manage_campaigns') == 'on'
        member.can_view_analytics = request.form.get('can_view_analytics') == 'on'
        member.can_manage_team = request.form.get('can_manage_team') == 'on'
        member.can_manage_billing = request.form.get('can_manage_billing') == 'on'
        
        db.session.commit()
        flash(f'Team member "{member.full_name}" updated successfully!', 'success')
        return redirect(url_for('team.members'))
    
    org_id = current_user.organization_id
    departments = Department.query.filter_by(organization_id=org_id).all()
    return render_template('team/edit_member.html', member=member, departments=departments)


@team_bp.route('/members/<int:member_id>/delete', methods=['POST'])
@login_required
def delete_member(member_id):
    """Delete team member"""
    member = TeamMember.query.get_or_404(member_id)
    name = member.full_name
    
    db.session.delete(member)
    db.session.commit()
    
    flash(f'Team member "{name}" removed successfully!', 'success')
    return redirect(url_for('team.members'))
