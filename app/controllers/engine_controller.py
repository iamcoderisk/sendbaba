"""
Email Engine API Controller
Provides statistics and management for the email engine
"""
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
import logging

logger = logging.getLogger(__name__)

engine_bp = Blueprint('engine', __name__, url_prefix='/api/engine')


@engine_bp.route('/stats')
@login_required
def get_stats():
    """Get email engine statistics"""
    try:
        from app.tasks.email_tasks import get_engine_stats
        stats = get_engine_stats()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        logger.error(f"Error getting engine stats: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@engine_bp.route('/warmup/<ip>', methods=['POST'])
@login_required  
def set_warmup_day(ip):
    """Set warmup day for an IP"""
    try:
        from app.utils.email_engine import get_email_engine
        day = request.json.get('day', 1)
        engine = get_email_engine()
        success = engine.set_warmup_day(ip, day)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@engine_bp.route('/health')
def health():
    """Health check endpoint"""
    try:
        from app.utils.email_engine import get_email_engine
        engine = get_email_engine()
        stats = engine.get_stats()
        
        healthy = any(ip['available'] for ip in stats['ips'])
        
        return jsonify({
            'healthy': healthy,
            'ips_available': sum(1 for ip in stats['ips'] if ip['available']),
            'total_ips': len(stats['ips']),
            'capacity_remaining': stats['total_capacity_today'] - stats['total_sent_today']
        })
    except Exception as e:
        return jsonify({'healthy': False, 'error': str(e)}), 500
