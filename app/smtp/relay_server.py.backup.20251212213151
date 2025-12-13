"""
SendBaba SMTP with Working TLS - FINAL FIX
"""
import smtplib
import ssl
import dns.resolver
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
import logging
try:
    from premailer import transform as inline_css
    HAS_PREMAILER = True
except ImportError:
    HAS_PREMAILER = False
    inline_css = None
from typing import Dict, Tuple, Optional
import time
import sys
import os

sys.path.insert(0, '/opt/sendbaba-staging')

logger = logging.getLogger(__name__)


class DomainDKIM:
    """DKIM signing"""
    def __init__(self, domain: str, selector: str = 'mail'):
        self.domain = domain
        self.selector = selector
        self.private_key_path = f'/opt/sendbaba-staging/data/dkim/{domain}_private.key'
        self.private_key = None
        
        if os.path.exists(self.private_key_path):
            try:
                with open(self.private_key_path, 'rb') as f:
                    self.private_key = f.read()
                logger.info(f"✅ DKIM: {domain}")
            except:
                pass
    
    def sign(self, message_bytes: bytes) -> bytes:
        if not self.private_key:
            return message_bytes
        try:
            import dkim
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


class ProfessionalSMTPRelay:
    """Professional SMTP with TLS"""
    
    def __init__(self):
        self.mx_cache = {}
        self.dkim_cache = {}
        self.hostname = 'mail.sendbaba.com'
        logger.info("✅ SMTP Relay initialized")
    
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
        msg = MIMEMultipart('alternative')
        
        # FIXED: Properly handle empty strings for sender
        sender = email_data.get('from') or email_data.get('from_email') or 'noreply@sendbaba.com'
        if not sender or '@' not in str(sender):
            sender = 'noreply@sendbaba.com'
        sender = str(sender).strip()
        
        # Extract domain safely
        try:
            sender_domain = sender.split('@')[1] if '@' in sender else 'sendbaba.com'
        except:
            sender_domain = 'sendbaba.com'
        
        # Get from_name, default to domain name
        from_name = email_data.get('from_name') or sender_domain.split('.')[0].title()
        from_name = str(from_name).strip() if from_name else 'SendBaba'
        
        recipient = email_data.get('to') or email_data.get('to_email')
        
        # Log what we're using
        logger.info(f"From: {from_name} <{sender}>")
        
        # Professional headers for better deliverability
        msg['From'] = f'{from_name} <{sender}>'
        msg['To'] = recipient
        msg['Subject'] = email_data.get('subject', 'Message')
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain=sender_domain)
        msg['MIME-Version'] = '1.0'
        
        # Return-Path for bounces
        msg['Return-Path'] = f'bounces@{sender_domain}'
        
        # Reply-To (use provided or same as sender)
        reply_to = email_data.get('reply_to', sender)
        msg['Reply-To'] = reply_to
        
        # List-Unsubscribe header (helps with spam score)
        unsubscribe_url = f'https://sendbaba.com/unsubscribe?email={recipient}&domain={sender_domain}'
        msg['List-Unsubscribe'] = f'<{unsubscribe_url}>'
        msg['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'
        
        # Precedence header
        msg['Precedence'] = 'bulk'
        
        # DO NOT include X-Mailer (can trigger spam filters)
        
        text_body = email_data.get('text_body', '')
        html_body = email_data.get('html_body', '')
        
        # Always include both text and HTML versions
        if not text_body and html_body:
            # Generate text from HTML
            import re
            text_body = re.sub('<[^<]+?>', '', html_body)
            text_body = text_body.strip()
        
        if text_body:
            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        if html_body:
            # Inline CSS for email client compatibility (Gmail strips <style> tags)
            if HAS_PREMAILER:
                try:
                    html_body = inline_css(html_body, remove_classes=True, strip_important=False)
                    logger.info("✅ CSS inlined for email")
                except Exception as css_err:
                    logger.warning(f"CSS inline failed: {css_err}")
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        elif not text_body:
            msg.attach(MIMEText('Message from ' + sender_domain, 'plain', 'utf-8'))
        
        message_bytes = msg.as_bytes()
        
        dkim_handler = self.get_dkim_for_domain(sender_domain)
        if dkim_handler and dkim_handler.private_key:
            signed = dkim_handler.sign(message_bytes)
            if signed != message_bytes:
                logger.info(f"✅ DKIM signed")
                return signed, sender_domain
        
        return message_bytes, sender_domain
    
    def send_email(self, email_data: dict, retry_count: int = 0) -> Dict:
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
        
        mx_servers = self.get_mx_servers(recipient_domain)
        if not mx_servers:
            return {'success': False, 'message': 'No MX'}
        
        signed_message, sender_domain = self.create_message(email_data)
        
        for mx_server in mx_servers[:3]:
            try:
                logger.info(f"📤 {mx_server}")
                
                # Create connection with proper hostname
                smtp = smtplib.SMTP(mx_server, 25, timeout=30)
                smtp.ehlo(self.hostname)
                
                # Try STARTTLS if available
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
                else:
                    tls_used = False
                
                # Send email
                smtp.sendmail(sender, [recipient], signed_message)
                smtp.quit()
                
                logger.info(f"✅ Sent to {recipient} successfully")
                return {
                    'success': True,
                    'message': 'Email sent',
                    'mx_server': mx_server,
                    'tls': tls_used,
                    'encrypted': tls_used
                }
                
            except Exception as e:
                logger.warning(f"Failed: {e}")
                try:
                    smtp.quit()
                except:
                    pass
                continue
        
        if retry_count < 2:
            time.sleep(2 ** retry_count)
            return self.send_email(email_data, retry_count + 1)
        
        return {'success': False, 'message': 'All MX failed'}


relay = ProfessionalSMTPRelay()

def send_email_sync(email_data: dict) -> dict:
    return relay.send_email(email_data)

async def send_via_relay(email_data: dict) -> dict:
    return relay.send_email(email_data)
