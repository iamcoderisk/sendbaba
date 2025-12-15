#!/usr/bin/env python3
"""
SendBaba High-Speed Campaign Sender
Uses existing relay_server with parallel workers
"""
import psycopg2
import time
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import queue

sys.path.insert(0, '/opt/sendbaba-staging')

from app.smtp.relay_server import send_email_sync
from app.services.email_tracker import prepare_email_for_tracking

# ============================================
# CONFIGURATION - ADJUST THESE FOR SPEED
# ============================================
CONCURRENT_WORKERS = 15        # Parallel senders (safe for 10 IPs)
BATCH_SIZE = 200               # Emails per batch fetch
DELAY_BETWEEN_EMAILS = 0.02    # 20ms between emails per worker
STATS_UPDATE_INTERVAL = 30     # Update campaign stats every 30 sec

# Database config
DB_CONFIG = {
    'host': 'localhost',
    'database': 'emailer', 
    'user': 'emailer',
    'password': 'SecurePassword123'
}

# Thread-safe stats
stats = {
    'sent': 0,
    'failed': 0,
    'skipped': 0,
    'start_time': None,
    'lock': threading.Lock()
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def validate_and_fix_email(email):
    try:
        from app.utils.email_validator import validate_email
        is_valid, corrected, reason = validate_email(email, check_mx=False, auto_fix=True)
        return is_valid, corrected, reason
    except:
        if not email or '@' not in email:
            return False, email, 'invalid_format'
        return True, email.strip().lower(), None

def personalize(content, contact):
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
        '*|EMAIL|*': contact.get('email', ''),
    }
    for tag, value in replacements.items():
        content = content.replace(tag, str(value or ''))
    return content

def send_single_email(args):
    """Send a single email - worker function"""
    contact, campaign_data, org_id = args
    conn = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        campaign_id, from_name, from_email, subject, html_body, text_body, reply_to = campaign_data
        
        email_addr = contact['email']
        contact_id = contact['id']
        
        # Validate email
        is_valid, corrected_email, reason = validate_and_fix_email(email_addr)
        if not is_valid:
            with stats['lock']:
                stats['failed'] += 1
            return ('failed', f'Invalid email: {reason}')
        
        # Check if already sent
        cursor.execute("""
            SELECT id FROM emails 
            WHERE campaign_id = %s AND to_email = %s AND status = 'sent'
        """, (campaign_id, corrected_email))
        
        if cursor.fetchone():
            with stats['lock']:
                stats['skipped'] += 1
            return ('skipped', 'Already sent')
        
        # Personalize content
        personalized_subject = personalize(subject, contact)
        personalized_html = personalize(html_body, contact)
        personalized_text = personalize(text_body, contact) if text_body else None
        
        # Generate email ID
        import uuid
        email_id = str(uuid.uuid4())
        
        # Add tracking
        try:
            tracked_html, tracking_id = prepare_email_for_tracking(
                personalized_html, email_id, campaign_id, org_id, corrected_email
            )
        except:
            tracked_html = personalized_html
        
        # Create email record
        cursor.execute("""
            INSERT INTO emails (id, organization_id, campaign_id, contact_id, 
                               to_email, from_email, from_name, subject,
                               html_content, text_content, reply_to, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'sending', NOW())
            ON CONFLICT (campaign_id, to_email) DO NOTHING
            RETURNING id
        """, (email_id, org_id, campaign_id, contact_id, corrected_email,
              from_email, from_name, personalized_subject, tracked_html,
              personalized_text, reply_to))
        
        result = cursor.fetchone()
        if not result:
            with stats['lock']:
                stats['skipped'] += 1
            conn.commit()
            return ('skipped', 'Duplicate')
        
        conn.commit()
        
        # SEND THE EMAIL using existing relay_server
        success = send_email_sync(
            to_email=corrected_email,
            subject=personalized_subject,
            html_content=tracked_html,
            text_content=personalized_text,
            from_email=from_email,
            from_name=from_name,
            reply_to=reply_to,
            organization_id=org_id,
            email_id=email_id
        )
        
        # Update status
        if success:
            cursor.execute("""
                UPDATE emails SET status = 'sent', sent_at = NOW() WHERE id = %s
            """, (email_id,))
            with stats['lock']:
                stats['sent'] += 1
            status = 'sent'
        else:
            cursor.execute("""
                UPDATE emails SET status = 'failed', error_message = 'Send failed' WHERE id = %s
            """, (email_id,))
            with stats['lock']:
                stats['failed'] += 1
            status = 'failed'
        
        conn.commit()
        
        # Small delay
        time.sleep(DELAY_BETWEEN_EMAILS)
        
        return (status, None)
        
    except Exception as e:
        with stats['lock']:
            stats['failed'] += 1
        return ('failed', str(e))
    finally:
        if conn:
            conn.close()

def print_progress():
    """Print progress stats"""
    with stats['lock']:
        total = stats['sent'] + stats['failed'] + stats['skipped']
        elapsed = time.time() - stats['start_time'] if stats['start_time'] else 1
        rate = stats['sent'] / elapsed * 60 if elapsed > 0 else 0
        
        print(f"\r⚡ Sent: {stats['sent']:,} | Failed: {stats['failed']:,} | "
              f"Skipped: {stats['skipped']:,} | Rate: {rate:.0f}/min | "
              f"Workers: {CONCURRENT_WORKERS}  ", end='', flush=True)

