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
    """Dynamic pricing page - fetches plans from database"""
    from app import db
    from sqlalchemy import text
    
    try:
        # Fetch individual plans
        result = db.session.execute(text("""
            SELECT id, name, slug, type, email_limit_daily, email_limit_monthly,
                   contact_limit, team_member_limit, price_monthly, price_annual,
                   features, is_popular, is_active, sort_order
            FROM pricing_plans
            WHERE is_active = true AND type = 'individual'
            ORDER BY sort_order, price_monthly
        """))
        individual_plans = []
        for row in result:
            plan = {
                'id': row[0], 'name': row[1], 'slug': row[2], 'type': row[3],
                'email_limit_daily': row[4], 'email_limit_monthly': row[5],
                'contact_limit': row[6], 'team_member_limit': row[7],
                'price_monthly': float(row[8] or 0), 'price_annual': float(row[9] or 0),
                'features': row[10] if isinstance(row[10], list) else [],
                'is_popular': row[11], 'is_active': row[12], 'sort_order': row[13]
            }
            # Parse features if it's a string
            if plan['features'] and isinstance(plan['features'], str):
                import json
                try:
                    plan['features'] = json.loads(plan['features'])
                except:
                    plan['features'] = []
            individual_plans.append(plan)
        
        # Fetch team plans
        result = db.session.execute(text("""
            SELECT id, name, slug, type, email_limit_daily, email_limit_monthly,
                   contact_limit, team_member_limit, price_monthly, price_annual,
                   features, is_popular, is_active, sort_order
            FROM pricing_plans
            WHERE is_active = true AND type = 'team'
            ORDER BY sort_order, price_monthly
        """))
        team_plans = []
        for row in result:
            plan = {
                'id': row[0], 'name': row[1], 'slug': row[2], 'type': row[3],
                'email_limit_daily': row[4], 'email_limit_monthly': row[5],
                'contact_limit': row[6], 'team_member_limit': row[7],
                'price_monthly': float(row[8] or 0), 'price_annual': float(row[9] or 0),
                'features': row[10] if isinstance(row[10], list) else [],
                'is_popular': row[11], 'is_active': row[12], 'sort_order': row[13]
            }
            if plan['features'] and isinstance(plan['features'], str):
                import json
                try:
                    plan['features'] = json.loads(plan['features'])
                except:
                    plan['features'] = []
            team_plans.append(plan)
        
        return render_template('pricing.html', 
                             individual_plans=individual_plans, 
                             team_plans=team_plans)
    except Exception as e:
        print(f"Pricing error: {e}")
        return render_template('pricing.html', individual_plans=[], team_plans=[])

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
