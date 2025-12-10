"""
SendBaba Billing Controller - Payonus Integration
"""
from flask import Blueprint, render_template, request, jsonify, session, redirect
from flask_login import login_required, current_user
from app import db
from sqlalchemy import text
from datetime import datetime, timedelta
import json
import uuid
import requests
import logging
import os
import time

logger = logging.getLogger(__name__)

billing_bp = Blueprint('billing', __name__, url_prefix='/dashboard/billing')

# Payonus Configuration
PAYONUS_CLIENT_ID = os.environ.get('PAYONUS_CLIENT_ID', 'sk_live_prin56l8CT3QnF0l5Uv6s6NJ')
PAYONUS_CLIENT_SECRET = os.environ.get('PAYONUS_CLIENT_SECRET', 'GgqWiKbYlPQv8PVbLYYpIxoZMiQvE3vHFdn87QVXO7M3HILyXmcgEc3lzJ6V4ox9')
PAYONUS_BUSINESS_ID = os.environ.get('PAYONUS_BUSINESS_ID', 'f91791b6-bef5-44d9-a6ef-9f14106d319c')
PAYONUS_BASE_URL = 'https://core.payonus.com'

# Cache for access token
_payonus_token_cache = {'token': None, 'expires_at': 0}


def get_payonus_token():
    """Get Payonus access token with caching"""
    global _payonus_token_cache
    
    if _payonus_token_cache['token'] and time.time() < _payonus_token_cache['expires_at']:
        return _payonus_token_cache['token']
    
    try:
        resp = requests.post(
            f'{PAYONUS_BASE_URL}/api/v1/access-token',
            json={'apiClientId': PAYONUS_CLIENT_ID, 'apiClientSecret': PAYONUS_CLIENT_SECRET},
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        data = resp.json()
        if data.get('status') == 200:
            token = data['data']['access_token']
            expires_in = data['data'].get('expires_in', 86399)
            _payonus_token_cache = {'token': token, 'expires_at': time.time() + expires_in - 60}
            return token
    except Exception as e:
        logger.error(f"Payonus token error: {e}")
    return None


def get_organization_id():
    if current_user.is_authenticated:
        return getattr(current_user, 'organization_id', session.get('organization_id'))
    return session.get('organization_id')


def get_user_email():
    if current_user.is_authenticated:
        return getattr(current_user, 'email', '')
    return ''


def get_user_name():
    if current_user.is_authenticated:
        email = getattr(current_user, 'email', 'Customer')
        return email.split('@')[0] if email else 'Customer'
    return 'Customer'


def get_or_create_free_plan():
    """Get or create a free plan and return its ID"""
    try:
        result = db.session.execute(text("SELECT id FROM pricing_plans WHERE slug = 'free' LIMIT 1"))
        row = result.fetchone()
        if row:
            return row[0]
        
        plan_id = str(uuid.uuid4())
        db.session.execute(text("""
            INSERT INTO pricing_plans (id, name, slug, type, email_limit_daily, email_limit_monthly, 
                contact_limit, team_member_limit, price_monthly, price_annual, features, is_popular, is_active, sort_order)
            VALUES (:id, 'Free', 'free', 'individual', 100, 1000, 500, 1, 0, 0, 
                '["100 emails/day", "500 contacts", "Basic templates"]', false, true, 0)
        """), {'id': plan_id})
        db.session.commit()
        return plan_id
    except Exception as e:
        logger.error(f"Error getting/creating free plan: {e}")
        db.session.rollback()
        return str(uuid.uuid4())


def get_subscription(org_id):
    """Get subscription for organization"""
    try:
        result = db.session.execute(text("""
            SELECT id, plan_type, plan_name, status, billing_cycle, current_price,
                   email_limit_daily, email_limit_monthly, contact_limit, team_member_limit,
                   is_trial, trial_ends_at, current_period_start, current_period_end, next_billing_at
            FROM subscriptions WHERE organization_id = :org_id ORDER BY created_at DESC LIMIT 1
        """), {'org_id': org_id})
        
        row = result.fetchone()
        if row:
            return {
                'id': row[0], 'plan_type': row[1] or 'free', 'plan_name': row[2] or 'Free Trial',
                'status': row[3] or 'trial', 'billing_cycle': row[4] or 'monthly',
                'current_price': float(row[5] or 0), 'email_limit_daily': row[6] or 100,
                'email_limit_monthly': row[7] or 1000, 'contact_limit': row[8] or 500,
                'team_member_limit': row[9] or 1, 'is_trial': row[10] if row[10] is not None else True,
                'trial_ends_at': row[11], 'current_period_start': row[12],
                'current_period_end': row[13], 'next_billing_at': row[14]
            }
        
        # Create trial subscription
        sub_id = str(uuid.uuid4())
        plan_id = get_or_create_free_plan()
        now = datetime.utcnow()
        trial_end = now + timedelta(days=14)
        
        db.session.execute(text("""
            INSERT INTO subscriptions (id, organization_id, plan_id, plan_type, plan_name, status, 
                email_limit_daily, email_limit_monthly, contact_limit, team_member_limit,
                is_trial, trial_started_at, trial_ends_at, started_at, current_period_start, current_period_end, created_at)
            VALUES (:id, :org_id, :plan_id, 'free', 'Free Trial', 'trial', 100, 1000, 500, 1, 
                    true, :now, :trial_end, :now, :now, :trial_end, :now)
        """), {'id': sub_id, 'org_id': org_id, 'plan_id': plan_id, 'now': now, 'trial_end': trial_end})
        db.session.commit()
        
        return {
            'id': sub_id, 'plan_type': 'free', 'plan_name': 'Free Trial', 'status': 'trial',
            'billing_cycle': 'monthly', 'current_price': 0, 'email_limit_daily': 100,
            'email_limit_monthly': 1000, 'contact_limit': 500, 'team_member_limit': 1,
            'is_trial': True, 'trial_ends_at': trial_end, 'current_period_start': now,
            'current_period_end': trial_end, 'next_billing_at': None
        }
    except Exception as e:
        logger.error(f"Error getting subscription: {e}")
        db.session.rollback()
        return {'id': None, 'plan_type': 'free', 'plan_name': 'Free', 'status': 'trial',
                'billing_cycle': 'monthly', 'current_price': 0, 'email_limit_daily': 100,
                'email_limit_monthly': 1000, 'contact_limit': 500, 'team_member_limit': 1,
                'is_trial': True, 'trial_ends_at': datetime.utcnow() + timedelta(days=14),
                'current_period_start': datetime.utcnow(), 'current_period_end': datetime.utcnow() + timedelta(days=14),
                'next_billing_at': None}


def ensure_pricing_plans():
    try:
        count = db.session.execute(text("SELECT COUNT(*) FROM pricing_plans")).scalar()
        if count == 0:
            plans = [
                ('Free', 'free', 'individual', 100, 1000, 500, 1, 0, 0, '["100 emails/day", "500 contacts", "Basic templates"]', False, 1),
                ('Starter', 'starter', 'individual', 1000, 25000, 5000, 3, 29, 278, '["1,000 emails/day", "5,000 contacts", "Priority support"]', False, 2),
                ('Business', 'business', 'individual', 5000, 100000, 25000, 10, 79, 758, '["5,000 emails/day", "25,000 contacts", "API access"]', True, 3),
                ('Enterprise', 'enterprise', 'individual', 50000, 1000000, 100000, 50, 249, 2390, '["50,000 emails/day", "Dedicated IP", "SLA guarantee"]', False, 4),
            ]
            for name, slug, ptype, daily, monthly, contacts, team, price_m, price_a, features, popular, sort in plans:
                db.session.execute(text("""
                    INSERT INTO pricing_plans (id, name, slug, type, email_limit_daily, email_limit_monthly, 
                        contact_limit, team_member_limit, price_monthly, price_annual, features, is_popular, is_active, sort_order)
                    VALUES (:id, :name, :slug, :type, :daily, :monthly, :contacts, :team, :price_m, :price_a, :features, :popular, true, :sort)
                """), {'id': str(uuid.uuid4()), 'name': name, 'slug': slug, 'type': ptype, 'daily': daily,
                       'monthly': monthly, 'contacts': contacts, 'team': team, 'price_m': price_m,
                       'price_a': price_a, 'features': features, 'popular': popular, 'sort': sort})
            db.session.commit()
    except Exception as e:
        logger.error(f"Error ensuring pricing plans: {e}")
        db.session.rollback()


def parse_features(features_data):
    if features_data is None:
        return []
    if isinstance(features_data, list):
        return features_data
    if isinstance(features_data, str):
        try:
            return json.loads(features_data)
        except:
            return []
    return []


@billing_bp.route('/')
@billing_bp.route('')
@billing_bp.route('/dashboard')
@login_required
def billing_dashboard():
    org_id = get_organization_id()
    subscription = get_subscription(org_id)
    
    now = datetime.utcnow()
    today = now.date()
    month_start = now.replace(day=1).date()
    
    try:
        daily_emails = db.session.execute(text("SELECT COUNT(*) FROM emails WHERE organization_id = :org_id AND DATE(created_at) = :today"), 
                                          {'org_id': org_id, 'today': today}).scalar() or 0
        monthly_emails = db.session.execute(text("SELECT COUNT(*) FROM emails WHERE organization_id = :org_id AND created_at >= :month_start"), 
                                            {'org_id': org_id, 'month_start': month_start}).scalar() or 0
        contact_count = db.session.execute(text("SELECT COUNT(*) FROM contacts WHERE organization_id = :org_id"), {'org_id': org_id}).scalar() or 0
    except:
        daily_emails, monthly_emails, contact_count = 0, 0, 0
    
    usage = {
        'daily_emails': daily_emails, 'monthly_emails': monthly_emails, 'total_contacts': contact_count,
        'contact_count': contact_count, 'daily_limit': subscription.get('email_limit_daily', 100),
        'monthly_limit': subscription.get('email_limit_monthly', 1000), 'contact_limit': subscription.get('contact_limit', 500),
        'email_limit_daily': subscription.get('email_limit_daily', 100), 'email_limit_monthly': subscription.get('email_limit_monthly', 1000),
    }
    
    ensure_pricing_plans()
    try:
        result = db.session.execute(text("""
            SELECT id, name, slug, type, price_monthly, price_annual, features, 
                   email_limit_daily, email_limit_monthly, contact_limit, team_member_limit, is_popular
            FROM pricing_plans WHERE is_active = true ORDER BY sort_order
        """))
        plans = [{'id': r[0], 'name': r[1], 'slug': r[2], 'type': r[3], 'price_monthly': float(r[4] or 0),
                  'price_annual': float(r[5] or 0), 'features': parse_features(r[6]), 'email_limit_daily': r[7], 
                  'email_limit_monthly': r[8], 'contact_limit': r[9], 'team_member_limit': r[10], 'is_popular': r[11]} for r in result]
    except:
        plans = []
    
    try:
        result = db.session.execute(text("SELECT id, transaction_type, amount, currency, status, created_at, description FROM billing_history WHERE organization_id = :org_id ORDER BY created_at DESC LIMIT 10"), {'org_id': org_id})
        history = [{'id': r[0], 'type': r[1], 'amount': float(r[2] or 0), 'currency': r[3] or 'NGN', 'status': r[4], 'date': r[5], 'description': r[6]} for r in result]
    except:
        history = []
    
    return render_template('billing/dashboard.html', subscription=subscription, usage=usage, plans=plans, history=history)


@billing_bp.route('/plans')
@login_required
def plans_page():
    org_id = get_organization_id()
    subscription = get_subscription(org_id)
    ensure_pricing_plans()
    
    try:
        result = db.session.execute(text("""
            SELECT id, name, slug, type, price_monthly, price_annual, features, 
                   email_limit_daily, email_limit_monthly, contact_limit, team_member_limit, is_popular
            FROM pricing_plans WHERE is_active = true ORDER BY sort_order
        """))
        plans = [{'id': r[0], 'name': r[1], 'slug': r[2], 'type': r[3], 'price_monthly': float(r[4] or 0),
                  'price_annual': float(r[5] or 0), 'features': parse_features(r[6]), 'email_limit_daily': r[7], 
                  'email_limit_monthly': r[8], 'contact_limit': r[9], 'team_member_limit': r[10], 'is_popular': r[11]} for r in result]
    except:
        plans = []
    
    individual_plans = [p for p in plans if p['type'] == 'individual']
    team_plans = [p for p in plans if p['type'] == 'team']
    
    return render_template('billing/plans.html', subscription=subscription, plans=plans, individual_plans=individual_plans, team_plans=team_plans)


@billing_bp.route('/invoices')
@login_required
def invoices():
    org_id = get_organization_id()
    try:
        result = db.session.execute(text("SELECT id, invoice_number, total, currency, status, invoice_date, due_date, paid_at, pdf_url FROM invoices WHERE organization_id = :org_id ORDER BY invoice_date DESC LIMIT 50"), {'org_id': org_id})
        invoices = [{'id': r[0], 'invoice_number': r[1], 'total': float(r[2] or 0), 'currency': r[3] or 'NGN', 'status': r[4], 'invoice_date': r[5], 'due_date': r[6], 'paid_at': r[7], 'pdf_url': r[8]} for r in result]
    except:
        invoices = []
    return render_template('billing/invoices.html', invoices=invoices)


@billing_bp.route('/api/subscription')
@login_required
def api_subscription():
    return jsonify({'success': True, 'subscription': get_subscription(get_organization_id())})


@billing_bp.route('/api/initialize-payment', methods=['POST'])
@login_required
def api_initialize_payment():
    """Initialize payment with Payonus Payment Links"""
    org_id = get_organization_id()
    data = request.get_json()
    
    plan_slug = data.get('plan')
    billing_cycle = data.get('billing_cycle', 'monthly')
    
    try:
        result = db.session.execute(text("SELECT id, name, price_monthly, price_annual FROM pricing_plans WHERE slug = :slug"), {'slug': plan_slug})
        plan = result.fetchone()
        if not plan:
            return jsonify({'success': False, 'error': 'Plan not found'})
        price = float(plan[3]) if billing_cycle == 'annual' else float(plan[2])
        plan_name = plan[1]
    except:
        return jsonify({'success': False, 'error': 'Plan not found'})
    
    if price <= 0:
        return jsonify({'success': False, 'error': 'Cannot checkout free plan'})
    
    # Convert to NGN (assuming USD price * 1500 rate, or use direct NGN)
    amount_ngn = int(price * 1500)  # Adjust exchange rate as needed
    reference = f"sb-{org_id[:8]}-{int(time.time())}"
    
    # Create billing record
    payment_id = str(uuid.uuid4())
    try:
        db.session.execute(text("""
            INSERT INTO billing_history (id, organization_id, transaction_type, amount, currency, status, korapay_reference, description)
            VALUES (:id, :org_id, 'subscription', :amount, 'NGN', 'pending', :ref, :desc)
        """), {'id': payment_id, 'org_id': org_id, 'amount': amount_ngn, 'ref': reference, 'desc': f"Subscription: {plan_name} ({billing_cycle})"})
        db.session.commit()
    except Exception as e:
        logger.error(f"Error creating payment: {e}")
        db.session.rollback()
    
    # Get Payonus token and create payment link
    token = get_payonus_token()
    if not token:
        return jsonify({'success': False, 'error': 'Payment service unavailable'})
    
    try:
        resp = requests.post(
            f'{PAYONUS_BASE_URL}/api/v1/payment-links',
            json={
                'name': f'SendBaba {plan_name} {reference}',
                'description': f'{plan_name} Plan - {billing_cycle.title()} Subscription',
                'businessId': PAYONUS_BUSINESS_ID,
                'amount': amount_ngn,
                'currency': 'NGN',
                'isOneOff': True,
                'customisedUrlSuffix': reference,
                'notificationUrl': request.url_root.rstrip('/') + '/dashboard/billing/webhook/payonus',
                'metadata': json.dumps({'org_id': org_id, 'plan_slug': plan_slug, 'billing_cycle': billing_cycle, 'payment_id': payment_id})
            },
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            timeout=30
        )
        
        result = resp.json()
        logger.info(f"Payonus response: {result}")
        
        if result.get('status') == 200:
            checkout_url = result['data']['url']
            return jsonify({'success': True, 'checkout_url': checkout_url, 'reference': reference})
        
        return jsonify({'success': False, 'error': result.get('message', 'Payment initialization failed')})
    except Exception as e:
        logger.error(f"Payonus error: {e}")
        return jsonify({'success': False, 'error': 'Payment service unavailable'})


@billing_bp.route('/payment-callback')
@login_required  
def payment_callback():
    reference = request.args.get('reference')
    status = request.args.get('status', '')
    
    if status == 'success' or status == 'successful':
        return redirect('/dashboard/billing?success=true')
    return redirect('/dashboard/billing?error=payment_failed')


@billing_bp.route('/webhook/payonus', methods=['POST'])
def payonus_webhook():
    """Handle Payonus webhook"""
    try:
        data = request.get_json()
        logger.info(f"Payonus webhook: {data}")
        
        event_type = data.get('event') or data.get('type', '')
        payment_data = data.get('data', {})
        reference = payment_data.get('reference') or payment_data.get('customisedUrlSuffix', '')
        status = payment_data.get('status', '').lower()
        
        if status in ['success', 'successful', 'completed'] or 'success' in event_type.lower():
            # Update billing history
            db.session.execute(text("""
                UPDATE billing_history SET status = 'completed', paid_at = :now
                WHERE korapay_reference = :ref AND status = 'pending'
            """), {'now': datetime.utcnow(), 'ref': reference})
            
            # Get metadata and update subscription
            metadata_str = payment_data.get('metadata', '{}')
            try:
                metadata = json.loads(metadata_str) if isinstance(metadata_str, str) else metadata_str
            except:
                metadata = {}
            
            org_id = metadata.get('org_id')
            plan_slug = metadata.get('plan_slug')
            billing_cycle = metadata.get('billing_cycle', 'monthly')
            
            if org_id and plan_slug:
                plan_result = db.session.execute(text("""
                    SELECT id, name, email_limit_daily, email_limit_monthly, contact_limit, team_member_limit
                    FROM pricing_plans WHERE slug = :slug
                """), {'slug': plan_slug})
                plan = plan_result.fetchone()
                
                if plan:
                    now = datetime.utcnow()
                    period_end = now + timedelta(days=365 if billing_cycle == 'annual' else 30)
                    
                    db.session.execute(text("""
                        UPDATE subscriptions SET plan_id = :plan_id, plan_type = :plan_slug, plan_name = :plan_name, 
                            status = 'active', billing_cycle = :cycle, email_limit_daily = :daily,
                            email_limit_monthly = :monthly, contact_limit = :contacts, team_member_limit = :team,
                            is_trial = false, current_period_start = :now, current_period_end = :period_end,
                            next_billing_at = :period_end, last_payment_at = :now, updated_at = :now
                        WHERE organization_id = :org_id
                    """), {'org_id': org_id, 'plan_id': plan[0], 'plan_slug': plan_slug, 'plan_name': plan[1],
                           'cycle': billing_cycle, 'daily': plan[2], 'monthly': plan[3], 'contacts': plan[4], 
                           'team': plan[5], 'now': now, 'period_end': period_end})
            
            db.session.commit()
        
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        db.session.rollback()
        return jsonify({'status': 'error'}), 500


@billing_bp.route('/webhook/korapay', methods=['POST'])
def korapay_webhook():
    return payonus_webhook()


@billing_bp.route('/api/cancel', methods=['POST'])
@login_required
def api_cancel_subscription():
    org_id = get_organization_id()
    db.session.execute(text("UPDATE subscriptions SET status = 'canceled', canceled_at = :now, updated_at = :now WHERE organization_id = :org_id"), 
                       {'org_id': org_id, 'now': datetime.utcnow()})
    db.session.commit()
    return jsonify({'success': True, 'message': 'Subscription canceled.'})
