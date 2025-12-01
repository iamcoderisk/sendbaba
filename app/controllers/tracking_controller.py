"""
Email Tracking Controller
Open and click tracking
"""
from flask import Blueprint, request, redirect, Response
import redis
import json
import logging
from datetime import datetime
import psycopg2

logger = logging.getLogger(__name__)

tracking_bp = Blueprint('tracking', __name__, url_prefix='/track')

REDIS_HOST = 'localhost'
REDIS_PORT = 6379
DB_CONFIG = {
    'host': '127.0.0.1',
    'database': 'emailer',
    'user': 'emailer',
    'password': 'SecurePassword123'
}

# 1x1 transparent GIF
TRACKING_PIXEL = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'


def get_redis():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def get_db():
    return psycopg2.connect(**DB_CONFIG)


@tracking_bp.route('/open/<tracking_id>')
def track_open(tracking_id):
    """Track email open"""
    try:
        r = get_redis()
        tracking_data = r.hgetall(f'tracking:{tracking_id}')
        
        if tracking_data:
            # Update open status
            r.hset(f'tracking:{tracking_id}', mapping={
                'opened': 'true',
                'opened_at': datetime.utcnow().isoformat(),
                'open_ip': request.remote_addr,
                'open_ua': request.user_agent.string[:200] if request.user_agent else ''
            })
            
            # Increment open count
            r.hincrby(f'tracking:{tracking_id}', 'open_count', 1)
            
            # Update database
            email_id = tracking_data.get('email_id')
            if email_id:
                try:
                    conn = get_db()
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE emails SET opened_at = COALESCE(opened_at, NOW()), 
                        open_count = COALESCE(open_count, 0) + 1
                        WHERE id = %s
                    """, (email_id,))
                    conn.commit()
                    cursor.close()
                    conn.close()
                except Exception as e:
                    logger.error(f"DB update failed: {e}")
            
            # Update campaign stats
            org_id = tracking_data.get('org_id')
            if org_id:
                r.hincrby(f'campaign_stats:{org_id}', 'opens', 1)
            
            logger.info(f"Open tracked: {tracking_id}")
    except Exception as e:
        logger.error(f"Track open error: {e}")
    
    return Response(TRACKING_PIXEL, mimetype='image/gif')


@tracking_bp.route('/click/<tracking_id>')
def track_click(tracking_id):
    """Track link click"""
    url = request.args.get('url', 'https://sendbaba.com')
    
    try:
        r = get_redis()
        tracking_data = r.hgetall(f'tracking:{tracking_id}')
        
        if tracking_data:
            # Update click status
            r.hset(f'tracking:{tracking_id}', mapping={
                'clicked': 'true',
                'clicked_at': datetime.utcnow().isoformat(),
                'click_ip': request.remote_addr,
                'last_clicked_url': url[:500]
            })
            
            # Increment click count
            r.hincrby(f'tracking:{tracking_id}', 'click_count', 1)
            
            # Log individual click
            r.lpush(f'clicks:{tracking_id}', json.dumps({
                'url': url,
                'timestamp': datetime.utcnow().isoformat(),
                'ip': request.remote_addr
            }))
            
            # Update database
            email_id = tracking_data.get('email_id')
            if email_id:
                try:
                    conn = get_db()
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE emails SET clicked_at = COALESCE(clicked_at, NOW()),
                        click_count = COALESCE(click_count, 0) + 1
                        WHERE id = %s
                    """, (email_id,))
                    conn.commit()
                    cursor.close()
                    conn.close()
                except Exception as e:
                    logger.error(f"DB update failed: {e}")
            
            # Update campaign stats
            org_id = tracking_data.get('org_id')
            if org_id:
                r.hincrby(f'campaign_stats:{org_id}', 'clicks', 1)
            
            logger.info(f"Click tracked: {tracking_id} -> {url[:50]}")
    except Exception as e:
        logger.error(f"Track click error: {e}")
    
    import urllib.parse
    return redirect(urllib.parse.unquote(url))


@tracking_bp.route('/unsubscribe')
def unsubscribe():
    """Handle unsubscribe"""
    tracking_id = request.args.get('id', '')
    email = request.args.get('email', '')
    
    try:
        r = get_redis()
        
        if tracking_id:
            tracking_data = r.hgetall(f'tracking:{tracking_id}')
            email = tracking_data.get('recipient', email)
            org_id = tracking_data.get('org_id', '')
            
            if email and org_id:
                # Add to suppression list
                r.sadd(f'suppression:{org_id}', email.lower())
                
                # Log unsubscribe
                r.hset(f'tracking:{tracking_id}', 'unsubscribed', 'true')
                r.hset(f'tracking:{tracking_id}', 'unsubscribed_at', datetime.utcnow().isoformat())
                
                logger.info(f"Unsubscribed: {email}")
    except Exception as e:
        logger.error(f"Unsubscribe error: {e}")
    
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Unsubscribed</title></head>
    <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
        <h1>You have been unsubscribed</h1>
        <p>You will no longer receive emails from this sender.</p>
    </body>
    </html>
    """


@tracking_bp.route('/stats/<tracking_id>')
def get_stats(tracking_id):
    """Get tracking stats (internal use)"""
    try:
        r = get_redis()
        data = r.hgetall(f'tracking:{tracking_id}')
        return {'success': True, 'data': data}
    except Exception as e:
        return {'success': False, 'error': str(e)}
