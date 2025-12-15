#!/usr/bin/env python3
"""
SendBaba Universal Campaign Processor
======================================
System-wide email sending engine for ALL users and ALL campaigns.
Fully dynamic - no hardcoded values.
"""
import psycopg2
import psycopg2.pool
import time
import sys
import os
import threading
import signal
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from collections import defaultdict
import uuid as uuid_module
import socket

# ============================================
# CONFIGURATION (All dynamic, no hardcoding)
# ============================================
class Config:
    # Worker settings - can be adjusted via env vars
    MIN_WORKERS = int(os.environ.get('SENDBABA_MIN_WORKERS', 10))
    MAX_WORKERS = int(os.environ.get('SENDBABA_MAX_WORKERS', 30))
    DEFAULT_WORKERS = int(os.environ.get('SENDBABA_WORKERS', 15))
    
    # Batch settings
    BATCH_SIZE = int(os.environ.get('SENDBABA_BATCH_SIZE', 100))
    
    # Timing
    DELAY_BETWEEN_EMAILS = float(os.environ.get('SENDBABA_DELAY', 0.02))
    QUEUE_CHECK_INTERVAL = 5
    STATS_UPDATE_INTERVAL = 30
    
    # Database - from env or defaults
    DB_POOL_MIN = 5
    DB_POOL_MAX = 20
    DB_CONFIG = {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'database': os.environ.get('DB_NAME', 'emailer'),
        'user': os.environ.get('DB_USER', 'emailer'),
        'password': os.environ.get('DB_PASSWORD', 'SecurePassword123')
    }
    
    # IP Pool - loaded from database or env
    IP_POOL = os.environ.get('SENDBABA_IP_POOL', 
        '38.207.131.28,38.207.131.29,38.207.131.30,38.207.131.31,38.207.131.32,'
        '38.207.131.33,38.207.131.34,38.207.131.35,38.207.131.36,38.207.131.37'
    ).split(',')

# Logging
os.makedirs('/var/log', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/var/log/sendbaba_processor.log')
    ]
)
logger = logging.getLogger('CampaignProcessor')

# Database pool
db_pool = None

def init_db_pool():
    global db_pool
    db_pool = psycopg2.pool.ThreadedConnectionPool(
        Config.DB_POOL_MIN, Config.DB_POOL_MAX, **Config.DB_CONFIG
    )
    logger.info("Database pool initialized")

def get_db():
    return db_pool.getconn()

def release_db(conn):
    db_pool.putconn(conn)

# ============================================
# HELPERS
# ============================================
def validate_email_addr(addr):
    if not addr or '@' not in addr or '.' not in addr:
        return False, addr, 'invalid_format'
    return True, addr.strip().lower(), None

def personalize_content(content, contact):
    """Replace all merge tags with contact data"""
    if not content:
        return content
    
    first = contact.get('first_name') or ''
    last = contact.get('last_name') or ''
    email = contact.get('email') or ''
    full_name = f"{first} {last}".strip()
    
    replacements = {
        '{{first_name}}': first, '{{FIRST_NAME}}': first,
        '{{last_name}}': last, '{{LAST_NAME}}': last,
        '{{email}}': email, '{{EMAIL}}': email,
        '{{name}}': full_name, '{{NAME}}': full_name,
        '*|FNAME|*': first, '*|LNAME|*': last,
        '*|EMAIL|*': email, '*|NAME|*': full_name,
    }
    
    for tag, val in replacements.items():
        content = content.replace(tag, str(val))
    return content

# ============================================
# STATS
# ============================================
class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.sent = 0
        self.failed = 0
        self.skipped = 0
        self.start_time = time.time()
        self.by_campaign = defaultdict(lambda: {'sent': 0, 'failed': 0})
    
    def add(self, campaign_id, status):
        with self.lock:
            if status == 'sent':
                self.sent += 1
                self.by_campaign[campaign_id]['sent'] += 1
            elif status == 'failed':
                self.failed += 1
                self.by_campaign[campaign_id]['failed'] += 1
            else:
                self.skipped += 1
    
    def rate(self):
        with self.lock:
            elapsed = time.time() - self.start_time
            return self.sent / elapsed * 60 if elapsed > 0 else 0
    
    def totals(self):
        with self.lock:
            return {'sent': self.sent, 'failed': self.failed, 'skipped': self.skipped}

