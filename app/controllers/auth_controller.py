from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from app import db
from app.models.user import User
from app.models.organization import Organization
from datetime import datetime
import secrets
import logging

logger = logging.getLogger(__name__)
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# Email service
HAS_EMAIL_SERVICE = False
try:
    from app.services.email_service import EmailService, on_user_register, on_user_login
    HAS_EMAIL_SERVICE = True
    logger.info("✅ Email service loaded")
except ImportError as e:
    logger.error(f"❌ Email service not available: {e}")

# Team member support
try:
    from app.models.team import TeamMember
    HAS_TEAM_MEMBER = True
except ImportError:
    HAS_TEAM_MEMBER = False


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect('/dashboard/')
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            flash('Please enter email and password', 'error')
            return render_template('auth/login.html')
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=request.form.get('remember', False))
            
            # Update last login
            try:
                user.last_login = datetime.utcnow()
                db.session.commit()
            except:
                db.session.rollback()
            
            next_page = request.args.get('next')
            if next_page and 'logout' not in next_page:
                return redirect(next_page)
            return redirect('/dashboard/')
        else:
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
        
        if len(password) < 8:
            flash('Password must be at least 8 characters long', 'error')
            return render_template('auth/register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered. Please login instead.', 'error')
            return redirect(url_for('auth.login'))
        
        try:
            # Create organization
            org = Organization(name=f"{name}'s Organization")
            db.session.add(org)
            db.session.flush()
            logger.info(f"✅ Organization created: {org.id}")
            
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
            logger.info(f"✅ User created: {user.email}")
            
            # Send welcome email AFTER commit (separate transaction)
            if HAS_EMAIL_SERVICE:
                try:
                    logger.info(f"📧 Sending welcome email to {user.email}...")
                    email_svc = EmailService()
                    user_name = name.split()[0] if name else email.split('@')[0]
                    verification_token = secrets.token_urlsafe(32)
                    result = email_svc.send_welcome_email(user.email, user_name, verification_token)
                    if result:
                        logger.info(f"✅ Welcome email sent to {user.email}")
                    else:
                        logger.error(f"❌ Welcome email failed for {user.email}")
                except Exception as e:
                    logger.error(f"❌ Welcome email error: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                logger.warning("⚠️ Email service not available")
            
            # Log the user in
            login_user(user)
            flash('Registration successful! Welcome to SendBaba.', 'success')
            return redirect('/dashboard/')
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"❌ Signup error: {e}")
            import traceback
            traceback.print_exc()
            flash('Registration failed. Please try again.', 'error')
    
    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect('/')


@auth_bp.route('/verify-email/<token>')
def verify_email(token):
    """Verify user email"""
    user = User.query.filter_by(verification_token=token).first()
    
    if not user:
        flash('Invalid or expired verification link.', 'error')
        return redirect(url_for('auth.login'))
    
    user.is_verified = True
    user.verification_token = None
    db.session.commit()
    
    flash('Email verified successfully! You now have full access.', 'success')
    
    if current_user.is_authenticated:
        return redirect('/dashboard/')
    return redirect(url_for('auth.login'))


@auth_bp.route('/resend-verification')
@login_required
def resend_verification_email():
    """Resend verification email"""
    if getattr(current_user, 'is_verified', True):
        flash('Your email is already verified.', 'info')
        return redirect('/dashboard/')
    
    try:
        from app.services.email_service import EmailService
        import secrets
        
        token = secrets.token_urlsafe(32)
        current_user.verification_token = token
        db.session.commit()
        
        email_svc = EmailService()
        user_name = current_user.first_name or current_user.email.split('@')[0]
        email_svc.send_welcome_email(current_user.email, user_name, token)
        
        flash('Verification email sent! Check your inbox.', 'success')
    except Exception as e:
        flash('Failed to send verification email.', 'error')
    
    return redirect('/dashboard/')
