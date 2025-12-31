"""
TURBO DISTRIBUTED SENDER
========================
Splits large campaigns across ALL Celery workers for maximum speed.
Target: 10,000+ emails/minute
"""
import os
import sys
import uuid
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from celery import shared_task

logger = logging.getLogger(__name__)

# Add parent path
sys.path.insert(0, '/opt/sendbaba-staging')

from app.tasks.email_tasks import (
    get_db_connection, personalize, validate_and_fix_email, 
    is_gmail, prepare_email_for_tracking, update_progress
)
from app.smtp.relay_server import send_email_sync


@shared_task(bind=True, max_retries=3)
def send_chunk(self, chunk_data):
    """Send a chunk of emails - runs on ANY available worker"""
    campaign_id = chunk_data['campaign_id']
    campaign = chunk_data['campaign']
    contacts = chunk_data['contacts']
    chunk_id = chunk_data['chunk_id']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    stats = {'sent': 0, 'failed': 0, 'skipped': 0}
    
    logger.info(f"🚀 Chunk {chunk_id}: Processing {len(contacts)} contacts")
    
    THREADS = 500  # 100 threads per chunk
    
    def send_one(contact_data):
        """Send single email"""
        t_conn = get_db_connection()
        t_cursor = t_conn.cursor()
        result = {'sent': 0, 'failed': 0, 'skipped': 0}
        
        try:
            contact = {
                'id': contact_data[0],
                'email': contact_data[1],
                'first_name': contact_data[2],
                'last_name': contact_data[3]
            }
            
            is_valid, to_email, _ = validate_and_fix_email((contact['email'] or '').strip())
            if not is_valid:
                result['skipped'] = 1
                return result
            
            subject = personalize(campaign['subject'], contact)
            html_body = personalize(campaign['html_body'], contact)
            text_body = personalize(campaign.get('text_body', ''), contact) if campaign.get('text_body') else ''
            
            email_id = str(uuid.uuid4())
            tracking_id = None
            
            if html_body:
                try:
                    html_body, tracking_id = prepare_email_for_tracking(
                        html_body=html_body, email_id=email_id,
                        org_id=campaign['organization_id'],
                        campaign_id=campaign_id, recipient=to_email
                    )
                except:
                    pass
            
            # Insert record
            try:
                t_cursor.execute("""
                    INSERT INTO emails (id, organization_id, campaign_id, from_email, to_email,
                        sender, recipient, subject, html_body, text_body, status, tracking_id, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'sending',%s,NOW()) ON CONFLICT DO NOTHING
                """, (email_id, campaign['organization_id'], campaign_id, campaign['from_email'],
                      to_email, campaign['from_email'], to_email, subject, html_body, text_body, tracking_id))
                t_conn.commit()
            except:
                t_conn.rollback()
            
            # Send
            try:
                res = send_email_sync({
                    'from': campaign['from_email'],
                    'from_name': campaign['from_name'],
                    'to': to_email,
                    'subject': subject,
                    'html_body': html_body,
                    'text_body': text_body,
                    'reply_to': campaign.get('reply_to', '')
                })
                
                if res.get('success'):
                    t_cursor.execute("UPDATE emails SET status='sent', sent_at=NOW() WHERE id=%s", (email_id,))
                    result['sent'] = 1
                else:
                    t_cursor.execute("UPDATE emails SET status='failed', error_message=%s WHERE id=%s", 
                                    (res.get('message', 'Error')[:500], email_id))
                    result['failed'] = 1
            except Exception as e:
                t_cursor.execute("UPDATE emails SET status='failed', error_message=%s WHERE id=%s", (str(e)[:500], email_id))
                result['failed'] = 1
            
            t_conn.commit()
        except Exception as e:
            result['failed'] = 1
        finally:
            try:
                t_cursor.close()
                t_conn.close()
            except:
                pass
        
        return result
    
    # Execute with thread pool
    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = [executor.submit(send_one, c) for c in contacts]
        for future in as_completed(futures):
            try:
                r = future.result(timeout=60)
                stats['sent'] += r.get('sent', 0)
                stats['failed'] += r.get('failed', 0)
                stats['skipped'] += r.get('skipped', 0)
            except:
                stats['failed'] += 1
    
    # Update campaign count
    cursor.execute("UPDATE campaigns SET sent_count = sent_count + %s WHERE id = %s", (stats['sent'], campaign_id))
    conn.commit()
    
    logger.info(f"✅ Chunk {chunk_id} done: {stats['sent']} sent, {stats['failed']} failed")
    
    cursor.close()
    conn.close()
    
    return stats


def launch_turbo_campaign(campaign_id: str, chunk_size: int = 2000):
    """Launch campaign in TURBO mode - distributes across all workers"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get campaign
    cursor.execute("""
        SELECT id, organization_id, name, from_name, from_email, subject,
               COALESCE(html_content, html_body, '') as html_body, text_body, reply_to
        FROM campaigns WHERE id = %s
    """, (campaign_id,))
    row = cursor.fetchone()
    
    if not row:
        return {'success': False, 'error': 'Campaign not found'}
    
    campaign = {
        'id': row[0], 'organization_id': row[1], 'name': row[2],
        'from_name': row[3], 'from_email': row[4], 'subject': row[5],
        'html_body': row[6], 'text_body': row[7], 'reply_to': row[8]
    }
    
    # Get contacts
    cursor.execute("""
        SELECT id, email, first_name, last_name FROM contacts
        WHERE organization_id = %s AND status = 'active'
    """, (campaign['organization_id'],))
    contacts = cursor.fetchall()
    
    total = len(contacts)
    logger.info(f"🚀 TURBO MODE: {total} contacts, chunk_size={chunk_size}")
    
    # Update campaign status
    cursor.execute("UPDATE campaigns SET status='sending', started_at=NOW(), sent_count=0 WHERE id=%s", (campaign_id,))
    conn.commit()
    
    # Split into chunks and dispatch to workers
    chunks = [contacts[i:i+chunk_size] for i in range(0, total, chunk_size)]
    
    logger.info(f"📦 Dispatching {len(chunks)} chunks to workers...")
    
    for i, chunk in enumerate(chunks):
        send_chunk.delay({
            'campaign_id': campaign_id,
            'campaign': campaign,
            'contacts': chunk,
            'chunk_id': i + 1
        })
    
    cursor.close()
    conn.close()
    
    return {
        'success': True,
        'campaign_id': campaign_id,
        'total_contacts': total,
        'chunks': len(chunks),
        'chunk_size': chunk_size
    }
