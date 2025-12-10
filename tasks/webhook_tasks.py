"""
Webhook Delivery Tasks
Real-time event notifications
"""
from celery_app import celery_app
import requests
import redis
import json
import hmac
import hashlib
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

REDIS_HOST = 'localhost'
REDIS_PORT = 6379


def get_redis():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password='SendBaba2024SecureRedis', decode_responses=True)


def sign_payload(payload: str, secret: str) -> str:
    """Sign webhook payload with HMAC-SHA256"""
    return hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()


@celery_app.task(bind=True, max_retries=5, default_retry_delay=30)
def trigger_webhook(self, org_id: str, event_type: str, data: dict):
    """Trigger webhook for organization"""
    r = get_redis()
    
    # Get webhook config for org
    webhook_config = r.hgetall(f'webhook:{org_id}')
    
    if not webhook_config or not webhook_config.get('url'):
        return {'success': False, 'reason': 'No webhook configured'}
    
    url = webhook_config['url']
    secret = webhook_config.get('secret', '')
    
    # Build payload
    payload = {
        'event': event_type,
        'timestamp': datetime.utcnow().isoformat(),
        'organization_id': org_id,
        'data': data
    }
    
    payload_json = json.dumps(payload)
    
    # Sign payload
    signature = sign_payload(payload_json, secret) if secret else ''
    
    headers = {
        'Content-Type': 'application/json',
        'X-SendBaba-Event': event_type,
        'X-SendBaba-Signature': signature,
        'X-SendBaba-Timestamp': str(int(datetime.utcnow().timestamp()))
    }
    
    try:
        response = requests.post(url, data=payload_json, headers=headers, timeout=10)
        
        if response.status_code >= 200 and response.status_code < 300:
            logger.info(f"Webhook delivered: {event_type} to {org_id}")
            return {'success': True, 'status_code': response.status_code}
        else:
            raise Exception(f"Webhook failed: {response.status_code}")
    
    except Exception as e:
        logger.warning(f"Webhook error: {e}")
        raise self.retry(exc=e)


@celery_app.task
def process_webhook_queue():
    """Process queued webhooks"""
    r = get_redis()
    
    for _ in range(100):
        item = r.lpop('webhook_queue')
        if not item:
            break
        
        try:
            data = json.loads(item)
            trigger_webhook.delay(
                data.get('org_id'),
                data.get('event'),
                data.get('data', {})
            )
        except Exception as e:
            logger.error(f"Webhook queue error: {e}")


def queue_webhook(org_id: str, event: str, data: dict):
    """Queue webhook for async delivery"""
    r = get_redis()
    r.rpush('webhook_queue', json.dumps({
        'org_id': org_id,
        'event': event,
        'data': data
    }))
