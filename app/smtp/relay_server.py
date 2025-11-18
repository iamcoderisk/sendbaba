"""
Multi-tenant SMTP Relay Server
Optimized for inbox delivery
"""
import smtplib
import dns.resolver
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
import logging
from typing import Dict
import time
import socket

logger = logging.getLogger(__name__)


class SMTPRelay:
    """Production SMTP relay with inbox optimization"""
    
    def __init__(self):
        self.mx_cache = {}
        self.server_ip = self.get_server_ip()
    
    def get_server_ip(self):
        """Get server public IP"""
        try:
            return socket.gethostbyname(socket.gethostname())
        except:
            return '156.67.29.186'
    
    def get_mx_servers(self, domain: str) -> list:
        """Get MX servers for domain"""
        if domain in self.mx_cache:
            cache_time, mx_list = self.mx_cache[domain]
            if time.time() - cache_time < 3600:
                return mx_list
        
        try:
            mx_records = dns.resolver.resolve(domain, 'MX')
            mx_servers = sorted(
                [(r.preference, str(r.exchange).rstrip('.')) for r in mx_records]
            )
            mx_list = [mx[1] for mx in mx_servers]
            
            self.mx_cache[domain] = (time.time(), mx_list)
            
            logger.info(f"MX servers for {domain}: {mx_list}")
            return mx_list
            
        except dns.resolver.NXDOMAIN:
            logger.error(f"Domain does not exist: {domain}")
            return []
        except dns.resolver.NoAnswer:
            logger.error(f"No MX records for: {domain}")
            return []
        except Exception as e:
            logger.error(f"MX lookup failed for {domain}: {e}")
            return []
    
    def create_message(self, email_data: dict) -> MIMEMultipart:
        """Create properly formatted email for inbox delivery"""
        msg = MIMEMultipart('alternative')
        
        sender = email_data.get('from', 'noreply@sendbaba.com')
        recipient = email_data.get('to')
        
        # Required headers
        msg['From'] = sender
        msg['To'] = recipient
        msg['Subject'] = email_data.get('subject', 'Message from SendBaba')
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain=sender.split('@')[1] if '@' in sender else 'sendbaba.com')
        
        # Inbox optimization headers
        msg['X-Mailer'] = 'SendBaba/2.0'
        msg['X-Priority'] = '3'
        msg['Importance'] = 'Normal'
        msg['MIME-Version'] = '1.0'
        
        # Authentication headers (will be added by MTA)
        msg['X-SendBaba-Server'] = self.server_ip
        
        # List management headers (helps with deliverability)
        campaign_id = email_data.get('campaign_id')
        if campaign_id:
            msg['List-Unsubscribe'] = f'<https://sendbaba.com/unsubscribe/{campaign_id}>'
            msg['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'
        
        # Content
        text_body = email_data.get('text_body', '')
        html_body = email_data.get('html_body', email_data.get('body', ''))
        
        # Always include text version (improves deliverability)
        if not text_body and html_body:
            # Strip HTML for text version
            import re
            text_body = re.sub('<[^<]+?>', '', html_body)
        
        if text_body:
            text_part = MIMEText(text_body, 'plain', 'utf-8')
            msg.attach(text_part)
        
        if html_body:
            html_part = MIMEText(html_body, 'html', 'utf-8')
            msg.attach(html_part)
        
        if not text_body and not html_body:
            # Fallback
            default_text = email_data.get('subject', 'Message from SendBaba')
            text_part = MIMEText(default_text, 'plain', 'utf-8')
            msg.attach(text_part)
        
        return msg
    
    def send_email(self, email_data: dict, retry_count: int = 0) -> Dict:
        """Send email with proper error handling"""
        recipient = email_data.get('to', '').strip()
        sender = email_data.get('from', 'noreply@sendbaba.com')
        
        if not recipient or '@' not in recipient:
            return {
                'success': False,
                'message': 'Invalid recipient',
                'bounce': True,
                'bounce_type': 'hard'
            }
        
        # Get recipient domain
        try:
            recipient_domain = recipient.split('@')[1]
        except:
            return {
                'success': False,
                'message': 'Invalid email format',
                'bounce': True,
                'bounce_type': 'hard'
            }
        
        # Get MX servers
        mx_servers = self.get_mx_servers(recipient_domain)
        
        if not mx_servers:
            return {
                'success': False,
                'message': 'No MX servers found',
                'bounce': True,
                'bounce_type': 'hard'
            }
        
        # Create message
        msg = self.create_message(email_data)
        
        # Try each MX server
        last_error = None
        
        for mx_server in mx_servers[:3]:
            try:
                logger.info(f"📤 Connecting to {mx_server} for {recipient}")
                
                # Create SMTP connection
                smtp = smtplib.SMTP(timeout=30)
                smtp.set_debuglevel(0)
                
                # Connect
                smtp.connect(mx_server, 25)
                
                # EHLO with proper hostname
                smtp.ehlo('mail.sendbaba.com')
                
                # Try STARTTLS
                try:
                    smtp.starttls()
                    smtp.ehlo('mail.sendbaba.com')
                    logger.info(f"✅ STARTTLS successful for {mx_server}")
                except:
                    logger.warning(f"⚠️  STARTTLS not supported by {mx_server}")
                
                # Send email
                smtp.sendmail(sender, [recipient], msg.as_string())
                smtp.quit()
                
                logger.info(f"✅ Email sent to {recipient} via {mx_server}")
                
                return {
                    'success': True,
                    'message': 'Email sent successfully',
                    'mx_server': mx_server
                }
            
            except smtplib.SMTPRecipientsRefused as e:
                logger.warning(f"❌ Recipient refused by {mx_server}: {e}")
                return {
                    'success': False,
                    'message': 'Recipient does not exist or rejected',
                    'bounce': True,
                    'bounce_type': 'hard'
                }
            
            except smtplib.SMTPDataError as e:
                logger.warning(f"⚠️  Data error from {mx_server}: {e}")
                last_error = str(e)
                continue
            
            except (smtplib.SMTPConnectError, ConnectionRefusedError, TimeoutError, OSError) as e:
                logger.warning(f"⚠️  Connection error to {mx_server}: {e}")
                last_error = str(e)
                continue
            
            except Exception as e:
                logger.error(f"❌ Unexpected error with {mx_server}: {e}")
                last_error = str(e)
                continue
        
        # All MX servers failed - retry
        if retry_count < 2:
            logger.info(f"🔄 Retrying email to {recipient} (attempt {retry_count + 2}/3)")
            time.sleep(2 ** retry_count)
            return self.send_email(email_data, retry_count + 1)
        
        return {
            'success': False,
            'message': f'All MX servers failed: {last_error}',
            'bounce': False,
            'retry': True
        }


# Global instance
relay = SMTPRelay()


def send_email_sync(email_data: dict) -> dict:
    """Synchronous send wrapper"""
    return relay.send_email(email_data)
