#!/usr/bin/env python3
"""
FAST Parallel Campaign Sender
Target: 30+ emails/second using ThreadPoolExecutor
"""
import os
import sys
import time
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import psycopg2

sys.path.insert(0, '/opt/sendbaba-staging')
os.environ['DATABASE_URL'] = 'postgresql://emailer:SecurePassword123@localhost:5432/emailer'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

from app.smtp.relay_server import send_email_sync

# Configuration
MAX_WORKERS = 30  # 30 parallel threads
PROGRESS_INTERVAL = 100  # Log every 100 emails

stats_lock = Lock()
stats = {'sent': 0, 'failed': 0, 'total': 0}

def get_db():
    return psycopg2.connect(
        host='localhost', database='emailer', 
        user='emailer', password='SecurePassword123'
    )

def send_one_email(args):
    """Send single email - called by thread pool"""
    email_data, email_id, campaign_id = args
    global stats
    
    try:
        result = send_email_sync(email_data)
        success = result.get('success', False)
        
        # Update DB
        conn = get_db()
        cur = conn.cursor()
        if success:
            cur.execute("UPDATE emails SET status = 'sent', sent_at = NOW() WHERE id = %s", (email_id,))
            with stats_lock:
                stats['sent'] += 1
        else:
            error = result.get('message', 'Unknown')[:500]
            cur.execute("UPDATE emails SET status = 'failed', error_message = %s WHERE id = %s", (error, email_id))
            with stats_lock:
                stats['failed'] += 1
        conn.commit()
        cur.close()
        conn.close()
        
        return success
    except Exception as e:
        with stats_lock:
            stats['failed'] += 1
        logger.error(f"Send error: {e}")
        return False

