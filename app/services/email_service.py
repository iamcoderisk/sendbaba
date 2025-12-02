"""
SendBaba Email Service
Handles all transactional emails using SendBaba's own SMTP infrastructure
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from flask import request
import logging
import secrets

logger = logging.getLogger(__name__)


class EmailService:
    """Email service using SendBaba's Postal server"""
    
    def __init__(self):
        self.smtp_host = 'localhost'
        self.smtp_port = 25
        self.from_email = 'noreply@sendbaba.com'
        self.from_name = 'SendBaba'
        self.logo_url = 'https://playmaster.sendbaba.com/static/images/logo.png'
    
    def send_email(self, to_email, subject, html_content, text_content=None):
        """Send email via SendBaba SMTP"""
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            msg['X-Mailer'] = 'SendBaba/1.0'
            
            if text_content:
                msg.attach(MIMEText(text_content, 'plain'))
            msg.attach(MIMEText(html_content, 'html'))
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                server.sendmail(self.from_email, to_email, msg.as_string())
            
            logger.info(f"Email sent to {to_email}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Email failed to {to_email}: {e}")
            return False
    
    def send_welcome_email(self, user_email, user_name, verification_token):
        """Send welcome email with verification link"""
        verification_link = f"https://playmaster.sendbaba.com/verify-email/{verification_token}"
        html = self._get_welcome_template(user_name, user_email, verification_link)
        text = f"Welcome to SendBaba, {user_name}! Verify your email: {verification_link}"
        return self.send_email(user_email, "🎉 Welcome to SendBaba - Verify Your Email", html, text)
    
    def send_login_notification(self, user_email, user_name, login_info):
        """Send login notification email"""
        html = self._get_login_template(user_name, login_info)
        text = f"New login detected: {login_info['datetime']} from {login_info['ip_address']}"
        return self.send_email(user_email, "🔐 New Login to Your SendBaba Account", html, text)
    
    def send_password_reset(self, user_email, user_name, reset_token):
        """Send password reset email"""
        reset_link = f"https://playmaster.sendbaba.com/reset-password/{reset_token}"
        html = self._get_reset_template(user_name, reset_link)
        text = f"Reset your password: {reset_link}"
        return self.send_email(user_email, "🔑 Reset Your SendBaba Password", html, text)
    
    def send_verification_email(self, user_email, user_name, verification_token):
        """Resend verification email"""
        verification_link = f"https://playmaster.sendbaba.com/verify-email/{verification_token}"
        html = self._get_verification_template(user_name, verification_link)
        text = f"Verify your email: {verification_link}"
        return self.send_email(user_email, "✉️ Verify Your SendBaba Email", html, text)

    def _base_template(self, content, preview=""):
        """Base email wrapper with SendBaba branding"""
        return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SendBaba</title>
</head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="display:none;max-height:0;overflow:hidden;">{preview}</div>
<table width="100%" cellspacing="0" cellpadding="0" style="background:#f3f4f6;">
<tr><td align="center" style="padding:40px 20px;">
<table width="600" cellspacing="0" cellpadding="0" style="max-width:600px;width:100%;">

<!-- Logo -->
<tr><td align="center" style="padding-bottom:32px;">
<img src="{self.logo_url}" alt="SendBaba" style="height:48px;width:auto;" />
</td></tr>

<!-- Content Card -->
<tr><td>
<table width="100%" cellspacing="0" cellpadding="0" style="background:#fff;border-radius:24px;box-shadow:0 4px 6px rgba(0,0,0,0.1);">
<tr><td style="padding:48px 40px;">
{content}
</td></tr>
</table>
</td></tr>

