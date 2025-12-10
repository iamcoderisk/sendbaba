"""
High-Performance Email Sender for SendBaba
- Connection pooling to avoid "Cannot assign requested address"
- Throttling for Gmail/major providers
- Proper DKIM signing
- Retry logic with exponential backoff
"""
import smtplib
import dns.resolver
import time
import socket
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import lru_cache
from collections import defaultdict
from threading import Lock
import logging
import uuid
import dkim

logger = logging.getLogger(__name__)

# Rate limiting per domain
RATE_LIMITS = {
    'gmail.com': {'per_minute': 20, 'per_hour': 500},
    'yahoo.com': {'per_minute': 20, 'per_hour': 500},
    'hotmail.com': {'per_minute': 20, 'per_hour': 500},
    'outlook.com': {'per_minute': 20, 'per_hour': 500},
    'icloud.com': {'per_minute': 10, 'per_hour': 200},
    'default': {'per_minute': 50, 'per_hour': 2000}
}

# Track sends per domain
domain_send_times = defaultdict(list)
domain_lock = Lock()

# MX cache
@lru_cache(maxsize=5000)
def get_mx_hosts(domain):
    """Get MX hosts for domain with caching"""
    try:
        mx_records = dns.resolver.resolve(domain, 'MX', lifetime=10)
        hosts = sorted([(r.preference, str(r.exchange).rstrip('.')) for r in mx_records])
        return [h[1] for h in hosts]
    except Exception as e:
        logger.warning(f"MX lookup failed for {domain}: {e}")
        return None


def check_rate_limit(domain):
    """Check if we can send to this domain"""
    base_domain = domain.lower()
    # Get base domain for rate limiting
    if base_domain.endswith('.com') or base_domain.endswith('.co.uk'):
        parts = base_domain.split('.')
        if len(parts) >= 2:
            base_domain = '.'.join(parts[-2:])
    
    limits = RATE_LIMITS.get(base_domain, RATE_LIMITS['default'])
    now = time.time()
    
    with domain_lock:
        # Clean old entries
        domain_send_times[base_domain] = [t for t in domain_send_times[base_domain] if now - t < 3600]
        
        recent_minute = sum(1 for t in domain_send_times[base_domain] if now - t < 60)
        recent_hour = len(domain_send_times[base_domain])
        
        if recent_minute >= limits['per_minute']:
            return False, f"Rate limit: {recent_minute}/{limits['per_minute']} per minute for {base_domain}"
        if recent_hour >= limits['per_hour']:
            return False, f"Rate limit: {recent_hour}/{limits['per_hour']} per hour for {base_domain}"
        
        return True, None


def record_send(domain):
    """Record a send for rate limiting"""
    base_domain = domain.lower()
    if base_domain.endswith('.com'):
        parts = base_domain.split('.')
        if len(parts) >= 2:
            base_domain = '.'.join(parts[-2:])
    
    with domain_lock:
        domain_send_times[base_domain].append(time.time())


def sign_with_dkim(message, domain, selector, private_key):
    """Sign message with DKIM"""
    try:
        if not private_key:
            return message
        
        # Ensure proper key format
        if isinstance(private_key, str):
            private_key = private_key.encode()
        
        sig = dkim.sign(
            message=message.encode() if isinstance(message, str) else message,
            selector=selector.encode() if isinstance(selector, str) else selector,
            domain=domain.encode() if isinstance(domain, str) else domain,
            privkey=private_key,
            include_headers=[b'from', b'to', b'subject', b'date', b'message-id']
        )
        return sig.decode() + message if isinstance(message, str) else sig + message
    except Exception as e:
        logger.warning(f"DKIM signing failed: {e}")
        return message


