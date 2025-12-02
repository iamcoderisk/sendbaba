"""
SendBaba Email Tasks
Production-grade Celery tasks for bulk email
Handles millions of emails with auto-retry
"""
from celery_app import celery_app
from celery import shared_task, group, chain, chord
from celery.exceptions import Retry, MaxRetriesExceededError
from datetime import datetime, timedelta
import smtplib
import dns.resolver
import json
import uuid
import time
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection
DB_CONFIG = {
    'host': '127.0.0.1',
    'database': 'emailer',
    'user': 'emailer',
    'password': 'SecurePassword123'
}

def get_db():
    import psycopg2
    return psycopg2.connect(**DB_CONFIG)

def get_redis():
    import redis
    return redis.Redis(host='localhost', port=6379, decode_responses=True)


# ============================================
# MX LOOKUP WITH CACHING
# ============================================

MX_CACHE = {}
MX_CACHE_TTL = 300  # 5 minutes

def get_mx_server(domain):
    """Get MX server with caching"""
    now = time.time()
    
    # Check cache
    if domain in MX_CACHE:
        cached, timestamp = MX_CACHE[domain]
        if now - timestamp < MX_CACHE_TTL:
            return cached
    
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        mx_records = sorted([(r.preference, str(r.exchange).rstrip('.')) for r in answers])
        
        if mx_records:
            mx_server = mx_records[0][1]
            MX_CACHE[domain] = (mx_server, now)
            return mx_server
    except Exception as e:
        logger.warning(f"MX lookup failed for {domain}: {e}")
    
    return None


# ============================================
# SINGLE EMAIL TASK
# ============================================

@celery_app.task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,
    autoretry_for=(smtplib.SMTPException, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=3600,
    retry_jitter=True
)
def send_single_email(self, email_data):
    """
    Send a single email with auto-retry
    
    Args:
        email_data: dict with id, from, to, subject, html_body, text_body
    
    Returns:
        dict with success status and details
    """
    email_id = email_data.get('id', 'unknown')
    recipient = email_data.get('to')
    
    try:
        # Extract domain
        domain = recipient.split('@')[1]
        
        # Get MX server
        mx_server = get_mx_server(domain)
        if not mx_server:
            # Hard bounce - no MX record
            update_email_status(email_id, 'bounced', 'No MX record found')
            return {'success': False, 'bounce': True, 'reason': 'No MX record'}
        
        # Build message
        msg = MIMEMultipart('alternative')
        msg['From'] = email_data.get('from', 'noreply@sendbaba.com')
        msg['To'] = recipient
        msg['Subject'] = email_data.get('subject', '')
        msg['Message-ID'] = f"<{email_id}@sendbaba.com>"
        msg['X-Campaign-ID'] = email_data.get('campaign_id', '')
        
        if email_data.get('reply_to'):
            msg['Reply-To'] = email_data['reply_to']
        
        # Add body parts
        if email_data.get('text_body'):
            msg.attach(MIMEText(email_data['text_body'], 'plain', 'utf-8'))
        if email_data.get('html_body'):
            msg.attach(MIMEText(email_data['html_body'], 'html', 'utf-8'))
        
        # Send via SMTP
        with smtplib.SMTP(mx_server, 25, timeout=30) as server:
            server.starttls()
            server.sendmail(
                email_data.get('from', 'noreply@sendbaba.com'),
                [recipient],
                msg.as_string()
            )
        
        # Success - update database
        update_email_status(email_id, 'sent')
        
        logger.info(f"✓ Sent to {recipient} via {mx_server}")
        
        return {
            'success': True,
            'email_id': email_id,
            'recipient': recipient,
            'mx_server': mx_server
        }
    
    except smtplib.SMTPRecipientsRefused as e:
        # Hard bounce
        update_email_status(email_id, 'bounced', str(e))
        logger.warning(f"✗ Hard bounce: {recipient}")
        return {'success': False, 'bounce': True, 'reason': str(e)}
    
    except smtplib.SMTPResponseException as e:
        if e.code >= 500 and e.code < 600:
            # Permanent failure
            update_email_status(email_id, 'bounced', f"{e.code}: {e.message}")
            return {'success': False, 'bounce': True, 'reason': str(e)}
        else:
            # Temporary failure - retry
            logger.warning(f"↻ Retry {self.request.retries + 1}/5: {recipient} - {e}")
            raise self.retry(exc=e)
    
    except (smtplib.SMTPException, ConnectionError, TimeoutError) as e:
        # Temporary failure - retry
        logger.warning(f"↻ Retry {self.request.retries + 1}/5: {recipient} - {e}")
        update_email_status(email_id, 'retrying', str(e))
        raise self.retry(exc=e)
    
    except MaxRetriesExceededError:
        # Max retries reached
        update_email_status(email_id, 'failed', 'Max retries exceeded')
        logger.error(f"✗ Failed after retries: {recipient}")
        return {'success': False, 'reason': 'Max retries exceeded'}
    
    except Exception as e:
        # Unexpected error
        update_email_status(email_id, 'failed', str(e))
        logger.error(f"✗ Error: {recipient} - {e}")
        return {'success': False, 'reason': str(e)}


