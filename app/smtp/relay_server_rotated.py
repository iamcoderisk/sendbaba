"""
SendBaba SMTP Relay Server with Multi-IP Rotation
==================================================
EXACT copy of original relay_server.py with IP rotation integrated.
This is a permanent, production-ready solution.
"""

import smtplib
import ssl
import dns.resolver
import logging
import os
import sys
import time
import re
from typing import Dict, Tuple, Optional

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import make_msgid, formatdate

sys.path.insert(0, '/opt/sendbaba-staging')

try:
    import dkim
    DKIM_AVAILABLE = True
except ImportError:
    DKIM_AVAILABLE = False

try:
    from premailer import transform as inline_css
    HAS_PREMAILER = True
except ImportError:
    HAS_PREMAILER = False

# Import IP rotation
try:
    from app.utils.ip_rotation import get_ip_for_sending, get_ip_stats
    IP_ROTATION_AVAILABLE = True
except ImportError:
    IP_ROTATION_AVAILABLE = False

logger = logging.getLogger(__name__)

# Configuration
DKIM_KEY_DIR = '/opt/sendbaba-staging/data/dkim'
DEFAULT_IP = '156.67.29.186'
DEFAULT_HOSTNAME = 'mail.sendbaba.com'


class DomainDKIM:
    """DKIM signing - EXACT copy from original"""
    def __init__(self, domain: str, selector: str = 'mail'):
        self.domain = domain
        self.selector = selector
        self.private_key_path = f'{DKIM_KEY_DIR}/{domain}_private.key'
        self.private_key = None
        self._load_key()
    
    def _load_key(self):
        try:
            if os.path.exists(self.private_key_path):
                with open(self.private_key_path, 'rb') as f:
                    self.private_key = f.read()
                logger.info(f"✅ DKIM: {self.domain}")
        except:
            pass
    
    def sign(self, message_bytes: bytes) -> bytes:
        if not self.private_key:
            return message_bytes
        try:
            signature = dkim.sign(
                message=message_bytes,
                selector=self.selector.encode('utf-8'),
                domain=self.domain.encode('utf-8'),
                privkey=self.private_key,
                include_headers=[b'from', b'to', b'subject', b'date', b'message-id']
            )
            if signature and signature != message_bytes:
                return signature + message_bytes
            return message_bytes
        except:
            return message_bytes


