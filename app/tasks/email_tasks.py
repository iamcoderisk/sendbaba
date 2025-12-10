"""
SendBaba Email Tasks - Clean Rewrite
Simple, working bulk email system
"""
import os
import sys
import uuid
import smtplib
import logging
import dns.resolver
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Add path
sys.path.insert(0, '/opt/sendbaba-staging')

from celery_app import celery_app

logger = logging.getLogger(__name__)

# ============================================
# DATABASE HELPER
# ============================================
def get_db_connection():
    """Get direct database connection"""
    import psycopg2
    return psycopg2.connect(
        host='localhost',
        database='sendbaba',
        user='sendbaba',
        password='SB_Secure_2024!'
    )

# ============================================
# EMAIL HELPERS  
# ============================================
def get_mx_server(domain):
    """Get MX server for domain"""
    try:
        records = dns.resolver.resolve(domain, 'MX')
        mx_record = sorted(records, key=lambda x: x.preference)[0]
        return str(mx_record.exchange).rstrip('.')
    except Exception as e:
        logger.error(f"MX lookup failed for {domain}: {e}")
        return None

def send_email_smtp(from_email, to_email, subject, html_body, text_body=None):
    """Send single email via SMTP"""
    try:
        domain = to_email.split('@')[1]
        mx_server = get_mx_server(domain)
        
        if not mx_server:
            return False, "No MX record"
        
        msg = MIMEMultipart('alternative')
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg['Message-ID'] = f"<{uuid.uuid4()}@sendbaba.com>"
        
        if text_body:
            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        if html_body:
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        with smtplib.SMTP(mx_server, 25, timeout=30) as server:
            server.ehlo('mail.sendbaba.com')
            try:
                server.starttls()
                server.ehlo('mail.sendbaba.com')
            except:
                pass
            server.sendmail(from_email, [to_email], msg.as_string())
        
        return True, "Sent"
    except Exception as e:
        return False, str(e)

def personalize(content, contact):
    """Replace merge tags"""
    if not content:
        return content
    
    replacements = {
        '{{first_name}}': contact.get('first_name', ''),
        '{{last_name}}': contact.get('last_name', ''),
        '{{email}}': contact.get('email', ''),
        '{{FIRST_NAME}}': contact.get('first_name', ''),
        '{{LAST_NAME}}': contact.get('last_name', ''),
        '*|FNAME|*': contact.get('first_name', ''),
        '*|LNAME|*': contact.get('last_name', ''),
    }
    
    for tag, value in replacements.items():
        content = content.replace(tag, str(value or ''))
    
    return content

