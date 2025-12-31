#!/usr/bin/env python3
"""
TURBO SENDER - Maximum Speed Email Delivery
============================================
Optimized for 100+ emails/second across 24 servers
Uses connection pooling, parallel threads, and smart IP rotation
"""
import os
import sys
import time
import uuid
import logging
import smtplib
import dns.resolver
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, local
from queue import Queue
import psycopg2
from psycopg2 import pool
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
import redis
import random

sys.path.insert(0, '/opt/sendbaba-staging')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION - TUNED FOR MAXIMUM SPEED
# =============================================================================
MAX_WORKERS = 100          # 100 parallel threads
BATCH_SIZE = 1000          # Process 1000 emails at a time
SMTP_TIMEOUT = 15          # 15 second timeout (faster failure)
CONNECTION_POOL_SIZE = 50  # Reuse DB connections
PROGRESS_INTERVAL = 500    # Log every 500 emails

# Force IPv4 only (no IPv6 PTR issues)
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _ipv4_getaddrinfo

# =============================================================================
# DATABASE CONNECTION POOL
# =============================================================================
db_pool = psycopg2.pool.ThreadedConnectionPool(
    10, CONNECTION_POOL_SIZE,
    host='localhost',
    database='emailer',
    user='emailer',
    password='SecurePassword123'
)

# Redis for IP rotation tracking
redis_client = redis.Redis(
    host='localhost', 
    port=6379, 
    password='SendBabaRedis2024!',
    decode_responses=True
)

