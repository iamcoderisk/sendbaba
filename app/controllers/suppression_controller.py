"""
Suppression List Controller
Manage bounces, unsubscribes, and complaints
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
import redis
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

suppression_bp = Blueprint('suppression', __name__, url_prefix='/api/suppression')

REDIS_HOST = 'localhost'
REDIS_PORT = 6379


def get_redis():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


@suppression_bp.route('/list', methods=['GET'])
@login_required
def list_suppressed():
    """Get suppression list for organization"""
    try:
        r = get_redis()
        org_id = str(current_user.organization_id)
        
        # Get org-specific suppressions
        emails = list(r.smembers(f'suppression:{org_id}'))
        
        return jsonify({
            'success': True,
            'count': len(emails),
            'emails': emails[:1000]  # Limit response
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@suppression_bp.route('/add', methods=['POST'])
@login_required
def add_suppression():
    """Add email to suppression list"""
    try:
        data = request.get_json()
        email = data.get('email', '').lower().strip()
        reason = data.get('reason', 'manual')
        
        if not email or '@' not in email:
            return jsonify({'success': False, 'error': 'Invalid email'}), 400
        
        r = get_redis()
        org_id = str(current_user.organization_id)
        
        r.sadd(f'suppression:{org_id}', email)
        
        logger.info(f"Added to suppression: {email} ({reason})")
        
        return jsonify({'success': True, 'email': email})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@suppression_bp.route('/remove', methods=['POST'])
@login_required
def remove_suppression():
    """Remove email from suppression list"""
    try:
        data = request.get_json()
        email = data.get('email', '').lower().strip()
        
        if not email:
            return jsonify({'success': False, 'error': 'Email required'}), 400
        
        r = get_redis()
        org_id = str(current_user.organization_id)
        
        removed = r.srem(f'suppression:{org_id}', email)
        
        return jsonify({'success': True, 'removed': bool(removed)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@suppression_bp.route('/check', methods=['POST'])
@login_required
def check_suppression():
    """Check if emails are suppressed"""
    try:
        data = request.get_json()
        emails = data.get('emails', [])
        
        if not emails:
            return jsonify({'success': False, 'error': 'Emails required'}), 400
        
        r = get_redis()
        org_id = str(current_user.organization_id)
        
        suppressed = []
        for email in emails[:1000]:
            email_lower = email.lower().strip()
            if r.sismember(f'suppression:{org_id}', email_lower) or \
               r.sismember('suppression:global', email_lower):
                suppressed.append(email)
        
        return jsonify({
            'success': True,
            'checked': len(emails),
            'suppressed': suppressed,
            'suppressed_count': len(suppressed)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@suppression_bp.route('/import', methods=['POST'])
@login_required
def import_suppressions():
    """Bulk import suppression list"""
    try:
        data = request.get_json()
        emails = data.get('emails', [])
        reason = data.get('reason', 'import')
        
        if not emails:
            return jsonify({'success': False, 'error': 'Emails required'}), 400
        
        r = get_redis()
        org_id = str(current_user.organization_id)
        
        added = 0
        for email in emails[:10000]:
            email_lower = email.lower().strip()
            if email_lower and '@' in email_lower:
                r.sadd(f'suppression:{org_id}', email_lower)
                added += 1
        
        logger.info(f"Imported {added} suppressions for org {org_id}")
        
        return jsonify({'success': True, 'added': added})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