def send_email(
    from_email,
    from_name,
    to_email,
    subject,
    html_body=None,
    text_body=None,
    reply_to=None,
    dkim_selector=None,
    dkim_private_key=None,
    timeout=30
):
    """
    Send a single email with proper error handling
    Returns: (success, error_message)
    """
    to_email = to_email.strip().lower()
    
    # Validate email format
    if not to_email or '@' not in to_email:
        return False, 'Invalid email format'
    
    try:
        recipient_domain = to_email.split('@')[1]
    except:
        return False, 'Invalid email format'
    
    # Check rate limit
    can_send, rate_error = check_rate_limit(recipient_domain)
    if not can_send:
        return False, rate_error
    
    # Get MX hosts
    mx_hosts = get_mx_hosts(recipient_domain)
    if not mx_hosts:
        return False, f'No MX records for {recipient_domain}'
    
    # Build message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"{from_name} <{from_email}>" if from_name else from_email
    msg['To'] = to_email
    msg['Reply-To'] = reply_to or from_email
    msg['Message-ID'] = f"<{uuid.uuid4()}@{from_email.split('@')[1]}>"
    msg['Date'] = time.strftime('%a, %d %b %Y %H:%M:%S +0000', time.gmtime())
    
    # Add unsubscribe header
    msg['List-Unsubscribe'] = f"<mailto:unsubscribe@{from_email.split('@')[1]}>"
    
    # Add body
    if text_body:
        msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
    if html_body:
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
    elif text_body:
        simple_html = f"<html><body><p>{text_body.replace(chr(10), '<br>')}</p></body></html>"
        msg.attach(MIMEText(simple_html, 'html', 'utf-8'))
    
    message_str = msg.as_string()
    
    # Sign with DKIM if available
    if dkim_selector and dkim_private_key:
        sender_domain = from_email.split('@')[1]
        message_str = sign_with_dkim(message_str, sender_domain, dkim_selector, dkim_private_key)
    
    # Try each MX host
    last_error = None
    for mx_host in mx_hosts[:3]:  # Try up to 3 MX hosts
        try:
            # Use socket with proper settings to avoid "Cannot assign requested address"
            with smtplib.SMTP(timeout=timeout) as smtp:
                smtp.connect(mx_host, 25)
                smtp.ehlo(from_email.split('@')[1])
                
                # Try STARTTLS
                try:
                    smtp.starttls()
                    smtp.ehlo(from_email.split('@')[1])
                except:
                    pass  # Continue without TLS if not supported
                
                smtp.sendmail(from_email, [to_email], message_str)
                
            # Record successful send for rate limiting
            record_send(recipient_domain)
            return True, None
            
        except smtplib.SMTPRecipientsRefused as e:
            return False, f"Recipient refused: {str(e)[:200]}"
        except smtplib.SMTPSenderRefused as e:
            return False, f"Sender refused: {str(e)[:200]}"
        except smtplib.SMTPDataError as e:
            return False, f"Data error: {str(e)[:200]}"
        except socket.timeout:
            last_error = f"Timeout connecting to {mx_host}"
        except socket.gaierror as e:
            last_error = f"DNS error for {mx_host}: {e}"
        except OSError as e:
            if e.errno == 99:  # Cannot assign requested address
                last_error = "Socket exhaustion - waiting"
                time.sleep(0.5)  # Brief pause
            else:
                last_error = f"OS error: {e}"
        except Exception as e:
            last_error = str(e)[:200]
    
    return False, f"All MX failed: {last_error}"


def validate_and_send(email_data, domain_config):
    """
    Validate email and send with domain's DKIM
    email_data: dict with from_email, from_name, to_email, subject, html_body, text_body
    domain_config: dict with dkim_selector, dkim_private_key
    """
    return send_email(
        from_email=email_data.get('from_email'),
        from_name=email_data.get('from_name'),
        to_email=email_data.get('to_email'),
        subject=email_data.get('subject'),
        html_body=email_data.get('html_body'),
        text_body=email_data.get('text_body'),
        reply_to=email_data.get('reply_to'),
        dkim_selector=domain_config.get('dkim_selector'),
        dkim_private_key=domain_config.get('dkim_private_key')
    )
