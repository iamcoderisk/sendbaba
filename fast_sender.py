#!/usr/bin/env python3
"""
SendBaba Universal Fast Sender
Correct function signature for send_email_sync
"""
import psycopg2
import psycopg2.pool
import sys
import time
import threading
import signal
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add SMTP server path
sys.path.insert(0, '/opt/sendbaba-smtp')
from app.smtp.relay_server import send_email_sync

# ============ CONFIG ============
WORKERS = 20
BATCH_SIZE = 150
DELAY = 0.015

DB = {
    'host': 'localhost',
    'database': 'emailer', 
    'user': 'emailer',
    'password': 'SecurePassword123'
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler('/var/log/sendbaba_sender.log')]
)
log = logging.getLogger('Sender')

pool = None

def init():
    global pool
    pool = psycopg2.pool.ThreadedConnectionPool(5, 25, **DB)

def get_conn():
    return pool.getconn()

def put_conn(c):
    pool.putconn(c)

class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.sent = self.failed = self.skip = 0
        self.start = time.time()
    
    def add(self, s):
        with self.lock:
            if s == 'sent': self.sent += 1
            elif s == 'failed': self.failed += 1
            else: self.skip += 1
    
    def rate(self):
        e = time.time() - self.start
        return self.sent / e * 60 if e > 0 else 0
    
    def __str__(self):
        return f"Sent:{self.sent:,} Fail:{self.failed:,} Skip:{self.skip:,} Rate:{self.rate():.0f}/min"

stats = Stats()

def personalize(t, c):
    if not t: return t
    for k, v in {
        '{{first_name}}': c.get('first_name') or '',
        '{{last_name}}': c.get('last_name') or '',
        '{{email}}': c.get('email') or '',
        '{{FIRST_NAME}}': c.get('first_name') or '',
        '{{LAST_NAME}}': c.get('last_name') or '',
        '*|FNAME|*': c.get('first_name') or '',
        '*|LNAME|*': c.get('last_name') or '',
    }.items():
        t = t.replace(k, v)
    return t

def send_one(contact, camp, org_id):
    import uuid
    c = get_conn()
    cur = c.cursor()
    cid = camp['id']
    email = contact['email'].strip().lower()
    
    try:
        # Check if already sent
        cur.execute("SELECT 1 FROM emails WHERE campaign_id=%s AND to_email=%s AND status IN ('sent','sending')", (cid, email))
        if cur.fetchone():
            stats.add('skip')
            put_conn(c)
            return
        
        # Personalize
        subj = personalize(camp['subject'], contact)
        html = personalize(camp['html_body'], contact)
        eid = str(uuid.uuid4())
        
        # Insert email record
        cur.execute("""
            INSERT INTO emails (id, organization_id, campaign_id, to_email, from_email, subject, html_body, status, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'sending',NOW())
            ON CONFLICT (campaign_id, to_email) DO NOTHING RETURNING id
        """, (eid, org_id, cid, email, camp['from_email'], subj, html))
        
        if not cur.fetchone():
            stats.add('skip')
            c.commit()
            put_conn(c)
            return
        c.commit()
        
        # Send using correct dict format
        email_data = {
            'from': camp['from_email'],
            'from_name': camp.get('from_name') or '',
            'to': email,
            'subject': subj,
            'html_body': html,
            'text_body': '',
            'reply_to': camp.get('reply_to') or ''
        }
        
        result = send_email_sync(email_data)
        ok = result.get('success', False)
        
        # Update status
        if ok:
            cur.execute("UPDATE emails SET status='sent', sent_at=NOW() WHERE id=%s", (eid,))
            stats.add('sent')
        else:
            err_msg = result.get('message', 'Send failed')[:255]
            cur.execute("UPDATE emails SET status='failed', error_message=%s WHERE id=%s", (err_msg, eid))
            stats.add('failed')
        
        c.commit()
        time.sleep(DELAY)
        
    except Exception as e:
        stats.add('failed')
        log.debug(f"Error: {e}")
    finally:
        put_conn(c)

def run():
    log.info("=" * 60)
    log.info("🚀 SendBaba Fast Sender - Universal")
    log.info(f"⚙️  Workers:{WORKERS} Batch:{BATCH_SIZE}")
    log.info("=" * 60)
    
    init()
    c = get_conn()
    cur = c.cursor()
    last_log = time.time()
    
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        while True:
            try:
                # Get active campaigns
                cur.execute("""
                    SELECT id, organization_id, name, from_name, from_email, subject, html_body, reply_to
                    FROM campaigns WHERE status IN ('sending','queued') ORDER BY created_at
                """)
                camps = cur.fetchall()
                
                if not camps:
                    time.sleep(5)
                    continue
                
                work = []
                for cp in camps:
                    camp = {
                        'id': cp[0], 'org_id': cp[1], 'name': cp[2], 
                        'from_name': cp[3], 'from_email': cp[4], 
                        'subject': cp[5], 'html_body': cp[6], 'reply_to': cp[7]
                    }
                    
                    # Get unsent contacts
                    cur.execute("""
                        SELECT id, email, first_name, last_name FROM contacts
                        WHERE organization_id=%s AND status='active' AND email IS NOT NULL AND email!=''
                        AND NOT EXISTS (SELECT 1 FROM emails WHERE campaign_id=%s AND to_email=contacts.email)
                        LIMIT %s
                    """, (camp['org_id'], camp['id'], BATCH_SIZE // len(camps)))
                    
                    for r in cur.fetchall():
                        work.append(({'id':r[0],'email':r[1],'first_name':r[2] or '','last_name':r[3] or ''}, camp, camp['org_id']))
                
                if not work:
                    # Check completion
                    for cp in camps:
                        cur.execute("""
                            SELECT COUNT(*) FROM contacts WHERE organization_id=%s AND status='active'
                            AND NOT EXISTS (SELECT 1 FROM emails WHERE campaign_id=%s AND to_email=contacts.email)
                        """, (cp[1], cp[0]))
                        if cur.fetchone()[0] == 0:
                            cur.execute("""
                                UPDATE campaigns 
                                SET status='completed', 
                                    emails_sent=(SELECT COUNT(*) FROM emails WHERE campaign_id=%s AND status='sent'), 
                                    completed_at=NOW() 
                                WHERE id=%s
                            """, (cp[0], cp[0]))
                            log.info(f"✅ Completed: {cp[2][:40]}")
                    c.commit()
                    time.sleep(2)
                    continue
                
                # Process batch in parallel
                futures = [ex.submit(send_one, *w) for w in work]
                for f in as_completed(futures):
                    pass
                
                # Update campaign stats
                for cp in camps:
                    cur.execute("""
                        UPDATE campaigns 
                        SET emails_sent=(SELECT COUNT(*) FROM emails WHERE campaign_id=%s AND status='sent'), 
                            updated_at=NOW() 
                        WHERE id=%s
                    """, (cp[0], cp[0]))
                c.commit()
                
                # Log progress
                if time.time() - last_log > 30:
                    log.info(f"📊 {stats} | Campaigns:{len(camps)}")
                    last_log = time.time()
                    
            except Exception as e:
                log.error(f"Error: {e}")
                time.sleep(5)

def stop(s, f):
    log.info("Stopping...")
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    run()
