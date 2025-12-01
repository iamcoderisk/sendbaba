from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from app import db
from app.models.user import User
from app.models.organization import Organization
from datetime import datetime

auth_bp = Blueprint('auth', __name__)

# Try to import TeamMember, but don't fail if it doesn't exist
try:
    from app.models.team import TeamMember
    HAS_TEAM_MEMBER = True
except ImportError:
    HAS_TEAM_MEMBER = False

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login - checks both regular users and team members"""
    if current_user.is_authenticated:
        return redirect('/dashboard/')
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            flash('Please enter email and password', 'error')
            return render_template('auth/login.html')
        
        # Try to find user
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=request.form.get('remember', False))
            
            # Update last login
            try:
                user.last_login = datetime.utcnow()
                
                # Also update team member if linked
                if HAS_TEAM_MEMBER:
                    team_member = TeamMember.query.filter_by(user_id=user.id).first()
                    if team_member:
                        team_member.last_login = datetime.utcnow()
                
                db.session.commit()
            except:
                pass
            
            # Redirect to next page or dashboard
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect('/dashboard/')
        else:
            # Check if they're a team member who hasn't accepted invitation yet
            if HAS_TEAM_MEMBER:
                team_member = TeamMember.query.filter_by(email=email, invitation_accepted=False).first()
                if team_member:
                    flash('Please accept your team invitation first. Check your email for the invitation link.', 'warning')
                    return render_template('auth/login.html')
            
            flash('Invalid email or password', 'error')
    
    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if current_user.is_authenticated:
        return redirect('/dashboard/')
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name', email.split('@')[0] if email else '')
        
        if not email or not password:
            flash('Email and password required', 'error')
            return render_template('auth/register.html')
        
        # Validate password length
        if len(password) < 8:
            flash('Password must be at least 8 characters long', 'error')
            return render_template('auth/register.html')
        
        # Check if user exists
        if User.query.filter_by(email=email).first():
            flash('Email already registered. Please login instead.', 'error')
            return redirect(url_for('auth.login'))
        
        try:
            # Create organization
            org = Organization(name=f"{name}'s Organization")
            db.session.add(org)
            db.session.flush()
            
            # Create user
            user = User(
                email=email,
                password=password,
                first_name=name.split()[0] if name else '',
                last_name=' '.join(name.split()[1:]) if len(name.split()) > 1 else ''
            )
            user.organization_id = org.id
            user.role = 'owner'
            user.is_verified = True
            
            db.session.add(user)
            db.session.commit()
            
            # Log the user in
            login_user(user)
            flash('Registration successful! Welcome to SendBaba.', 'success')
            return redirect('/dashboard/')
            
        except Exception as e:
            db.session.rollback()
            flash('Registration failed. Please try again.', 'error')
            print(f"Signup error: {e}")
            import traceback
            traceback.print_exc()
    
    return render_template('auth/register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out successfully.', 'success')
    return redirect('/')

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Forgot password"""
    if request.method == 'POST':
        email = request.form.get('email')
        # TODO: Implement password reset logic
        flash('Password reset instructions sent to your email.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/forgot_password.html')

# Legacy routes for backward compatibility
@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    return register()

@auth_bp.route('/auth/login', methods=['GET', 'POST'])
def auth_login():
    return login()

@auth_bp.route('/auth/register', methods=['GET', 'POST'])
def auth_register():
    return register()

@auth_bp.route('/auth/signup', methods=['GET', 'POST'])
def auth_signup():
    return register()

@auth_bp.route('/auth/logout')
@login_required
def auth_logout():
    return logout()
