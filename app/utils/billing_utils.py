"""
Billing utility functions for use across the application
"""
from functools import wraps
from flask import redirect, jsonify, request
from flask_login import current_user


def require_active_subscription(redirect_on_fail=True):
    """
    Decorator to require active subscription for a route.
    Use on campaign creation, sending, etc.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from app.controllers.billing_controller import get_organization_id, get_subscription_status, create_trial_subscription
            
            org_id = get_organization_id()
            if not org_id:
                if redirect_on_fail:
                    return redirect('/login')
                return jsonify({'success': False, 'error': 'Not authenticated'}), 401
            
            sub_status = get_subscription_status(org_id)
            
            if not sub_status:
                create_trial_subscription(org_id)
                return f(*args, **kwargs)
            
            if sub_status['is_active']:
                return f(*args, **kwargs)
            
            # Subscription not active
            if redirect_on_fail:
                return redirect('/billing?expired=true')
            
            return jsonify({
                'success': False,
                'error': 'subscription_expired',
                'message': sub_status.get('reason', 'Your subscription has expired'),
                'upgrade_url': '/billing/plans'
            }), 403
        
        return decorated_function
    return decorator


def check_can_send_campaign(org_id, email_count):
    """
    Check if organization can send a campaign with given email count.
    Returns (can_send, error_message)
    """
    from app.controllers.billing_controller import get_subscription_status, check_email_limit
    
    sub_status = get_subscription_status(org_id)
    
    if not sub_status:
        return False, "No active subscription found"
    
    if not sub_status['is_active']:
        return False, sub_status.get('reason', 'Subscription expired')
    
    can_send, message = check_email_limit(org_id, email_count)
    return can_send, message
