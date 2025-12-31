"""
SendBaba Mail Helper Functions
Login notifications, email templates, client detection
"""
import re
from datetime import datetime


def get_client_info(request):
    """Extract client information from request for login notifications"""
    
    # Get IP address
    ip = request.headers.get('X-Forwarded-For', request.headers.get('X-Real-IP', request.remote_addr))
    if ip and ',' in ip:
        ip = ip.split(',')[0].strip()
    
    # Get user agent
    user_agent = request.headers.get('User-Agent', 'Unknown')
    
    # Parse browser
    browser = 'Unknown Browser'
    if 'Firefox' in user_agent:
        match = re.search(r'Firefox/(\d+)', user_agent)
        browser = f"Firefox {match.group(1) if match else ''}"
    elif 'Chrome' in user_agent and 'Edg' not in user_agent:
        match = re.search(r'Chrome/(\d+)', user_agent)
        browser = f"Chrome {match.group(1) if match else ''}"
    elif 'Safari' in user_agent and 'Chrome' not in user_agent:
        match = re.search(r'Version/(\d+)', user_agent)
        browser = f"Safari {match.group(1) if match else ''}"
    elif 'Edg' in user_agent:
        match = re.search(r'Edg/(\d+)', user_agent)
        browser = f"Edge {match.group(1) if match else ''}"
    elif 'MSIE' in user_agent or 'Trident' in user_agent:
        browser = 'Internet Explorer'
    
    # Parse OS/Device
    device = 'Unknown Device'
    if 'Windows NT 10' in user_agent:
        device = 'Windows 10/11'
    elif 'Windows NT' in user_agent:
        device = 'Windows'
    elif 'Mac OS X' in user_agent:
        device = 'macOS'
    elif 'iPhone' in user_agent:
        device = 'iPhone'
    elif 'iPad' in user_agent:
        device = 'iPad'
    elif 'Android' in user_agent:
        if 'Mobile' in user_agent:
            device = 'Android Phone'
        else:
            device = 'Android Tablet'
    elif 'Linux' in user_agent:
        device = 'Linux'
    
    # Get location from IP
    location = 'Unknown Location'
    try:
        import urllib.request
        import json
        geo_url = f'http://ip-api.com/json/{ip}?fields=city,country,regionName'
        with urllib.request.urlopen(geo_url, timeout=3) as response:
            geo_data = json.loads(response.read().decode())
            if geo_data.get('city'):
                location = f"{geo_data.get('city', '')}, {geo_data.get('regionName', '')}, {geo_data.get('country', '')}"
            elif geo_data.get('country'):
                location = geo_data.get('country', 'Unknown')
    except:
        location = 'Location unavailable'
    
    # Format datetime
    now = datetime.now()
    datetime_str = now.strftime('%B %d, %Y at %I:%M %p')
    
    return {
        'ip': ip or 'Unknown',
        'browser': browser,
        'device': device,
        'location': location,
        'datetime': datetime_str,
        'user_agent': user_agent
    }


