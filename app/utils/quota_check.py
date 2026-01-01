"""
SendBaba Quota Check Utility
Checks user quota and flashes warnings
"""
from flask import flash
from flask_login import current_user
from app import db
from sqlalchemy import text
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def check_quota_and_flash(org_id):
    """Check quota and flash warning messages if needed"""
    try:
        now = datetime.utcnow()
        today = now.date()
        month_start = now.replace(day=1).date()
        
        # Get subscription limits from plan_tiers
        result = db.session.execute(text("""
            SELECT 
                COALESCE(p.daily_limit, 500) as daily_limit,
                COALESCE(p.monthly_limit, 5000) as monthly_limit
            FROM organizations o
            LEFT JOIN plan_tiers p ON p.name = COALESCE(o.plan_type, o.plan, 'free')
            WHERE o.id = :org_id
        """), {'org_id': org_id})
        limits = result.fetchone()
        
        if not limits:
            return
        
        daily_limit = limits[0]
        monthly_limit = limits[1]
        
        # Get current usage
        daily_sent = db.session.execute(text(
            "SELECT COUNT(*) FROM emails WHERE organization_id = :org_id AND DATE(created_at) = :today"
        ), {'org_id': org_id, 'today': today}).scalar() or 0
        
        monthly_sent = db.session.execute(text(
            "SELECT COUNT(*) FROM emails WHERE organization_id = :org_id AND created_at >= :month_start"
        ), {'org_id': org_id, 'month_start': month_start}).scalar() or 0
        
        # Calculate percentages
        daily_pct = (daily_sent / daily_limit * 100) if daily_limit > 0 else 0
        monthly_pct = (monthly_sent / monthly_limit * 100) if monthly_limit > 0 else 0
        
        # Flash warnings
        if daily_pct >= 100:
            flash('⚠️ Daily email limit reached! Upgrade to continue sending.', 'error')
        elif daily_pct >= 90:
            flash(f'⚠️ You\'ve used {int(daily_pct)}% of your daily email limit.', 'warning')
        
        if monthly_pct >= 100:
            flash('⚠️ Monthly email limit reached! Upgrade to continue sending.', 'error')
        elif monthly_pct >= 90:
            flash(f'⚠️ You\'ve used {int(monthly_pct)}% of your monthly email limit.', 'warning')
            
    except Exception as e:
        logger.error(f"Quota check error: {e}")
