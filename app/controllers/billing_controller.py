"""
SendBaba Billing Controller - Complete with Plans
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

logger = logging.getLogger(__name__)

billing_bp = Blueprint('billing', __name__, url_prefix='/dashboard/billing')

KORAPAY_PUBLIC_KEY = os.environ.get('KORAPAY_PUBLIC_KEY', 'pk_test_xxxxxxxxxxxxxxxxxxxxxxxx')
KORAPAY_SECRET_KEY = os.environ.get('KORAPAY_SECRET_KEY', 'sk_test_xxxxxxxxxxxxxxxxxxxxxxxx')
KORAPAY_BASE_URL = "https://api.korapay.com/merchant/api/v1"


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


def get_subscription(org_id):
    """Get subscription for organization, create trial if none exists"""
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
        
        # No subscription - create trial
        sub_id = str(uuid.uuid4())
        now = datetime.utcnow()
        trial_end = now + timedelta(days=14)
        
        db.session.execute(text("""
            INSERT INTO subscriptions (
                id, organization_id, plan_type, plan_name, status, 
                email_limit_daily, email_limit_monthly, contact_limit, team_member_limit,
                is_trial, trial_started_at, trial_ends_at, started_at,
                current_period_start, current_period_end, created_at
            ) VALUES (
                :id, :org_id, 'free', 'Free Trial', 'trial',
                100, 1000, 500, 1, true, :now, :trial_end, :now, :now, :trial_end, :now
            )
        """), {'id': sub_id, 'org_id': org_id, 'now': now, 'trial_end': trial_end})
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
        return {
            'id': None, 'plan_type': 'free', 'plan_name': 'Free', 'status': 'trial',
            'billing_cycle': 'monthly', 'current_price': 0, 'email_limit_daily': 100,
            'email_limit_monthly': 1000, 'contact_limit': 500, 'team_member_limit': 1,
            'is_trial': True, 'trial_ends_at': datetime.utcnow() + timedelta(days=14),
            'current_period_start': datetime.utcnow(), 'current_period_end': datetime.utcnow() + timedelta(days=14),
            'next_billing_at': None
        }


def ensure_pricing_plans():
    """Ensure pricing plans exist in database"""
    try:
        count = db.session.execute(text("SELECT COUNT(*) FROM pricing_plans")).scalar()
        if count == 0:
            logger.info("No pricing plans found, creating default plans...")
            plans = [
                ('Free', 'free', 'individual', 100, 1000, 500, 1, 0, 0, '["100 emails/day", "500 contacts", "Basic templates", "Email support"]', False, 1),
                ('Starter', 'starter', 'individual', 1000, 25000, 5000, 3, 29, 278.40, '["1,000 emails/day", "5,000 contacts", "All templates", "Priority support", "Basic analytics", "Custom branding"]', False, 2),
                ('Business', 'business', 'individual', 5000, 100000, 25000, 10, 79, 758.40, '["5,000 emails/day", "25,000 contacts", "Advanced analytics", "API access", "A/B testing", "24/7 priority support"]', True, 3),
                ('Enterprise', 'enterprise', 'individual', 50000, 1000000, 100000, 50, 249, 2390.40, '["50,000 emails/day", "100,000 contacts", "Dedicated IP", "Custom integrations", "SLA guarantee", "Dedicated account manager"]', False, 4),
                ('Team Starter', 'team-starter', 'team', 2000, 50000, 15000, 5, 99, 950.40, '["2,000 emails/day", "15,000 contacts", "5 team members", "Team analytics", "Shared templates", "Role permissions"]', False, 1),
                ('Team Pro', 'team-pro', 'team', 10000, 250000, 75000, 15, 199, 1910.40, '["10,000 emails/day", "75,000 contacts", "15 team members", "Advanced permissions", "Audit logs", "SSO integration"]', True, 2),
                ('Team Enterprise', 'team-enterprise', 'team', 50000, 1000000, 500000, 50, 499, 4790.40, '["50,000 emails/day", "500,000 contacts", "50 team members", "Enterprise SSO", "Custom contracts", "Dedicated support"]', False, 3),
            ]
            
            for name, slug, ptype, daily, monthly, contacts, team, price_m, price_a, features, popular, sort in plans:
                db.session.execute(text("""
                    INSERT INTO pricing_plans (id, name, slug, type, email_limit_daily, email_limit_monthly, 
                        contact_limit, team_member_limit, price_monthly, price_annual, features, is_popular, is_active, sort_order)
                    VALUES (:id, :name, :slug, :type, :daily, :monthly, :contacts, :team, :price_m, :price_a, :features, :popular, true, :sort)
                """), {
                    'id': str(uuid.uuid4()), 'name': name, 'slug': slug, 'type': ptype, 'daily': daily,
                    'monthly': monthly, 'contacts': contacts, 'team': team, 'price_m': price_m,
                    'price_a': price_a, 'features': features, 'popular': popular, 'sort': sort
                })
            db.session.commit()
            logger.info("Created default pricing plans")
    except Exception as e:
        logger.error(f"Error ensuring pricing plans: {e}")
        db.session.rollback()


@billing_bp.route('/')
@billing_bp.route('')
@login_required
def billing_dashboard():
    """Main billing dashboard"""
    org_id = get_organization_id()
    subscription = get_subscription(org_id)
    
    # Get usage
    now = datetime.utcnow()
    today = now.date()
    month_start = now.replace(day=1).date()
    
    try:
        daily_emails = db.session.execute(text("""
            SELECT COALESCE(SUM(emails_sent), 0) FROM usage_tracking 
            WHERE organization_id = :org_id AND period_date = :today
        """), {'org_id': org_id, 'today': today}).scalar() or 0
        
        monthly_emails = db.session.execute(text("""
            SELECT COALESCE(SUM(emails_sent), 0) FROM usage_tracking 
            WHERE organization_id = :org_id AND period_date >= :month_start
        """), {'org_id': org_id, 'month_start': month_start}).scalar() or 0
        
        total_contacts = db.session.execute(text("""
            SELECT COUNT(*) FROM contacts WHERE organization_id = :org_id
        """), {'org_id': org_id}).scalar() or 0
    except:
        daily_emails = monthly_emails = total_contacts = 0
    
    usage = {
        'daily_emails': daily_emails, 'monthly_emails': monthly_emails, 'total_contacts': total_contacts,
        'daily_limit': subscription['email_limit_daily'], 'monthly_limit': subscription['email_limit_monthly'],
        'contact_limit': subscription['contact_limit']
    }
    
    # Get invoices
    try:
        invoices_result = db.session.execute(text("""
            SELECT invoice_number, total, currency, status, invoice_date, pdf_url
            FROM invoices WHERE organization_id = :org_id ORDER BY created_at DESC LIMIT 5
        """), {'org_id': org_id})
        invoices = [{'invoice_number': r[0], 'total': float(r[1] or 0), 'currency': r[2] or 'USD',
                     'status': r[3], 'invoice_date': r[4], 'pdf_url': r[5]} for r in invoices_result]
    except:
        invoices = []
    
    return render_template('billing/dashboard.html', 
                         subscription=subscription, usage=usage, invoices=invoices,
                         expired=request.args.get('expired') == 'true',
                         success=request.args.get('success') == 'true')


@billing_bp.route('/plans')
@billing_bp.route('/plans/')
@login_required
def billing_plans():
    """View available plans"""
    org_id = get_organization_id()
    plan_type = request.args.get('type', 'individual')
    
    # Ensure plans exist
    ensure_pricing_plans()
    
    subscription = get_subscription(org_id)
    current_plan = subscription['plan_type']
    
    try:
        plans_result = db.session.execute(text("""
            SELECT id, name, slug, type, email_limit_daily, email_limit_monthly, 
                   contact_limit, team_member_limit, price_monthly, price_annual, features, is_popular
            FROM pricing_plans 
            WHERE is_active = true AND type = :type 
            ORDER BY sort_order
        """), {'type': plan_type})
        
        plans = []
        for r in plans_result:
            features = r[10]
            if isinstance(features, str):
                try:
                    features = json.loads(features)
                except:
                    features = []
            elif features is None:
                features = []
            
            plans.append({
                'id': r[0], 'name': r[1], 'slug': r[2], 'type': r[3], 
                'email_limit_daily': r[4] or 100,
                'email_limit_monthly': r[5] or 1000, 
                'contact_limit': r[6] or 500, 
                'team_member_limit': r[7] or 1,
                'price_monthly': float(r[8] or 0), 
                'price_annual': float(r[9] or 0),
                'features': features, 
                'is_popular': r[11],
                'is_current': r[2] == current_plan
            })
        
        logger.info(f"Loaded {len(plans)} plans for type {plan_type}")
        
    except Exception as e:
        logger.error(f"Error loading plans: {e}")
        plans = []
    
    return render_template('billing/plans.html', plans=plans, current_plan=current_plan, plan_type=plan_type)


@billing_bp.route('/checkout/<plan_slug>')
@login_required
def billing_checkout(plan_slug):
    """Checkout page"""
    billing_cycle = request.args.get('cycle', 'monthly')
    
    try:
        result = db.session.execute(text("""
            SELECT id, name, slug, email_limit_daily, email_limit_monthly, 
                   contact_limit, team_member_limit, price_monthly, price_annual, features
            FROM pricing_plans WHERE slug = :slug AND is_active = true
        """), {'slug': plan_slug})
        
        row = result.fetchone()
        if not row:
            return redirect('/dashboard/billing/plans')
        
        features = row[9]
        if isinstance(features, str):
            try:
                features = json.loads(features)
            except:
                features = []
        elif features is None:
            features = []
        
        plan = {
            'id': row[0], 'name': row[1], 'slug': row[2], 
            'email_limit_daily': row[3] or 100,
            'email_limit_monthly': row[4] or 1000, 
            'contact_limit': row[5] or 500, 
            'team_member_limit': row[6] or 1,
            'price_monthly': float(row[7] or 0), 
            'price_annual': float(row[8] or 0),
            'features': features
        }
    except Exception as e:
        logger.error(f"Checkout error: {e}")
        return redirect('/dashboard/billing/plans')
    
    price = plan['price_annual'] if billing_cycle == 'annual' else plan['price_monthly']
    return render_template('billing/checkout.html', plan=plan, billing_cycle=billing_cycle, price=price)


@billing_bp.route('/invoices')
@login_required
def billing_invoices():
    """View all invoices"""
    org_id = get_organization_id()
    
    try:
        result = db.session.execute(text("""
            SELECT id, invoice_number, total, currency, status, invoice_date, due_date, paid_at, pdf_url
            FROM invoices WHERE organization_id = :org_id ORDER BY created_at DESC
        """), {'org_id': org_id})
        invoices = [{'id': r[0], 'invoice_number': r[1], 'total': float(r[2] or 0), 'currency': r[3] or 'USD',
                     'status': r[4], 'invoice_date': r[5], 'due_date': r[6], 'paid_at': r[7], 'pdf_url': r[8]} for r in result]
    except:
        invoices = []
    
    return render_template('billing/invoices.html', invoices=invoices)


@billing_bp.route('/api/subscription')
@login_required
def api_subscription():
    org_id = get_organization_id()
    subscription = get_subscription(org_id)
    return jsonify({'success': True, 'subscription': subscription})


@billing_bp.route('/api/initialize-payment', methods=['POST'])
@login_required
def api_initialize_payment():
    org_id = get_organization_id()
    data = request.get_json()
    
    plan_slug = data.get('plan')
    billing_cycle = data.get('billing_cycle', 'monthly')
    
    try:
        result = db.session.execute(text("""
            SELECT id, name, price_monthly, price_annual FROM pricing_plans WHERE slug = :slug
        """), {'slug': plan_slug})
        plan = result.fetchone()
        if not plan:
            return jsonify({'success': False, 'error': 'Plan not found'})
    except:
        return jsonify({'success': False, 'error': 'Plan not found'})
    
    price = float(plan[3]) if billing_cycle == 'annual' else float(plan[2])
    if price <= 0:
        return jsonify({'success': False, 'error': 'Cannot checkout free plan'})
    
    amount_smallest = int(price * 100)
    reference = f"SB-{org_id[:8]}-{int(datetime.utcnow().timestamp())}"
    
    payment_id = str(uuid.uuid4())
    try:
        db.session.execute(text("""
            INSERT INTO billing_history (id, organization_id, transaction_type, amount, currency, status, korapay_reference, description)
            VALUES (:id, :org_id, 'subscription', :amount, 'USD', 'pending', :ref, :desc)
        """), {'id': payment_id, 'org_id': org_id, 'amount': price, 'ref': reference, 'desc': f"Subscription: {plan[1]} ({billing_cycle})"})
        db.session.commit()
    except Exception as e:
        logger.error(f"Error creating payment: {e}")
        db.session.rollback()
    
    callback_url = request.url_root.rstrip('/') + f"/dashboard/billing/payment-callback?reference={reference}"
    webhook_url = request.url_root.rstrip('/') + "/dashboard/billing/webhook/korapay"
    
    payload = {
        "reference": reference, "amount": amount_smallest, "currency": "USD",
        "customer": {"email": get_user_email(), "name": get_user_name()},
        "notification_url": webhook_url, "redirect_url": callback_url,
        "metadata": {"organization_id": org_id, "plan_slug": plan_slug, "billing_cycle": billing_cycle, "payment_id": payment_id}
    }
    
    try:
        response = requests.post(f"{KORAPAY_BASE_URL}/charges/initialize", json=payload,
            headers={"Authorization": f"Bearer {KORAPAY_SECRET_KEY}", "Content-Type": "application/json"}, timeout=30)
        result = response.json()
        
        if result.get('status'):
            return jsonify({'success': True, 'checkout_url': result['data']['checkout_url'], 'reference': reference})
        return jsonify({'success': False, 'error': result.get('message', 'Payment initialization failed')})
    except Exception as e:
        logger.error(f"Korapay error: {e}")
        return jsonify({'success': False, 'error': 'Payment service unavailable'})


@billing_bp.route('/payment-callback')
@login_required
def payment_callback():
    reference = request.args.get('reference')
    if not reference:
        return redirect('/dashboard/billing?error=invalid_reference')
    
    try:
        response = requests.get(f"{KORAPAY_BASE_URL}/charges/{reference}",
            headers={"Authorization": f"Bearer {KORAPAY_SECRET_KEY}"}, timeout=30)
        result = response.json()
        
        if result.get('status') and result.get('data', {}).get('status') == 'success':
            metadata = result['data'].get('metadata', {})
            org_id = metadata.get('organization_id') or get_organization_id()
            plan_slug = metadata.get('plan_slug')
            billing_cycle = metadata.get('billing_cycle', 'monthly')
            payment_id = metadata.get('payment_id')
            
            db.session.execute(text("""
                UPDATE billing_history SET status = 'completed', paid_at = :now, korapay_transaction_id = :tx_id
                WHERE korapay_reference = :ref
            """), {'now': datetime.utcnow(), 'tx_id': result['data'].get('transaction_id', ''), 'ref': reference})
            
            plan_result = db.session.execute(text("""
                SELECT name, email_limit_daily, email_limit_monthly, contact_limit, team_member_limit, price_monthly, price_annual
                FROM pricing_plans WHERE slug = :slug
            """), {'slug': plan_slug})
            
            plan = plan_result.fetchone()
            if plan:
                now = datetime.utcnow()
                period_end = now + timedelta(days=365 if billing_cycle == 'annual' else 30)
                price = float(plan[6]) if billing_cycle == 'annual' else float(plan[5])
                
                db.session.execute(text("""
                    UPDATE subscriptions SET plan_type = :plan_slug, plan_name = :plan_name, status = 'active',
                        billing_cycle = :cycle, current_price = :price, email_limit_daily = :daily,
                        email_limit_monthly = :monthly, contact_limit = :contacts, team_member_limit = :team,
                        is_trial = false, current_period_start = :now, current_period_end = :period_end,
                        next_billing_at = :period_end, last_payment_at = :now, updated_at = :now
                    WHERE organization_id = :org_id
                """), {'org_id': org_id, 'plan_slug': plan_slug, 'plan_name': plan[0], 'cycle': billing_cycle,
                       'price': price, 'daily': plan[1], 'monthly': plan[2], 'contacts': plan[3], 'team': plan[4],
                       'now': now, 'period_end': period_end})
                
                # Create invoice
                invoice_id = str(uuid.uuid4())
                invoice_number = f"INV-{now.strftime('%Y%m')}-{invoice_id[:8].upper()}"
                line_items = json.dumps([{'description': f"{plan[0]} Plan ({billing_cycle})", 'quantity': 1, 'unit_price': price, 'total': price}])
                
                db.session.execute(text("""
                    INSERT INTO invoices (id, organization_id, billing_history_id, invoice_number, status, subtotal, total, currency, line_items, invoice_date, paid_at)
                    VALUES (:id, :org_id, :payment_id, :inv_num, 'paid', :amount, :amount, 'USD', :items, :date, :date)
                """), {'id': invoice_id, 'org_id': org_id, 'payment_id': payment_id, 'inv_num': invoice_number, 'amount': price, 'items': line_items, 'date': now})
            
            db.session.commit()
            return redirect('/dashboard/billing?success=true')
        
        return redirect('/dashboard/billing?error=payment_failed')
    except Exception as e:
        logger.error(f"Payment callback error: {e}")
        return redirect('/dashboard/billing?error=verification_failed')


@billing_bp.route('/webhook/korapay', methods=['POST'])
def korapay_webhook():
    data = request.get_json()
    event = data.get('event')
    
    if event == 'charge.success':
        reference = data.get('data', {}).get('reference')
        if reference:
            db.session.execute(text("""
                UPDATE billing_history SET status = 'completed', paid_at = :now
                WHERE korapay_reference = :ref AND status = 'pending'
            """), {'now': datetime.utcnow(), 'ref': reference})
            db.session.commit()
    
    return jsonify({'status': 'ok'})


@billing_bp.route('/api/cancel', methods=['POST'])
@login_required
def api_cancel_subscription():
    org_id = get_organization_id()
    db.session.execute(text("""
        UPDATE subscriptions SET status = 'canceled', canceled_at = :now, updated_at = :now
        WHERE organization_id = :org_id
    """), {'org_id': org_id, 'now': datetime.utcnow()})
    db.session.commit()
    return jsonify({'success': True, 'message': 'Subscription canceled.'})