<!-- Footer -->
<tr><td align="center" style="padding-top:32px;">
<p style="margin:0 0 8px;color:#6b7280;font-size:13px;">© 2024 SendBaba. All rights reserved.</p>
<p style="margin:0;font-size:13px;">
<a href="https://sendbaba.com" style="color:#F97316;text-decoration:none;">Website</a> · 
<a href="https://sendbaba.com/privacy" style="color:#F97316;text-decoration:none;">Privacy</a>
</p>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>'''

    def _get_welcome_template(self, user_name, user_email, verification_link):
        content = f'''
<table width="100%" cellspacing="0" cellpadding="0">
<tr><td align="center" style="padding-bottom:24px;">
<div style="width:80px;height:80px;background:linear-gradient(135deg,#FFF7ED,#FFEDD5);border-radius:50%;text-align:center;line-height:80px;display:inline-block;">
<span style="font-size:40px;">🎉</span>
</div>
</td></tr>
</table>

<h1 style="margin:0 0 8px;font-size:28px;font-weight:700;color:#111827;text-align:center;">Welcome to SendBaba!</h1>
<p style="margin:0 0 32px;font-size:16px;color:#6b7280;text-align:center;">We\'re thrilled to have you on board, <strong style="color:#111827;">{user_name}</strong></p>

<!-- Features -->
<table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:32px;">
<tr><td style="padding:20px;background:linear-gradient(135deg,#FFF7ED,#FFEDD5);border-radius:16px;">
<table width="100%" cellspacing="0" cellpadding="0">
<tr>
<td width="48" valign="top"><div style="width:40px;height:40px;background:#F97316;border-radius:10px;text-align:center;line-height:40px;"><span style="font-size:18px;">📧</span></div></td>
<td style="padding-left:16px;"><p style="margin:0 0 4px;font-size:15px;font-weight:600;color:#111827;">Send Beautiful Campaigns</p><p style="margin:0;font-size:13px;color:#6b7280;">Create stunning emails that convert</p></td>
</tr>
</table>
</td></tr>
<tr><td style="height:12px;"></td></tr>
<tr><td style="padding:20px;background:#f9fafb;border-radius:16px;">
<table width="100%" cellspacing="0" cellpadding="0">
<tr>
<td width="48" valign="top"><div style="width:40px;height:40px;background:#10B981;border-radius:10px;text-align:center;line-height:40px;"><span style="font-size:18px;">📊</span></div></td>
<td style="padding-left:16px;"><p style="margin:0 0 4px;font-size:15px;font-weight:600;color:#111827;">Real-Time Analytics</p><p style="margin:0;font-size:13px;color:#6b7280;">Track opens, clicks, and conversions</p></td>
</tr>
</table>
</td></tr>
<tr><td style="height:12px;"></td></tr>
<tr><td style="padding:20px;background:#f9fafb;border-radius:16px;">
<table width="100%" cellspacing="0" cellpadding="0">
<tr>
<td width="48" valign="top"><div style="width:40px;height:40px;background:#6366F1;border-radius:10px;text-align:center;line-height:40px;"><span style="font-size:18px;">🚀</span></div></td>
<td style="padding-left:16px;"><p style="margin:0 0 4px;font-size:15px;font-weight:600;color:#111827;">Powerful Automation</p><p style="margin:0;font-size:13px;color:#6b7280;">Set up workflows that work for you</p></td>
</tr>
</table>
</td></tr>
</table>

<!-- Verify Button -->
<table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:32px;">
<tr><td style="padding:24px;background:#111827;border-radius:16px;text-align:center;">
<p style="margin:0 0 16px;font-size:14px;color:#9ca3af;">Verify your email to get started</p>
<a href="{verification_link}" style="display:inline-block;padding:16px 48px;background:linear-gradient(135deg,#F97316,#EA580C);color:#fff;font-size:16px;font-weight:600;text-decoration:none;border-radius:12px;">Verify My Email →</a>
<p style="margin:16px 0 0;font-size:12px;color:#6b7280;">Link expires in 24 hours</p>
</td></tr>
</table>

