#!/usr/bin/env python3
"""
IP WARMUP TEST SCRIPT
=====================
Sends test emails through ALL IPs to verify they work
Sends synchronously to each IP to ensure proper testing
"""
import os
import sys
import time
import smtplib
import socket
import psycopg2
import dns.resolver
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from datetime import datetime

sys.path.insert(0, '/opt/sendbaba-staging')

# Force IPv4
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _ipv4_getaddrinfo

# Configuration
DB_URL = 'postgresql://emailer:SecurePassword123@localhost:5432/emailer'
TEST_RECIPIENTS = [
    'prince.ekeminy@gmail.com',
    'ekeminyd@gmail.com',
    'princeekeminyd@yahoo.com',
    'dekeminiprince@gmail.com',
    'wayofmarcel6@gmail.com'
]

def get_db():
    return psycopg2.connect(DB_URL)

def get_mx_servers(domain):
    """Get MX servers for domain"""
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        mx_records = sorted([(r.preference, str(r.exchange).rstrip('.')) for r in answers])
        return [mx[1] for mx in mx_records[:3]]
    except Exception as e:
        print(f"  ❌ MX lookup failed: {e}")
        return []

def get_dkim_key(domain):
    """Get DKIM key from database"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT dkim_private_key FROM domains WHERE name = %s", (domain,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None

def send_test_email(ip_address, hostname, recipient, from_email, from_name, subject, html_body):
    """Send a single test email through specific IP"""
    try:
        sender_domain = from_email.split('@')[1]
        recipient_domain = recipient.split('@')[1]
        
        # Get MX servers
        mx_servers = get_mx_servers(recipient_domain)
        if not mx_servers:
            return False, "No MX records"
        
        # Build message
        msg = MIMEMultipart('alternative')
        msg['From'] = f"{from_name} <{from_email}>"
        msg['To'] = recipient
        msg['Subject'] = subject
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain=sender_domain)
        msg['X-Mailer'] = 'SendBaba/2.0'
        msg['X-SendBaba-IP'] = ip_address
        msg['X-SendBaba-Server'] = hostname
        
        # Add body
        text_body = f"Test email from {hostname} ({ip_address})"
        msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        # DKIM signing
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
            except Exception as e:
                print(f"    ⚠️ DKIM failed: {e}")
        
        # Send via SMTP using specific source IP
        for mx in mx_servers:
            try:
                # Create socket bound to specific IP
                smtp = smtplib.SMTP(timeout=30)
                smtp.connect(mx, 25, source_address=(ip_address, 0))
                smtp.starttls()
                smtp.sendmail(from_email, recipient, msg.as_bytes())
                smtp.quit()
                return True, mx
            except Exception as e:
                continue
        
        return False, "All MX failed"
    
    except Exception as e:
        return False, str(e)

def run_warmup_test():
    """Run warmup test for all IPs"""
    print("=" * 70)
    print("🔥 IP WARMUP TEST - SENDING THROUGH ALL SERVERS")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("")
    
    # Get organization info for ekeminyd@gmail.com
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT o.id, o.name, d.name as domain, d.id as domain_id
        FROM organizations o
        JOIN users u ON u.organization_id = o.id
        LEFT JOIN domains d ON d.organization_id = o.id AND d.is_verified = true
        WHERE u.email = 'ekeminyd@gmail.com'
        LIMIT 1
    """)
    org_row = cur.fetchone()
    
    if not org_row:
        print("❌ Organization not found for ekeminyd@gmail.com")
        return
    
    org_id, org_name, domain_name, domain_id = org_row
    print(f"📧 Organization: {org_name}")
    print(f"🌐 Domain: {domain_name}")
    print("")
    
    # Get all IPs
    cur.execute("""
        SELECT id, ip_address, hostname, warmup_day, daily_limit, sent_today, is_active
        FROM ip_pools
        WHERE is_active = true
        ORDER BY hostname
    """)
    all_ips = cur.fetchall()
    
    print(f"📊 Total IPs to test: {len(all_ips)}")
    print("")
    
    # Stats
    total_sent = 0
    total_failed = 0
    results = []
    
    # Send 2-3 emails through each IP
    emails_per_ip = 3 if len(all_ips) < 20 else 2
    
    print(f"📤 Sending {emails_per_ip} emails per IP ({len(all_ips) * emails_per_ip} total)")
    print("-" * 70)
    
    for ip_row in all_ips:
        ip_id, ip_address, hostname, warmup_day, daily_limit, sent_today, is_active = ip_row
        
        print(f"\n🖥️  {hostname} ({ip_address}) - Day {warmup_day}")
        
        ip_sent = 0
        ip_failed = 0
        
        for i in range(emails_per_ip):
            recipient = TEST_RECIPIENTS[i % len(TEST_RECIPIENTS)]
            
            from_email = f"test@{domain_name}" if domain_name else "test@sendbree.com"
            from_name = "SendBaba Warmup Test"
            subject = f"🔥 Warmup Test from {hostname} - {datetime.now().strftime('%H:%M:%S')}"
            
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2 style="color: #2563eb;">🔥 IP Warmup Test</h2>
                <p>This is a warmup test email to verify IP deliverability.</p>
                <table style="border-collapse: collapse; margin: 20px 0;">
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; background: #f5f5f5;"><strong>Server:</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{hostname}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; background: #f5f5f5;"><strong>IP Address:</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{ip_address}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; background: #f5f5f5;"><strong>Warmup Day:</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">Day {warmup_day}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; background: #f5f5f5;"><strong>Sent Today:</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{sent_today} / {daily_limit}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; background: #f5f5f5;"><strong>Timestamp:</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td>
                    </tr>
                </table>
                <p style="color: #666; font-size: 12px;">
                    Sent via SendBaba Email Infrastructure<br>
                    This email confirms that {hostname} is properly configured.
                </p>
            </body>
            </html>
            """
            
            print(f"    📤 Sending to {recipient}...", end=" ", flush=True)
            
            success, result = send_test_email(
                ip_address, hostname, recipient,
                from_email, from_name, subject, html_body
            )
            
            if success:
                print(f"✅ via {result}")
                ip_sent += 1
                total_sent += 1
                
                # Update sent_today in database
                cur.execute(
                    "UPDATE ip_pools SET sent_today = sent_today + 1 WHERE id = %s",
                    (ip_id,)
                )
                conn.commit()
            else:
                print(f"❌ {result}")
                ip_failed += 1
                total_failed += 1
            
            # Small delay between sends
            time.sleep(0.5)
        
        results.append({
            'hostname': hostname,
            'ip': ip_address,
            'warmup_day': warmup_day,
            'sent': ip_sent,
            'failed': ip_failed,
            'status': '✅' if ip_failed == 0 else ('⚠️' if ip_sent > 0 else '❌')
        })
    
    cur.close()
    conn.close()
    
    # Print summary
    print("")
    print("=" * 70)
    print("📊 WARMUP TEST SUMMARY")
    print("=" * 70)
    print("")
    print(f"{'Server':<25} {'IP':<17} {'Day':<5} {'Sent':<6} {'Failed':<8} {'Status'}")
    print("-" * 70)
    
    for r in results:
        print(f"{r['hostname']:<25} {r['ip']:<17} {r['warmup_day']:<5} {r['sent']:<6} {r['failed']:<8} {r['status']}")
    
    print("-" * 70)
    print(f"{'TOTAL':<25} {'':<17} {'':<5} {total_sent:<6} {total_failed:<8}")
    print("")
    print(f"✅ Successfully sent: {total_sent}")
    print(f"❌ Failed: {total_failed}")
    print(f"📊 Success rate: {(total_sent/(total_sent+total_failed)*100):.1f}%")
    print("")
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

if __name__ == '__main__':
    run_warmup_test()
