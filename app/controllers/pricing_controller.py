"""
Team Pricing Controller
"""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models.team import TeamMember
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

pricing_bp = Blueprint('pricing', __name__, url_prefix='/pricing')


@pricing_bp.route('/teams')
@login_required
def teams():
    """Team pricing page"""
    try:
        # Get available plans
        result = db.session.execute(text("""
            SELECT plan_name, min_members, max_members, daily_limit, 
                   monthly_price, annual_price, features
            FROM team_plans
            ORDER BY monthly_price ASC
        """))
        
        plans = []
        for row in result:
            plans.append({
                'name': row[0],
                'min_members': row[1],
                'max_members': row[2],
                'daily_limit': row[3],
                'monthly_price': float(row[4]),
                'annual_price': float(row[5]),
                'features': row[6]
            })
        
        # Get current organization plan
        current_plan = db.session.execute(text("""
            SELECT team_plan, team_member_count, team_daily_limit, team_plan_price
            FROM organizations
            WHERE id = :org_id
        """), {'org_id': current_user.organization_id}).fetchone()
        
        current_plan_data = None
        if current_plan:
            current_plan_data = {
                'plan': current_plan[0],
                'members': current_plan[1],
                'daily_limit': current_plan[2],
                'price': float(current_plan[3]) if current_plan[3] else 0
            }
        
        return render_template('pricing/teams.html', 
                             plans=plans, 
                             current_plan=current_plan_data)
        
    except Exception as e:
        logger.error(f"Pricing page error: {e}", exc_info=True)
        return render_template('pricing/teams.html', plans=[], current_plan=None)


@pricing_bp.route('/api/calculate', methods=['POST'])
@login_required
def calculate_price():
    """Calculate price based on team size"""
    try:
        data = request.get_json()
        team_size = data.get('team_size', 1)
        billing_cycle = data.get('billing_cycle', 'monthly')
        
        # Find appropriate plan
        result = db.session.execute(text("""
            SELECT plan_name, min_members, max_members, daily_limit, 
                   monthly_price, annual_price, features
            FROM team_plans
            WHERE min_members <= :team_size 
            AND (max_members >= :team_size OR max_members IS NULL)
            ORDER BY monthly_price ASC
            LIMIT 1
        """), {'team_size': team_size})
        
        plan = result.fetchone()
        
        if not plan:
            return jsonify({'success': False, 'error': 'No plan found'}), 400
        
        price = float(plan[5] if billing_cycle == 'annual' else plan[4])
        savings = 0
        
        if billing_cycle == 'annual':
            monthly_total = float(plan[4]) * 12
            annual_price = float(plan[5])
            savings = monthly_total - annual_price
        
        return jsonify({
            'success': True,
            'plan_name': plan[0],
            'team_size': team_size,
            'daily_limit': plan[3],
            'price': price,
            'billing_cycle': billing_cycle,
            'savings': savings,
            'price_per_member': round(price / team_size, 2),
            'features': plan[6]
        })
        
    except Exception as e:
        logger.error(f"Calculate price error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@pricing_bp.route('/api/upgrade', methods=['POST'])
@login_required
def upgrade_plan():
    """Upgrade organization to team plan"""
    try:
        data = request.get_json()
        plan_name = data.get('plan_name')
        team_size = data.get('team_size')
        billing_cycle = data.get('billing_cycle', 'monthly')
        
        # Get plan details
        result = db.session.execute(text("""
            SELECT daily_limit, monthly_price, annual_price
            FROM team_plans
            WHERE plan_name = :plan_name
        """), {'plan_name': plan_name})
        
        plan = result.fetchone()
        
        if not plan:
            return jsonify({'success': False, 'error': 'Invalid plan'}), 400
        
        price = float(plan[2] if billing_cycle == 'annual' else plan[1])
        
        # Update organization
        db.session.execute(text("""
            UPDATE organizations
            SET team_plan = :plan_name,
                team_daily_limit = :daily_limit,
                team_member_count = :team_size,
                team_plan_price = :price
            WHERE id = :org_id
        """), {
            'plan_name': plan_name,
            'daily_limit': plan[0],
            'team_size': team_size,
            'price': price,
            'org_id': current_user.organization_id
        })
        
        db.session.commit()
        
        logger.info(f"Organization {current_user.organization_id} upgraded to {plan_name}")
        
        return jsonify({
            'success': True,
            'message': f'Successfully upgraded to {plan_name.title()} plan!',
            'redirect': '/dashboard/'
        })
        
    except Exception as e:
        logger.error(f"Upgrade plan error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
