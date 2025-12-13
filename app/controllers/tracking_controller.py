"""
SendBaba Email Tracking Controller
==================================
Handles open tracking, click tracking, and unsubscribes
"""
from flask import Blueprint, request, redirect, Response, jsonify
import redis
import json
import logging
from datetime import datetime
import psycopg2

logger = logging.getLogger(__name__)

tracking_bp = Blueprint('tracking', __name__, url_prefix='/track')

# Configuration
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_PASSWORD = 'SendBaba2024SecureRedis'

DB_CONFIG = {
    'host': '127.0.0.1',
    'database': 'emailer',
    'user': 'emailer',
    'password': 'SecurePassword123'
}

# 1x1 transparent GIF
TRACKING_PIXEL = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'


def get_redis():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True)


def get_db():
    return psycopg2.connect(**DB_CONFIG)


@tracking_bp.route('/open/<tracking_id>')
def track_open(tracking_id):
    """Track email open via invisible pixel"""
    try:
        r = get_redis()
        tracking_data = r.hgetall(f'tracking:{tracking_id}')
        
        if tracking_data:
            email_id = tracking_data.get('email_id')
            org_id = tracking_data.get('org_id')
            campaign_id = tracking_data.get('campaign_id')
            is_first_open = tracking_data.get('opened') != 'true'
            
            # Update Redis tracking data
            r.hset(f'tracking:{tracking_id}', mapping={
                'opened': 'true',
                'opened_at': tracking_data.get('opened_at') or datetime.utcnow().isoformat(),
                'last_open_at': datetime.utcnow().isoformat(),
                'open_ip': request.remote_addr,
                'open_ua': (request.user_agent.string[:200] if request.user_agent else '')
            })
            r.hincrby(f'tracking:{tracking_id}', 'open_count', 1)
            
            # Update database
            if email_id:
                try:
                    conn = get_db()
                    cursor = conn.cursor()
                    
                    # Update email record
                    cursor.execute("""
                        UPDATE emails 
                        SET status = CASE WHEN status = 'sent' THEN 'opened' ELSE status END,
                            opened_at = COALESCE(opened_at, NOW()),
                            open_count = COALESCE(open_count, 0) + 1,
                            updated_at = NOW()
                        WHERE id = %s
                    """, (email_id,))
                    
                    # Update campaign stats if first open
                    if is_first_open and campaign_id:
                        cursor.execute("""
                            UPDATE campaigns 
                            SET emails_opened = COALESCE(emails_opened, 0) + 1,
                                updated_at = NOW()
                            WHERE id = %s
                        """, (campaign_id,))
                    
                    conn.commit()
                    cursor.close()
                    conn.close()
                except Exception as e:
                    logger.error(f"DB update failed: {e}")
            
            logger.info(f"📖 Open tracked: {tracking_id[:16]}... (email: {email_id[:8] if email_id else 'N/A'}...)")
            
    except Exception as e:
        logger.error(f"Track open error: {e}")
    
    # Return tracking pixel with cache-busting headers
    return Response(
        TRACKING_PIXEL, 
        mimetype='image/gif',
        headers={
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    )


@tracking_bp.route('/click/<tracking_id>')
def track_click(tracking_id):
    """Track link click and redirect"""
    url = request.args.get('url', 'https://sendbaba.com')
    
    try:
        r = get_redis()
        tracking_data = r.hgetall(f'tracking:{tracking_id}')
        
        if tracking_data:
            email_id = tracking_data.get('email_id')
            org_id = tracking_data.get('org_id')
            campaign_id = tracking_data.get('campaign_id')
            is_first_click = tracking_data.get('clicked') != 'true'
            
            # Update Redis tracking
            r.hset(f'tracking:{tracking_id}', mapping={
                'clicked': 'true',
                'clicked_at': tracking_data.get('clicked_at') or datetime.utcnow().isoformat(),
                'last_click_at': datetime.utcnow().isoformat(),
                'click_ip': request.remote_addr,
                'last_clicked_url': url[:500]
            })
            r.hincrby(f'tracking:{tracking_id}', 'click_count', 1)
            
            # Log click details
            r.lpush(f'clicks:{tracking_id}', json.dumps({
                'url': url,
                'timestamp': datetime.utcnow().isoformat(),
                'ip': request.remote_addr,
                'ua': request.user_agent.string[:100] if request.user_agent else ''
            }))
            r.ltrim(f'clicks:{tracking_id}', 0, 99)  # Keep last 100 clicks
            
            # Update database
            if email_id:
                try:
                    conn = get_db()
                    cursor = conn.cursor()
                    
                    # Update email record
                    cursor.execute("""
                        UPDATE emails 
                        SET status = 'clicked',
                            clicked_at = COALESCE(clicked_at, NOW()),
                            click_count = COALESCE(click_count, 0) + 1,
                            updated_at = NOW()
                        WHERE id = %s
                    """, (email_id,))
                    
                    # Update campaign stats if first click
                    if is_first_click and campaign_id:
                        cursor.execute("""
                            UPDATE campaigns 
                            SET emails_clicked = COALESCE(emails_clicked, 0) + 1,
                                updated_at = NOW()
                            WHERE id = %s
                        """, (campaign_id,))
                    
                    conn.commit()
                    cursor.close()
                    conn.close()
                except Exception as e:
                    logger.error(f"DB update failed: {e}")
            
            logger.info(f"🖱️ Click tracked: {tracking_id[:16]}... -> {url[:50]}...")
            
    except Exception as e:
        logger.error(f"Track click error: {e}")
    
    # Decode and redirect
    import urllib.parse
    decoded_url = urllib.parse.unquote(url)
    return redirect(decoded_url)


@tracking_bp.route('/unsubscribe')
def unsubscribe():
    """Handle unsubscribe requests"""
    tracking_id = request.args.get('id', '')
    email = request.args.get('email', '')
    
    success = False
    
    try:
        r = get_redis()
        
        if tracking_id:
            tracking_data = r.hgetall(f'tracking:{tracking_id}')
            email = tracking_data.get('recipient', email)
            org_id = tracking_data.get('org_id', '')
            
            if email and org_id:
                # Add to suppression list in Redis
                r.sadd(f'suppression:{org_id}', email.lower())
                
                # Mark as unsubscribed
                r.hset(f'tracking:{tracking_id}', mapping={
                    'unsubscribed': 'true',
                    'unsubscribed_at': datetime.utcnow().isoformat()
                })
                
                # Update database
                try:
                    conn = get_db()
                    cursor = conn.cursor()
                    
                    # Mark contact as unsubscribed
                    cursor.execute("""
                        UPDATE contacts 
                        SET status = 'unsubscribed', updated_at = NOW()
                        WHERE email = %s AND organization_id = %s
                    """, (email.lower(), org_id))
                    
                    # Add to suppression table if exists
                    cursor.execute("""
                        INSERT INTO suppression_list (organization_id, email, reason, created_at)
                        VALUES (%s, %s, 'unsubscribed', NOW())
                        ON CONFLICT DO NOTHING
                    """, (org_id, email.lower()))
                    
                    conn.commit()
                    cursor.close()
                    conn.close()
                    success = True
                except Exception as e:
                    logger.error(f"DB unsubscribe failed: {e}")
                    success = True  # Still mark as success since Redis worked
                
                logger.info(f"📭 Unsubscribed: {email}")
                
    except Exception as e:
        logger.error(f"Unsubscribe error: {e}")
    
    # Return styled unsubscribe confirmation page
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Unsubscribed - SendBaba</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                   text-align: center; padding: 50px 20px; background: #f5f5f5; }}
            .container {{ max-width: 500px; margin: 0 auto; background: white; 
                         padding: 40px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            h1 {{ color: #f87137; margin-bottom: 20px; }}
            p {{ color: #666; line-height: 1.6; }}
            .icon {{ font-size: 60px; margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="icon">{'✅' if success else '⚠️'}</div>
            <h1>{'Successfully Unsubscribed' if success else 'Unsubscribe Request'}</h1>
            <p>{'You have been removed from this mailing list and will no longer receive emails from this sender.' if success else 'We could not process your request. Please contact the sender directly.'}</p>
            <p style="margin-top: 30px; font-size: 12px; color: #999;">Powered by SendBaba</p>
        </div>
    </body>
    </html>
    '''


@tracking_bp.route('/stats/<tracking_id>')
def get_stats(tracking_id):
    """Get tracking stats (API endpoint)"""
    try:
        r = get_redis()
        data = r.hgetall(f'tracking:{tracking_id}')
        
        if not data:
            return jsonify({'success': False, 'error': 'Tracking ID not found'}), 404
        
        return jsonify({
            'success': True,
            'data': {
                'opened': data.get('opened') == 'true',
                'clicked': data.get('clicked') == 'true',
                'open_count': int(data.get('open_count', 0)),
                'click_count': int(data.get('click_count', 0)),
                'opened_at': data.get('opened_at'),
                'clicked_at': data.get('clicked_at'),
                'unsubscribed': data.get('unsubscribed') == 'true'
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@tracking_bp.route('/health')
def health():
    """Health check endpoint"""
    try:
        r = get_redis()
        r.ping()
        return jsonify({'status': 'healthy', 'redis': 'connected'})
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500