# ============================================
# MAIN CAMPAIGN TASK
# ============================================
@celery_app.task(bind=True)
def send_campaign(self, campaign_id):
    """
    Main task to send a campaign
    Fetches contacts and sends emails directly
    """
    logger.info(f"🚀 Starting campaign {campaign_id}")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get campaign
        cursor.execute("""
            SELECT id, organization_id, name, from_name, from_email, 
                   subject, html_body, text_body, reply_to
            FROM campaigns WHERE id = %s
        """, (campaign_id,))
        
        row = cursor.fetchone()
        if not row:
            logger.error(f"Campaign {campaign_id} not found")
            return {'success': False, 'error': 'Campaign not found'}
        
        campaign = {
            'id': row[0],
            'organization_id': row[1],
            'name': row[2],
            'from_name': row[3],
            'from_email': row[4],
            'subject': row[5],
            'html_body': row[6],
            'text_body': row[7],
            'reply_to': row[8]
        }
        
        org_id = campaign['organization_id']
        from_email = f"{campaign['from_name']} <{campaign['from_email']}>" if campaign['from_name'] else campaign['from_email']
        
        # Update status to sending
        cursor.execute("""
            UPDATE campaigns SET status = 'sending', started_at = NOW(), updated_at = NOW()
            WHERE id = %s
        """, (campaign_id,))
        conn.commit()
        
        # Get contacts
        cursor.execute("""
            SELECT id, email, first_name, last_name 
            FROM contacts 
            WHERE organization_id = %s AND status = 'active'
        """, (org_id,))
        
        contacts = cursor.fetchall()
        total = len(contacts)
        
        logger.info(f"📧 Sending to {total} contacts")
        
        sent = 0
        failed = 0
        
        for contact_row in contacts:
            contact = {
                'id': contact_row[0],
                'email': contact_row[1],
                'first_name': contact_row[2],
                'last_name': contact_row[3]
            }
            
            to_email = contact['email']
            if not to_email or '@' not in to_email:
                failed += 1
                continue
            
            # Personalize
            subject = personalize(campaign['subject'], contact)
            html_body = personalize(campaign['html_body'], contact)
            text_body = personalize(campaign['text_body'], contact)
            
            # Create email record
            email_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO emails (id, organization_id, campaign_id, from_email, to_email,
                                   sender, recipient, subject, html_body, text_body, 
                                   status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'sending', NOW())
            """, (email_id, org_id, campaign_id, campaign['from_email'], to_email,
                  campaign['from_email'], to_email, subject, html_body, text_body))
            conn.commit()
            
            # Send email
            success, message = send_email_smtp(from_email, to_email, subject, html_body, text_body)
            
            if success:
                cursor.execute("""
                    UPDATE emails SET status = 'sent', sent_at = NOW() WHERE id = %s
                """, (email_id,))
                sent += 1
                logger.info(f"✅ Sent to {to_email}")
            else:
                cursor.execute("""
                    UPDATE emails SET status = 'failed', error_message = %s WHERE id = %s
                """, (message[:500], email_id))
                failed += 1
                logger.warning(f"❌ Failed {to_email}: {message}")
            
            conn.commit()
            
            # Update campaign progress every 10 emails
            if (sent + failed) % 10 == 0:
                cursor.execute("""
                    UPDATE campaigns SET emails_sent = %s, updated_at = NOW() WHERE id = %s
                """, (sent, campaign_id))
                conn.commit()
        
        # Mark complete
        cursor.execute("""
            UPDATE campaigns 
            SET status = 'completed', emails_sent = %s, completed_at = NOW(), updated_at = NOW()
            WHERE id = %s
        """, (sent, campaign_id))
        conn.commit()
        
        logger.info(f"🎉 Campaign {campaign_id} complete: {sent} sent, {failed} failed")
        
        return {'success': True, 'sent': sent, 'failed': failed, 'total': total}
        
    except Exception as e:
        logger.error(f"Campaign {campaign_id} error: {e}")
        cursor.execute("""
            UPDATE campaigns SET status = 'failed', updated_at = NOW() WHERE id = %s
        """, (campaign_id,))
        conn.commit()
        return {'success': False, 'error': str(e)}
    finally:
        cursor.close()
        conn.close()

# ============================================
# SINGLE EMAIL TASK (for Team Send)
# ============================================
@celery_app.task
def send_single_email_task(email_id):
    """Send a single email from the Team page"""
    logger.info(f"📤 Sending single email {email_id}")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT from_email, to_email, subject, html_body, text_body
            FROM emails WHERE id = %s
        """, (email_id,))
        
        row = cursor.fetchone()
        if not row:
            return {'success': False, 'error': 'Email not found'}
        
        from_email, to_email, subject, html_body, text_body = row
        
        cursor.execute("UPDATE emails SET status = 'sending' WHERE id = %s", (email_id,))
        conn.commit()
        
        success, message = send_email_smtp(from_email, to_email, subject, html_body, text_body)
        
        if success:
            cursor.execute("""
                UPDATE emails SET status = 'sent', sent_at = NOW() WHERE id = %s
            """, (email_id,))
            logger.info(f"✅ Single email sent to {to_email}")
        else:
            cursor.execute("""
                UPDATE emails SET status = 'failed', error_message = %s WHERE id = %s
            """, (message[:500], email_id))
            logger.warning(f"❌ Single email failed to {to_email}: {message}")
        
        conn.commit()
        return {'success': success, 'message': message}
        
    except Exception as e:
        logger.error(f"Single email error: {e}")
        return {'success': False, 'error': str(e)}
    finally:
        cursor.close()
        conn.close()

# ============================================
# PERIODIC TASKS
# ============================================
@celery_app.task
def process_queued_campaigns():
    """Process campaigns stuck in 'queued' status"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT id, name FROM campaigns WHERE status = 'queued'
            ORDER BY created_at ASC LIMIT 5
        """)
        
        campaigns = cursor.fetchall()
        processed = 0
        
        for campaign_id, name in campaigns:
            logger.info(f"🔄 Processing queued campaign: {name}")
            send_campaign.delay(campaign_id)
            processed += 1
        
        return {'processed': processed, 'found': len(campaigns)}
    finally:
        cursor.close()
        conn.close()

@celery_app.task
def process_queued_single_emails():
    """Process single emails in queued status"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT id FROM emails 
            WHERE status = 'queued' AND campaign_id IS NULL
            ORDER BY created_at ASC LIMIT 50
        """)
        
        emails = cursor.fetchall()
        count = 0
        
        for (email_id,) in emails:
            send_single_email_task.delay(email_id)
            count += 1
        
        logger.info(f"Found {count} queued single emails to process")
        return {'queued_count': count}
    finally:
        cursor.close()
        conn.close()
