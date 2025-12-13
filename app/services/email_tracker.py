"""
SendBaba Email Tracking Service
===============================
Injects tracking pixels and rewrites links for open/click tracking
"""
import re
import uuid
import hashlib
import logging
import redis
from urllib.parse import quote, urlencode
from datetime import datetime

logger = logging.getLogger(__name__)

# Configuration
TRACKING_DOMAIN = 'https://playmaster.sendbaba.com'
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_PASSWORD = 'SendBaba2024SecureRedis'


def get_redis():
    """Get Redis connection"""
    return redis.Redis(
        host=REDIS_HOST, 
        port=REDIS_PORT, 
        password=REDIS_PASSWORD,
        decode_responses=True
    )


def generate_tracking_id(email_id: str, recipient: str) -> str:
    """Generate unique tracking ID for an email"""
    # Create deterministic but unique tracking ID
    data = f"{email_id}:{recipient}:{datetime.utcnow().date()}"
    return hashlib.sha256(data.encode()).hexdigest()[:32]


def create_tracking_record(tracking_id: str, email_id: str, org_id: str, 
                           campaign_id: str, recipient: str) -> bool:
    """Create tracking record in Redis"""
    try:
        r = get_redis()
        
        tracking_data = {
            'email_id': email_id,
            'org_id': org_id,
            'campaign_id': campaign_id or '',
            'recipient': recipient,
            'created_at': datetime.utcnow().isoformat(),
            'opened': 'false',
            'clicked': 'false',
            'open_count': '0',
            'click_count': '0'
        }
        
        # Store tracking data (expire after 90 days)
        r.hset(f'tracking:{tracking_id}', mapping=tracking_data)
        r.expire(f'tracking:{tracking_id}', 90 * 24 * 60 * 60)
        
        return True
    except Exception as e:
        logger.error(f"Failed to create tracking record: {e}")
        return False


def inject_tracking_pixel(html_body: str, tracking_id: str) -> str:
    """Inject invisible tracking pixel into HTML email"""
    if not html_body:
        return html_body
    
    # Create tracking pixel URL
    pixel_url = f"{TRACKING_DOMAIN}/track/open/{tracking_id}"
    
    # Tracking pixel HTML (1x1 transparent image)
    tracking_pixel = f'''<img src="{pixel_url}" width="1" height="1" border="0" style="display:block;width:1px;height:1px;border:0;" alt="" />'''
    
    # Try to inject before </body>
    if '</body>' in html_body.lower():
        # Find </body> case-insensitively
        pattern = re.compile(r'(</body>)', re.IGNORECASE)
        html_body = pattern.sub(f'{tracking_pixel}\\1', html_body, count=1)
    else:
        # Append to end if no body tag
        html_body += tracking_pixel
    
    return html_body


def rewrite_links(html_body: str, tracking_id: str) -> str:
    """Rewrite all links to go through click tracking"""
    if not html_body:
        return html_body
    
    def replace_link(match):
        original_url = match.group(1)
        
        # Skip tracking URLs, anchors, mailto, tel
        if any(skip in original_url.lower() for skip in [
            '/track/', 'mailto:', 'tel:', 'javascript:', '#', 
            'unsubscribe', tracking_id
        ]):
            return match.group(0)
        
        # Skip empty or relative URLs
        if not original_url or not original_url.startswith(('http://', 'https://')):
            return match.group(0)
        
        # Create tracking URL
        encoded_url = quote(original_url, safe='')
        tracking_url = f"{TRACKING_DOMAIN}/track/click/{tracking_id}?url={encoded_url}"
        
        return f'href="{tracking_url}"'
    
    # Match href attributes
    pattern = r'href=["\']([^"\']+)["\']'
    html_body = re.sub(pattern, replace_link, html_body, flags=re.IGNORECASE)
    
    return html_body


def add_unsubscribe_link(html_body: str, tracking_id: str, recipient: str) -> str:
    """Add unsubscribe link if not present"""
    if not html_body:
        return html_body
    
    # Check if unsubscribe link already exists
    if 'unsubscribe' in html_body.lower():
        return html_body
    
    # Create unsubscribe URL
    unsubscribe_url = f"{TRACKING_DOMAIN}/track/unsubscribe?id={tracking_id}&email={quote(recipient)}"
    
    # Unsubscribe footer
    unsubscribe_footer = f'''
    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; text-align: center; font-size: 12px; color: #666;">
        <p>If you no longer wish to receive these emails, you can <a href="{unsubscribe_url}" style="color: #666;">unsubscribe here</a>.</p>
    </div>
    '''
    
    # Inject before </body>
    if '</body>' in html_body.lower():
        pattern = re.compile(r'(</body>)', re.IGNORECASE)
        html_body = pattern.sub(f'{unsubscribe_footer}\\1', html_body, count=1)
    else:
        html_body += unsubscribe_footer
    
    return html_body


def prepare_email_for_tracking(html_body: str, email_id: str, org_id: str,
                                campaign_id: str, recipient: str) -> tuple:
    """
    Main function to prepare email with full tracking
    
    Returns:
        tuple: (processed_html, tracking_id)
    """
    if not html_body:
        return html_body, None
    
    # Generate tracking ID
    tracking_id = generate_tracking_id(email_id, recipient)
    
    # Create tracking record in Redis
    create_tracking_record(tracking_id, email_id, org_id, campaign_id, recipient)
    
    # Process HTML
    processed_html = html_body
    
    # 1. Rewrite links for click tracking
    processed_html = rewrite_links(processed_html, tracking_id)
    
    # 2. Add unsubscribe link
    processed_html = add_unsubscribe_link(processed_html, tracking_id, recipient)
    
    # 3. Inject tracking pixel (do this last)
    processed_html = inject_tracking_pixel(processed_html, tracking_id)
    
    logger.debug(f"Prepared tracking for email {email_id}, tracking_id: {tracking_id}")
    
    return processed_html, tracking_id


def get_tracking_stats(tracking_id: str) -> dict:
    """Get tracking statistics for an email"""
    try:
        r = get_redis()
        data = r.hgetall(f'tracking:{tracking_id}')
        return {
            'opened': data.get('opened') == 'true',
            'clicked': data.get('clicked') == 'true',
            'open_count': int(data.get('open_count', 0)),
            'click_count': int(data.get('click_count', 0)),
            'opened_at': data.get('opened_at'),
            'clicked_at': data.get('clicked_at')
        }
    except Exception as e:
        logger.error(f"Failed to get tracking stats: {e}")
        return {}
