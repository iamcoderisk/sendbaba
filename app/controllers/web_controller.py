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
