"""
SendBaba Email Tasks
Production-grade with rate limiting, bounce handling, and tracking
"""
from celery_app import celery_app
from celery import shared_task
from celery.exceptions import Retry, MaxRetriesExceededError
import smtplib
import ssl
import dns.resolver
import json
import uuid
import time
import logging
import redis
import psycopg2
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import hashlib

logger = logging.getLogger(__name__)

# Configuration
DB_CONFIG = {
    'host': '127.0.0.1',
    'database': 'emailer',
    'user': 'emailer',
    'password': 'SecurePassword123'
}

REDIS_HOST = 'localhost'
REDIS_PORT = 6379

# Rate limits per domain (emails per minute)
DOMAIN_RATE_LIMITS = {
    'gmail.com': 20,
    'googlemail.com': 20,
    'yahoo.com': 15,
    'yahoo.co.uk': 15,
    'hotmail.com': 15,
    'outlook.com': 15,
    'live.com': 15,
    'msn.com': 15,
    'aol.com': 10,
    'icloud.com': 15,
    'me.com': 15,
    'default': 30
}

# MX Cache
MX_CACHE = {}
MX_CACHE_TTL = 3600


def get_db():
    return psycopg2.connect(**DB_CONFIG)


def get_redis():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def get_mx_servers(domain: str) -> List[str]:
    """Get MX servers with caching"""
    now = time.time()
    if domain in MX_CACHE:
        servers, cached_time = MX_CACHE[domain]
        if now - cached_time < MX_CACHE_TTL:
            return servers
    
    try:
        records = dns.resolver.resolve(domain, 'MX')
        servers = [str(r.exchange).rstrip('.') for r in sorted(records, key=lambda x: x.preference)]
        MX_CACHE[domain] = (servers, now)
        return servers
    except Exception as e:
        logger.warning(f"MX lookup failed for {domain}: {e}")
        return []


def check_rate_limit(domain: str) -> bool:
    """Check if we can send to this domain (rate limiting)"""
    r = get_redis()
    key = f"ratelimit:{domain}:{int(time.time() // 60)}"
    
    limit = DOMAIN_RATE_LIMITS.get(domain, DOMAIN_RATE_LIMITS['default'])
    current = r.incr(key)
    
    if current == 1:
        r.expire(key, 120)  # 2 minute TTL
    
    return current <= limit


def wait_for_rate_limit(domain: str, max_wait: int = 60) -> bool:
    """Wait until rate limit allows sending"""
    start = time.time()
    while time.time() - start < max_wait:
        if check_rate_limit(domain):
            return True
        time.sleep(1)
    return False


def is_suppressed(email: str, org_id: str) -> bool:
    """Check if email is in suppression list"""
    r = get_redis()
    
    # Check global suppression
    if r.sismember('suppression:global', email.lower()):
        return True
    
    # Check org-specific suppression
    if r.sismember(f'suppression:{org_id}', email.lower()):
        return True
    
    return False


