"""
Auth Hooks - Integration with authentication system
Add these calls to your auth controller for login/registration
"""
from flask import request
from app.services.login_helper import get_login_info, send_login_notification, log_login_activity
from app.services.email_service import email_service
import secrets
import logging

logger = logging.getLogger(__name__)


def on_user_register(user, send_verification=True):
    """
    Call this after a new user registers
    
    Usage in your auth controller:
        from app.services.auth_hooks import on_user_register
        
        # After creating user:
        on_user_register(user)
    """
    try:
        # Generate verification token
        verification_token = secrets.token_urlsafe(32)
        
        # Save token to user (you may need to add this field to your User model)
        user.verification_token = verification_token
        
        from app import db
        db.session.commit()
        
        if send_verification:
            # Get user name
            user_name = getattr(user, 'first_name', None) or user.email.split('@')[0]
            
            # Send welcome email
            email_service.send_welcome_email(
                user_email=user.email,
                user_name=user_name,
                verification_token=verification_token
            )
            
            logger.info(f"Welcome email sent to {user.email}")
        
        return verification_token
    except Exception as e:
        logger.error(f"Failed to handle registration: {e}")
        return None


def on_user_login(user, send_notification=True):
    """
    Call this after a user successfully logs in
    
    Usage in your auth controller:
        from app.services.auth_hooks import on_user_login
        
        # After successful login:
        on_user_login(user)
    """
    try:
        # Capture login info
        login_info = get_login_info()
        
        # Log to database
        log_login_activity(user, login_info)
        
        # Send notification email
        if send_notification:
            send_login_notification(user, login_info)
        
        # Update last login
        from datetime import datetime
        from app import db
        
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        return login_info
    except Exception as e:
        logger.error(f"Failed to handle login: {e}")
        return None


def on_password_reset_request(user):
    """
    Call this when user requests password reset
    
    Usage:
        from app.services.auth_hooks import on_password_reset_request
        on_password_reset_request(user)
    """
    try:
        reset_token = secrets.token_urlsafe(32)
        
        user.reset_token = reset_token
        
        from app import db
        from datetime import datetime, timedelta
        
        user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()
        
        user_name = getattr(user, 'first_name', None) or user.email.split('@')[0]
        
        email_service.send_password_reset(
            user_email=user.email,
            user_name=user_name,
            reset_token=reset_token
        )
        
        logger.info(f"Password reset email sent to {user.email}")
        return reset_token
    except Exception as e:
        logger.error(f"Failed to send password reset: {e}")
        return None


# Example integration code for your auth controller:
"""
# In app/controllers/auth_controller.py

from app.services.auth_hooks import on_user_register, on_user_login, on_password_reset_request

@auth_bp.route('/register', methods=['POST'])
def register():
    # ... your registration logic ...
    
    # Create user
    user = User(email=email, password=password)
    db.session.add(user)
    db.session.commit()
    
    # Send welcome email with verification
    on_user_register(user)
    
    return jsonify({'success': True})


@auth_bp.route('/login', methods=['POST'])
def login():
    # ... your login logic ...
    
    # After successful authentication:
    login_user(user)
    
    # Send login notification
    on_user_login(user)
    
    return redirect('/dashboard')


@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    email = request.form.get('email')
    user = User.query.filter_by(email=email).first()
    
    if user:
        on_password_reset_request(user)
    
    # Always return success to prevent email enumeration
    return jsonify({'success': True})
"""