def fast_send_campaign(campaign_id: str, max_workers: int = MAX_WORKERS):
    """Send remaining emails in parallel"""
    global stats
    stats = {'sent': 0, 'failed': 0, 'total': 0}
    
    conn = get_db()
    cur = conn.cursor()
    
    start_time = time.time()
    
    # Get campaign details
    cur.execute("""
        SELECT id, organization_id, name, from_name, from_email,
               subject, html_body, text_body, reply_to
        FROM campaigns WHERE id = %s
    """, (campaign_id,))
    row = cur.fetchone()
    
    if not row:
        logger.error("Campaign not found!")
        return
    
    campaign = {
        'id': row[0], 'org_id': row[1], 'name': row[2],
        'from_name': row[3] or 'Support', 'from_email': row[4] or 'noreply@sendbaba.com', 
        'subject': row[5] or 'No Subject',
        'html_body': row[6] or '<p>Hello</p>', 'text_body': row[7] or 'Hello', 
        'reply_to': row[8] or row[4]
    }
    
    logger.info(f"Campaign: {campaign['name']}")
    logger.info(f"From: {campaign['from_name']} <{campaign['from_email']}>")
    logger.info(f"Subject: {campaign['subject']}")
    logger.info(f"HTML Length: {len(campaign['html_body'])} chars")
    
    # Check if html_body is empty
    if not campaign['html_body'] or len(campaign['html_body']) < 10:
        logger.error("❌ Campaign has no HTML body! Cannot send.")
        return
    
    # Update status to sending
    cur.execute("UPDATE campaigns SET status = 'sending', started_at = COALESCE(started_at, NOW()) WHERE id = %s", (campaign_id,))
    conn.commit()
    
    # Get contacts that haven't been emailed yet
    cur.execute("""
        SELECT c.id, c.email, c.first_name, c.last_name
        FROM contacts c
        WHERE c.organization_id = %s 
        AND c.status = 'active'
        AND c.email IS NOT NULL
        AND c.email != ''
        AND NOT EXISTS (
            SELECT 1 FROM emails e WHERE e.campaign_id = %s AND e.to_email = c.email
        )
        ORDER BY c.id
    """, (campaign['org_id'], campaign_id))
    
    contacts = cur.fetchall()
    stats['total'] = len(contacts)
    
    logger.info(f"🚀 FAST SEND: {campaign['name']}")
    logger.info(f"📧 Remaining contacts: {stats['total']}")
    logger.info(f"⚡ Workers: {max_workers}")
    
    if stats['total'] == 0:
        logger.info("✅ All emails already sent!")
        cur.execute("UPDATE campaigns SET status = 'completed' WHERE id = %s", (campaign_id,))
        conn.commit()
        return
    
    # Prepare email tasks
    tasks = []
    for contact in contacts:
        email_id = str(uuid.uuid4())
        to_email = contact[1]
        first_name = contact[2] or ''
        last_name = contact[3] or ''
        
        # Personalize
        subject = campaign['subject'].replace('{{first_name}}', first_name).replace('{{last_name}}', last_name)
        html_body = campaign['html_body'].replace('{{first_name}}', first_name).replace('{{last_name}}', last_name)
        text_body = campaign['text_body'].replace('{{first_name}}', first_name).replace('{{last_name}}', last_name) if campaign['text_body'] else ''
        
        # Pre-insert email record with ALL required fields
        cur.execute("""
            INSERT INTO emails (
                id, campaign_id, organization_id, 
                from_email, to_email, 
                sender, recipient,
                subject, html_body, text_body,
                status, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'sending', NOW())
        """, (
            email_id, campaign_id, campaign['org_id'],
            campaign['from_email'], to_email,
            campaign['from_email'], to_email,  # sender and recipient
            subject, html_body, text_body
        ))
        
        email_data = {
            'from': campaign['from_email'],
            'from_name': campaign['from_name'],
            'to': to_email,
            'subject': subject,
            'html_body': html_body,
            'text_body': text_body,
            'reply_to': campaign['reply_to'],
            'org_id': campaign['org_id']
        }
        tasks.append((email_data, email_id, campaign_id))
    
    conn.commit()
    logger.info(f"📝 Pre-inserted {len(tasks)} email records")
    
    # PARALLEL SEND
    logger.info(f"⚡ Starting parallel send with {max_workers} threads...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(send_one_email, task): task for task in tasks}
        
        completed = 0
        for future in as_completed(futures):
            completed += 1
            
            if completed % PROGRESS_INTERVAL == 0:
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = stats['total'] - completed
                eta = remaining / rate / 60 if rate > 0 else 0
                
                logger.info(f"📊 {completed}/{stats['total']} | {rate:.1f}/sec | ETA: {eta:.1f}min | ✅{stats['sent']} ❌{stats['failed']}")
                
                # Update campaign progress
                cur.execute("UPDATE campaigns SET sent_count = %s WHERE id = %s", (stats['sent'], campaign_id))
                conn.commit()
    
    # Final update
    elapsed = time.time() - start_time
    rate = stats['total'] / elapsed if elapsed > 0 else 0
    
    final_status = 'completed' if stats['failed'] < stats['total'] * 0.1 else 'completed_with_errors'
    cur.execute("""
        UPDATE campaigns SET status = %s, sent_count = %s, sent_at = NOW() WHERE id = %s
    """, (final_status, stats['sent'], campaign_id))
    conn.commit()
    
    logger.info(f"")
    logger.info(f"{'='*50}")
    logger.info(f"✅ CAMPAIGN COMPLETE!")
    logger.info(f"📧 Sent: {stats['sent']} | Failed: {stats['failed']}")
    logger.info(f"⏱️ Time: {elapsed/60:.1f} minutes")
    logger.info(f"🚀 Speed: {rate:.1f} emails/second")
    logger.info(f"{'='*50}")
    
    cur.close()
    conn.close()

if __name__ == '__main__':
    campaign_id = sys.argv[1] if len(sys.argv) > 1 else 'camp_1765784743_058fe64c84'
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    fast_send_campaign(campaign_id, workers)
