"""
AGGRESSIVE BULK SENDER - Maximum Speed
Target: 80,000 emails in 10 minutes = 8,000/min = 133/sec
"""
import psycopg2
import psycopg2.pool
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import uuid
import sys
sys.path.insert(0, '/opt/sendbaba-staging')
from app.smtp.relay_server import send_email_sync
from app.tasks.email_tasks import personalize, validate_and_fix_email, prepare_email_for_tracking

# Database pool for maximum connections
DB_POOL = psycopg2.pool.ThreadedConnectionPool(
    50, 200,
    host='localhost', database='emailer', 
    user='emailer', password='SecurePassword123'
)

CAMPAIGN_ID = 'camp_1765985767_4dbffc3ec7'
MAX_THREADS = 1000  # Maximum parallel threads
BATCH_SIZE = 5000   # Process in batches

def get_campaign():
    conn = DB_POOL.getconn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, organization_id, name, from_name, from_email, subject,
               COALESCE(html_content, html_body, '') as html_body, text_body, reply_to
        FROM campaigns WHERE id = %s
    """, (CAMPAIGN_ID,))
    row = cur.fetchone()
    cur.close()
    DB_POOL.putconn(conn)
    return {
        'id': row[0], 'organization_id': row[1], 'name': row[2],
        'from_name': row[3], 'from_email': row[4], 'subject': row[5],
        'html_body': row[6], 'text_body': row[7], 'reply_to': row[8]
    }

def get_unsent_contacts(limit=5000):
    conn = DB_POOL.getconn()
    cur = conn.cursor()
    # Get contacts that haven't been emailed yet
    cur.execute("""
        SELECT c.id, c.email, c.first_name, c.last_name 
        FROM contacts c
        WHERE c.organization_id = (SELECT organization_id FROM campaigns WHERE id = %s)
        AND c.status = 'active'
        AND NOT EXISTS (
            SELECT 1 FROM emails e 
            WHERE e.campaign_id = %s 
            AND e.to_email = c.email
        )
        LIMIT %s
    """, (CAMPAIGN_ID, CAMPAIGN_ID, limit))
    contacts = cur.fetchall()
    cur.close()
    DB_POOL.putconn(conn)
    return contacts

def send_one(args):
    contact, campaign = args
    conn = DB_POOL.getconn()
    cur = conn.cursor()
    result = {'sent': 0, 'failed': 0}
    
    try:
        email_addr = (contact[1] or '').strip()
        is_valid, to_email, _ = validate_and_fix_email(email_addr)
        if not is_valid:
            DB_POOL.putconn(conn)
            return {'sent': 0, 'failed': 0, 'skipped': 1}
        
        contact_dict = {'id': contact[0], 'email': contact[1], 'first_name': contact[2], 'last_name': contact[3]}
        subject = personalize(campaign['subject'], contact_dict)
        html_body = personalize(campaign['html_body'], contact_dict)
        
        email_id = str(uuid.uuid4())
        tracking_id = None
        try:
            html_body, tracking_id = prepare_email_for_tracking(
                html_body=html_body, email_id=email_id,
                org_id=campaign['organization_id'],
                campaign_id=CAMPAIGN_ID, recipient=to_email
            )
        except:
            pass
        
        # Insert record
        cur.execute("""
            INSERT INTO emails (id, organization_id, campaign_id, from_email, to_email,
                sender, recipient, subject, html_body, status, tracking_id, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'sending',%s,NOW()) ON CONFLICT DO NOTHING
        """, (email_id, campaign['organization_id'], CAMPAIGN_ID, campaign['from_email'],
              to_email, campaign['from_email'], to_email, subject, html_body, tracking_id))
        conn.commit()
        
        # Send
        res = send_email_sync({
            'from': campaign['from_email'],
            'from_name': campaign['from_name'],
            'to': to_email,
            'subject': subject,
            'html_body': html_body,
            'reply_to': campaign.get('reply_to', '')
        })
        
        if res.get('success'):
            cur.execute("UPDATE emails SET status='sent', sent_at=NOW() WHERE id=%s", (email_id,))
            result['sent'] = 1
        else:
            cur.execute("UPDATE emails SET status='failed', error_message=%s WHERE id=%s", 
                       (res.get('message', 'Error')[:200], email_id))
            result['failed'] = 1
        conn.commit()
    except Exception as e:
        result['failed'] = 1
    finally:
        cur.close()
        DB_POOL.putconn(conn)
    
    return result

def main():
    print("🚀 AGGRESSIVE BULK SENDER STARTING...")
    campaign = get_campaign()
    print(f"📧 Campaign: {campaign['name']}")
    
    total_sent = 0
    total_failed = 0
    start_time = time.time()
    batch_num = 0
    
    while True:
        batch_num += 1
        contacts = get_unsent_contacts(BATCH_SIZE)
        
        if not contacts:
            print("✅ All contacts processed!")
            break
        
        print(f"\n📦 Batch {batch_num}: Processing {len(contacts)} contacts with {MAX_THREADS} threads...")
        batch_start = time.time()
        
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            futures = [executor.submit(send_one, (c, campaign)) for c in contacts]
            batch_sent = 0
            batch_failed = 0
            
            for future in as_completed(futures):
                try:
                    r = future.result(timeout=30)
                    batch_sent += r.get('sent', 0)
                    batch_failed += r.get('failed', 0)
                except:
                    batch_failed += 1
        
        total_sent += batch_sent
        total_failed += batch_failed
        batch_time = time.time() - batch_start
        total_time = time.time() - start_time
        rate = (total_sent + total_failed) / total_time * 60 if total_time > 0 else 0
        
        print(f"   ✅ Batch done in {batch_time:.1f}s | Sent: {batch_sent} | Failed: {batch_failed}")
        print(f"   📊 TOTAL: {total_sent} sent, {total_failed} failed | Speed: {rate:.0f}/min")
    
    total_time = time.time() - start_time
    print(f"\n🏁 COMPLETED in {total_time/60:.1f} minutes")
    print(f"   Total Sent: {total_sent}")
    print(f"   Total Failed: {total_failed}")
    print(f"   Average Speed: {(total_sent+total_failed)/total_time*60:.0f} emails/min")

if __name__ == '__main__':
    main()
