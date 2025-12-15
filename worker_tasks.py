"""
SendBaba Worker Tasks
=====================
Standalone email sending tasks for distributed workers.
These tasks connect directly to PostgreSQL and Redis without Flask.
"""
import os
import sys
import logging
import time
import json
import smtplib
import ssl
import dns.resolver
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, Optional, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
import redis

from celery_worker_config import celery_app

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Database connection
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://emailer:SecurePassword123@156.67.29.186:5432/emailer')
REDIS_URL = os.environ.get('REDIS_URL', 'redis://:SendBabaRedis2024!@194.163.128.208:6379/0')

def get_db_connection():
    """Get a database connection."""
    return psycopg2.connect(DATABASE_URL)

def get_redis_client():
    """Get Redis client."""
    return redis.from_url(REDIS_URL)

def get_mx_records(domain: str) -> list:
    """Get MX records for a domain."""
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        mx_records = sorted([(r.preference, str(r.exchange).rstrip('.')) for r in answers])
        return [mx[1] for mx in mx_records]
    except Exception as e:
        logger.error(f"MX lookup failed for {domain}: {e}")
        return []

def send_email_direct(
    to_email: str,
    from_email: str,
    from_name: str,
    subject: str,
    html_body: str,
    text_body: str = None,
    reply_to: str = None,
    dkim_selector: str = None,
    dkim_private_key: str = None,
    custom_headers: dict = None,
    source_ip: str = None
) -> Tuple[bool, str]:
    """
    Send email directly via SMTP to recipient's MX server.
    """
    try:
        # Get recipient domain
        recipient_domain = to_email.split('@')[1]
        mx_records = get_mx_records(recipient_domain)
        
        if not mx_records:
            return False, f"No MX records found for {recipient_domain}"
        
        # Build message
        msg = MIMEMultipart('alternative')
        msg['From'] = f"{from_name} <{from_email}>" if from_name else from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg['Message-ID'] = f"<{os.urandom(16).hex()}@{from_email.split('@')[1]}>"
        msg['Date'] = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S +0000')
        
        if reply_to:
            msg['Reply-To'] = reply_to
        
        # Add custom headers
        if custom_headers:
            for key, value in custom_headers.items():
                msg[key] = value
        
        # Add body parts
        if text_body:
            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        # Sign with DKIM if available
        if dkim_selector and dkim_private_key:
            try:
                import dkim
                from_domain = from_email.split('@')[1]
                sig = dkim.sign(
                    message=msg.as_bytes(),
                    selector=dkim_selector.encode(),
                    domain=from_domain.encode(),
                    privkey=dkim_private_key.encode(),
                    include_headers=[b'from', b'to', b'subject', b'date', b'message-id']
                )
                msg['DKIM-Signature'] = sig.decode().replace('DKIM-Signature: ', '')
            except Exception as e:
                logger.warning(f"DKIM signing failed: {e}")
        
        # Try each MX server
        last_error = None
        for mx_host in mx_records[:3]:  # Try top 3 MX servers
            try:
                # Connect with TLS
                context = ssl.create_default_context()
                
                with smtplib.SMTP(mx_host, 25, timeout=30, source_address=(source_ip, 0) if source_ip else None) as server:
                    server.ehlo()
                    if server.has_extn('STARTTLS'):
                        server.starttls(context=context)
                        server.ehlo()
                    
                    server.sendmail(from_email, [to_email], msg.as_string())
                    return True, f"Sent via {mx_host}"
                    
            except smtplib.SMTPRecipientsRefused as e:
                return False, f"Recipient refused: {e}"
            except smtplib.SMTPSenderRefused as e:
                return False, f"Sender refused: {e}"
            except Exception as e:
                last_error = str(e)
                logger.warning(f"MX {mx_host} failed: {e}")
                continue
        
        return False, f"All MX servers failed. Last error: {last_error}"
        
    except Exception as e:
        logger.error(f"Send failed: {e}")
        return False, str(e)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_single_email_task(self, email_data: dict) -> dict:
    """
    Celery task to send a single email.
    
    email_data should contain:
    - to_email
    - from_email
    - from_name
    - subject
    - html_body
    - text_body (optional)
    - reply_to (optional)
    - dkim_selector (optional)
    - dkim_private_key (optional)
    - email_id (for tracking)
    - campaign_id (optional)
    """
    start_time = time.time()
    email_id = email_data.get('email_id')
    
    try:
        success, message = send_email_direct(
            to_email=email_data['to_email'],
            from_email=email_data['from_email'],
            from_name=email_data.get('from_name', ''),
            subject=email_data['subject'],
            html_body=email_data['html_body'],
            text_body=email_data.get('text_body'),
            reply_to=email_data.get('reply_to'),
            dkim_selector=email_data.get('dkim_selector'),
            dkim_private_key=email_data.get('dkim_private_key'),
            source_ip=email_data.get('source_ip')
        )
        
        elapsed = time.time() - start_time
        
        # Update database
        if email_id:
            try:
                conn = get_db_connection()
                with conn.cursor() as cur:
                    status = 'sent' if success else 'failed'
                    cur.execute("""
                        UPDATE emails 
                        SET status = %s, 
                            sent_at = NOW(),
                            smtp_response = %s,
                            updated_at = NOW()
                        WHERE id = %s
                    """, (status, message, email_id))
                    conn.commit()
                conn.close()
            except Exception as db_error:
                logger.error(f"DB update failed: {db_error}")
        
        result = {
            'success': success,
            'message': message,
            'email_id': email_id,
            'elapsed': elapsed,
            'worker': self.request.hostname
        }
        
        if success:
            logger.info(f"✅ Sent to {email_data['to_email']} in {elapsed:.2f}s")
        else:
            logger.warning(f"❌ Failed to {email_data['to_email']}: {message}")
            
        return result
        
    except Exception as e:
        logger.error(f"Task error: {e}")
        raise self.retry(exc=e)


@celery_app.task(bind=True)
def send_batch_emails_task(self, emails: list) -> dict:
    """
    Send a batch of emails.
    """
    results = {
        'total': len(emails),
        'sent': 0,
        'failed': 0,
        'errors': []
    }
    
    for email_data in emails:
        try:
            success, message = send_email_direct(
                to_email=email_data['to_email'],
                from_email=email_data['from_email'],
                from_name=email_data.get('from_name', ''),
                subject=email_data['subject'],
                html_body=email_data['html_body'],
                text_body=email_data.get('text_body'),
                reply_to=email_data.get('reply_to'),
                dkim_selector=email_data.get('dkim_selector'),
                dkim_private_key=email_data.get('dkim_private_key'),
                source_ip=email_data.get('source_ip')
            )
            
            if success:
                results['sent'] += 1
            else:
                results['failed'] += 1
                results['errors'].append({'email': email_data['to_email'], 'error': message})
                
        except Exception as e:
            results['failed'] += 1
            results['errors'].append({'email': email_data.get('to_email', 'unknown'), 'error': str(e)})
    
    logger.info(f"Batch complete: {results['sent']}/{results['total']} sent")
    return results


@celery_app.task
def health_check_task() -> dict:
    """Health check task."""
    import socket
    return {
        'status': 'healthy',
        'hostname': socket.gethostname(),
        'timestamp': datetime.utcnow().isoformat()
    }


# Register tasks
celery_app.tasks.register(send_single_email_task)
celery_app.tasks.register(send_batch_emails_task)
celery_app.tasks.register(health_check_task)
