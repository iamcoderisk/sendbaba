"""
SendBaba Pricing Controller - Handles redirects and team pricing
"""
from flask import Blueprint, render_template, request, jsonify, redirect
from flask_login import login_required, current_user
from app import db
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

pricing_bp = Blueprint('pricing', __name__)


# Redirect old URLs to new billing URLs
@pricing_bp.route('/pricing')
@pricing_bp.route('/pricing/')
@pricing_bp.route('/plans')
@pricing_bp.route('/plans/')
def redirect_to_billing_plans():
    """Redirect old pricing URLs to new billing plans"""
    return redirect('/dashboard/billing/plans', code=301)


@pricing_bp.route('/billing')
def redirect_to_billing():
    """Redirect /billing to /dashboard/billing"""
    return redirect('/dashboard/billing', code=301)


@pricing_bp.route('/pricing/teams')
@login_required
def teams():
    """Team pricing page - redirects to billing plans"""
    return redirect('/dashboard/billing/plans?type=team', code=301)


@pricing_bp.route('/pricing/api/calculate', methods=['POST'])
@login_required
def calculate_price():
    """Calculate price based on team size"""
    try:
        data = request.get_json()
        team_size = data.get('team_size', 1)
        billing_cycle = data.get('billing_cycle', 'monthly')
        
        # Find appropriate plan
        result = db.session.execute(text("""
            SELECT name, team_member_limit, email_limit_daily, 
                   price_monthly, price_annual, features
            FROM pricing_plans
            WHERE type = 'team' AND is_active = true
            AND team_member_limit >= :team_size
            ORDER BY price_monthly ASC
            LIMIT 1
        """), {'team_size': team_size})
        
        plan = result.fetchone()
        
        if not plan:
            return jsonify({'success': False, 'error': 'No plan found'}), 400
        
        price = float(plan[4] if billing_cycle == 'annual' else plan[3])
        savings = 0
        
        if billing_cycle == 'annual':
            monthly_total = float(plan[3]) * 12
            annual_price = float(plan[4])
            savings = monthly_total - annual_price
        
        return jsonify({
            'success': True,
            'plan_name': plan[0],
            'team_size': team_size,
            'daily_limit': plan[2],
            'price': price,
            'billing_cycle': billing_cycle,
            'savings': savings,
            'price_per_member': round(price / team_size, 2),
            'features': plan[5]
        })
        
    except Exception as e:
        logger.error(f"Calculate price error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
