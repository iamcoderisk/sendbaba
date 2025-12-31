#!/usr/bin/env python3
"""
Resume Campaign Sender - Sends pending/failed emails
"""
import os
import sys
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import psycopg2

sys.path.insert(0, '/opt/sendbaba-staging')
os.environ['DATABASE_URL'] = 'postgresql://emailer:SecurePassword123@localhost:5432/emailer'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

from app.smtp.relay_server import send_email_sync

MAX_WORKERS = 50
PROGRESS_INTERVAL = 500

stats_lock = Lock()
stats = {'sent': 0, 'failed': 0, 'total': 0}

def get_db():
    return psycopg2.connect(
        host='localhost', database='emailer', 
        user='emailer', password='SecurePassword123'
    )

def send_one_email(email_row):
    """Send single email from existing record"""
    global stats
    email_id, to_email, subject, html_body, text_body, from_email, org_id = email_row
    
    try:
        # Get campaign from_name
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT from_name FROM campaigns WHERE id = (SELECT campaign_id FROM emails WHERE id = %s)", (email_id,))
        from_name_row = cur.fetchone()
        from_name = from_name_row[0] if from_name_row else 'Support'
        cur.close()
        conn.close()
        
        email_data = {
            'from': from_email,
            'from_name': from_name,
            'to': to_email,
            'subject': subject,
            'html_body': html_body or '<p>Hello</p>',
            'text_body': text_body or '',
            'org_id': org_id
        }
        
        result = send_email_sync(email_data)
        success = result.get('success', False)
        
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
        return False

def resume_campaign(campaign_id: str, max_workers: int = MAX_WORKERS):
    """Resume sending pending emails"""
    global stats
    stats = {'sent': 0, 'failed': 0, 'total': 0}
    
    conn = get_db()
    cur = conn.cursor()
    
    start_time = time.time()
    
    # Get pending emails
    cur.execute("""
        SELECT id, to_email, subject, html_body, text_body, from_email, organization_id
        FROM emails
        WHERE campaign_id = %s 
        AND status IN ('pending', 'sending')
        ORDER BY id
    """, (campaign_id,))
    
    emails = cur.fetchall()
    stats['total'] = len(emails)
    
    logger.info(f"🚀 RESUMING CAMPAIGN: {campaign_id}")
    logger.info(f"📧 Pending emails: {stats['total']}")
    logger.info(f"⚡ Workers: {max_workers}")
    
    if stats['total'] == 0:
        logger.info("✅ No pending emails!")
        return
    
    # Update campaign status
    cur.execute("UPDATE campaigns SET status = 'sending' WHERE id = %s", (campaign_id,))
    conn.commit()
    
    # Mark all as sending
    cur.execute("UPDATE emails SET status = 'sending' WHERE campaign_id = %s AND status = 'pending'", (campaign_id,))
    conn.commit()
    
    # PARALLEL SEND
    logger.info(f"⚡ Starting parallel send...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(send_one_email, email): email for email in emails}
        
        completed = 0
        for future in as_completed(futures):
            completed += 1
            
            if completed % PROGRESS_INTERVAL == 0:
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = stats['total'] - completed
                eta = remaining / rate / 60 if rate > 0 else 0
                
                logger.info(f"📊 {completed}/{stats['total']} | {rate:.1f}/sec | ETA: {eta:.1f}min | ✅{stats['sent']} ❌{stats['failed']}")
                
                # Update campaign
                cur.execute("UPDATE campaigns SET sent_count = %s WHERE id = %s", 
                           (stats['sent'] + 13262, campaign_id))  # Add previously sent
                conn.commit()
    
    # Final update
    elapsed = time.time() - start_time
    rate = stats['total'] / elapsed if elapsed > 0 else 0
    
    total_sent = stats['sent'] + 13262  # Add previously sent
    final_status = 'completed' if stats['failed'] < stats['total'] * 0.1 else 'completed_with_errors'
    cur.execute("""
        UPDATE campaigns SET status = %s, sent_count = %s, sent_at = NOW() WHERE id = %s
    """, (final_status, total_sent, campaign_id))
    conn.commit()
    
    logger.info(f"")
    logger.info(f"{'='*50}")
    logger.info(f"✅ CAMPAIGN COMPLETE!")
    logger.info(f"📧 This run: Sent {stats['sent']} | Failed {stats['failed']}")
    logger.info(f"📧 Total sent: {total_sent}")
    logger.info(f"⏱️ Time: {elapsed/60:.1f} minutes")
    logger.info(f"🚀 Speed: {rate:.1f} emails/second")
    logger.info(f"{'='*50}")
    
    cur.close()
    conn.close()

if __name__ == '__main__':
    campaign_id = sys.argv[1] if len(sys.argv) > 1 else 'camp_1765784743_058fe64c84'
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    resume_campaign(campaign_id, workers)