def update_email_status(email_id, status, error=None):
    """Update email status in database"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        if status == 'sent':
            cursor.execute(
                "UPDATE emails SET status = %s, sent_at = NOW() WHERE id = %s",
                (status, email_id)
            )
        else:
            cursor.execute(
                "UPDATE emails SET status = %s, error_message = %s WHERE id = %s",
                (status, error[:500] if error else None, email_id)
            )
        
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"DB update error: {e}")


# ============================================
# BULK BATCH TASK
# ============================================

@celery_app.task(bind=True)
def send_bulk_batch(self, campaign_id, contact_batch, campaign_data):
    """
    Send batch of emails (up to 1000 contacts)
    Creates individual tasks for each email
    """
    results = {'queued': 0, 'errors': 0}
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        for contact in contact_batch:
            try:
                email_id = str(uuid.uuid4())
                
                # Personalize content
                subject = personalize(campaign_data['subject'], contact)
                html_body = personalize(campaign_data.get('html_body'), contact)
                text_body = personalize(campaign_data.get('text_body'), contact)
                
                # Create email record
                cursor.execute("""
                    INSERT INTO emails (
                        id, organization_id, campaign_id, sender, recipient,
                        from_email, to_email, subject, html_body, text_body,
                        status, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'queued', NOW())
                """, (
                    email_id,
                    campaign_data['organization_id'],
                    campaign_id,
                    campaign_data['from_email'],
                    contact['email'],
                    campaign_data['from_email'],
                    contact['email'],
                    subject,
                    html_body,
                    text_body
                ))
                
                # Queue individual email task
                email_task_data = {
                    'id': email_id,
                    'from': f"{campaign_data.get('from_name', '')} <{campaign_data['from_email']}>".strip(),
                    'to': contact['email'],
                    'subject': subject,
                    'html_body': html_body,
                    'text_body': text_body,
                    'reply_to': campaign_data.get('reply_to'),
                    'campaign_id': campaign_id,
                    'organization_id': campaign_data['organization_id']
                }
                
                send_single_email.apply_async(
                    args=[email_task_data],
                    queue='default',
                    priority=5
                )
                
                results['queued'] += 1
            
            except Exception as e:
                results['errors'] += 1
                logger.error(f"Error queuing email to {contact.get('email')}: {e}")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Batch complete: {results['queued']} queued, {results['errors']} errors")
        
    except Exception as e:
        logger.error(f"Batch error: {e}")
        results['errors'] = len(contact_batch)
    
    return results


def personalize(content, contact):
    """Replace merge tags with contact data"""
    if not content:
        return content
    
    first_name = contact.get('first_name', '')
    last_name = contact.get('last_name', '')
    email = contact.get('email', '')
    
    replacements = {
        '{{first_name}}': first_name,
        '{{last_name}}': last_name,
        '{{email}}': email,
        '{{FIRST_NAME}}': first_name,
        '{{LAST_NAME}}': last_name,
        '{{EMAIL}}': email,
        '*|FNAME|*': first_name,
        '*|LNAME|*': last_name,
        '*|EMAIL|*': email,
    }
    
    for tag, value in replacements.items():
        content = content.replace(tag, str(value))
    
    return content


# ============================================
# CAMPAIGN ORCHESTRATOR
# ============================================

@celery_app.task(bind=True)
def send_campaign(self, campaign_id):
    """
    Main campaign send task
    Fetches contacts in batches and creates batch tasks
    Handles 1M+ contacts
    """
    BATCH_SIZE = 1000  # Contacts per batch task
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Get campaign
        cursor.execute("""
            SELECT id, organization_id, name, from_name, from_email, reply_to,
                   subject, html_body, text_body, status
            FROM campaigns WHERE id = %s
        """, (campaign_id,))
        
        row = cursor.fetchone()
        if not row:
            logger.error(f"Campaign {campaign_id} not found")
            return {'success': False, 'error': 'Campaign not found'}
        
        campaign_data = {
            'id': row[0],
            'organization_id': row[1],
            'name': row[2],
            'from_name': row[3],
            'from_email': row[4],
            'reply_to': row[5],
            'subject': row[6],
            'html_body': row[7],
            'text_body': row[8]
        }
        
        org_id = campaign_data['organization_id']
        
        # Get total contacts
        cursor.execute("""
            SELECT COUNT(*) FROM contacts 
            WHERE organization_id = %s AND status = 'active'
        """, (org_id,))
        total_contacts = cursor.fetchone()[0]
        
        if total_contacts == 0:
            cursor.close()
            conn.close()
            return {'success': False, 'error': 'No contacts'}
        
        # Update campaign status
        cursor.execute("""
            UPDATE campaigns 
            SET status = 'sending', total_recipients = %s, emails_sent = 0, updated_at = NOW()
            WHERE id = %s
        """, (total_contacts, campaign_id))
        conn.commit()
        
        logger.info(f"Campaign {campaign_id}: Starting send to {total_contacts} contacts")
        
        # Process contacts in batches
        offset = 0
        batch_num = 0
        total_batches = (total_contacts + BATCH_SIZE - 1) // BATCH_SIZE
        
        while offset < total_contacts:
            # Fetch batch
            cursor.execute("""
                SELECT id, email, first_name, last_name
                FROM contacts 
                WHERE organization_id = %s AND status = 'active'
                ORDER BY id
                OFFSET %s LIMIT %s
            """, (org_id, offset, BATCH_SIZE))
            
            rows = cursor.fetchall()
            if not rows:
                break
            
            # Convert to list of dicts
            contact_batch = [
                {'id': r[0], 'email': r[1], 'first_name': r[2], 'last_name': r[3]}
                for r in rows
            ]
            
            # Queue batch task
            send_bulk_batch.apply_async(
                args=[campaign_id, contact_batch, campaign_data],
                queue='bulk',
                priority=5
            )
            
            batch_num += 1
            offset += BATCH_SIZE
            
            logger.info(f"Campaign {campaign_id}: Queued batch {batch_num}/{total_batches}")
        
        cursor.close()
        conn.close()
        
        logger.info(f"Campaign {campaign_id}: All {total_batches} batches queued")
        
        return {
            'success': True,
            'campaign_id': campaign_id,
            'total_contacts': total_contacts,
            'batches_queued': batch_num
        }
    
    except Exception as e:
        logger.error(f"Campaign {campaign_id} error: {e}")
        
        # Mark as failed
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE campaigns SET status = 'failed', updated_at = NOW() WHERE id = %s",
                (campaign_id,)
            )
            conn.commit()
            cursor.close()
            conn.close()
        except:
            pass
        
        return {'success': False, 'error': str(e)}


# ============================================
# RETRY FAILED EMAILS
# ============================================

@celery_app.task
def process_retry_queue():
    """Process emails that need retry"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Get emails to retry (failed in last hour, not bounced)
        cursor.execute("""
            SELECT id, organization_id, campaign_id, from_email, to_email,
                   subject, html_body, text_body
            FROM emails 
            WHERE status = 'retrying' 
            AND updated_at < NOW() - INTERVAL '5 minutes'
            LIMIT 1000
        """)
        
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        retried = 0
        for row in rows:
            email_data = {
                'id': row[0],
                'from': row[3],
                'to': row[4],
                'subject': row[5],
                'html_body': row[6],
                'text_body': row[7],
                'campaign_id': row[2],
                'organization_id': row[1]
            }
            
            send_single_email.apply_async(
                args=[email_data],
                queue='retry',
                priority=3
            )
            retried += 1
        
        if retried > 0:
            logger.info(f"Retried {retried} emails")
        
        return {'retried': retried}
    
    except Exception as e:
        logger.error(f"Retry queue error: {e}")
        return {'error': str(e)}


