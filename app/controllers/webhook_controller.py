"""
Webhook Configuration Controller
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
import redis
import secrets
import logging

logger = logging.getLogger(__name__)

webhook_bp = Blueprint('webhook', __name__, url_prefix='/api/webhook')

REDIS_HOST = 'localhost'
REDIS_PORT = 6379


def get_redis():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


@webhook_bp.route('/config', methods=['GET'])
@login_required
def get_webhook_config():
    """Get webhook configuration"""
    try:
        r = get_redis()
        org_id = str(current_user.organization_id)
        
        config = r.hgetall(f'webhook:{org_id}')
        
        # Mask secret
        if config.get('secret'):
            config['secret'] = config['secret'][:8] + '...'
        
        return jsonify({
            'success': True,
            'config': config or {}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webhook_bp.route('/config', methods=['POST'])
@login_required
def update_webhook_config():
    """Update webhook configuration"""
    try:
        data = request.get_json()
        url = data.get('url', '')
        events = data.get('events', ['email.sent', 'email.bounced', 'email.opened', 'email.clicked'])
        
        r = get_redis()
        org_id = str(current_user.organization_id)
        
        # Generate new secret if not exists
        existing = r.hgetall(f'webhook:{org_id}')
        secret = existing.get('secret') or secrets.token_hex(32)
        
        r.hset(f'webhook:{org_id}', mapping={
            'url': url,
            'secret': secret,
            'events': ','.join(events),
            'enabled': 'true' if url else 'false'
        })
        
        return jsonify({
            'success': True,
            'secret': secret  # Return full secret on update
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webhook_bp.route('/test', methods=['POST'])
@login_required
def test_webhook():
    """Send test webhook"""
    try:
        from tasks.webhook_tasks import trigger_webhook
        
        org_id = str(current_user.organization_id)
        
        trigger_webhook.delay(org_id, 'test', {
            'message': 'This is a test webhook',
            'timestamp': datetime.utcnow().isoformat()
        })
        
        return jsonify({'success': True, 'message': 'Test webhook queued'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


from datetime import datetime