def add_to_suppression(email: str, org_id: str, reason: str):
    """Add email to suppression list"""
    r = get_redis()
    email_lower = email.lower()
    
    # Add to org suppression
    r.sadd(f'suppression:{org_id}', email_lower)
    
    # If hard bounce, add to global
    if reason in ['hard_bounce', 'invalid', 'does_not_exist']:
        r.sadd('suppression:global', email_lower)
    
    # Log to database
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO suppression_list (id, organization_id, email, reason, created_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (organization_id, email) DO UPDATE SET reason = EXCLUDED.reason
        """, (str(uuid.uuid4()), org_id, email_lower, reason))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to log suppression: {e}")


def generate_tracking_id() -> str:
    """Generate unique tracking ID"""
    return hashlib.sha256(f"{uuid.uuid4()}{time.time()}".encode()).hexdigest()[:32]


def add_tracking_pixel(html: str, tracking_id: str, tracking_domain: str) -> str:
    """Add open tracking pixel to HTML"""
    pixel = f'<img src="https://{tracking_domain}/track/open/{tracking_id}" width="1" height="1" style="display:none;" alt="" />'
    
    # Add before </body> if exists, else append
    if '</body>' in html.lower():
        html = html.replace('</body>', f'{pixel}</body>')
        html = html.replace('</BODY>', f'{pixel}</BODY>')
    else:
        html += pixel
    
    return html


def add_click_tracking(html: str, tracking_id: str, tracking_domain: str) -> str:
    """Replace links with tracking links"""
    import re
    
    def replace_link(match):
        original_url = match.group(1)
        if tracking_domain in original_url or 'unsubscribe' in original_url.lower():
            return match.group(0)
        
        import urllib.parse
        encoded_url = urllib.parse.quote(original_url, safe='')
        return f'href="https://{tracking_domain}/track/click/{tracking_id}?url={encoded_url}"'
    
    return re.sub(r'href="([^"]+)"', replace_link, html, flags=re.IGNORECASE)


@celery_app.task(bind=True, max_retries=5, default_retry_delay=60)
def send_single_email(self, email_data: dict) -> dict:
    """
    Send single email with rate limiting, tracking, and bounce handling
    """
    email_id = email_data.get('id', str(uuid.uuid4()))
    recipient = email_data.get('to') or email_data.get('to_email', '')
    org_id = email_data.get('organization_id', '')
    
    try:
        # Check suppression
        if is_suppressed(recipient, org_id):
            logger.info(f"Skipping suppressed email: {recipient}")
            update_email_status(email_id, 'suppressed')
            return {'success': False, 'reason': 'suppressed'}
        
        # Extract domain
        recipient_domain = recipient.split('@')[1].lower()
        
        # Check rate limit
        if not wait_for_rate_limit(recipient_domain, max_wait=30):
            raise self.retry(exc=Exception("Rate limit exceeded"), countdown=30)
        
        # Get MX servers
        mx_servers = get_mx_servers(recipient_domain)
        if not mx_servers:
            add_to_suppression(recipient, org_id, 'no_mx')
            update_email_status(email_id, 'bounced', 'No MX record')
            return {'success': False, 'bounce': True, 'reason': 'No MX record'}
        
        # Build message
        sender = email_data.get('from') or email_data.get('from_email') or 'noreply@sendbaba.com'
        if not sender or '@' not in sender:
            sender = 'noreply@sendbaba.com'
        
        sender_domain = sender.split('@')[1]
        from_name = email_data.get('from_name') or sender_domain.split('.')[0].title()
        subject = email_data.get('subject', 'Message')
        html_body = email_data.get('html_body') or email_data.get('html', '')
        text_body = email_data.get('text_body', '')
        
        # Add tracking
        tracking_id = email_data.get('tracking_id') or generate_tracking_id()
        tracking_domain = email_data.get('tracking_domain', 'track.sendbaba.com')
        
        if html_body:
            html_body = add_tracking_pixel(html_body, tracking_id, tracking_domain)
            html_body = add_click_tracking(html_body, tracking_id, tracking_domain)
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = f'{from_name} <{sender}>'
        msg['To'] = recipient
        msg['Subject'] = subject
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain=sender_domain)
        msg['X-Tracking-ID'] = tracking_id
        
        if email_data.get('reply_to'):
            msg['Reply-To'] = email_data['reply_to']
        
        # Add unsubscribe header
        unsubscribe_url = f'https://sendbaba.com/unsubscribe?id={tracking_id}'
        msg['List-Unsubscribe'] = f'<{unsubscribe_url}>'
        msg['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'
        
        # Body
        if text_body:
            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        if html_body:
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        # Send
        for mx_server in mx_servers[:3]:
            try:
                smtp = smtplib.SMTP(mx_server, 25, timeout=30)
                smtp.ehlo('mail.sendbaba.com')
                
                if smtp.has_extn('STARTTLS'):
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    smtp.starttls(context=context)
                    smtp.ehlo('mail.sendbaba.com')
                
                smtp.sendmail(sender, [recipient], msg.as_bytes())
                smtp.quit()
                
                # Success - update status and log tracking
                update_email_status(email_id, 'sent')
                log_tracking_event(tracking_id, email_id, org_id, recipient, 'sent')
                
                # Trigger webhook
                trigger_webhook.delay(org_id, 'email.sent', {
                    'email_id': email_id,
                    'recipient': recipient,
                    'tracking_id': tracking_id
                })
                
                logger.info(f"✓ Sent to {recipient}")
                return {'success': True, 'tracking_id': tracking_id}
            
            except smtplib.SMTPRecipientsRefused as e:
                add_to_suppression(recipient, org_id, 'hard_bounce')
                update_email_status(email_id, 'bounced', str(e))
                trigger_webhook.delay(org_id, 'email.bounced', {
                    'email_id': email_id,
                    'recipient': recipient,
                    'type': 'hard'
                })
                return {'success': False, 'bounce': True}
            
            except smtplib.SMTPDataError as e:
                if e.smtp_code >= 500:
                    add_to_suppression(recipient, org_id, 'hard_bounce')
                    update_email_status(email_id, 'bounced', str(e))
                    return {'success': False, 'bounce': True}
                continue
            
            except Exception as e:
                logger.warning(f"MX {mx_server} failed: {e}")
                continue
        
        # All MX failed - retry
        raise self.retry(exc=Exception("All MX servers failed"))
    
    except MaxRetriesExceededError:
        update_email_status(email_id, 'failed', 'Max retries exceeded')
        return {'success': False, 'reason': 'Max retries'}
    
    except Exception as e:
        logger.error(f"Send error: {e}")
        raise self.retry(exc=e)


def update_email_status(email_id: str, status: str, error: str = None):
    """Update email status in database"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        if status == 'sent':
            cursor.execute("""
                UPDATE emails SET status = %s, sent_at = NOW(), updated_at = NOW()
                WHERE id = %s
            """, (status, email_id))
        else:
            cursor.execute("""
                UPDATE emails SET status = %s, error_message = %s, updated_at = NOW()
                WHERE id = %s
            """, (status, error[:500] if error else None, email_id))
        
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"DB update failed: {e}")