# ============================================
# UPDATE CAMPAIGN STATS
# ============================================

@celery_app.task
def update_campaign_stats():
    """Update campaign statistics from email results"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Get campaigns that are sending
        cursor.execute("""
            SELECT id FROM campaigns WHERE status = 'sending'
        """)
        
        campaign_ids = [row[0] for row in cursor.fetchall()]
        
        for campaign_id in campaign_ids:
            # Count email statuses
            cursor.execute("""
                SELECT 
                    COUNT(*) FILTER (WHERE status = 'sent') as sent,
                    COUNT(*) FILTER (WHERE status = 'bounced') as bounced,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed,
                    COUNT(*) FILTER (WHERE status IN ('queued', 'retrying')) as pending
                FROM emails WHERE campaign_id = %s
            """, (campaign_id,))
            
            stats = cursor.fetchone()
            sent, bounced, failed, pending = stats
            
            # Update campaign
            if pending == 0:
                # All done
                cursor.execute("""
                    UPDATE campaigns 
                    SET status = 'sent', emails_sent = %s, bounces = %s, 
                        sent_at = NOW(), updated_at = NOW()
                    WHERE id = %s
                """, (sent, bounced, campaign_id))
            else:
                cursor.execute("""
                    UPDATE campaigns 
                    SET emails_sent = %s, bounces = %s, updated_at = NOW()
                    WHERE id = %s
                """, (sent, bounced, campaign_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return {'updated': len(campaign_ids)}
    
    except Exception as e:
        logger.error(f"Stats update error: {e}")
        return {'error': str(e)}


# ============================================
# CLEANUP OLD RESULTS
# ============================================

@celery_app.task
def cleanup_old_results():
    """Clean up old task results from Redis"""
    try:
        r = get_redis()
        
        # Clean celery results older than 1 hour
        # This is handled by result_expires config, but we can force cleanup
        
        return {'status': 'ok'}
    
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        return {'error': str(e)}


# ============================================
# HIGH PRIORITY EMAIL
# ============================================

@celery_app.task(bind=True, max_retries=3)
def send_high_priority(self, email_data):
    """Send high priority email (transactional)"""
    return send_single_email(email_data)