def send_login_notification(mailbox, login_info):
    """Send login notification email to recovery email"""
    try:
        from app.smtp.relay_server import send_email_sync
        
        recovery_email = mailbox.get('recovery_email')
        if not recovery_email:
            print(f"No recovery email for {mailbox.get('email')}, skipping login notification")
            return False
        
        name = mailbox.get('name') or mailbox.get('email', '').split('@')[0]
        email = mailbox.get('email')
        
        html_body = f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f3f4f6;">
    <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
        
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #f97316 0%, #ea580c 100%); border-radius: 20px 20px 0 0; padding: 30px; text-align: center;">
            <div style="background: rgba(255,255,255,0.2); display: inline-block; padding: 14px; border-radius: 14px; margin-bottom: 16px;">
                <span style="font-size: 36px;">🔔</span>
            </div>
            <h1 style="margin: 0; color: white; font-size: 24px; font-weight: 700;">New Login Detected</h1>
        </div>
        
        <!-- Content -->
        <div style="background: white; border-radius: 0 0 20px 20px; padding: 30px; box-shadow: 0 10px 40px rgba(0,0,0,0.1);">
            
            <p style="color: #374151; font-size: 16px; line-height: 1.6; margin: 0 0 20px;">
                Hi <strong style="color: #f97316;">{name}</strong>,
            </p>
            
            <p style="color: #6b7280; font-size: 15px; line-height: 1.6; margin: 0 0 24px;">
                We noticed a new sign-in to your SendBaba Mail account. If this was you, you can safely ignore this email.
            </p>
            
            <!-- Login Details Box -->
            <div style="background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border: 2px solid #fbbf24; border-radius: 16px; padding: 24px; margin-bottom: 24px;">
                <h3 style="margin: 0 0 16px; color: #92400e; font-size: 16px;">
                    🔐 Login Details
                </h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 10px 0; border-bottom: 1px dashed #fbbf24; color: #78716c; font-size: 14px; width: 35%;">📧 Account</td>
                        <td style="padding: 10px 0; border-bottom: 1px dashed #fbbf24; color: #1f2937; font-size: 14px; font-weight: 600;">{email}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px 0; border-bottom: 1px dashed #fbbf24; color: #78716c; font-size: 14px;">📅 Date & Time</td>
                        <td style="padding: 10px 0; border-bottom: 1px dashed #fbbf24; color: #1f2937; font-size: 14px;">{login_info['datetime']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px 0; border-bottom: 1px dashed #fbbf24; color: #78716c; font-size: 14px;">🌍 Location</td>
                        <td style="padding: 10px 0; border-bottom: 1px dashed #fbbf24; color: #1f2937; font-size: 14px;">{login_info['location']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px 0; border-bottom: 1px dashed #fbbf24; color: #78716c; font-size: 14px;">🌐 IP Address</td>
                        <td style="padding: 10px 0; border-bottom: 1px dashed #fbbf24; color: #1f2937; font-size: 14px; font-family: 'Courier New', monospace;">{login_info['ip']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px 0; border-bottom: 1px dashed #fbbf24; color: #78716c; font-size: 14px;">💻 Device</td>
                        <td style="padding: 10px 0; border-bottom: 1px dashed #fbbf24; color: #1f2937; font-size: 14px;">{login_info['device']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px 0; color: #78716c; font-size: 14px;">🌐 Browser</td>
                        <td style="padding: 10px 0; color: #1f2937; font-size: 14px;">{login_info['browser']}</td>
                    </tr>
                </table>
            </div>
            
            <!-- Warning Box -->
            <div style="background: linear-gradient(135deg, #fef2f2 0%, #fecaca 100%); border: 2px solid #f87171; border-radius: 12px; padding: 20px; margin-bottom: 24px;">
                <p style="margin: 0; color: #991b1b; font-size: 14px; line-height: 1.6;">
                    <strong>⚠️ Wasn't you?</strong><br>
                    If you didn't sign in, your account may be compromised. Please reset your password immediately.
                </p>
            </div>
            
            <!-- Action Buttons -->
            <div style="text-align: center;">
                <a href="https://mail.sendbaba.com/settings" style="display: inline-block; background: linear-gradient(135deg, #f97316, #ea580c); color: white; text-decoration: none; padding: 14px 28px; border-radius: 10px; font-weight: 600; font-size: 14px; margin: 5px;">
                    🔒 Secure Account
                </a>
                <a href="mailto:support@sendbaba.com?subject=Suspicious Login - {email}" style="display: inline-block; background: linear-gradient(135deg, #fecaca, #fca5a5); color: #991b1b; text-decoration: none; padding: 14px 28px; border-radius: 10px; font-weight: 600; font-size: 14px; margin: 5px;">
                    🚨 Report Activity
                </a>
            </div>
        </div>
        
        <!-- Footer -->
        <div style="text-align: center; padding: 24px;">
            <p style="color: #9ca3af; font-size: 12px; margin: 0;">
                Security notification from SendBaba Mail<br>
                © 2024 SendBaba. Professional Email Solutions.
            </p>
        </div>
    </div>
</body>
</html>
'''
        
        send_email_sync({
            'from': 'security@sendbaba.com',
            'from_name': 'SendBaba Security',
            'to': recovery_email,
            'subject': f'🔔 New login to {email} from {login_info["location"]}',
            'html_body': html_body,
            'text_body': f'''New Login Detected

Hi {name},

We detected a new sign-in to your SendBaba Mail account.

Account: {email}
Date & Time: {login_info['datetime']}
Location: {login_info['location']}
IP Address: {login_info['ip']}
Device: {login_info['device']}
Browser: {login_info['browser']}

If this wasn't you, please secure your account immediately at https://mail.sendbaba.com/settings

- SendBaba Security Team
'''
        })
        print(f"Login notification sent to {recovery_email}")
        return True
    except Exception as e:
        print(f"Failed to send login notification: {e}")
        return False


def get_welcome_email_html(first_name, sendbaba_email, recovery_email):
    """Generate stunning welcome email with SendBaba branding"""
    return f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome to SendBaba Mail</title>
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #fff7ed 0%, #fed7aa 100%);">
    <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
        
        <!-- Header Banner -->
        <div style="background: linear-gradient(135deg, #f97316 0%, #ea580c 50%, #dc2626 100%); border-radius: 24px 24px 0 0; padding: 40px 30px; text-align: center;">
            <div style="display: inline-block; background: rgba(255,255,255,0.2); padding: 16px 32px; border-radius: 16px; margin-bottom: 20px;">
                <span style="font-size: 40px;">📧</span>
            </div>
            <h1 style="margin: 0; color: white; font-size: 28px; font-weight: 700; text-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                Welcome to SendBaba Mail!
            </h1>
            <p style="margin: 12px 0 0; color: rgba(255,255,255,0.9); font-size: 16px;">
                Your Professional Email Journey Starts Now
            </p>
        </div>
        
        <!-- Main Content Card -->
        <div style="background: white; border-radius: 0 0 24px 24px; padding: 40px 30px; box-shadow: 0 20px 60px rgba(249, 115, 22, 0.15);">
            
            <!-- Greeting -->
            <p style="color: #374151; font-size: 18px; line-height: 1.6; margin: 0 0 20px;">
                Hi <strong style="color: #f97316;">{first_name}</strong> 👋
            </p>
            <p style="color: #6b7280; font-size: 16px; line-height: 1.7; margin: 0 0 30px;">
                Congratulations! Your SendBaba Mail account is ready. You now have access to a powerful, professional email platform that puts you ahead of the competition.
            </p>
            
            <!-- Account Details Box -->
            <div style="background: linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%); border: 2px solid #fed7aa; border-radius: 20px; padding: 28px; margin-bottom: 30px;">
                <div style="margin-bottom: 16px;">
                    <span style="font-size: 24px; margin-right: 12px;">🔐</span>
                    <span style="color: #c2410c; font-size: 18px; font-weight: 600;">Your Account Details</span>
                </div>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 12px 0; border-bottom: 1px dashed #fed7aa; color: #92400e; font-size: 14px; width: 40%;">📬 Email Address</td>
                        <td style="padding: 12px 0; border-bottom: 1px dashed #fed7aa; color: #1f2937; font-size: 14px; font-weight: 600; font-family: 'Courier New', monospace;">{sendbaba_email}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 0; border-bottom: 1px dashed #fed7aa; color: #92400e; font-size: 14px;">🔄 Recovery Email</td>
                        <td style="padding: 12px 0; border-bottom: 1px dashed #fed7aa; color: #1f2937; font-size: 14px;">{recovery_email}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 0; color: #92400e; font-size: 14px;">🌐 Login URL</td>
                        <td style="padding: 12px 0; color: #1f2937; font-size: 14px;"><a href="https://mail.sendbaba.com" style="color: #f97316; text-decoration: none; font-weight: 600;">mail.sendbaba.com</a></td>
                    </tr>
                </table>
            </div>
            
            <!-- Login Button -->
            <div style="text-align: center; margin-bottom: 40px;">
                <a href="https://mail.sendbaba.com/login" style="display: inline-block; background: linear-gradient(135deg, #f97316 0%, #ea580c 50%, #dc2626 100%); color: white; text-decoration: none; padding: 18px 50px; border-radius: 14px; font-weight: 700; font-size: 16px; box-shadow: 0 8px 30px rgba(249, 115, 22, 0.4);">
                    🚀 Login to Your Mailbox
                </a>
            </div>
            
            <!-- Why SendBaba Section -->
            <div style="margin-bottom: 35px;">
                <h3 style="color: #1f2937; font-size: 20px; margin: 0 0 20px;">
                    <span style="background: linear-gradient(135deg, #f97316, #ea580c); color: white; width: 36px; height: 36px; border-radius: 10px; display: inline-block; text-align: center; line-height: 36px; margin-right: 12px; font-size: 18px;">⚡</span>
                    Why Choose SendBaba Mail?
                </h3>
                
                <!-- Feature 1 -->
                <div style="background: #f0fdf4; border-left: 4px solid #22c55e; padding: 16px 20px; border-radius: 0 12px 12px 0; margin-bottom: 12px;">
                    <table style="width: 100%;">
                        <tr>
                            <td style="width: 40px; vertical-align: top;"><span style="font-size: 24px;">🛡️</span></td>
                            <td>
                                <strong style="color: #166534; font-size: 15px;">Enterprise-Grade Security</strong>
                                <p style="margin: 6px 0 0; color: #4b5563; font-size: 13px; line-height: 1.5;">End-to-end encryption, spam protection, and advanced threat detection.</p>
                            </td>
                        </tr>
                    </table>
                </div>
                
                <!-- Feature 2 -->
                <div style="background: #eff6ff; border-left: 4px solid #3b82f6; padding: 16px 20px; border-radius: 0 12px 12px 0; margin-bottom: 12px;">
                    <table style="width: 100%;">
                        <tr>
                            <td style="width: 40px; vertical-align: top;"><span style="font-size: 24px;">🎨</span></td>
                            <td>
                                <strong style="color: #1e40af; font-size: 15px;">Custom Domain Support</strong>
                                <p style="margin: 6px 0 0; color: #4b5563; font-size: 13px; line-height: 1.5;">Add your own domain for branded emails like you@yourbusiness.com.</p>
                            </td>
                        </tr>
                    </table>
                </div>
                
                <!-- Feature 3 -->
                <div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 16px 20px; border-radius: 0 12px 12px 0; margin-bottom: 12px;">
                    <table style="width: 100%;">
                        <tr>
                            <td style="width: 40px; vertical-align: top;"><span style="font-size: 24px;">⚡</span></td>
                            <td>
                                <strong style="color: #92400e; font-size: 15px;">Lightning Fast Delivery</strong>
                                <p style="margin: 6px 0 0; color: #4b5563; font-size: 13px; line-height: 1.5;">Optimized infrastructure ensures instant email delivery worldwide.</p>
                            </td>
                        </tr>
                    </table>
                </div>
                
                <!-- Feature 4 -->
                <div style="background: #fae8ff; border-left: 4px solid #a855f7; padding: 16px 20px; border-radius: 0 12px 12px 0; margin-bottom: 12px;">
                    <table style="width: 100%;">
                        <tr>
                            <td style="width: 40px; vertical-align: top;"><span style="font-size: 24px;">👥</span></td>
                            <td>
                                <strong style="color: #7e22ce; font-size: 15px;">Team Collaboration</strong>
                                <p style="margin: 6px 0 0; color: #4b5563; font-size: 13px; line-height: 1.5;">Invite team members and collaborate seamlessly.</p>
                            </td>
                        </tr>
                    </table>
                </div>
                
                <!-- Feature 5 -->
                <div style="background: #ecfdf5; border-left: 4px solid #10b981; padding: 16px 20px; border-radius: 0 12px 12px 0; margin-bottom: 12px;">
                    <table style="width: 100%;">
                        <tr>
                            <td style="width: 40px; vertical-align: top;"><span style="font-size: 24px;">💰</span></td>
                            <td>
                                <strong style="color: #047857; font-size: 15px;">Incredibly Cost Effective</strong>
                                <p style="margin: 6px 0 0; color: #4b5563; font-size: 13px; line-height: 1.5;">Premium features at a fraction of Google Workspace or Microsoft 365.</p>
                            </td>
                        </tr>
                    </table>
                </div>
                
                <!-- Feature 6 -->
                <div style="background: #fff1f2; border-left: 4px solid #f43f5e; padding: 16px 20px; border-radius: 0 12px 12px 0;">
                    <table style="width: 100%;">
                        <tr>
                            <td style="width: 40px; vertical-align: top;"><span style="font-size: 24px;">📱</span></td>
                            <td>
                                <strong style="color: #be123c; font-size: 15px;">Access Anywhere</strong>
                                <p style="margin: 6px 0 0; color: #4b5563; font-size: 13px; line-height: 1.5;">Web interface, mobile apps, IMAP/SMTP for any email client.</p>
                            </td>
                        </tr>
                    </table>
                </div>
            </div>
            
            <!-- Comparison Section -->
            <div style="background: #1f2937; border-radius: 16px; padding: 24px; margin-bottom: 30px;">
                <h4 style="color: white; margin: 0 0 16px; font-size: 16px; text-align: center;">📊 SendBaba vs. Others</h4>
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <tr style="border-bottom: 1px solid #374151;">
                        <td style="padding: 10px 8px; color: #9ca3af;">Feature</td>
                        <td style="padding: 10px 8px; color: #f97316; font-weight: 600; text-align: center;">SendBaba</td>
                        <td style="padding: 10px 8px; color: #9ca3af; text-align: center;">Gmail</td>
                        <td style="padding: 10px 8px; color: #9ca3af; text-align: center;">Outlook</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #374151;">
                        <td style="padding: 10px 8px; color: #d1d5db;">Custom Domain</td>
                        <td style="padding: 10px 8px; text-align: center;">✅</td>
                        <td style="padding: 10px 8px; text-align: center; color: #9ca3af;">Paid</td>
                        <td style="padding: 10px 8px; text-align: center; color: #9ca3af;">Paid</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #374151;">
                        <td style="padding: 10px 8px; color: #d1d5db;">No Ads</td>
                        <td style="padding: 10px 8px; text-align: center;">✅</td>
                        <td style="padding: 10px 8px; text-align: center; color: #9ca3af;">❌</td>
                        <td style="padding: 10px 8px; text-align: center; color: #9ca3af;">❌</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #374151;">
                        <td style="padding: 10px 8px; color: #d1d5db;">Full Privacy</td>
                        <td style="padding: 10px 8px; text-align: center;">✅</td>
                        <td style="padding: 10px 8px; text-align: center; color: #9ca3af;">⚠️</td>
                        <td style="padding: 10px 8px; text-align: center; color: #9ca3af;">⚠️</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px 8px; color: #d1d5db;">Email Marketing</td>
                        <td style="padding: 10px 8px; text-align: center;">✅</td>
                        <td style="padding: 10px 8px; text-align: center; color: #9ca3af;">❌</td>
                        <td style="padding: 10px 8px; text-align: center; color: #9ca3af;">❌</td>
                    </tr>
                </table>
            </div>
            
            <!-- Quick Tips -->
            <div style="background: #fafafa; border-radius: 16px; padding: 24px; margin-bottom: 30px;">
                <h4 style="margin: 0 0 16px; color: #374151; font-size: 16px;">💡 Quick Start Tips</h4>
                <ul style="margin: 0; padding-left: 20px; color: #6b7280; font-size: 14px; line-height: 2;">
                    <li>Set up your email signature in Settings</li>
                    <li>Add your custom domain for branded emails</li>
                    <li>Invite team members to collaborate</li>
                    <li>Enable login notifications for security</li>
                    <li>Connect via IMAP/SMTP for mobile access</li>
                </ul>
            </div>
            
            <!-- Support -->
            <div style="text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb;">
                <p style="color: #9ca3af; font-size: 13px; margin: 0 0 16px;">
                    Need help? We're here for you!
                </p>
                <a href="mailto:support@sendbaba.com" style="display: inline-block; background: #f3f4f6; color: #374151; text-decoration: none; padding: 12px 24px; border-radius: 10px; font-size: 14px; margin: 4px;">
                    📧 Contact Support
                </a>
                <a href="https://sendbaba.com/docs" style="display: inline-block; background: #f3f4f6; color: #374151; text-decoration: none; padding: 12px 24px; border-radius: 10px; font-size: 14px; margin: 4px;">
                    📚 Documentation
                </a>
            </div>
        </div>
        
        <!-- Footer -->
        <div style="text-align: center; padding: 30px 20px;">
            <p style="color: #9ca3af; font-size: 12px; margin: 0 0 12px;">
                © 2024 SendBaba. Professional Email Solutions.
            </p>
            <p style="margin: 0;">
                <a href="https://sendbaba.com" style="color: #f97316; text-decoration: none; font-size: 12px; margin: 0 10px;">Website</a>
                <a href="https://mail.sendbaba.com" style="color: #f97316; text-decoration: none; font-size: 12px; margin: 0 10px;">Webmail</a>
                <a href="mailto:support@sendbaba.com" style="color: #f97316; text-decoration: none; font-size: 12px; margin: 0 10px;">Support</a>
            </p>
        </div>
    </div>
</body>
</html>
'''