stats = Stats()

# ============================================
# IP ROTATION
# ============================================
ip_idx = 0
ip_lock = threading.Lock()

def next_ip():
    global ip_idx
    with ip_lock:
        ip = Config.IP_POOL[ip_idx % len(Config.IP_POOL)]
        ip_idx += 1
        return ip

# ============================================
# RAW SMTP SENDER
# ============================================
def send_raw_smtp(to_addr, subject, html, from_email, from_name, reply_to=None):
    """Send email using raw socket SMTP (no email module dependency)"""
    try:
        ip = next_ip()
        
        # Build message
        boundary = f"----=_Part_{uuid_module.uuid4().hex[:16]}"
        domain = from_email.split('@')[1] if '@' in from_email else 'localhost'
        
        headers = [
            f"From: {from_name} <{from_email}>" if from_name else f"From: {from_email}",
            f"To: {to_addr}",
            f"Subject: {subject}",
            f"Message-ID: <{uuid_module.uuid4().hex}@{domain}>",
            f"Date: {datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S +0000')}",
            "MIME-Version: 1.0",
            f'Content-Type: multipart/alternative; boundary="{boundary}"',
            "X-Mailer: SendBaba/2.0",
        ]
        if reply_to:
            headers.append(f"Reply-To: {reply_to}")
        
        body = "\r\n".join([
            f"--{boundary}",
            "Content-Type: text/html; charset=utf-8",
            "Content-Transfer-Encoding: 7bit",
            "",
            html,
            f"--{boundary}--"
        ])
        
        message = "\r\n".join(headers) + "\r\n\r\n" + body
        
        # SMTP via raw socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30)
        sock.connect((ip, 25))
        
        def recv():
            return sock.recv(4096).decode('utf-8', errors='ignore')
        
        def send_cmd(cmd):
            sock.send((cmd + "\r\n").encode())
            return recv()
        
        recv()  # greeting
        send_cmd(f"EHLO {domain}")
        send_cmd(f"MAIL FROM:<{from_email}>")
        rcpt_resp = send_cmd(f"RCPT TO:<{to_addr}>")
        
        if '250' not in rcpt_resp and '251' not in rcpt_resp:
            sock.close()
            return False, rcpt_resp.strip()
        
        send_cmd("DATA")
        sock.send((message + "\r\n.\r\n").encode())
        data_resp = recv()
        send_cmd("QUIT")
        sock.close()
        
        return '250' in data_resp, None
        
    except Exception as e:
        return False, str(e)

# ============================================
# EMAIL WORKER
# ============================================
def process_email(task):
    """Send a single email"""
    contact, campaign, org_id = task
    campaign_id = campaign['id']
    conn = None
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        to_email = contact['email']
        
        # Validate
        valid, clean_email, err = validate_email_addr(to_email)
        if not valid:
            stats.add(campaign_id, 'failed')
            release_db(conn)
            return 'failed'
        
        # Check if already sent
        cur.execute("""
            SELECT id FROM emails 
            WHERE campaign_id = %s AND to_email = %s 
            AND status IN ('sent', 'sending')
        """, (campaign_id, clean_email))
        
        if cur.fetchone():
            stats.add(campaign_id, 'skipped')
            release_db(conn)
            return 'skipped'
        
        # Personalize
        subject = personalize_content(campaign['subject'], contact)
        html = personalize_content(campaign['html_body'], contact)
        
        # Create email record
        email_id = str(uuid_module.uuid4())
        cur.execute("""
            INSERT INTO emails (
                id, organization_id, campaign_id, to_email, from_email, 
                subject, html_body, status, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'sending', NOW())
            ON CONFLICT (campaign_id, to_email) DO NOTHING
            RETURNING id
        """, (email_id, org_id, campaign_id, clean_email, 
              campaign['from_email'], subject, html))
        
        if not cur.fetchone():
            stats.add(campaign_id, 'skipped')
            conn.commit()
            release_db(conn)
            return 'skipped'
        
        conn.commit()
        
        # Send
        success, error = send_raw_smtp(
            clean_email, subject, html,
            campaign['from_email'],
            campaign.get('from_name'),
            campaign.get('reply_to')
        )
        
        # Update status
        if success:
            cur.execute("""
                UPDATE emails SET status = 'sent', sent_at = NOW() WHERE id = %s
            """, (email_id,))
            stats.add(campaign_id, 'sent')
        else:
            cur.execute("""
                UPDATE emails SET status = 'failed', error_message = %s WHERE id = %s
            """, (str(error)[:255] if error else 'Send failed', email_id))
            stats.add(campaign_id, 'failed')
        
        conn.commit()
        release_db(conn)
        
        time.sleep(Config.DELAY_BETWEEN_EMAILS)
        return 'sent' if success else 'failed'
        
    except Exception as e:
        stats.add(campaign_id, 'failed')
        logger.debug(f"Email error: {e}")
        if conn:
            try:
                release_db(conn)
            except:
                pass
        return 'failed'

