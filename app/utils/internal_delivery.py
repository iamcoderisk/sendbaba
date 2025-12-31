"""
SendBaba Internal Delivery System
Direct delivery between SendBaba users without SMTP relay
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import uuid
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = "postgresql://emailer:SecurePassword123@localhost/emailer"

def get_db():
    return psycopg2.connect(DATABASE_URL)

def is_internal_user(email):
    """Check if email belongs to a SendBaba mailbox"""
    if not email:
        return False
    
    email = email.lower().strip()
    domain = email.split('@')[-1] if '@' in email else ''
    
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check if mailbox exists
        cur.execute("SELECT id FROM mailboxes WHERE email = %s AND is_active = true", (email,))
        result = cur.fetchone()
        
        if result:
            conn.close()
            return True
        
        # Check if domain is a verified SendBaba domain
        if domain == 'sendbaba.com':
            conn.close()
            return True
        
        # Check mailbox_domains (legacy)
        cur.execute("""
            SELECT 1 FROM mailbox_domains 
            WHERE domain = %s AND is_active = true AND mx_verified = true
        """, (domain,))
        if cur.fetchone():
            conn.close()
            return True
        
        # Check webmail_domains (custom domains)
        try:
            cur.execute("""
                SELECT 1 FROM webmail_domains 
                WHERE domain_name = %s AND is_active = true AND dns_verified = true
            """, (domain,))
            if cur.fetchone():
                conn.close()
                return True
        except:
            pass
        
        conn.close()
        return False
    except Exception as e:
        logger.error(f"Error checking internal user: {e}")
        return False

def get_mailbox_id(email):
    """Get mailbox ID for an email, or create if on valid domain"""
    email = email.lower().strip()
    
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check if mailbox exists
        cur.execute("SELECT id FROM mailboxes WHERE email = %s", (email,))
        result = cur.fetchone()
        
        if result:
            conn.close()
            return result['id']
        
        conn.close()
        return None
    except Exception as e:
        logger.error(f"Error getting mailbox ID: {e}")
        return None

def deliver_internal(from_email, from_name, to_email, subject, body_text, body_html, 
                     message_id=None, in_reply_to=None, thread_id=None, 
                     has_audio=False, audio_url=None):
    """
    Deliver email directly to recipient's inbox (no SMTP)
    Returns: {'success': bool, 'email_id': int or None, 'error': str or None}
    """
    to_email = to_email.lower().strip()
    
    try:
        # Get recipient's mailbox
        recipient_mailbox_id = get_mailbox_id(to_email)
        
        if not recipient_mailbox_id:
            return {'success': False, 'error': f'Mailbox not found: {to_email}'}
        
        # Generate message ID if not provided
        if not message_id:
            message_id = f'<{uuid.uuid4()}@sendbaba.com>'
        
        if not thread_id:
            thread_id = in_reply_to if in_reply_to else message_id
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Insert into recipient's inbox
        cur.execute("""
            INSERT INTO mailbox_emails
            (mailbox_id, message_id, in_reply_to, thread_id, from_email, from_name,
             to_email, subject, body_text, body_html, folder, is_read, 
             has_attachments, received_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'inbox', false, %s, NOW())
            RETURNING id
        """, (
            recipient_mailbox_id, message_id, in_reply_to, thread_id,
            from_email, from_name, to_email, subject, body_text, body_html,
            has_audio
        ))
        
        email_id = cur.fetchone()['id']
        conn.commit()
        conn.close()
        
        logger.info(f"📬 Internal delivery: {from_email} -> {to_email} (ID: {email_id})")
        
        # Send real-time notification
        try:
            from app.socketio_events import notify_new_email
            notify_new_email(to_email, {
                'id': email_id,
                'from_email': from_email,
                'from_name': from_name,
                'subject': subject,
                'body_text': body_text[:100] if body_text else '',
                'has_audio': has_audio,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as ws_err:
            logger.warning(f"WebSocket notification failed: {ws_err}")
        
        return {'success': True, 'email_id': email_id, 'internal': True}
        
    except Exception as e:
        logger.error(f"Internal delivery error: {e}")
        return {'success': False, 'error': str(e)}
