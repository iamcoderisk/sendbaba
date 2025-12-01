"""
IP Warmup Controller
Monitor and manage IP warming
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
import redis
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

warmup_bp = Blueprint('warmup', __name__, url_prefix='/api/warmup')

REDIS_HOST = 'localhost'
REDIS_PORT = 6379

# Default sending IP
DEFAULT_IP = '156.67.29.186'

# Warmup schedule
WARMUP_SCHEDULE = {
    1: 50, 2: 100, 3: 200, 4: 400, 5: 600, 6: 900, 7: 1200,
    14: 2500, 21: 5000, 28: 10000, 35: 20000, 42: 35000,
    49: 50000, 56: 75000, 63: 100000
}


def get_redis():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


@warmup_bp.route('/status', methods=['GET'])
@login_required
def get_warmup_status():
    """Get warmup status for all IPs"""
    try:
        r = get_redis()
        ip = request.args.get('ip', DEFAULT_IP)
        
        # Get warmup start date
        start_date = r.hget(f'warmup:{ip}', 'start_date')
        
        if not start_date:
            # Initialize warmup
            r.hset(f'warmup:{ip}', 'start_date', datetime.utcnow().isoformat())
            start_date = datetime.utcnow().isoformat()
            warmup_day = 1
        else:
            start = datetime.fromisoformat(start_date)
            warmup_day = (datetime.utcnow() - start).days + 1
        
        # Get daily limit
        daily_limit = WARMUP_SCHEDULE.get(1)
        for day in sorted(WARMUP_SCHEDULE.keys(), reverse=True):
            if warmup_day >= day:
                daily_limit = WARMUP_SCHEDULE[day]
                break
        
        # Get sent today
        today = datetime.utcnow().strftime('%Y-%m-%d')
        sent_today = int(r.get(f'sent:{ip}:{today}') or 0)
        
        return jsonify({
            'success': True,
            'ip': ip,
            'warmup_day': warmup_day,
            'daily_limit': daily_limit,
            'sent_today': sent_today,
            'remaining': max(0, daily_limit - sent_today),
            'progress_percent': min(100, round((warmup_day / 63) * 100, 1)),
            'fully_warmed': warmup_day >= 63,
            'start_date': start_date,
            'schedule': WARMUP_SCHEDULE
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@warmup_bp.route('/reset', methods=['POST'])
@login_required
def reset_warmup():
    """Reset warmup for an IP"""
    try:
        data = request.get_json()
        ip = data.get('ip', DEFAULT_IP)
        
        r = get_redis()
        r.delete(f'warmup:{ip}')
        r.hset(f'warmup:{ip}', 'start_date', datetime.utcnow().isoformat())
        
        logger.info(f"Warmup reset for IP: {ip}")
        
        return jsonify({'success': True, 'message': f'Warmup reset for {ip}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@warmup_bp.route('/history', methods=['GET'])
@login_required
def get_warmup_history():
    """Get warmup sending history"""
    try:
        r = get_redis()
        ip = request.args.get('ip', DEFAULT_IP)
        days = int(request.args.get('days', 30))
        
        history = []
        for i in range(days):
            date = (datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d')
            sent = int(r.get(f'sent:{ip}:{date}') or 0)
            history.append({'date': date, 'sent': sent})
        
        return jsonify({
            'success': True,
            'ip': ip,
            'history': history
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


from datetime import timedelta
