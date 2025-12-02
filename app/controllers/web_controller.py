"""
SendBaba Web Controller - Landing Pages
"""
from flask import Blueprint, render_template, request, flash, redirect, url_for

web_bp = Blueprint('web', __name__)

@web_bp.route('/')
def index():
    return render_template('index.html')

@web_bp.route('/pricing')
def pricing():
    return render_template('pricing.html')

@web_bp.route('/features')
def features():
    return render_template('features.html')

@web_bp.route('/docs')
def docs():
    return render_template('docs.html')

@web_bp.route('/about')
def about():
    return render_template('about.html')

@web_bp.route('/contact')
def contact():
    return render_template('contact.html')

@web_bp.route('/contact/submit', methods=['POST'])
def contact_submit():
    name = request.form.get('name')
    email = request.form.get('email')
    subject = request.form.get('subject')
    message = request.form.get('message')
    # TODO: Send email or save to database
    flash('Thank you for your message! We will get back to you soon.', 'success')
    return redirect(url_for('web.contact'))


@web_bp.route('/verify-email/<token>')
def verify_email(token):
    """Verify user email - root level route"""
    from app.models.user import User
    from app import db
    from flask import flash, redirect, url_for
    from flask_login import current_user
    
    user = User.query.filter_by(verification_token=token).first()
    
    if not user:
        flash('Invalid or expired verification link.', 'error')
        return redirect('/auth/login')
    
    user.is_verified = True
    user.verification_token = None
    db.session.commit()
    
    flash('Email verified successfully!', 'success')
    
    if current_user.is_authenticated:
        return redirect('/dashboard/')
    return redirect('/auth/login')
