"""
SendBaba Usage Service
======================
Handles email usage tracking, limit enforcement, and plan management.
"""
import os
from datetime import datetime, date
from functools import wraps
from flask import g, jsonify
import logging

logger = logging.getLogger(__name__)

class UsageService:
    def __init__(self, db=None):
        self._db = db
    
    @property
    def db(self):
        if self._db is None:
            from app import db
            self._db = db
        return self._db
    
    def get_organization_usage(self, org_id):
        """Get current usage for an organization"""
        from sqlalchemy import text
        
        result = self.db.session.execute(text("""
            SELECT 
                o.id,
                o.name,
                COALESCE(o.plan_type, o.plan, 'free') as plan,
                o.sending_enabled,
                o.sending_disabled_reason,
                o.overage_allowed,
                COALESCE(p.daily_limit, 500) as daily_limit,
                COALESCE(p.monthly_limit, 5000) as monthly_limit,
                COALESCE(p.price_per_extra_email, 0.001) as overage_rate,
                COALESCE(d.emails_sent, 0) as emails_sent_today,
                COALESCE(m.emails_sent, 0) as emails_sent_this_month,
                COALESCE(p.daily_limit, 500) - COALESCE(d.emails_sent, 0) as remaining_today,
                COALESCE(p.monthly_limit, 5000) - COALESCE(m.emails_sent, 0) as remaining_this_month
            FROM organizations o
            LEFT JOIN plan_tiers p ON p.name = COALESCE(o.plan_type, o.plan, 'free')
            LEFT JOIN organization_daily_usage d ON d.organization_id = o.id AND d.date = CURRENT_DATE
            LEFT JOIN (
                SELECT organization_id, SUM(emails_sent) as emails_sent
                FROM organization_daily_usage
                WHERE date >= DATE_TRUNC('month', CURRENT_DATE)
                GROUP BY organization_id
            ) m ON m.organization_id = o.id
            WHERE o.id = :org_id
        """), {'org_id': org_id})
        
        row = result.fetchone()
        if not row:
            return None
        
        return {
            'organization_id': row[0],
            'organization_name': row[1],
            'plan': row[2],
            'sending_enabled': row[3],
            'sending_disabled_reason': row[4],
            'overage_allowed': row[5],
            'daily_limit': row[6],
            'monthly_limit': row[7],
            'overage_rate': float(row[8]) if row[8] else 0.001,
            'emails_sent_today': row[9],
            'emails_sent_this_month': row[10],
            'remaining_today': max(0, row[11]),
            'remaining_this_month': max(0, row[12]),
            'daily_usage_percent': round((row[9] / row[6]) * 100, 1) if row[6] > 0 else 0,
            'monthly_usage_percent': round((row[10] / row[7]) * 100, 1) if row[7] > 0 else 0
        }
    
    def can_send(self, org_id, email_count=1):
        """Check if organization can send emails"""
        from sqlalchemy import text
        
        result = self.db.session.execute(
            text("SELECT * FROM check_email_limit(:org_id, :count)"),
            {'org_id': org_id, 'count': email_count}
        )
        row = result.fetchone()
        
        if row:
            return {
                'allowed': row[0],
                'reason': row[1],
                'remaining': row[2],
                'limit_type': row[3]
            }
        return {'allowed': False, 'reason': 'Unknown error', 'remaining': 0, 'limit_type': 'error'}
    
    def record_usage(self, org_id, sent=0, failed=0, bounced=0):
        """Record email usage"""
        from sqlalchemy import text
        
        try:
            self.db.session.execute(
                text("SELECT record_email_usage(:org_id, :sent, :failed, :bounced)"),
                {'org_id': org_id, 'sent': sent, 'failed': failed, 'bounced': bounced}
            )
            self.db.session.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to record usage: {e}")
            self.db.session.rollback()
            return False
    
    def disable_sending(self, org_id, reason):
        """Disable sending for an organization"""
        from sqlalchemy import text
        
        try:
            self.db.session.execute(text("""
                UPDATE organizations 
                SET sending_enabled = FALSE, sending_disabled_reason = :reason, updated_at = NOW()
                WHERE id = :org_id
            """), {'org_id': org_id, 'reason': reason})
            self.db.session.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to disable sending: {e}")
            return False
    
    def enable_sending(self, org_id):
        """Enable sending for an organization"""
        from sqlalchemy import text
        
        try:
            self.db.session.execute(text("""
                UPDATE organizations 
                SET sending_enabled = TRUE, sending_disabled_reason = NULL, updated_at = NOW()
                WHERE id = :org_id
            """), {'org_id': org_id})
            self.db.session.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to enable sending: {e}")
            return False
    
    def get_plan_details(self, plan_name='free'):
        """Get plan details"""
        from sqlalchemy import text
        
        result = self.db.session.execute(
            text("SELECT * FROM plan_tiers WHERE name = :name"),
            {'name': plan_name}
        )
        row = result.fetchone()
        
        if row:
            return {
                'name': row[1],
                'display_name': row[2],
                'daily_limit': row[3],
                'monthly_limit': row[4],
                'price_monthly': float(row[5]) if row[5] else 0,
                'price_yearly': float(row[6]) if row[6] else 0,
                'price_per_extra_email': float(row[7]) if row[7] else 0.001,
                'features': row[8] or {}
            }
        return None
    
    def get_all_plans(self):
        """Get all available plans"""
        from sqlalchemy import text
        
        result = self.db.session.execute(text("""
            SELECT name, display_name, daily_limit, monthly_limit, 
                   price_monthly, price_yearly, price_per_extra_email, features
            FROM plan_tiers 
            WHERE is_active = TRUE
            ORDER BY price_monthly ASC
        """))
        
        plans = []
        for row in result.fetchall():
            plans.append({
                'name': row[0],
                'display_name': row[1],
                'daily_limit': row[2],
                'monthly_limit': row[3],
                'price_monthly': float(row[4]) if row[4] else 0,
                'price_yearly': float(row[5]) if row[5] else 0,
                'price_per_extra_email': float(row[6]) if row[6] else 0.001,
                'features': row[7] or {}
            })
        return plans
    
    def upgrade_plan(self, org_id, new_plan):
        """Upgrade organization's plan"""
        from sqlalchemy import text
        
        try:
            self.db.session.execute(text("""
                UPDATE organizations 
                SET plan_type = :plan, plan = :plan, 
                    sending_enabled = TRUE, sending_disabled_reason = NULL,
                    updated_at = NOW()
                WHERE id = :org_id
            """), {'org_id': org_id, 'plan': new_plan})
            self.db.session.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to upgrade plan: {e}")
            return False


# Decorator for enforcing limits
def require_email_quota(email_count=1):
    """Decorator to check email quota before allowing action"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from flask_login import current_user
            
            if not hasattr(current_user, 'organization_id'):
                return jsonify({'error': 'No organization'}), 403
            
            service = UsageService()
            check = service.can_send(str(current_user.organization_id), email_count)
            
            if not check['allowed']:
                return jsonify({
                    'error': 'Email limit exceeded',
                    'reason': check['reason'],
                    'remaining': check['remaining'],
                    'limit_type': check['limit_type'],
                    'upgrade_url': '/dashboard/billing/upgrade'
                }), 429
            
            g.email_quota = check
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# Global instance
usage_service = UsageService()