<table width="100%" cellspacing="0" cellpadding="0" style="background:#f9fafb;border-radius:12px;">
<tr><td style="padding:20px;">
<p style="margin:0 0 8px;font-size:12px;font-weight:600;color:#6b7280;text-transform:uppercase;">Your Account</p>
<p style="margin:0;font-size:15px;color:#111827;">{user_email}</p>
</td></tr>
</table>
'''
        return self._base_template(content, "Welcome to SendBaba! Verify your email to get started.")

    def _get_login_template(self, user_name, login_info):
        content = f'''
<table width="100%" cellspacing="0" cellpadding="0">
<tr><td align="center" style="padding-bottom:24px;">
<div style="width:80px;height:80px;background:linear-gradient(135deg,#ECFDF5,#D1FAE5);border-radius:50%;text-align:center;line-height:80px;display:inline-block;">
<span style="font-size:40px;">🔐</span>
</div>
</td></tr>
</table>

<h1 style="margin:0 0 8px;font-size:28px;font-weight:700;color:#111827;text-align:center;">New Login Detected</h1>
<p style="margin:0 0 32px;font-size:16px;color:#6b7280;text-align:center;">Hi <strong style="color:#111827;">{user_name}</strong>, we noticed a new login to your account</p>

<table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:24px;">
<tr><td style="padding:24px;background:#1F2937;border-radius:16px;">
<p style="margin:0 0 20px;font-size:12px;font-weight:600;color:#9ca3af;text-transform:uppercase;">Login Details</p>

<table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:12px;">
<tr><td style="padding:8px 0;border-bottom:1px solid #374151;">
<span style="color:#9ca3af;font-size:13px;">Date & Time</span><br>
<span style="color:#fff;font-size:15px;font-weight:500;">{login_info['datetime']}</span>
</td></tr>
<tr><td style="padding:8px 0;border-bottom:1px solid #374151;">
<span style="color:#9ca3af;font-size:13px;">IP Address</span><br>
<span style="color:#fff;font-size:15px;font-weight:500;">{login_info['ip_address']}</span>
</td></tr>
<tr><td style="padding:8px 0;border-bottom:1px solid #374151;">
<span style="color:#9ca3af;font-size:13px;">Device</span><br>
<span style="color:#fff;font-size:15px;font-weight:500;">{login_info['device']}</span>
</td></tr>
<tr><td style="padding:8px 0;border-bottom:1px solid #374151;">
<span style="color:#9ca3af;font-size:13px;">Browser</span><br>
<span style="color:#fff;font-size:15px;font-weight:500;">{login_info['browser']}</span>
</td></tr>
<tr><td style="padding:8px 0;">
<span style="color:#9ca3af;font-size:13px;">Location</span><br>
<span style="color:#fff;font-size:15px;font-weight:500;">{login_info['location']}</span>
</td></tr>
</table>
</td></tr>
</table>

<table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:16px;">
<tr><td style="padding:16px;background:#ECFDF5;border-radius:12px;border-left:4px solid #10B981;">
<span style="color:#065F46;font-size:14px;">✅ If this was you, no action is needed.</span>
</td></tr>
</table>

<table width="100%" cellspacing="0" cellpadding="0">
<tr><td style="padding:16px;background:#FEF2F2;border-radius:12px;border-left:4px solid #EF4444;">
<span style="color:#991B1B;font-size:14px;font-weight:500;">⚠️ Didn\'t recognize this login?</span><br>
<a href="https://playmaster.sendbaba.com/dashboard/settings" style="display:inline-block;margin-top:12px;padding:10px 20px;background:#EF4444;color:#fff;font-size:13px;font-weight:600;text-decoration:none;border-radius:8px;">Secure My Account</a>
</td></tr>
</table>
'''
        return self._base_template(content, "New login detected on your SendBaba account")

    def _get_reset_template(self, user_name, reset_link):
        content = f'''