# =============================================================================
# IP ROTATION WITH LOAD BALANCING
# =============================================================================
class IPRotator:
    """Smart IP rotation across all servers with load balancing"""
    
    def __init__(self):
        self.lock = Lock()
        self.ip_index = 0
        self.ips = []
        self.load_ips()
    
    def load_ips(self):
        """Load active IPs from database"""
        conn = db_pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT ip_address, hostname, daily_limit, sent_today
                FROM ip_pools 
                WHERE is_active = true
                ORDER BY 
                    CASE WHEN warmup_day >= 30 THEN 0 ELSE 1 END,
                    (daily_limit - sent_today) DESC
            """)
            self.ips = cur.fetchall()
            cur.close()
            logger.info(f"Loaded {len(self.ips)} IPs for rotation")
        finally:
            db_pool.putconn(conn)
    
    def get_next_ip(self):
        """Get next available IP using round-robin with capacity check"""
        with self.lock:
            if not self.ips:
                self.load_ips()
            
            # Try each IP until we find one with capacity
            for _ in range(len(self.ips)):
                ip_data = self.ips[self.ip_index % len(self.ips)]
                self.ip_index += 1
                
                ip_address = ip_data[0]
                daily_limit = ip_data[2]
                
                # Check Redis for current count
                key = f"ip_sent:{ip_address}:{time.strftime('%Y%m%d')}"
                current = int(redis_client.get(key) or 0)
                
                if current < daily_limit:
                    # Increment counter
                    redis_client.incr(key)
                    redis_client.expire(key, 86400)  # 24 hour expiry
                    return ip_address, ip_data[1]  # IP, hostname
            
            # All IPs at capacity - use random
            ip_data = random.choice(self.ips)
            return ip_data[0], ip_data[1]

ip_rotator = IPRotator()

# =============================================================================
# MX CACHE
# =============================================================================
mx_cache = {}
mx_cache_lock = Lock()

def get_mx_servers(domain):
    """Get MX servers with caching"""
    with mx_cache_lock:
        if domain in mx_cache:
            return mx_cache[domain]
    
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        mx_records = sorted([(r.preference, str(r.exchange).rstrip('.')) for r in answers])
        servers = [mx[1] for mx in mx_records[:3]]
        
        with mx_cache_lock:
            mx_cache[domain] = servers
        return servers
    except:
        return []

# =============================================================================
# DKIM CACHE
# =============================================================================
dkim_cache = {}
dkim_cache_lock = Lock()

def get_dkim_key(domain):
    """Get DKIM key with caching"""
    with dkim_cache_lock:
        if domain in dkim_cache:
            return dkim_cache[domain]
    
    conn = db_pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT dkim_private_key FROM domains WHERE name = %s AND dkim_private_key IS NOT NULL",
            (domain,)
        )
        row = cur.fetchone()
        key = row[0] if row else None
        cur.close()
        
        with dkim_cache_lock:
            dkim_cache[domain] = key
        return key
    finally:
        db_pool.putconn(conn)

# =============================================================================
# FAST EMAIL SENDER
# =============================================================================
def send_single_email(email_data):
    """Send single email with optimizations"""
    try:
        recipient = email_data.get('to', '').strip()
        sender = email_data.get('from', '').strip()
        
        if not recipient or '@' not in recipient:
            return {'success': False, 'error': 'Invalid recipient'}
        
        recipient_domain = recipient.split('@')[1]
        sender_domain = sender.split('@')[1] if '@' in sender else 'sendbaba.com'
        
        # Get MX servers (cached)
        mx_servers = get_mx_servers(recipient_domain)
        if not mx_servers:
            return {'success': False, 'error': 'No MX'}
        
        # Get sending IP
        source_ip, source_hostname = ip_rotator.get_next_ip()
        
        # Build message
        msg = MIMEMultipart('alternative')
        msg['From'] = f"{email_data.get('from_name', 'SendBaba')} <{sender}>"
        msg['To'] = recipient
        msg['Subject'] = email_data.get('subject', '')
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain=sender_domain)
        msg['X-Mailer'] = 'SendBaba/2.0'
        
        # Body
        html_body = email_data.get('html_body', '')
        text_body = email_data.get('text_body', '') or html_body.replace('<', ' <').replace('>', '> ')
        
        if text_body:
            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        if html_body:
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        # DKIM signing (cached key)
        dkim_key = get_dkim_key(sender_domain)
        if dkim_key:
            try:
                import dkim
                sig = dkim.sign(
                    msg.as_bytes(),
                    b'default',
                    sender_domain.encode(),
                    dkim_key.encode(),
                    include_headers=[b'From', b'To', b'Subject', b'Date', b'Message-ID']
                )
                msg['DKIM-Signature'] = sig.decode().replace('DKIM-Signature: ', '')
            except:
                pass
        
        # Send via SMTP
        for mx in mx_servers:
            try:
                with smtplib.SMTP(mx, 25, timeout=SMTP_TIMEOUT, source_address=(source_ip, 0)) as smtp:
                    smtp.starttls()
                    smtp.sendmail(sender, recipient, msg.as_bytes())
                    return {'success': True, 'ip': source_ip, 'mx': mx}
            except Exception as e:
                continue
        
        return {'success': False, 'error': 'All MX failed', 'ip': source_ip}
    
    except Exception as e:
        return {'success': False, 'error': str(e)}

# =============================================================================
# TURBO CAMPAIGN SENDER
# =============================================================================
class TurboSender:
    """High-speed campaign sender"""
    
    def __init__(self, campaign_id, max_workers=MAX_WORKERS):
        self.campaign_id = campaign_id
        self.max_workers = max_workers
        self.stats = {'sent': 0, 'failed': 0, 'total': 0}
        self.stats_lock = Lock()
        self.start_time = None
    
    def update_stats(self, success):
        with self.stats_lock:
            if success:
                self.stats['sent'] += 1
            else:
                self.stats['failed'] += 1
    
    def send_email_task(self, task):
        """Task for thread pool"""
        email_data, email_id = task
        result = send_single_email(email_data)
        self.update_stats(result.get('success', False))
        return email_id, result
    
    def run(self):
        """Execute campaign at maximum speed"""
        self.start_time = time.time()
        
        conn = db_pool.getconn()
        cur = conn.cursor()
        
        try:
            # Get campaign
            cur.execute("""
                SELECT id, organization_id, name, from_name, from_email,
                       subject, html_body, text_body, reply_to
                FROM campaigns WHERE id = %s
            """, (self.campaign_id,))
            row = cur.fetchone()
            
            if not row:
                logger.error("Campaign not found!")
                return
            
            campaign = {
                'id': row[0], 'org_id': row[1], 'name': row[2],
                'from_name': row[3] or 'SendBaba', 
                'from_email': row[4],
                'subject': row[5] or '',
                'html_body': row[6] or '',
                'text_body': row[7] or '',
                'reply_to': row[8]
            }
            
            # Validate
            if not campaign['html_body']:
                logger.error("Campaign has no HTML body!")
                return
            
            # Update status
            cur.execute(
                "UPDATE campaigns SET status = 'sending', started_at = NOW() WHERE id = %s",
                (self.campaign_id,)
            )
            conn.commit()
            
            # Get pending contacts
            cur.execute("""
                SELECT c.id, c.email, c.first_name, c.last_name
                FROM contacts c
                WHERE c.organization_id = %s
                AND c.status = 'active'
                AND c.email IS NOT NULL
                AND c.email != ''
                AND NOT EXISTS (
                    SELECT 1 FROM emails e 
                    WHERE e.campaign_id = %s AND e.to_email = c.email
                )
                ORDER BY c.id
            """, (campaign['org_id'], self.campaign_id))
            
            contacts = cur.fetchall()
            self.stats['total'] = len(contacts)
            
            logger.info(f"")
            logger.info(f"{'='*60}")
            logger.info(f"🚀 TURBO SENDER - {campaign['name']}")
            logger.info(f"{'='*60}")
            logger.info(f"📧 Contacts: {self.stats['total']}")
            logger.info(f"⚡ Workers: {self.max_workers}")
            logger.info(f"🔄 IP Pool: {len(ip_rotator.ips)} servers")
            logger.info(f"{'='*60}")
            
            if self.stats['total'] == 0:
                logger.info("✅ No pending emails!")
                cur.execute(
                    "UPDATE campaigns SET status = 'completed' WHERE id = %s",
                    (self.campaign_id,)
                )
                conn.commit()
                return
            
            # Prepare tasks
            tasks = []
            for contact in contacts:
                email_id = str(uuid.uuid4())
                first_name = contact[2] or ''
                last_name = contact[3] or ''
                
                # Personalize
                subject = campaign['subject'].replace('{{first_name}}', first_name).replace('{{last_name}}', last_name)
                html_body = campaign['html_body'].replace('{{first_name}}', first_name).replace('{{last_name}}', last_name)
                
                # Pre-insert email record
                cur.execute("""
                    INSERT INTO emails (id, campaign_id, organization_id, from_email, to_email,
                                       sender, recipient, subject, html_body, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'sending', NOW())
                """, (email_id, self.campaign_id, campaign['org_id'], 
                      campaign['from_email'], contact[1],
                      campaign['from_email'], contact[1],
                      subject, html_body))
                
                email_data = {
                    'from': campaign['from_email'],
                    'from_name': campaign['from_name'],
                    'to': contact[1],
                    'subject': subject,
                    'html_body': html_body,
                    'text_body': campaign['text_body'],
                }
                tasks.append((email_data, email_id))
            
            conn.commit()
            logger.info(f"📝 Prepared {len(tasks)} email tasks")
            
            # PARALLEL EXECUTION
            logger.info(f"⚡ Starting parallel send...")
            
            results = []
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {executor.submit(self.send_email_task, task): task for task in tasks}
                
                completed = 0
                for future in as_completed(futures):
                    email_id, result = future.result()
                    results.append((email_id, result))
                    completed += 1
                    
                    # Progress logging
                    if completed % PROGRESS_INTERVAL == 0:
                        elapsed = time.time() - self.start_time
                        rate = completed / elapsed
                        remaining = self.stats['total'] - completed
                        eta = remaining / rate / 60 if rate > 0 else 0
                        
                        logger.info(
                            f"📊 {completed:,}/{self.stats['total']:,} | "
                            f"{rate:.1f}/sec | "
                            f"ETA: {eta:.1f}min | "
                            f"✅{self.stats['sent']:,} ❌{self.stats['failed']:,}"
                        )
                        
                        # Update campaign progress
                        cur.execute(
                            "UPDATE campaigns SET sent_count = %s WHERE id = %s",
                            (self.stats['sent'], self.campaign_id)
                        )
                        conn.commit()
            
            # Batch update email statuses
            logger.info(f"📝 Updating email statuses...")
            for email_id, result in results:
                status = 'sent' if result.get('success') else 'failed'
                error = result.get('error', '')[:500] if result.get('error') else None
                cur.execute(
                    "UPDATE emails SET status = %s, error_message = %s, sent_at = NOW() WHERE id = %s",
                    (status, error, email_id)
                )
            conn.commit()
            
            # Final stats
            elapsed = time.time() - self.start_time
            rate = self.stats['total'] / elapsed if elapsed > 0 else 0
            
            final_status = 'completed' if self.stats['failed'] < self.stats['total'] * 0.1 else 'completed_with_errors'
            cur.execute("""
                UPDATE campaigns SET status = %s, sent_count = %s, sent_at = NOW() WHERE id = %s
            """, (final_status, self.stats['sent'], self.campaign_id))
            conn.commit()
            
            logger.info(f"")
            logger.info(f"{'='*60}")
            logger.info(f"✅ CAMPAIGN COMPLETE!")
            logger.info(f"{'='*60}")
            logger.info(f"📧 Sent: {self.stats['sent']:,}")
            logger.info(f"❌ Failed: {self.stats['failed']:,}")
            logger.info(f"⏱️  Time: {elapsed/60:.1f} minutes")
            logger.info(f"🚀 Speed: {rate:.1f} emails/second")
            logger.info(f"🚀 Speed: {rate*60:.0f} emails/minute")
            logger.info(f"{'='*60}")
            
        except Exception as e:
            logger.error(f"Campaign error: {e}")
            import traceback
            traceback.print_exc()
            cur.execute("UPDATE campaigns SET status = 'failed' WHERE id = %s", (self.campaign_id,))
            conn.commit()
        finally:
            cur.close()
            db_pool.putconn(conn)


def main():
    if len(sys.argv) < 2:
        print("Usage: python turbo_sender.py <campaign_id> [max_workers]")
        sys.exit(1)
    
    campaign_id = sys.argv[1]
    max_workers = int(sys.argv[2]) if len(sys.argv) > 2 else MAX_WORKERS
    
    sender = TurboSender(campaign_id, max_workers)
    sender.run()


if __name__ == '__main__':
    main()
