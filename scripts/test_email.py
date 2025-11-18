#!/usr/bin/env python3
"""Quick test for SendBaba SMTP"""
import sys
sys.path.insert(0, '/opt/sendbaba-staging')

from app.smtp.relay_server import send_email_sync
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

print("="*70)
print("🧪 SENDBABA SMTP TEST")
print("="*70)

result = send_email_sync({
    'from': 'hello@sendbaba.com',
    'to': 'ekeminyd@gmail.com',
    'subject': f'✅ SendBaba Working - {datetime.now().strftime("%H:%M:%S")}',
    'html_body': '''
    <html>
    <body style="font-family: Arial; padding: 20px; background: #f5f5f5;">
        <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px;">
            <h1 style="color: #4CAF50;">✅ SendBaba is Working!</h1>
            <p style="font-size: 16px;">Your custom SMTP server successfully delivered this email.</p>
            <div style="background: #f0f0f0; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <strong>Server Details:</strong><br>
                • Hostname: mail.sendbaba.com<br>
                • IP: 156.67.29.186<br>
                • Domain: sendbaba.com<br>
                • Status: Production Ready ✅
            </div>
            <p style="color: #666;">Check email headers for SPF/DKIM authentication status.</p>
        </div>
    </body>
    </html>
    ''',
    'text_body': 'SendBaba test email - Your SMTP server is working!'
})

print("\n" + "="*70)
print("📊 TEST RESULTS")
print("="*70)
print(f"✅ Success:     {result.get('success')}")
print(f"🔒 TLS Used:    {result.get('tls')}")
print(f"🔐 DKIM Signed: {result.get('dkim')}")
print(f"🌐 MX Server:   {result.get('mx_server')}")
print(f"📧 Status:      {result.get('message')}")
print("="*70)

if result.get('success'):
    print("\n🎉 SUCCESS! Email sent to ekeminyd@gmail.com")
    print("📬 Check your Gmail inbox now!")
    print("")
    print("💡 Note: 'Sent plaintext' means TLS fallback (normal for port 25)")
else:
    print("\n❌ FAILED!")
    print(f"Error: {result.get('message')}")