def log_tracking_event(tracking_id: str, email_id: str, org_id: str, recipient: str, event_type: str):
    """Log tracking event"""
    try:
        r = get_redis()
        r.hset(f"tracking:{tracking_id}", mapping={
            'email_id': email_id,
            'org_id': org_id,
            'recipient': recipient,
            'sent_at': datetime.utcnow().isoformat(),
            'status': event_type
        })
        r.expire(f"tracking:{tracking_id}", 86400 * 30)  # 30 days
    except Exception as e:
        logger.error(f"Tracking log failed: {e}")


@celery_app.task(bind=True)
def send_bulk_batch(self, campaign_id: str, contacts: list, campaign_data: dict):
    """Send batch of emails"""
    results = {'queued': 0, 'skipped': 0}
    org_id = campaign_data.get('organization_id', '')
    
    for contact in contacts:
        email = contact.get('email', '')
        
        # Skip suppressed
        if is_suppressed(email, org_id):
            results['skipped'] += 1
            continue
        
        # Personalize
        subject = campaign_data.get('subject', '')
        html = campaign_data.get('html_body', '')
        
        for key, val in contact.items():
            placeholder = '{{' + key + '}}'
            subject = subject.replace(placeholder, str(val or ''))
            html = html.replace(placeholder, str(val or ''))
        
        # Queue individual send
        email_id = str(uuid.uuid4())
        
        send_single_email.apply_async(
            args=[{
                'id': email_id,
                'from': campaign_data.get('from_email'),
                'from_name': campaign_data.get('from_name'),
                'to': email,
                'subject': subject,
                'html_body': html,
                'reply_to': campaign_data.get('reply_to'),
                'organization_id': org_id,
                'campaign_id': campaign_id
            }],
            queue='bulk'
        )
        results['queued'] += 1
    
    return results


@celery_app.task
def process_bounces():
    """Process bounce notifications from queue"""
    r = get_redis()
    
    # Process up to 100 bounces
    for _ in range(100):
        bounce = r.lpop('bounce_queue')
        if not bounce:
            break
        
        try:
            data = json.loads(bounce)
            email = data.get('email', '')
            org_id = data.get('organization_id', '')
            bounce_type = data.get('type', 'soft')
            
            if bounce_type == 'hard':
                add_to_suppression(email, org_id, 'hard_bounce')
            
            logger.info(f"Processed bounce: {email} ({bounce_type})")
        except Exception as e:
            logger.error(f"Bounce processing error: {e}")


@celery_app.task
def cleanup_old_tracking():
    """Clean up old tracking data"""
    r = get_redis()
    # Redis handles TTL automatically, but we can clean up database
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM email_tracking 
            WHERE created_at < NOW() - INTERVAL '90 days'
        """)
        deleted = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"Cleaned up {deleted} old tracking records")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
