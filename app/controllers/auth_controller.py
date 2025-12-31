"""Authentication controller"""
import re
import secrets
import hashlib
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import db, User, Organization
import logging

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# Check if email service is available
try:
    from app.services.email_service import EmailService
    HAS_EMAIL_SERVICE = True
except ImportError:
    HAS_EMAIL_SERVICE = False


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect('/dashboard/')

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Email and password required', 'error')
            return render_template('auth/login.html')

        user = User.query.filter_by(email=email).first()

        if not user:
            flash('Invalid email or password', 'error')
            return render_template('auth/login.html')

        if not user.check_password(password):
            flash('Invalid email or password', 'error')
            return render_template('auth/login.html')

        if not user.is_active:
            flash('Your account has been deactivated. Please contact support.', 'error')
            return render_template('auth/login.html')

        login_user(user, remember=True)

        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        return redirect('/dashboard/')

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration with product choice"""
    if current_user.is_authenticated:
        return redirect('/dashboard/')

    if request.method == 'POST':
        registration_type = request.form.get('registration_type', 'campaign')

        if registration_type == 'mailbox':
            return _register_mailbox()
        else:
            return _register_campaign()

    return render_template('auth/register.html')


def _register_campaign():
    """Handle campaign user registration"""
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    name = request.form.get('name', '').strip()

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
        org = Organization(name=f"{name}'s Organization")
        db.session.add(org)
        db.session.flush()

        user = User(
            email=email,
            password=password,
            first_name=name.split()[0] if name else '',
            last_name=' '.join(name.split()[1:]) if len(name.split()) > 1 else ''
        )
        user.organization_id = org.id
        user.role = 'owner'
        user.is_verified = True
        user.registration_type = 'campaign'

        db.session.add(user)
        db.session.commit()

        if HAS_EMAIL_SERVICE:
            try:
                email_svc = EmailService()
                user_name = name.split()[0] if name else email.split('@')[0]
                email_svc.send_welcome_email(email, user_name, '')
            except Exception as e:
                logger.error(f"Welcome email error: {e}")

        login_user(user)
        flash('Registration successful! Welcome to SendBaba.', 'success')
        return redirect('/dashboard/')

    except Exception as e:
        db.session.rollback()
        logger.error(f"Signup error: {e}")
        flash('Registration failed. Please try again.', 'error')
        return render_template('auth/register.html')


def _register_mailbox():
    """Handle mailbox user registration"""
    import psycopg2
    from psycopg2.extras import RealDictCursor

    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    recovery_email = request.form.get('recovery_email', '').strip().lower()
    username = request.form.get('username', '').strip().lower()
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')

    name = f"{first_name} {last_name}".strip()
    sendbaba_email = f"{username}@sendbaba.com"

    if not first_name or not last_name:
        flash('First name and last name are required', 'error')
        return render_template('auth/register.html')

    if not username or not recovery_email or not password:
        flash('All fields are required', 'error')
        return render_template('auth/register.html')

    if len(password) < 8:
        flash('Password must be at least 8 characters long', 'error')
        return render_template('auth/register.html')

    if password != confirm_password:
        flash('Passwords do not match', 'error')
        return render_template('auth/register.html')

    if len(username) < 3:
        flash('Username must be at least 3 characters', 'error')
        return render_template('auth/register.html')

    if not re.match(r'^[a-z0-9._]+$', username):
        flash('Username can only contain lowercase letters, numbers, dots, and underscores', 'error')
        return render_template('auth/register.html')

    conn = None
    try:
        conn = psycopg2.connect("postgresql://emailer:SecurePassword123@localhost/emailer")
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT id FROM mailboxes WHERE email = %s", (sendbaba_email,))
        if cur.fetchone():
            flash('This SendBaba email is already taken. Please choose another.', 'error')
            conn.close()
            return render_template('auth/register.html')

        existing_user = User.query.filter_by(email=recovery_email).first()
        
        if existing_user:
            user_id = existing_user.id
        else:
            org = Organization(name=f"{name}'s Mailbox")
            db.session.add(org)
            db.session.flush()

            user = User(
                email=recovery_email,
                password=password,
                first_name=first_name,
                last_name=last_name
            )
            user.organization_id = org.id
            user.role = 'owner'
            user.is_verified = True
            user.registration_type = 'mailbox'

            db.session.add(user)
            db.session.commit()
            user_id = user.id

        slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
        slug = f"{slug}-{secrets.token_hex(4)}"

        cur.execute("""
            INSERT INTO mailbox_organizations (name, slug, owner_user_id, plan, max_mailboxes, max_storage_gb, is_active)
            VALUES (%s, %s, %s, 'free', 5, 1, true)
            RETURNING id
        """, (f"{name}'s Mailbox", slug, user_id))

        org_row = cur.fetchone()
        org_id = org_row['id']

        password_hash = hashlib.sha256(password.encode()).hexdigest()
        cur.execute("""
            INSERT INTO mailboxes (organization_id, email, name, password_hash, role, is_active, recovery_email, storage_used_mb)
            VALUES (%s, %s, %s, %s, 'admin', true, %s, 0)
            RETURNING id
        """, (org_id, sendbaba_email, name, password_hash, recovery_email))

        conn.commit()
        conn.close()

        try:
            from app.smtp.relay_server import send_email_sync
            html_body = f'''
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="text-align: center; margin-bottom: 30px;">
                        <h1 style="color: #F7601F;">Welcome to SendBaba Mail!</h1>
                    </div>
                    <p>Hi <strong>{first_name}</strong>,</p>
                    <p>Your SendBaba Mail account has been created successfully!</p>
                    <div style="background: #FFF7ED; padding: 24px; border-radius: 16px; margin: 24px 0; border: 1px solid #F7601F;">
                        <h3 style="margin: 0 0 12px; color: #F7601F;">Your Account Details:</h3>
                        <p style="margin: 8px 0;"><strong>Email:</strong> {sendbaba_email}</p>
                        <p style="margin: 8px 0;"><strong>Login:</strong> <a href="https://mail.sendbaba.com">mail.sendbaba.com</a></p>
                    </div>
                </div>
            </body>
            </html>
            '''
            send_email_sync({
                'from': 'noreply@sendbaba.com',
                'from_name': 'SendBaba Mail',
                'to': recovery_email,
                'subject': f'Your SendBaba Mail Account: {sendbaba_email}',
                'html_body': html_body,
                'text_body': f'Your SendBaba Mail: {sendbaba_email}\nLogin: https://mail.sendbaba.com'
            })
        except Exception as e:
            logger.error(f"Failed to send credentials: {e}")

        flash('Registration successful! You can now login at mail.sendbaba.com', 'success')
        return redirect('https://mail.sendbaba.com')

    except Exception as e:
        db.session.rollback()
        if conn:
            conn.rollback()
            conn.close()
        logger.error(f"Mailbox signup error: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Registration failed. Please try again.', 'error')
        return render_template('auth/register.html')


@auth_bp.route('/api/check-email')
def check_email_availability():
    """Check if a SendBaba email is available"""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    username = request.args.get('username', '').lower().strip()
    
    if not username or len(username) < 3:
        return jsonify({'available': False, 'error': 'Username must be at least 3 characters'})
    
    if not re.match(r'^[a-z0-9._]+$', username):
        return jsonify({'available': False, 'error': 'Invalid characters in username'})
    
    email = f"{username}@sendbaba.com"
    
    try:
        conn = psycopg2.connect("postgresql://emailer:SecurePassword123@localhost/emailer")
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT id FROM mailboxes WHERE email = %s", (email,))
        exists = cur.fetchone() is not None
        conn.close()
        
        if exists:
            suggestions = [f"{username}1", f"{username}2", f"{username}123", f"{username}.mail"]
            return jsonify({'available': False, 'suggestions': suggestions})
        
        return jsonify({'available': True, 'email': email})
        
    except Exception as e:
        logger.error(f"Email check error: {e}")
        return jsonify({'available': False, 'error': 'Check failed, please try again'})


@auth_bp.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/verify-email/<token>')
def verify_email(token):
    """Verify email with token"""
    user = User.query.filter_by(verification_token=token).first()
    if not user:
        flash('Invalid or expired verification link.', 'error')
        return redirect(url_for('auth.login'))
    user.is_verified = True
    user.verification_token = None
    db.session.commit()
    flash('Email verified successfully! You can now login.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Handle forgot password"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('Please enter your email address', 'error')
            return render_template('auth/forgot_password.html')
        user = User.query.filter_by(email=email).first()
        if user:
            token = secrets.token_urlsafe(32)
            user.verification_token = token
            db.session.commit()
            logger.info(f"Password reset requested for {email}")
        flash('If an account exists with that email, you will receive a password reset link.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html')