# ============================================
# CAMPAIGN MANAGER
# ============================================
class CampaignManager:
    def __init__(self):
        self.campaigns = {}
        self.lock = threading.Lock()
    
    def load_active(self):
        """Load all active campaigns from ALL organizations"""
        conn = get_db()
        cur = conn.cursor()
        
        try:
            # Get all campaigns with status 'sending' or 'queued'
            cur.execute("""
                SELECT id, organization_id, name, from_name, from_email,
                       subject, html_body, text_body, reply_to, total_recipients
                FROM campaigns
                WHERE status IN ('sending', 'queued')
                ORDER BY created_at ASC
            """)
            
            rows = cur.fetchall()
            
            with self.lock:
                current = set()
                for r in rows:
                    cid = r[0]
                    current.add(cid)
                    
                    if cid not in self.campaigns:
                        self.campaigns[cid] = {
                            'id': cid,
                            'org_id': r[1],
                            'name': r[2],
                            'from_name': r[3],
                            'from_email': r[4],
                            'subject': r[5],
                            'html_body': r[6],
                            'text_body': r[7],
                            'reply_to': r[8],
                            'total': r[9] or 0
                        }
                        logger.info(f"📧 Campaign added: {r[2][:40]}... (org: {r[1][:8]})")
                
                # Remove completed
                for cid in list(self.campaigns.keys()):
                    if cid not in current:
                        name = self.campaigns[cid].get('name', cid)[:30]
                        del self.campaigns[cid]
                        logger.info(f"✅ Campaign removed: {name}")
            
            return len(self.campaigns)
        finally:
            release_db(conn)
    
    def get_batch(self, limit):
        """Get batch of unsent emails from ALL active campaigns (fair round-robin)"""
        work = []
        
        with self.lock:
            cids = list(self.campaigns.keys())
        
        if not cids:
            return work
        
        per_campaign = max(10, limit // len(cids))
        
        for cid in cids:
            camp = self.campaigns.get(cid)
            if not camp:
                continue
            
            conn = get_db()
            cur = conn.cursor()
            
            try:
                # Get contacts for this org that haven't been emailed for this campaign
                cur.execute("""
                    SELECT c.id, c.email, c.first_name, c.last_name
                    FROM contacts c
                    WHERE c.organization_id = %s
                    AND c.status = 'active'
                    AND c.email IS NOT NULL
                    AND c.email != ''
                    AND NOT EXISTS (
                        SELECT 1 FROM emails e
                        WHERE e.campaign_id = %s
                        AND e.to_email = c.email
                    )
                    ORDER BY c.created_at
                    LIMIT %s
                """, (camp['org_id'], cid, per_campaign))
                
                for row in cur.fetchall():
                    contact = {
                        'id': row[0],
                        'email': row[1],
                        'first_name': row[2] or '',
                        'last_name': row[3] or ''
                    }
                    work.append((contact, camp, camp['org_id']))
            finally:
                release_db(conn)
        
        return work
    
    def update_campaign_stats(self):
        """Update sent counts for all campaigns"""
        with self.lock:
            cids = list(self.campaigns.keys())
        
        conn = get_db()
        cur = conn.cursor()
        
        try:
            for cid in cids:
                cur.execute("""
                    UPDATE campaigns 
                    SET emails_sent = (
                        SELECT COUNT(*) FROM emails 
                        WHERE campaign_id = %s AND status = 'sent'
                    ),
                    updated_at = NOW()
                    WHERE id = %s
                """, (cid, cid))
            conn.commit()
        finally:
            release_db(conn)
    
    def check_completions(self):
        """Mark completed campaigns"""
        with self.lock:
            cids = list(self.campaigns.keys())
        
        conn = get_db()
        cur = conn.cursor()
        
        try:
            for cid in cids:
                camp = self.campaigns.get(cid)
                if not camp:
                    continue
                
                # Count sent and failed
                cur.execute("""
                    SELECT 
                        COUNT(*) FILTER (WHERE status = 'sent'),
                        COUNT(*) FILTER (WHERE status = 'failed')
                    FROM emails WHERE campaign_id = %s
                """, (cid,))
                sent, failed = cur.fetchone()
                
                # Count remaining
                cur.execute("""
                    SELECT COUNT(*) FROM contacts c
                    WHERE c.organization_id = %s
                    AND c.status = 'active'
                    AND c.email IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1 FROM emails e
                        WHERE e.campaign_id = %s AND e.to_email = c.email
                    )
                """, (camp['org_id'], cid))
                remaining = cur.fetchone()[0]
                
                if remaining == 0:
                    status = 'completed' if failed == 0 else 'completed_with_errors'
                    cur.execute("""
                        UPDATE campaigns 
                        SET status = %s, emails_sent = %s, completed_at = NOW()
                        WHERE id = %s
                    """, (status, sent, cid))
                    logger.info(f"✅ Campaign completed: {camp['name'][:30]} | Sent: {sent} | Failed: {failed}")
            
            conn.commit()
        finally:
            release_db(conn)
    
    def count(self):
        with self.lock:
            return len(self.campaigns)

# ============================================
# MAIN PROCESSOR
# ============================================
class Processor:
    def __init__(self):
        self.running = False
        self.manager = CampaignManager()
    
    def run(self):
        logger.info("=" * 60)
        logger.info("🚀 SendBaba Universal Campaign Processor")
        logger.info(f"⚙️  Workers: {Config.DEFAULT_WORKERS} (max {Config.MAX_WORKERS})")
        logger.info(f"⚙️  IPs: {len(Config.IP_POOL)}")
        logger.info(f"⚙️  Batch: {Config.BATCH_SIZE}")
        logger.info("=" * 60)
        
        init_db_pool()
        self.running = True
        
        last_stats = time.time()
        last_check = time.time()
        
        with ThreadPoolExecutor(max_workers=Config.MAX_WORKERS) as executor:
            while self.running:
                try:
                    # Load campaigns
                    active = self.manager.load_active()
                    
                    if active == 0:
                        time.sleep(Config.QUEUE_CHECK_INTERVAL)
                        continue
                    
                    # Get work batch
                    work = self.manager.get_batch(Config.BATCH_SIZE)
                    
                    if not work:
                        # No pending, check completion
                        if time.time() - last_check > 10:
                            self.manager.check_completions()
                            last_check = time.time()
                        time.sleep(2)
                        continue
                    
                    # Process batch in parallel
                    futures = [executor.submit(process_email, item) for item in work]
                    for f in as_completed(futures):
                        try:
                            f.result()
                        except Exception as e:
                            logger.error(f"Worker error: {e}")
                    
                    # Periodic updates
                    now = time.time()
                    if now - last_stats > Config.STATS_UPDATE_INTERVAL:
                        self.manager.update_campaign_stats()
                        self.manager.check_completions()
                        
                        t = stats.totals()
                        r = stats.rate()
                        logger.info(
                            f"📊 Sent: {t['sent']:,} | Failed: {t['failed']:,} | "
                            f"Rate: {r:.0f}/min | Active: {active}"
                        )
                        last_stats = now
                    
                except Exception as e:
                    logger.error(f"Processor error: {e}")
                    time.sleep(5)
        
        logger.info("🛑 Processor stopped")
    
    def stop(self):
        self.running = False

# ============================================
# ENTRY POINT
# ============================================
processor = None

def handle_signal(sig, frame):
    global processor
    logger.info("Received shutdown signal...")
    if processor:
        processor.stop()
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    processor = Processor()
    processor.run()