<table width="100%" cellspacing="0" cellpadding="0">
<tr><td align="center" style="padding-bottom:24px;">
<div style="width:80px;height:80px;background:linear-gradient(135deg,#FEF3C7,#FDE68A);border-radius:50%;text-align:center;line-height:80px;display:inline-block;">
<span style="font-size:40px;">🔑</span>
</div>
</td></tr>
</table>

<h1 style="margin:0 0 8px;font-size:28px;font-weight:700;color:#111827;text-align:center;">Reset Your Password</h1>
<p style="margin:0 0 32px;font-size:16px;color:#6b7280;text-align:center;">Hi <strong style="color:#111827;">{user_name}</strong>, we received a request to reset your password</p>

<table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:32px;">
<tr><td align="center">
<a href="{reset_link}" style="display:inline-block;padding:18px 56px;background:linear-gradient(135deg,#F97316,#EA580C);color:#fff;font-size:16px;font-weight:600;text-decoration:none;border-radius:12px;">Reset Password →</a>
</td></tr>
</table>

<table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:24px;">
<tr><td style="padding:20px;background:#FFF7ED;border-radius:12px;text-align:center;">
<p style="margin:0;font-size:14px;color:#C2410C;"><strong>⏱️ This link expires in 1 hour</strong></p>
</td></tr>
</table>

<p style="margin:0;font-size:13px;color:#9ca3af;text-align:center;">If you didn\'t request this, ignore this email.</p>
'''
        return self._base_template(content, "Reset your SendBaba password")

    def _get_verification_template(self, user_name, verification_link):
        content = f'''
<table width="100%" cellspacing="0" cellpadding="0">
<tr><td align="center" style="padding-bottom:24px;">
<div style="width:80px;height:80px;background:linear-gradient(135deg,#DBEAFE,#BFDBFE);border-radius:50%;text-align:center;line-height:80px;display:inline-block;">
<span style="font-size:40px;">✉️</span>
</div>
</td></tr>
</table>

<h1 style="margin:0 0 8px;font-size:28px;font-weight:700;color:#111827;text-align:center;">Verify Your Email</h1>
<p style="margin:0 0 32px;font-size:16px;color:#6b7280;text-align:center;">Hi <strong style="color:#111827;">{user_name}</strong>, please verify your email to continue using SendBaba</p>

<table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:32px;">
<tr><td align="center">
<a href="{verification_link}" style="display:inline-block;padding:18px 56px;background:linear-gradient(135deg,#F97316,#EA580C);color:#fff;font-size:16px;font-weight:600;text-decoration:none;border-radius:12px;">Verify Email →</a>
</td></tr>
</table>

