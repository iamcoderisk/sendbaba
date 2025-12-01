"""
Team Invitation Acceptance Controller
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user
from app import db
from app.models.team import TeamMember
from app.models.user import User
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
team_invite_bp = Blueprint('team_invite', __name__, url_prefix='/team')


@team_invite_bp.route('/accept-invite/<token>', methods=['GET', 'POST'])
def accept_invite(token):
    """Accept team invitation and set password"""
    member = TeamMember.query.filter_by(invitation_token=token).first()
    
    if not member:
        flash('Invalid invitation link!', 'error')
        return redirect(url_for('auth.login'))
    
    if member.invitation_accepted:
        flash('This invitation has already been accepted! Please log in.', 'info')
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate password
        if not password or len(password) < 8:
            flash('Password must be at least 8 characters long!', 'error')
            return render_template('team/accept_invite.html', member=member)
        
        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return render_template('team/accept_invite.html', member=member)
        
        try:
            # Check if user already exists with this email
            existing_user = User.query.filter_by(email=member.email).first()
            
            if existing_user:
                # User exists - just link the team member to them
                member.user_id = existing_user.id
                member.invitation_accepted = True
                member.is_active = True
                member.invitation_token = None
                member.last_login = datetime.utcnow()
                
                # Update existing user's password if they want
                existing_user.set_password(password)
                
                db.session.commit()
                
                flash('Welcome back! Your team membership has been activated.', 'success')
                
            else:
                # Create new User account from TeamMember
                new_user = User(
                    email=member.email,
                    password=password,  # User model will hash it
                    first_name=member.first_name,
                    last_name=member.last_name
                )
                new_user.organization_id = member.organization_id
                new_user.is_active = True
                new_user.is_verified = True
                new_user.role = member.role
                new_user.last_login = datetime.utcnow()
                
                db.session.add(new_user)
                db.session.flush()  # Get the user ID
                
                # Link TeamMember to User
                member.user_id = new_user.id
                member.invitation_accepted = True
                member.is_active = True
                member.invitation_token = None
                member.last_login = datetime.utcnow()
                
                # Copy password hash to team member (for reference)
                member.password_hash = new_user.password_hash
                
                db.session.commit()
                
                flash('Welcome to the team! You can now log in with your email and password.', 'success')
            
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error accepting invitation: {e}")
            import traceback
            traceback.print_exc()
            flash('An error occurred. Please try again.', 'error')
            return render_template('team/accept_invite.html', member=member)
    
    return render_template('team/accept_invite.html', member=member)
