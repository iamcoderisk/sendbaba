"""
World-Class SMTP Relay Server - Fixed
"""
import smtplib
import dns.resolver
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
import logging
from typing import Dict
import time

logger = logging.getLogger(__name__)


class SMTPRelay:
    """Production SMTP relay with proper connection handling"""
    
    def __init__(self):
        self.mx_cache = {}
    
    def get_mx_servers(self, domain: str) -> list:
        """Get MX servers for domain"""
        if domain in self.mx_cache:
            cache_time, mx_list = self.mx_cache[domain]
            if time.time() - cache_time < 3600:  # 1 hour cache
                return mx_list
        
        try:
            mx_records = dns.resolver.resolve(domain, 'MX')
            mx_servers = sorted(
                [(r.preference, str(r.exchange).rstrip('.')) for r in mx_records]
            )
            mx_list = [mx[1] for mx in mx_servers]
            
            # Cache result
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
        """Create properly formatted email"""
        msg = MIMEMultipart('alternative')
        
        # Headers
        msg['From'] = email_data.get('from', 'noreply@sendbaba.com')
        msg['To'] = email_data.get('to')
        msg['Subject'] = email_data.get('subject', 'No Subject')
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain='sendbaba.com')
        
        # Anti-spam headers
        msg['X-Mailer'] = 'SendBaba SMTP 2.0'
        msg['X-Priority'] = '3'
        
        # List management
        if email_data.get('campaign_id'):
            msg['List-Unsubscribe'] = f'<https://sendbaba.com/unsubscribe/{email_data["campaign_id"]}>'
        
        # Content
        text_body = email_data.get('text_body', '')
        html_body = email_data.get('html_body', email_data.get('body', ''))
        
        if text_body:
            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        
        if html_body:
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        elif not text_body:
            # Fallback
            msg.attach(MIMEText('SendBaba Email', 'plain', 'utf-8'))
        
        return msg
    
    def send_email(self, email_data: dict, retry_count: int = 0) -> Dict:
        """Send email via SMTP"""
        recipient = email_data.get('to', '').strip()
        
        if not recipient or '@' not in recipient:
            return {
                'success': False,
                'message': 'Invalid recipient',
                'bounce': True,
                'bounce_type': 'hard'
            }
        
        # Get domain
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
        msg_string = msg.as_string()
        
        # Try each MX server
        last_error = None
        
        for mx_server in mx_servers[:3]:
            try:
                logger.info(f"📤 Sending to {recipient} via {mx_server}")
                
                # Create new SMTP connection for each attempt
                smtp = smtplib.SMTP(timeout=30)
                smtp.connect(mx_server, 25)
                smtp.ehlo('mail.sendbaba.com')
                
                # Try STARTTLS
                try:
                    smtp.starttls()
                    smtp.ehlo('mail.sendbaba.com')
                except:
                    pass
                
                # Send
                smtp.sendmail(
                    email_data.get('from', 'noreply@sendbaba.com'),
                    [recipient],
                    msg_string
                )
                
                smtp.quit()
                
                logger.info(f"✅ Sent to {recipient} via {mx_server}")
                
                return {
                    'success': True,
                    'message': 'Email sent',
                    'mx_server': mx_server
                }
            
            except smtplib.SMTPRecipientsRefused as e:
                logger.warning(f"Recipient refused: {e}")
                return {
                    'success': False,
                    'message': 'Recipient does not exist',
                    'bounce': True,
                    'bounce_type': 'hard'
                }
            
            except smtplib.SMTPDataError as e:
                logger.warning(f"Data error from {mx_server}: {e}")
                last_error = str(e)
                continue
            
            except (smtplib.SMTPConnectError, ConnectionRefusedError, TimeoutError) as e:
                logger.warning(f"Connection error to {mx_server}: {e}")
                last_error = str(e)
                continue
            
            except Exception as e:
                logger.error(f"Error with {mx_server}: {e}")
                last_error = str(e)
                continue
        
        # Retry logic
        if retry_count < 2:
            time.sleep(2 ** retry_count)
            return self.send_email(email_data, retry_count + 1)
        
        return {
            'success': False,
            'message': f'All MX failed: {last_error}',
            'bounce': False,
            'retry': True
        }


# Global instance
relay = SMTPRelay()


def send_email_sync(email_data: dict) -> dict:
    """Synchronous send"""
    return relay.send_email(email_data)