def update_campaign_stats(campaign_id):
    """Update campaign statistics in database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE campaigns SET 
                emails_sent = (SELECT COUNT(*) FROM emails WHERE campaign_id = %s AND status = 'sent'),
                updated_at = NOW()
            WHERE id = %s
        """, (campaign_id, campaign_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"\n[WARN] Stats update failed: {e}")

def run_campaign(campaign_id):
    """Main campaign runner with parallel workers"""
    print(f"🚀 SendBaba HIGH-SPEED Campaign Sender")
    print(f"=" * 60)
    print(f"⚙️  Workers: {CONCURRENT_WORKERS}")
    print(f"⚙️  Batch Size: {BATCH_SIZE}")
    print(f"⚙️  Delay: {DELAY_BETWEEN_EMAILS*1000:.0f}ms per email")
    print(f"=" * 60)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get campaign info
    cursor.execute("""
        SELECT id, organization_id, name, from_name, from_email,
               subject, html_body, text_body, reply_to, total_recipients
        FROM campaigns WHERE id = %s
    """, (campaign_id,))
    
    row = cursor.fetchone()
    if not row:
        print(f"❌ Campaign not found: {campaign_id}")
        return
    
    campaign_id, org_id, name, from_name, from_email, subject, html_body, text_body, reply_to, total_recipients = row
    campaign_data = (campaign_id, from_name, from_email, subject, html_body, text_body, reply_to)
    
    print(f"📧 Campaign: {name[:50]}")
    print(f"📊 Total Recipients: {total_recipients:,}")
    
    # Get already sent count
    cursor.execute("""
        SELECT COUNT(*) FROM emails WHERE campaign_id = %s AND status = 'sent'
    """, (campaign_id,))
    already_sent = cursor.fetchone()[0]
    print(f"✅ Already Sent: {already_sent:,}")
    print(f"⏳ Remaining: ~{total_recipients - already_sent:,}")
    print(f"=" * 60)
    
    # Update campaign status
    cursor.execute("UPDATE campaigns SET status = 'sending' WHERE id = %s", (campaign_id,))
    conn.commit()
    
    # Get all contacts for this campaign's list
    cursor.execute("""
        SELECT cl.list_id FROM campaign_lists cl WHERE cl.campaign_id = %s
    """, (campaign_id,))
    list_ids = [r[0] for r in cursor.fetchall()]
    
    if not list_ids:
        print("❌ No contact lists found for campaign")
        return
    
    stats['start_time'] = time.time()
    last_stats_update = time.time()
    
    # Process in batches
    offset = 0
    
    with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as executor:
        while True:
            # Fetch batch of contacts not yet sent
            cursor.execute("""
                SELECT DISTINCT c.id, c.email, c.first_name, c.last_name
                FROM contacts c
                JOIN contact_list_members clm ON c.id = clm.contact_id
                WHERE clm.list_id = ANY(%s)
                AND c.status = 'active'
                AND c.email IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM emails e 
                    WHERE e.campaign_id = %s 
                    AND e.to_email = c.email 
                    AND e.status IN ('sent', 'sending')
                )
                ORDER BY c.id
                LIMIT %s
            """, (list_ids, campaign_id, BATCH_SIZE))
            
            contacts = cursor.fetchall()
            
            if not contacts:
                print("\n\n✅ All contacts processed!")
                break
            
            # Prepare work items
            work_items = []
            for c in contacts:
                contact = {
                    'id': c[0],
                    'email': c[1],
                    'first_name': c[2] or '',
                    'last_name': c[3] or ''
                }
                work_items.append((contact, campaign_data, org_id))
            
            # Submit batch to thread pool
            futures = [executor.submit(send_single_email, item) for item in work_items]
            
            # Wait for batch to complete
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception as e:
                    print(f"\n[ERROR] Worker exception: {e}")
            
            # Print progress
            print_progress()
            
            # Periodic stats update
            if time.time() - last_stats_update > STATS_UPDATE_INTERVAL:
                update_campaign_stats(campaign_id)
                last_stats_update = time.time()
    
    # Final update
    update_campaign_stats(campaign_id)
    
    # Mark complete if all done
    cursor.execute("""
        SELECT COUNT(*) FROM emails 
        WHERE campaign_id = %s AND status IN ('queued', 'pending', 'sending')
    """, (campaign_id,))
    remaining = cursor.fetchone()[0]
    
    if remaining == 0:
        cursor.execute("""
            UPDATE campaigns SET status = 'completed', completed_at = NOW() WHERE id = %s
        """, (campaign_id,))
    
    conn.commit()
    conn.close()
    
    # Final stats
    elapsed = time.time() - stats['start_time']
    print(f"\n\n{'=' * 60}")
    print(f"🏁 CAMPAIGN COMPLETE")
    print(f"{'=' * 60}")
    print(f"✅ Sent: {stats['sent']:,}")
    print(f"❌ Failed: {stats['failed']:,}")
    print(f"⏭️  Skipped: {stats['skipped']:,}")
    print(f"⏱️  Time: {elapsed/60:.1f} minutes")
    print(f"⚡ Avg Rate: {stats['sent']/elapsed*60:.0f} emails/min")
    print(f"{'=' * 60}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        # Auto-find active campaign
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name FROM campaigns 
            WHERE status = 'sending' 
            ORDER BY created_at DESC LIMIT 1
        """)
        result = cursor.fetchone()
        conn.close()
        
        if result:
            campaign_id = result[0]
            print(f"📧 Found active campaign: {result[1][:50]}")
        else:
            print("Usage: python3 fast_campaign_sender.py <campaign_id>")
            sys.exit(1)
    else:
        campaign_id = sys.argv[1]
    
    run_campaign(campaign_id)