class RotatedSMTPRelay:
    """
    Professional SMTP Relay with Multi-IP Rotation
    
    This is an EXACT copy of ProfessionalSMTPRelay with IP rotation added.
    IP rotation tracks which IP should be used for warmup/limits tracking.
    Actual sending uses the server's default route (156.67.29.186).
    
    For TRUE multi-IP sending from different source IPs, use distributed
    workers running on each IP's server.
    """
    
    def __init__(self):
        self.mx_cache = {}
        self.dkim_cache = {}
        self.hostname = DEFAULT_HOSTNAME
        logger.info("✅ SMTP Relay (Rotated) initialized")
    
    def get_dkim_for_domain(self, domain: str) -> Optional[DomainDKIM]:
        if domain not in self.dkim_cache:
            self.dkim_cache[domain] = DomainDKIM(domain)
        return self.dkim_cache[domain]
    
    def get_mx_servers(self, domain: str) -> list:
        if domain in self.mx_cache:
            cache_time, mx_list = self.mx_cache[domain]
            if time.time() - cache_time < 3600:
                return mx_list
        try:
            mx_records = dns.resolver.resolve(domain, 'MX')
            mx_list = [str(r.exchange).rstrip('.') for r in sorted(mx_records, key=lambda x: x.preference)]
            self.mx_cache[domain] = (time.time(), mx_list)
            logger.info(f"MX: {mx_list[:2]}")
            return mx_list
        except Exception as e:
            logger.error(f"MX failed: {e}")
            return []
    
    def create_message(self, email_data: dict) -> Tuple[bytes, str]:
        """Create message - EXACT same as original ProfessionalSMTPRelay"""
        msg = MIMEMultipart('alternative')
        
        # Handle sender - EXACT same logic as original
        sender = email_data.get('from') or email_data.get('from_email') or 'noreply@sendbaba.com'
        if not sender or '@' not in str(sender):
            sender = 'noreply@sendbaba.com'
        sender = str(sender).strip()
        
        try:
            sender_domain = sender.split('@')[1] if '@' in sender else 'sendbaba.com'
        except:
            sender_domain = 'sendbaba.com'
        
        from_name = email_data.get('from_name') or sender_domain.split('.')[0].title()
        from_name = str(from_name).strip() if from_name else 'SendBaba'
        
        recipient = email_data.get('to') or email_data.get('to_email')
        
        logger.info(f"From: {from_name} <{sender}>")
        
        # Headers - EXACT same as original
        msg['From'] = f'{from_name} <{sender}>'
        msg['To'] = recipient
        msg['Subject'] = email_data.get('subject', 'Message')
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain=sender_domain)
        msg['MIME-Version'] = '1.0'
        msg['Return-Path'] = f'bounces@{sender_domain}'
        
        reply_to = email_data.get('reply_to', sender)
        msg['Reply-To'] = reply_to
        
        unsubscribe_url = f'https://sendbaba.com/unsubscribe?email={recipient}&domain={sender_domain}'
        msg['List-Unsubscribe'] = f'<{unsubscribe_url}>'
        msg['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'
        msg['Precedence'] = 'bulk'
        
        # Body handling - EXACT same as original
        text_body = email_data.get('text_body', '')
        html_body = email_data.get('html_body', '')
        
        if not text_body and html_body:
            text_body = re.sub('<[^<]+?>', '', html_body).strip()
        
        if text_body:
            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        if html_body:
            if HAS_PREMAILER:
                try:
                    html_body = inline_css(html_body, remove_classes=True, strip_important=False)
                except:
                    pass
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        elif not text_body:
            msg.attach(MIMEText('Message from ' + sender_domain, 'plain', 'utf-8'))
        
        # DKIM signing - EXACT same as original
        message_bytes = msg.as_bytes()
        
        dkim_handler = self.get_dkim_for_domain(sender_domain)
        if dkim_handler and dkim_handler.private_key:
            signed = dkim_handler.sign(message_bytes)
            if signed != message_bytes:
                logger.info(f"✅ DKIM signed")
                return signed, sender_domain
        
        return message_bytes, sender_domain
    
    def send_email(self, email_data: dict, retry_count: int = 0, use_rotation: bool = True) -> Dict:
        """
        Send email with IP rotation tracking.
        
        Args:
            email_data: Email data dict
            retry_count: Current retry attempt
            use_rotation: Whether to use IP rotation for tracking
        
        Returns:
            Result dict with success, message, mx_server, tls, source_ip
        """
        recipient = email_data.get('to') or email_data.get('to_email', '')
        recipient = str(recipient).strip()
        
        sender = email_data.get('from') or email_data.get('from_email') or 'noreply@sendbaba.com'
        if not sender or '@' not in str(sender):
            sender = 'noreply@sendbaba.com'
        
        # Validate recipient
        if not recipient or '@' not in recipient:
            return {'success': False, 'message': 'Invalid recipient'}
        
        try:
            recipient_domain = recipient.split('@')[1]
        except:
            return {'success': False, 'message': 'Invalid format'}
        
        # Get IP from rotation for tracking/warmup
        tracked_ip = DEFAULT_IP
        tracked_hostname = DEFAULT_HOSTNAME
        
        if use_rotation and IP_ROTATION_AVAILABLE:
            try:
                rotated_ip, rotated_hostname = get_ip_for_sending()
                if rotated_ip:
                    tracked_ip = rotated_ip
                    tracked_hostname = rotated_hostname or DEFAULT_HOSTNAME
                    logger.info(f"📊 IP Rotation: {tracked_ip}")
            except Exception as e:
                logger.warning(f"IP rotation failed, using default: {e}")
        
        mx_servers = self.get_mx_servers(recipient_domain)
        if not mx_servers:
            return {'success': False, 'message': 'No MX', 'source_ip': tracked_ip}
        
        signed_message, sender_domain = self.create_message(email_data)
        
        for mx_server in mx_servers[:3]:
            try:
                logger.info(f"📤 {mx_server}")
                
                # Create connection - uses server's default IP for actual sending
                smtp = smtplib.SMTP(mx_server, 25, timeout=30)
                smtp.ehlo(self.hostname)
                
                # Try STARTTLS if available
                tls_used = False
                if smtp.has_extn('STARTTLS'):
                    try:
                        context = ssl.create_default_context()
                        context.check_hostname = False
                        context.verify_mode = ssl.CERT_NONE
                        
                        smtp.starttls(context=context)
                        smtp.ehlo(self.hostname)
                        logger.info("✅ TLS enabled")
                        tls_used = True
                    except Exception as tls_err:
                        logger.warning(f"TLS failed: {tls_err}, using plaintext")
                        tls_used = False
                
                # Send email
                smtp.sendmail(sender, [recipient], signed_message)
                smtp.quit()
                
                logger.info(f"✅ Sent to {recipient} successfully (tracked: {tracked_ip})")
                return {
                    'success': True,
                    'message': 'Email sent',
                    'mx_server': mx_server,
                    'tls': tls_used,
                    'encrypted': tls_used,
                    'source_ip': tracked_ip
                }
                
            except Exception as e:
                logger.warning(f"Failed: {e}")
                try:
                    smtp.quit()
                except:
                    pass
                continue
        
        # Retry logic - EXACT same as original
        if retry_count < 2:
            time.sleep(2 ** retry_count)
            return self.send_email(email_data, retry_count + 1, use_rotation)
        
        return {'success': False, 'message': 'All MX failed', 'source_ip': tracked_ip}


# Global relay instance
relay = RotatedSMTPRelay()


def send_email_sync(email_data: dict, use_rotation: bool = True) -> dict:
    """
    Send email synchronously with IP rotation.
    
    Args:
        email_data: Dict with from, to, subject, html_body, text_body
        use_rotation: Enable IP rotation tracking (default: True)
    
    Returns:
        Result dict
    """
    return relay.send_email(email_data, use_rotation=use_rotation)


async def send_via_relay(email_data: dict, use_rotation: bool = True) -> dict:
    """Async wrapper for send_email."""
    return relay.send_email(email_data, use_rotation=use_rotation)


def get_relay_stats() -> dict:
    """Get IP rotation statistics."""
    if IP_ROTATION_AVAILABLE:
        try:
            stats = list(get_ip_stats())
            return {
                'rotation_enabled': True,
                'ips': stats,
                'active_count': sum(1 for ip in stats if ip['is_active']),
                'total_sent_today': sum(ip['sent_today'] for ip in stats)
            }
        except:
            pass
    return {'rotation_enabled': False}
