"""
SendBaba Billing Controller - Fully Dynamic
Uses pricing_plans table for all plan data
"""
from flask import Blueprint, render_template, request, jsonify, session, redirect, flash
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

_payonus_token_cache = {'token': None, 'expires_at': 0}


def get_payonus_token():
    global _payonus_token_cache
    if _payonus_token_cache['token'] and time.time() < _payonus_token_cache['expires_at']:
        return _payonus_token_cache['token']
    try:
        resp = requests.post(
            f'{PAYONUS_BASE_URL}/api/v1/access-token',
            json={'apiClientId': PAYONUS_CLIENT_ID, 'apiClientSecret': PAYONUS_CLIENT_SECRET},
            headers={'Content-Type': 'application/json'}, timeout=30
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
    return getattr(current_user, 'email', '') if current_user.is_authenticated else ''


def get_plan_by_slug(slug):
    """Get plan details from pricing_plans table - SINGLE SOURCE OF TRUTH"""
    try:
        result = db.session.execute(text("""
            SELECT id, name, slug, type, price_monthly, price_annual, 
                   email_limit_daily, email_limit_monthly, contact_limit, 
                   team_member_limit, features, is_popular
            FROM pricing_plans 
            WHERE slug = :slug AND is_active = true
        """), {'slug': slug})
        row = result.fetchone()
        if row:
            return {
                'id': row[0], 'name': row[1], 'slug': row[2], 'type': row[3],
                'price_monthly': float(row[4] or 0), 'price_annual': float(row[5] or 0),
                'email_limit_daily': row[6] or 100, 'email_limit_monthly': row[7] or 1000,
                'contact_limit': row[8] or 500, 'team_member_limit': row[9] or 1,
                'features': parse_features(row[10]), 'is_popular': row[11]
            }
    except Exception as e:
        logger.error(f"Error getting plan: {e}")
    return None


def get_free_plan():
    """Get free plan from pricing_plans - creates if not exists"""
    plan = get_plan_by_slug('free')
    if plan:
        return plan
    
    # Create free plan if not exists
    try:
        plan_id = str(uuid.uuid4())
        db.session.execute(text("""
            INSERT INTO pricing_plans (id, name, slug, type, email_limit_daily, email_limit_monthly, 
                contact_limit, team_member_limit, price_monthly, price_annual, features, is_popular, is_active, sort_order)
            VALUES (:id, 'Free', 'free', 'individual', 100, 1000, 500, 1, 0, 0, 
                '["100 emails/day", "500 contacts", "Basic templates"]', false, true, 0)
        """), {'id': plan_id})
        db.session.commit()
        return get_plan_by_slug('free')
    except Exception as e:
        logger.error(f"Error creating free plan: {e}")
        db.session.rollback()
    
    # Return default free plan
    return {
        'id': None, 'name': 'Free', 'slug': 'free', 'type': 'individual',
        'price_monthly': 0, 'price_annual': 0, 'email_limit_daily': 100,
        'email_limit_monthly': 1000, 'contact_limit': 500, 'team_member_limit': 1,
        'features': ['100 emails/day', '500 contacts'], 'is_popular': False
    }


def get_subscription(org_id):
    """Get subscription for organization - FULLY DYNAMIC from pricing_plans"""
    try:
        # First try subscriptions table
        result = db.session.execute(text("""
            SELECT s.id, s.plan_type, s.plan_name, s.status, s.billing_cycle, s.current_price,
                   s.email_limit_daily, s.email_limit_monthly, s.contact_limit, s.team_member_limit,
                   s.is_trial, s.trial_ends_at, s.current_period_start, s.current_period_end, s.next_billing_at
            FROM subscriptions s WHERE s.organization_id = :org_id ORDER BY s.created_at DESC LIMIT 1
        """), {'org_id': org_id})
        row = result.fetchone()
        
        if row:
            return {
                'id': row[0], 'plan_type': row[1] or 'free', 'plan_name': row[2] or 'Free',
                'status': row[3] or 'active', 'billing_cycle': row[4] or 'monthly',
                'current_price': float(row[5] or 0), 'email_limit_daily': row[6] or 100,
                'email_limit_monthly': row[7] or 1000, 'contact_limit': row[8] or 500,
                'team_member_limit': row[9] or 1, 'is_trial': row[10] if row[10] is not None else False,
                'trial_ends_at': row[11], 'current_period_start': row[12],
                'current_period_end': row[13], 'next_billing_at': row[14]
            }
        
        # Fallback: Check organization's plan and get limits from pricing_plans
        result = db.session.execute(text("""
            SELECT o.id, COALESCE(o.plan_type, o.plan, 'free') as plan_slug
            FROM organizations o WHERE o.id = :org_id
        """), {'org_id': org_id})
        org_row = result.fetchone()
        
        if org_row:
            plan_slug = org_row[1] or 'free'
            plan = get_plan_by_slug(plan_slug) or get_free_plan()
            
            return {
                'id': None, 'plan_type': plan['slug'], 'plan_name': plan['name'],
                'status': 'active', 'billing_cycle': 'monthly',
                'current_price': plan['price_monthly'], 
                'email_limit_daily': plan['email_limit_daily'],
                'email_limit_monthly': plan['email_limit_monthly'], 
                'contact_limit': plan['contact_limit'],
                'team_member_limit': plan['team_member_limit'], 
                'is_trial': False, 'trial_ends_at': None,
                'current_period_start': None, 'current_period_end': None, 'next_billing_at': None
            }
        
        # No org found - return free defaults
        free_plan = get_free_plan()
        return {
            'id': None, 'plan_type': 'free', 'plan_name': 'Free', 'status': 'active',
            'billing_cycle': 'monthly', 'current_price': 0,
            'email_limit_daily': free_plan['email_limit_daily'],
            'email_limit_monthly': free_plan['email_limit_monthly'],
            'contact_limit': free_plan['contact_limit'],
            'team_member_limit': free_plan['team_member_limit'],
            'is_trial': False, 'trial_ends_at': None,
            'current_period_start': None, 'current_period_end': None, 'next_billing_at': None
        }
        
    except Exception as e:
        logger.error(f"Error getting subscription: {e}")
        db.session.rollback()
        free_plan = get_free_plan()
        return {
            'id': None, 'plan_type': 'free', 'plan_name': 'Free', 'status': 'active',
            'billing_cycle': 'monthly', 'current_price': 0,
            'email_limit_daily': free_plan['email_limit_daily'],
            'email_limit_monthly': free_plan['email_limit_monthly'],
            'contact_limit': free_plan['contact_limit'],
            'team_member_limit': free_plan['team_member_limit'],
            'is_trial': False, 'trial_ends_at': None,
            'current_period_start': None, 'current_period_end': None, 'next_billing_at': None
        }


def get_usage_with_quota_check(org_id, subscription):
    """Get usage and check if quota exceeded"""
    now = datetime.utcnow()
    today = now.date()
    month_start = now.replace(day=1).date()
    
    daily_limit = subscription.get('email_limit_daily', 100)
    monthly_limit = subscription.get('email_limit_monthly', 1000)
    contact_limit = subscription.get('contact_limit', 500)
    
    try:
        daily_emails = db.session.execute(text(
            "SELECT COUNT(*) FROM emails WHERE organization_id = :org_id AND DATE(created_at) = :today"
        ), {'org_id': org_id, 'today': today}).scalar() or 0
        
        monthly_emails = db.session.execute(text(
            "SELECT COUNT(*) FROM emails WHERE organization_id = :org_id AND created_at >= :month_start"
        ), {'org_id': org_id, 'month_start': month_start}).scalar() or 0
        
        contact_count = db.session.execute(text(
            "SELECT COUNT(*) FROM contacts WHERE organization_id = :org_id"
        ), {'org_id': org_id}).scalar() or 0
    except:
        daily_emails, monthly_emails, contact_count = 0, 0, 0
    
    daily_pct = (daily_emails / daily_limit * 100) if daily_limit > 0 else 0
    monthly_pct = (monthly_emails / monthly_limit * 100) if monthly_limit > 0 else 0
    
    return {
        'daily_emails': daily_emails,
        'monthly_emails': monthly_emails,
        'total_contacts': contact_count,
        'contact_count': contact_count,
        'daily_limit': daily_limit,
        'monthly_limit': monthly_limit,
        'contact_limit': contact_limit,
        'email_limit_daily': daily_limit,
        'email_limit_monthly': monthly_limit,
        'daily_pct': daily_pct,
        'monthly_pct': monthly_pct
    }


def check_and_flash_quota_warnings(usage):
    """Check usage and flash appropriate warnings"""
    daily_pct = usage.get('daily_pct', 0)
    monthly_pct = usage.get('monthly_pct', 0)
    
    if daily_pct >= 100:
        flash('⚠️ You have reached your daily email limit! Upgrade your plan to continue sending.', 'error')
    elif daily_pct >= 90:
        flash('⚠️ You have used 90% of your daily email limit. Consider upgrading your plan.', 'warning')
    
    if monthly_pct >= 100:
        flash('⚠️ You have reached your monthly email limit! Upgrade to continue sending.', 'error')
    elif monthly_pct >= 90:
        flash('⚠️ You have used 90% of your monthly email limit.', 'warning')


def parse_features(features_data):
    """Parse features from JSON or string"""
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


def get_all_plans(plan_type='individual'):
    """Get all active plans from pricing_plans - DYNAMIC"""
    try:
        result = db.session.execute(text("""
            SELECT id, name, slug, type, price_monthly, price_annual, features, 
                   email_limit_daily, email_limit_monthly, contact_limit, team_member_limit, is_popular
            FROM pricing_plans 
            WHERE is_active = true AND (type = :ptype OR :ptype = 'all')
            ORDER BY sort_order, price_monthly
        """), {'ptype': plan_type})
        
        plans = []
        for r in result:
            plans.append({
                'id': r[0], 'name': r[1], 'slug': r[2], 'type': r[3],
                'price_monthly': float(r[4] or 0), 'price_annual': float(r[5] or 0),
                'features': parse_features(r[6]), 'email_limit_daily': r[7],
                'email_limit_monthly': r[8], 'contact_limit': r[9],
                'team_member_limit': r[10], 'is_popular': r[11]
            })
        return plans
    except Exception as e:
        logger.error(f"Error getting plans: {e}")
        return []


# ============================================================
# ROUTES
# ============================================================

@billing_bp.route('/')
@billing_bp.route('')
@billing_bp.route('/dashboard')
@login_required
def billing_dashboard():
    org_id = get_organization_id()
    subscription = get_subscription(org_id)
    usage = get_usage_with_quota_check(org_id, subscription)
    
    # Flash warnings if quota exceeded
    check_and_flash_quota_warnings(usage)
    
    # Get all plans dynamically
    plans = get_all_plans('all')
    
    # Get invoices/billing history
    invoices = []
    try:
        result = db.session.execute(text("""
            SELECT id, transaction_type, amount, currency, status, created_at, description 
            FROM billing_history 
            WHERE organization_id = :org_id 
            ORDER BY created_at DESC LIMIT 10
        """), {'org_id': org_id})
        invoices = [{'id': r[0], 'type': r[1], 'amount': float(r[2] or 0), 'currency': r[3] or 'USD', 
                     'status': r[4], 'created_at': r[5], 'description': r[6]} for r in result]
    except Exception as e:
        logger.error(f"Error getting invoices: {e}")
    
    return render_template('billing/dashboard.html', 
                          subscription=subscription, 
                          usage=usage, 
                          plans=plans, 
                          invoices=invoices)


@billing_bp.route('/plans')
@login_required
def plans_page():
    org_id = get_organization_id()
    subscription = get_subscription(org_id)
    plan_type = request.args.get('type', 'individual')
    
    # Get plans dynamically from database
    plans = get_all_plans('all')
    individual_plans = [p for p in plans if p['type'] == 'individual']
    team_plans = [p for p in plans if p['type'] == 'team']
    
    current_plan = subscription.get('plan_type', 'free')
    
    return render_template('billing/plans.html', 
                          subscription=subscription, 
                          plans=plans,
                          individual_plans=individual_plans,
                          team_plans=team_plans,
                          current_plan=current_plan, 
                          plan_type=plan_type)


@billing_bp.route('/invoices')
@login_required
def invoices_page():
    org_id = get_organization_id()
    invoices = []
    try:
        result = db.session.execute(text("""
            SELECT id, invoice_number, total, currency, status, invoice_date, due_date, paid_at, pdf_url 
            FROM invoices 
            WHERE organization_id = :org_id 
            ORDER BY invoice_date DESC LIMIT 50
        """), {'org_id': org_id})
        invoices = [{'id': r[0], 'invoice_number': r[1], 'total': float(r[2] or 0), 
                     'currency': r[3] or 'USD', 'status': r[4], 'invoice_date': r[5],
                     'due_date': r[6], 'paid_at': r[7], 'pdf_url': r[8]} for r in result]
    except Exception as e:
        logger.error(f"Error getting invoices: {e}")
    
    return render_template('billing/invoices.html', invoices=invoices)


@billing_bp.route('/api/subscription')
@login_required
def api_subscription():
    return jsonify({'success': True, 'subscription': get_subscription(get_organization_id())})


@billing_bp.route('/api/usage')
@login_required
def api_usage():
    org_id = get_organization_id()
    subscription = get_subscription(org_id)
    usage = get_usage_with_quota_check(org_id, subscription)
    
    return jsonify({
        'success': True,
        'usage': usage,
        'quota_exceeded': usage['daily_pct'] >= 100 or usage['monthly_pct'] >= 100,
        'near_limit': usage['daily_pct'] >= 75 or usage['monthly_pct'] >= 75
    })


@billing_bp.route('/api/plans')
@login_required
def api_plans():
    """Get all plans - API endpoint"""
    plans = get_all_plans('all')
    return jsonify({'success': True, 'plans': plans})


@billing_bp.route('/api/initialize-payment', methods=['POST'])
@login_required
def api_initialize_payment():
    org_id = get_organization_id()
    data = request.get_json()
    
    plan_slug = data.get('plan')
    billing_cycle = data.get('billing_cycle', 'monthly')
    
    # Get plan from database dynamically
    plan = get_plan_by_slug(plan_slug)
    if not plan:
        return jsonify({'success': False, 'error': 'Plan not found'})
    
    price = plan['price_annual'] if billing_cycle == 'annual' else plan['price_monthly']
    
    if price <= 0:
        return jsonify({'success': False, 'error': 'Cannot checkout free plan'})
    
    amount_ngn = int(price * 1500)  # Convert to NGN
    reference = f"sb-{org_id[:8]}-{int(time.time())}"
    
    # Create billing record
    payment_id = str(uuid.uuid4())
    try:
        db.session.execute(text("""
            INSERT INTO billing_history (id, organization_id, transaction_type, amount, currency, status, korapay_reference, description)
            VALUES (:id, :org_id, 'subscription', :amount, 'NGN', 'pending', :ref, :desc)
        """), {'id': payment_id, 'org_id': org_id, 'amount': amount_ngn, 'ref': reference, 
               'desc': f"Subscription: {plan['name']} ({billing_cycle})"})
        db.session.commit()
    except Exception as e:
        logger.error(f"Error creating payment record: {e}")
        db.session.rollback()
    
    token = get_payonus_token()
    if not token:
        return jsonify({'success': False, 'error': 'Payment service unavailable'})
    
    try:
        resp = requests.post(
            f'{PAYONUS_BASE_URL}/api/v1/payment-links',
            json={
                'name': f'SendBaba {plan["name"]} {reference}',
                'description': f'{plan["name"]} Plan - {billing_cycle.title()} Subscription',
                'businessId': PAYONUS_BUSINESS_ID,
                'amount': amount_ngn,
                'currency': 'NGN',
                'isOneOff': True,
                'customisedUrlSuffix': reference,
                'notificationUrl': request.url_root.rstrip('/') + '/dashboard/billing/webhook/payonus',
                'metadata': json.dumps({
                    'org_id': org_id, 
                    'plan_slug': plan_slug, 
                    'billing_cycle': billing_cycle, 
                    'payment_id': payment_id
                })
            },
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            timeout=30
        )
        
        result = resp.json()
        if result.get('status') == 200:
            return jsonify({'success': True, 'checkout_url': result['data']['url'], 'reference': reference})
        return jsonify({'success': False, 'error': result.get('message', 'Payment initialization failed')})
    except Exception as e:
        logger.error(f"Payonus error: {e}")
        return jsonify({'success': False, 'error': 'Payment service unavailable'})


@billing_bp.route('/payment-callback')
@login_required  
def payment_callback():
    status = request.args.get('status', '')
    if status in ['success', 'successful']:
        return redirect('/dashboard/billing?success=true')
    return redirect('/dashboard/billing?error=payment_failed')


@billing_bp.route('/webhook/payonus', methods=['POST'])
def payonus_webhook():
    try:
        data = request.get_json()
        logger.info(f"Payonus webhook: {data}")
        
        payment_data = data.get('data', {})
        reference = payment_data.get('reference') or payment_data.get('customisedUrlSuffix', '')
        status = payment_data.get('status', '').lower()
        
        if status in ['success', 'successful', 'completed']:
            db.session.execute(text("""
                UPDATE billing_history SET status = 'completed', paid_at = :now
                WHERE korapay_reference = :ref AND status = 'pending'
            """), {'now': datetime.utcnow(), 'ref': reference})
            
            metadata_str = payment_data.get('metadata', '{}')
            try:
                metadata = json.loads(metadata_str) if isinstance(metadata_str, str) else metadata_str
            except:
                metadata = {}
            
            org_id = metadata.get('org_id')
            plan_slug = metadata.get('plan_slug')
            billing_cycle = metadata.get('billing_cycle', 'monthly')
            
            if org_id and plan_slug:
                # Get plan details dynamically
                plan = get_plan_by_slug(plan_slug)
                
                if plan:
                    now = datetime.utcnow()
                    period_end = now + timedelta(days=365 if billing_cycle == 'annual' else 30)
                    
                    # Check if subscription exists
                    existing = db.session.execute(text(
                        "SELECT id FROM subscriptions WHERE organization_id = :org_id"
                    ), {'org_id': org_id}).fetchone()
                    
                    if existing:
                        db.session.execute(text("""
                            UPDATE subscriptions SET 
                                plan_id = :plan_id, plan_type = :plan_slug, plan_name = :plan_name, 
                                status = 'active', billing_cycle = :cycle, 
                                current_price = :price,
                                email_limit_daily = :daily, email_limit_monthly = :monthly, 
                                contact_limit = :contacts, team_member_limit = :team,
                                is_trial = false, current_period_start = :now, 
                                current_period_end = :period_end,
                                next_billing_at = :period_end, last_payment_at = :now, updated_at = :now
                            WHERE organization_id = :org_id
                        """), {
                            'org_id': org_id, 'plan_id': plan['id'], 'plan_slug': plan_slug, 
                            'plan_name': plan['name'], 'cycle': billing_cycle,
                            'price': plan['price_annual'] if billing_cycle == 'annual' else plan['price_monthly'],
                            'daily': plan['email_limit_daily'], 'monthly': plan['email_limit_monthly'],
                            'contacts': plan['contact_limit'], 'team': plan['team_member_limit'],
                            'now': now, 'period_end': period_end
                        })
                    else:
                        sub_id = str(uuid.uuid4())
                        db.session.execute(text("""
                            INSERT INTO subscriptions (
                                id, organization_id, plan_id, plan_type, plan_name, status,
                                billing_cycle, current_price, email_limit_daily, email_limit_monthly,
                                contact_limit, team_member_limit, is_trial,
                                current_period_start, current_period_end, started_at, created_at
                            ) VALUES (
                                :id, :org_id, :plan_id, :plan_slug, :plan_name, 'active',
                                :cycle, :price, :daily, :monthly, :contacts, :team, false,
                                :now, :period_end, :now, :now
                            )
                        """), {
                            'id': sub_id, 'org_id': org_id, 'plan_id': plan['id'], 
                            'plan_slug': plan_slug, 'plan_name': plan['name'], 'cycle': billing_cycle,
                            'price': plan['price_annual'] if billing_cycle == 'annual' else plan['price_monthly'],
                            'daily': plan['email_limit_daily'], 'monthly': plan['email_limit_monthly'],
                            'contacts': plan['contact_limit'], 'team': plan['team_member_limit'],
                            'now': now, 'period_end': period_end
                        })
                    
                    # Update organization plan
                    db.session.execute(text("""
                        UPDATE organizations SET 
                            plan = :plan_slug, plan_type = :plan_slug,
                            daily_email_limit = :daily, monthly_email_limit = :monthly,
                            updated_at = :now
                        WHERE id = :org_id
                    """), {
                        'org_id': org_id, 'plan_slug': plan_slug,
                        'daily': plan['email_limit_daily'], 'monthly': plan['email_limit_monthly'],
                        'now': now
                    })
            
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
    try:
        db.session.execute(text("""
            UPDATE subscriptions SET status = 'canceled', canceled_at = :now, updated_at = :now 
            WHERE organization_id = :org_id
        """), {'org_id': org_id, 'now': datetime.utcnow()})
        db.session.commit()
        return jsonify({'success': True, 'message': 'Subscription canceled.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})
