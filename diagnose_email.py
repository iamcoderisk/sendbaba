import sys
sys.path.insert(0, '/opt/sendbaba-staging')

from app import create_app, db
from sqlalchemy import text
import dns.resolver
import socket

app = create_app()

print("\n" + "="*60)
print("📧 EMAIL DELIVERY DIAGNOSTIC REPORT")
print("="*60)

with app.app_context():
    # 1. Check recent emails
    print("\n1️⃣  RECENT EMAIL STATUS:")
    print("-" * 60)
    
    result = db.session.execute(text("""
        SELECT 
            id, sender, recipient, status, 
            error_message, created_at, sent_at
        FROM emails 
        ORDER BY created_at DESC 
        LIMIT 10
    """))
    
    emails = result.fetchall()
    
    if not emails:
        print("❌ No emails found in database")
    else:
        for email in emails:
            status_icon = "✅" if email[3] == "sent" else "⏳" if email[3] == "queued" else "❌"
            print(f"\n{status_icon} ID: {email[0][:8]}...")
            print(f"   From: {email[1]}")
            print(f"   To: {email[2]}")
            print(f"   Status: {email[3]}")
            print(f"   Created: {email[5]}")
            if email[4]:
                print(f"   ❌ Error: {email[4][:100]}")
    
    # 2. Check domains
    print("\n\n2️⃣  DOMAIN CONFIGURATION:")
    print("-" * 60)
    
    result = db.session.execute(text("""
        SELECT domain_name, dns_verified, dkim_public_key
        FROM domains
        LIMIT 5
    """))
    
    domains = result.fetchall()
    
    if not domains:
        print("❌ No domains configured!")
        print("   → Add a domain at /dashboard/domains")
    else:
        for domain in domains:
            verified_icon = "✅" if domain[1] else "⚠️"
            print(f"\n{verified_icon} {domain[0]}")
            print(f"   DNS Verified: {domain[1]}")
            print(f"   DKIM Key: {'Present' if domain[2] else 'Missing'}")
    
    # 3. Check DNS records
    print("\n\n3️⃣  DNS VERIFICATION:")
    print("-" * 60)
    
    if domains:
        test_domain = domains[0][0]
        print(f"\nTesting: {test_domain}")
        
        # Check MX records
        try:
            mx_records = dns.resolver.resolve(test_domain, 'MX')
            print(f"✅ MX Records found:")
            for mx in mx_records:
                print(f"   → {mx.exchange} (priority: {mx.preference})")
        except Exception as e:
            print(f"❌ MX Records: Not found")
        
        # Check SPF
        try:
            txt_records = dns.resolver.resolve(test_domain, 'TXT')
            spf_found = False
            for txt in txt_records:
                txt_str = str(txt).strip('"')
                if 'v=spf1' in txt_str:
                    spf_found = True
                    print(f"✅ SPF Record: {txt_str[:80]}...")
            if not spf_found:
                print(f"❌ SPF Record: Not found")
        except Exception as e:
            print(f"❌ SPF Record: Not found")
    
    # 4. Server configuration
    print("\n\n4️⃣  SERVER CONFIGURATION:")
    print("-" * 60)
    
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        print(f"✅ Hostname: {hostname}")
        print(f"✅ Server IP: {ip}")
    except Exception as e:
        print(f"❌ Server info error: {e}")
    
    # 5. Worker status
    print("\n\n5️⃣  WORKER QUEUE:")
    print("-" * 60)
    
    result = db.session.execute(text("""
        SELECT status, COUNT(*) as count
        FROM emails
        WHERE created_at >= NOW() - INTERVAL '1 hour'
        GROUP BY status
    """))
    
    queue_stats = result.fetchall()
    
    for stat in queue_stats:
        print(f"   {stat[0]}: {stat[1]}")

print("\n" + "="*60)
print("END OF DIAGNOSTIC REPORT")
print("="*60 + "\n")