<p style="margin:0;font-size:13px;color:#9ca3af;text-align:center;">Link expires in 24 hours.</p>
'''
        return self._base_template(content, "Verify your SendBaba email")


# ============================================
# LOGIN INFO HELPERS
# ============================================

def parse_user_agent(ua_string):
    """Parse user agent string"""
    ua = ua_string.lower()
    
    if 'mobile' in ua or ('android' in ua and 'mobile' in ua):
        device = 'Mobile'
    elif 'tablet' in ua or 'ipad' in ua:
        device = 'Tablet'
    else:
        device = 'Desktop'
    
    if 'windows' in ua:
        os_name = 'Windows'
    elif 'mac os' in ua:
        os_name = 'macOS'
    elif 'linux' in ua:
        os_name = 'Linux'
    elif 'android' in ua:
        os_name = 'Android'
    elif 'iphone' in ua or 'ipad' in ua:
        os_name = 'iOS'
    else:
        os_name = 'Unknown'
    
    if 'edg/' in ua:
        browser = 'Edge'
    elif 'chrome' in ua:
        browser = 'Chrome'
    elif 'firefox' in ua:
        browser = 'Firefox'
    elif 'safari' in ua:
        browser = 'Safari'
    else:
        browser = 'Unknown'
    
    return f"{device} ({os_name})", browser


def get_location_from_ip(ip_address):
    """Get location from IP"""
    try:
        if ip_address in ['127.0.0.1', 'localhost', '::1'] or ip_address.startswith(('192.168.', '10.', '172.')):
            return "Local Network"
        
        import urllib.request
        import json
        
        url = f'http://ip-api.com/json/{ip_address}?fields=status,city,regionName,country'
        req = urllib.request.Request(url, headers={'User-Agent': 'SendBaba/1.0'})
        
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if data.get('status') == 'success':
                parts = [p for p in [data.get('city'), data.get('regionName'), data.get('country')] if p]
                return ', '.join(parts) if parts else "Unknown"
        return "Unknown"
    except:
        return "Unknown"


def get_login_info(request_obj):
    """Extract login information"""
    ip = request_obj.headers.get('X-Forwarded-For', request_obj.remote_addr)
    if ',' in str(ip):
        ip = ip.split(',')[0].strip()
    
    ua_string = request_obj.headers.get('User-Agent', '')
    device, browser = parse_user_agent(ua_string)
    location = get_location_from_ip(ip)
    now = datetime.utcnow()
    
    return {
        'ip_address': ip,
        'device': device,
        'browser': browser,
        'location': location,
        'datetime': now.strftime("%B %d, %Y at %I:%M %p UTC"),
        'timestamp': now,
        'user_agent': ua_string[:500]
    }


# ============================================
# AUTH HOOKS
# ============================================

def on_user_register(user):
    """Send welcome email after registration"""
    try:
        from app import db
        
        verification_token = secrets.token_urlsafe(32)
        user.verification_token = verification_token
        user.is_verified = False
        db.session.commit()
        
        user_name = getattr(user, 'first_name', None) or user.email.split('@')[0]
        
        email_service = EmailService()
        email_service.send_welcome_email(user.email, user_name, verification_token)
        
        return verification_token
    except Exception as e:
        logger.error(f"on_user_register failed: {e}")
        return None


def on_user_login(user, request_obj):
    """Send login notification"""
    try:
        from app import db
        
        login_info = get_login_info(request_obj)
        
        try:
            from app.models.team import AuditLog
            log = AuditLog(
                organization_id=str(getattr(user, 'organization_id', '')),
                user_id=str(user.id),
                action='user_login',
                resource_type='user',
                resource_id=str(user.id),
                details=f"{login_info['device']} - {login_info['browser']} - {login_info['location']}",
                ip_address=login_info['ip_address'],
                user_agent=login_info['user_agent']
            )
            db.session.add(log)
        except:
            pass
        
        user.last_login = login_info['timestamp']
        db.session.commit()
        
        user_name = getattr(user, 'first_name', None) or user.email.split('@')[0]
        email_service = EmailService()
        email_service.send_login_notification(user.email, user_name, login_info)
        
        return login_info
    except Exception as e:
        logger.error(f"on_user_login failed: {e}")
        return None


def resend_verification(user):
    """Resend verification email"""
    try:
        from app import db
        
        if not user.verification_token:
            user.verification_token = secrets.token_urlsafe(32)
            db.session.commit()
        
        user_name = getattr(user, 'first_name', None) or user.email.split('@')[0]
        
        email_service = EmailService()
        email_service.send_verification_email(user.email, user_name, user.verification_token)
        
        return True
    except Exception as e:
        logger.error(f"resend_verification failed: {e}")
        return False


email_service = EmailService()


def on_password_reset_request(user):
    """Send password reset email"""
    try:
        from app import db
        import secrets
        
        reset_token = secrets.token_urlsafe(32)
        user.reset_token = reset_token
        user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()
        
        user_name = getattr(user, 'first_name', None) or user.email.split('@')[0]
        
        email_service = EmailService()
        email_service.send_password_reset(user.email, user_name, reset_token)
        
        return reset_token
    except Exception as e:
        logger.error(f"on_password_reset_request failed: {e}")
        return None
