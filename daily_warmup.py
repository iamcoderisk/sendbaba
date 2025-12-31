#!/usr/bin/env python3
"""
DAILY IP WARMUP SCRIPT
======================
Sends warmup emails through ALL IPs to build reputation
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
import random

sys.path.insert(0, '/opt/sendbaba-staging')

# Force IPv4
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _ipv4_getaddrinfo

DB_URL = 'postgresql://emailer:SecurePassword123@localhost:5432/emailer'

# Fresh test emails for warmup rotation
TEST_EMAILS = [
    # Gmail accounts
    'prince.ekeminy@gmail.com',
    'ekeminyd@gmail.com',
    'dekeminiprince@gmail.com',
    'wayofmarcel6@gmail.com',
    'stormscode01@gmail.com',
    'stormscode02@gmail.com',
    'sendbaba.test1@gmail.com',
    'sendbaba.test2@gmail.com',
    'sendbaba.warmup@gmail.com',
    'testmail.sendbaba@gmail.com',
    # Yahoo accounts
    'princeekeminyd@yahoo.com',
    'sendbaba.test@yahoo.com',
    'warmup.sendbaba@yahoo.com',
    # Outlook accounts
    'sendbaba.test@outlook.com',
    'warmup.sendbaba@outlook.com',
    'testsendbaba@hotmail.com',
    # Other providers
    'test@sendbaba.com',
    'warmup@sendbaba.com',
    'hello@sendbaba.com',
    'support@sendbaba.com',
]

def get_db():
    return psycopg2.connect(DB_URL)

def get_mx_servers(domain):
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        mx_records = sorted([(r.preference, str(r.exchange).rstrip('.')) for r in answers])
        return [mx[1] for mx in mx_records[:3]]
    except:
        return []

def get_dkim_key(domain):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT dkim_private_key FROM domains WHERE domain = %s", (domain,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None
    except:
        return None

def send_email(ip_address, hostname, recipient, from_email, from_name, subject, html_body):
    try:
        sender_domain = from_email.split('@')[1]
        recipient_domain = recipient.split('@')[1]
        
        mx_servers = get_mx_servers(recipient_domain)
        if not mx_servers:
            return False, "No MX"
        
        msg = MIMEMultipart('alternative')
        msg['From'] = f"{from_name} <{from_email}>"
        msg['To'] = recipient
        msg['Subject'] = subject
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain=sender_domain)
        msg['X-Mailer'] = 'SendBaba/2.0'
        
        text_body = f"Warmup email from {hostname}"
        msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        # DKIM
        dkim_key = get_dkim_key(sender_domain)
        if dkim_key:
            try:
                import dkim
                sig = dkim.sign(
                    msg.as_bytes(), b'default', sender_domain.encode(),
                    dkim_key.encode(),
                    include_headers=[b'From', b'To', b'Subject', b'Date', b'Message-ID']
                )
                msg['DKIM-Signature'] = sig.decode().replace('DKIM-Signature: ', '')
            except:
                pass
        
        for mx in mx_servers:
            try:
                smtp = smtplib.SMTP(timeout=30)
                smtp.connect(mx, 25, source_address=(ip_address, 0))
                smtp.starttls()
                smtp.sendmail(from_email, recipient, msg.as_bytes())
                smtp.quit()
                return True, mx
            except:
                continue
        
        return False, "MX failed"
    except Exception as e:
        return False, str(e)[:50]

def run_daily_warmup():
    print("=" * 70)
    print("🔥 DAILY IP WARMUP - ALL 24 SERVERS")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("")
    
    conn = get_db()
    cur = conn.cursor()
    
    # Get ekeminyd organization
    cur.execute("""
        SELECT o.id, o.name FROM organizations o
        JOIN users u ON u.organization_id = o.id
        WHERE u.email = 'ekeminyd@gmail.com' LIMIT 1
    """)
    org = cur.fetchone()
    
    if not org:
        print("❌ Organization not found")
        return
    
    org_id, org_name = org
    
    # Get domain
    cur.execute("SELECT domain FROM domains WHERE organization_id = %s AND is_verified = true LIMIT 1", (org_id,))
    domain_row = cur.fetchone()
    domain_name = domain_row[0] if domain_row else 'sendbree.com'
    
    print(f"📧 Organization: {org_name}")
    print(f"🌐 Domain: {domain_name}")
    
    # Get all IPs
    cur.execute("""
        SELECT id, ip_address, hostname, warmup_day, daily_limit, sent_today
        FROM ip_pools WHERE is_active = true
        ORDER BY warmup_day ASC, hostname
    """)
    all_ips = cur.fetchall()
    
    # Calculate emails per IP
    # New IPs (day 1-7): 3 emails each
    # Warming IPs (day 8-29): 2 emails each  
    # Warmed IPs (day 30+): 2 emails each
    
    total_ips = len(all_ips)
    print(f"📊 Total IPs: {total_ips}")
    print("")
    
    total_sent = 0
    total_failed = 0
    results = []
    
    email_index = 0
    
    for ip_row in all_ips:
        ip_id, ip_address, hostname, warmup_day, daily_limit, sent_today = ip_row
        
        # Determine emails to send based on warmup stage
        if warmup_day <= 7:
            emails_count = 3  # New IPs need more warmup
        elif warmup_day <= 29:
            emails_count = 2
        else:
            emails_count = 2
        
        status_icon = "🆕" if warmup_day < 30 else "🔥"
        print(f"\n{status_icon} {hostname} ({ip_address}) - Day {warmup_day}")
        
        ip_sent = 0
        ip_failed = 0
        
        for i in range(emails_count):
            # Rotate through test emails
            recipient = TEST_EMAILS[email_index % len(TEST_EMAILS)]
            email_index += 1
            
            from_email = f"warmup@{domain_name}"
            from_name = "SendBaba"
            
            # Varied subject lines for better warmup
            subjects = [
                f"📧 Daily Update from {hostname}",
                f"🔔 Notification from SendBaba",
                f"✅ System Status Check",
                f"📊 Your Daily Summary",
                f"🌟 Important Information",
            ]
            subject = random.choice(subjects) + f" - {datetime.now().strftime('%H:%M')}"
            
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0;">SendBaba</h1>
                    <p style="color: rgba(255,255,255,0.8); margin: 10px 0 0 0;">Email Infrastructure</p>
                </div>
                <div style="background: #ffffff; padding: 30px; border: 1px solid #e5e7eb;">
                    <h2 style="color: #1f2937;">Server Status Update</h2>
                    <p style="color: #4b5563;">This is a routine warmup email to maintain optimal deliverability.</p>
                    <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                        <tr style="background: #f9fafb;">
                            <td style="padding: 12px; border: 1px solid #e5e7eb;"><strong>Server</strong></td>
                            <td style="padding: 12px; border: 1px solid #e5e7eb;">{hostname}</td>
                        </tr>
                        <tr>
                            <td style="padding: 12px; border: 1px solid #e5e7eb;"><strong>IP Address</strong></td>
                            <td style="padding: 12px; border: 1px solid #e5e7eb;">{ip_address}</td>
                        </tr>
                        <tr style="background: #f9fafb;">
                            <td style="padding: 12px; border: 1px solid #e5e7eb;"><strong>Warmup Day</strong></td>
                            <td style="padding: 12px; border: 1px solid #e5e7eb;">Day {warmup_day}</td>
                        </tr>
                        <tr>
                            <td style="padding: 12px; border: 1px solid #e5e7eb;"><strong>Timestamp</strong></td>
                            <td style="padding: 12px; border: 1px solid #e5e7eb;">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td>
                        </tr>
                    </table>
                    <p style="color: #6b7280; font-size: 14px;">
                        This email confirms that your email server is functioning correctly.
                    </p>
                </div>
                <div style="background: #f9fafb; padding: 20px; border-radius: 0 0 10px 10px; text-align: center;">
                    <p style="color: #9ca3af; font-size: 12px; margin: 0;">
                        Sent via SendBaba Email Infrastructure<br>
                        © 2024 SendBaba. All rights reserved.
                    </p>
                </div>
            </body>
            </html>
            """
            
            print(f"    📤 [{i+1}/{emails_count}] -> {recipient}...", end=" ", flush=True)
            
            success, result = send_email(
                ip_address, hostname, recipient,
                from_email, from_name, subject, html_body
            )
            
            if success:
                print(f"✅ {result}")
                ip_sent += 1
                total_sent += 1
                cur.execute("UPDATE ip_pools SET sent_today = sent_today + 1 WHERE id = %s", (ip_id,))
                conn.commit()
            else:
                print(f"❌ {result}")
                ip_failed += 1
                total_failed += 1
            
            time.sleep(0.5)  # Small delay between sends
        
        status = '✅' if ip_failed == 0 else ('⚠️' if ip_sent > 0 else '❌')
        results.append({
            'hostname': hostname,
            'ip': ip_address,
            'day': warmup_day,
            'sent': ip_sent,
            'failed': ip_failed,
            'status': status
        })
    
    cur.close()
    conn.close()
    
    # Print summary
    print("")
    print("=" * 70)
    print("📊 DAILY WARMUP SUMMARY")
    print("=" * 70)
    print("")
    print(f"{'Server':<25} {'IP':<17} {'Day':<5} {'Sent':<6} {'Fail':<6} {'Status'}")
    print("-" * 70)
    
    for r in results:
        day_str = f"D{r['day']}"
        print(f"{r['hostname']:<25} {r['ip']:<17} {day_str:<5} {r['sent']:<6} {r['failed']:<6} {r['status']}")
    
    print("-" * 70)
    success_rate = (total_sent / (total_sent + total_failed) * 100) if (total_sent + total_failed) > 0 else 0
    
    print("")
    print(f"✅ Total Sent: {total_sent}")
    print(f"❌ Total Failed: {total_failed}")
    print(f"📊 Success Rate: {success_rate:.1f}%")
    print("")
    print(f"⏰ Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Recommendations
    print("")
    print("💡 RECOMMENDATIONS:")
    if total_failed > 0:
        print("   - Check failed IPs for PTR/rDNS issues")
        print("   - Verify firewall allows outbound port 25")
    print("   - Run this script daily to maintain warmup")
    print("   - Increase volume gradually over 30 days")
    print("=" * 70)

if __name__ == '__main__':
    run_daily_warmup()
