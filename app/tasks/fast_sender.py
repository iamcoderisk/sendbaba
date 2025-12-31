"""
High-Speed Parallel Email Sender
=================================
Optimized for sending 100k+ emails in under 1 hour
Uses ThreadPoolExecutor for parallel SMTP connections
"""
import os
import sys
import time
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

sys.path.insert(0, '/opt/sendbaba-staging')

import psycopg2
from app.smtp.relay_server import send_email_sync

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Configuration for speed
MAX_WORKERS = 50  # Parallel threads
BATCH_SIZE = 100  # Emails per batch update
GMAIL_DELAY = 0.05  # 50ms delay for Gmail (minimal)

# Thread-safe counters
stats_lock = Lock()
stats = {'sent': 0, 'failed': 0, 'total': 0}

def get_db():
    return psycopg2.connect(
        host='localhost',
        database='emailer', 
        user='emailer',
        password='SecurePassword123'
    )

def send_single(email_data):
    """Send a single email - thread-safe"""
    global stats
    try:
        result = send_email_sync(email_data)
        success = result.get('success', False)
        
        with stats_lock:
            if success:
                stats['sent'] += 1
            else:
                stats['failed'] += 1
        
        return {
            'email_id': email_data.get('email_id'),
            'to': email_data.get('to'),
            'success': success,
            'error': result.get('error', '')
        }
    except Exception as e:
        with stats_lock:
            stats['failed'] += 1
        return {
            'email_id': email_data.get('email_id'),
            'to': email_data.get('to'),
            'success': False,
            'error': str(e)
        }

def fast_send_campaign(campaign_id: str, max_workers: int = MAX_WORKERS):
    """
    Send campaign emails in parallel
    Target: 109k emails in 50 minutes = ~36 emails/second
    """
    global stats
    stats = {'sent': 0, 'failed': 0, 'total': 0}
    
    conn = get_db()
    cursor = conn.cursor()
    
    start_time = time.time()
    
    try:
        # Get campaign
        cursor.execute("""
            SELECT id, organization_id, name, from_name, from_email,
                   subject, html_body, text_body, reply_to
            FROM campaigns WHERE id = %s
        """, (campaign_id,))
        
        row = cursor.fetchone()
        if not row:
            return {'error': 'Campaign not found'}
        
        campaign = {
            'id': row[0], 'organization_id': row[1], 'name': row[2],
            'from_name': row[3], 'from_email': row[4], 'subject': row[5],
            'html_body': row[6], 'text_body': row[7], 'reply_to': row[8]
        }
        
        # Update status
        cursor.execute("UPDATE campaigns SET status = 'sending', started_at = NOW() WHERE id = %s", (campaign_id,))
        conn.commit()
        
        # Get ALL contacts
        cursor.execute("""
            SELECT id, email, first_name, last_name
            FROM contacts
            WHERE organization_id = %s AND status = 'active'
            AND email IS NOT NULL AND email != ''
            ORDER BY id
        """, (campaign['organization_id'],))
        
        contacts = cursor.fetchall()
        stats['total'] = len(contacts)
        
        logger.info(f"🚀 FAST SEND: {campaign['name']} - {stats['total']} contacts with {max_workers} workers")
        
        # Prepare all email data
        email_tasks = []
        for contact in contacts:
            email_id = str(uuid.uuid4())
            
            # Simple personalization
            subject = campaign['subject'].replace('{{first_name}}', contact[2] or '').replace('{{last_name}}', contact[3] or '')
            html_body = campaign['html_body'].replace('{{first_name}}', contact[2] or '').replace('{{last_name}}', contact[3] or '')
            
            email_data = {
                'email_id': email_id,
                'contact_id': contact[0],
                'from': f"{campaign['from_name']} <{campaign['from_email']}>",
                'to': contact[1],
                'subject': subject,
                'html_body': html_body,
                'text_body': campaign['text_body'],
                'org_id': campaign['organization_id'],
                'campaign_id': campaign_id
            }
            email_tasks.append(email_data)
        
        # Pre-insert all emails as 'sending'
        logger.info(f"📝 Pre-inserting {len(email_tasks)} email records...")
        for task in email_tasks:
            cursor.execute("""
                INSERT INTO emails (id, campaign_id, organization_id, from_email, to_email, subject, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'sending', NOW())
            """, (task['email_id'], campaign_id, task['org_id'], campaign['from_email'], task['to'], task['subject']))
        conn.commit()
        
        # PARALLEL SENDING
        logger.info(f"⚡ Starting parallel send with {max_workers} workers...")
        results = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(send_single, task): task for task in email_tasks}
            
            completed = 0
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                completed += 1
                
                # Progress update every 1000 emails
                if completed % 1000 == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed
                    remaining = (stats['total'] - completed) / rate if rate > 0 else 0
                    logger.info(f"📊 Progress: {completed}/{stats['total']} ({rate:.1f}/sec) - ETA: {remaining/60:.1f} min")
        
        # Batch update email statuses
        logger.info(f"📝 Updating email statuses...")
        for result in results:
            status = 'sent' if result['success'] else 'failed'
            error = result.get('error', '')[:500] if result.get('error') else None
            cursor.execute("""
                UPDATE emails SET status = %s, error_message = %s, sent_at = NOW() WHERE id = %s
            """, (status, error, result['email_id']))
        conn.commit()
        
        # Final stats
        elapsed = time.time() - start_time
        rate = stats['total'] / elapsed if elapsed > 0 else 0
        
        # Update campaign
        final_status = 'completed' if stats['failed'] < stats['total'] * 0.1 else 'completed_with_errors'
        cursor.execute("""
            UPDATE campaigns SET status = %s, sent_count = %s, sent_at = NOW() WHERE id = %s
        """, (final_status, stats['sent'], campaign_id))
        conn.commit()
        
        logger.info(f"✅ COMPLETE: {stats['sent']} sent, {stats['failed']} failed in {elapsed:.1f}s ({rate:.1f}/sec)")
        
        return {
            'success': True,
            'sent': stats['sent'],
            'failed': stats['failed'],
            'total': stats['total'],
            'time_seconds': elapsed,
            'rate_per_second': rate
        }
        
    except Exception as e:
        logger.error(f"Campaign error: {e}")
        cursor.execute("UPDATE campaigns SET status = 'failed' WHERE id = %s", (campaign_id,))
        conn.commit()
        return {'error': str(e)}
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    # Test
    import sys
    if len(sys.argv) > 1:
        result = fast_send_campaign(sys.argv[1])
        print(result)
