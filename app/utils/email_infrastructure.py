"""
SendBaba Enterprise Email Infrastructure
- Multi-IP rotation
- Per-provider throttling
- IP warmup tracking
- Smart routing based on reputation
"""
import time
import random
import socket
import smtplib
import dns.resolver
from collections import defaultdict
from threading import Lock
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging
import hashlib

logger = logging.getLogger(__name__)

# ============================================
# IP POOL CONFIGURATION
# ============================================

@dataclass
class SendingIP:
    ip: str
    hostname: str
    daily_limit: int = 10000
    hourly_limit: int = 1000
    warmup_day: int = 1  # Day 1 = new IP, Day 30+ = fully warmed
    is_active: bool = True
    reputation_score: float = 100.0  # 0-100, higher is better
    sent_today: int = 0
    sent_this_hour: int = 0
    last_reset_date: str = ""
    last_reset_hour: int = -1
    consecutive_failures: int = 0
    
    def reset_counters_if_needed(self):
        """Reset daily/hourly counters"""
        now = datetime.utcnow()
        today = now.strftime("%Y-%m-%d")
        current_hour = now.hour
        
        if self.last_reset_date != today:
            self.sent_today = 0
            self.last_reset_date = today
            
        if self.last_reset_hour != current_hour:
            self.sent_this_hour = 0
            self.last_reset_hour = current_hour
    
    def can_send(self) -> Tuple[bool, str]:
        """Check if this IP can send"""
        self.reset_counters_if_needed()
        
        if not self.is_active:
            return False, "IP is inactive"
        
        if self.consecutive_failures >= 10:
            return False, "Too many consecutive failures"
        
        # Warmup limits (conservative)
        warmup_daily_limit = min(self.daily_limit, self._warmup_limit())
        
        if self.sent_today >= warmup_daily_limit:
            return False, f"Daily limit reached ({self.sent_today}/{warmup_daily_limit})"
        
        if self.sent_this_hour >= self.hourly_limit:
            return False, f"Hourly limit reached ({self.sent_this_hour}/{self.hourly_limit})"
        
        return True, "OK"
    
    def _warmup_limit(self) -> int:
        """Calculate daily limit based on warmup day"""
        # Warmup schedule: gradual increase over 30 days
        warmup_schedule = {
            1: 100, 2: 200, 3: 300, 4: 500, 5: 750,
            6: 1000, 7: 1500, 8: 2000, 9: 2500, 10: 3000,
            11: 3500, 12: 4000, 13: 4500, 14: 5000, 15: 5500,
            16: 6000, 17: 6500, 18: 7000, 19: 7500, 20: 8000,
            21: 8500, 22: 9000, 23: 9500, 24: 10000, 25: 12000,
            26: 15000, 27: 20000, 28: 25000, 29: 30000, 30: 50000,
        }
        return warmup_schedule.get(self.warmup_day, 50000)
    
    def record_send(self, success: bool):
        """Record a send attempt"""
        self.sent_today += 1
        self.sent_this_hour += 1
        
        if success:
            self.consecutive_failures = 0
            # Slightly improve reputation on success
            self.reputation_score = min(100, self.reputation_score + 0.01)
        else:
            self.consecutive_failures += 1
            # Decrease reputation on failure
            self.reputation_score = max(0, self.reputation_score - 0.5)


# ============================================
# PROVIDER RATE LIMITS
# ============================================

PROVIDER_LIMITS = {
    # Format: {domain: {per_minute: X, per_hour: Y, per_ip_per_minute: Z}}
    'gmail.com': {'per_minute': 60, 'per_hour': 1000, 'per_ip_per_minute': 10},
    'googlemail.com': {'per_minute': 60, 'per_hour': 1000, 'per_ip_per_minute': 10},
    'yahoo.com': {'per_minute': 50, 'per_hour': 800, 'per_ip_per_minute': 8},
    'yahoo.co.uk': {'per_minute': 50, 'per_hour': 800, 'per_ip_per_minute': 8},
    'hotmail.com': {'per_minute': 50, 'per_hour': 800, 'per_ip_per_minute': 8},
    'outlook.com': {'per_minute': 50, 'per_hour': 800, 'per_ip_per_minute': 8},
    'live.com': {'per_minute': 50, 'per_hour': 800, 'per_ip_per_minute': 8},
    'icloud.com': {'per_minute': 30, 'per_hour': 500, 'per_ip_per_minute': 5},
    'aol.com': {'per_minute': 50, 'per_hour': 800, 'per_ip_per_minute': 8},
    'default': {'per_minute': 100, 'per_hour': 2000, 'per_ip_per_minute': 20},
}


# ============================================
# EMAIL INFRASTRUCTURE MANAGER
# ============================================

class EmailInfrastructure:
    """Manages multi-IP email sending with smart routing"""
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._ip_lock = Lock()
        self._rate_lock = Lock()
        
        # Initialize IP pool
        self.ip_pool: Dict[str, SendingIP] = {}
        self._init_ip_pool()
        
        # Rate limiting trackers
        self._provider_sends: Dict[str, List[float]] = defaultdict(list)
        self._ip_provider_sends: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        
        logger.info(f"Email Infrastructure initialized with {len(self.ip_pool)} IPs")
    
    def _init_ip_pool(self):
        """Initialize the IP pool with available servers"""
        # Configure your IPs here
        ips_config = [
            # (IP, hostname, warmup_day, daily_limit)
            ('156.67.29.186', 'mail1.sendbaba.com', 15, 20000),   # Main server - partially warmed
            ('161.97.162.82', 'mail2.sendbaba.com', 5, 5000),     # Worker 1 - newer
            ('207.244.232.12', 'mail3.sendbaba.com', 5, 5000),    # Worker 2 - newer
            ('31.220.109.225', 'mail4.sendbaba.com', 5, 5000),    # Worker 3 - newer
        ]
        
        for ip, hostname, warmup_day, daily_limit in ips_config:
            self.ip_pool[ip] = SendingIP(
                ip=ip,
                hostname=hostname,
                warmup_day=warmup_day,
                daily_limit=daily_limit,
                hourly_limit=daily_limit // 10,
            )
    
    def get_provider(self, email: str) -> str:
        """Extract provider from email"""
        try:
            domain = email.split('@')[1].lower()
            # Map common domains
            if 'gmail' in domain or 'googlemail' in domain:
                return 'gmail.com'
            if 'yahoo' in domain:
                return 'yahoo.com'
            if 'hotmail' in domain or 'outlook' in domain or 'live' in domain:
                return 'outlook.com'
            return domain
        except:
            return 'default'
    
    def check_provider_rate_limit(self, provider: str) -> Tuple[bool, float]:
        """Check if we can send to this provider"""
        limits = PROVIDER_LIMITS.get(provider, PROVIDER_LIMITS['default'])
        now = time.time()
        
        with self._rate_lock:
            # Clean old entries
            self._provider_sends[provider] = [
                t for t in self._provider_sends[provider] if now - t < 3600
            ]
            
            sends_last_minute = sum(1 for t in self._provider_sends[provider] if now - t < 60)
            sends_last_hour = len(self._provider_sends[provider])
            
            if sends_last_minute >= limits['per_minute']:
                wait_time = 60 - (now - min(t for t in self._provider_sends[provider] if now - t < 60))
                return False, wait_time
            
            if sends_last_hour >= limits['per_hour']:
                return False, 300  # Wait 5 minutes
            
            return True, 0
    
    def check_ip_provider_rate_limit(self, ip: str, provider: str) -> Tuple[bool, float]:
        """Check per-IP rate limit for a provider"""
        limits = PROVIDER_LIMITS.get(provider, PROVIDER_LIMITS['default'])
        now = time.time()
        
        with self._rate_lock:
            self._ip_provider_sends[ip][provider] = [
                t for t in self._ip_provider_sends[ip][provider] if now - t < 60
            ]
            
            sends_last_minute = len(self._ip_provider_sends[ip][provider])
            
            if sends_last_minute >= limits['per_ip_per_minute']:
                oldest = min(self._ip_provider_sends[ip][provider])
                wait_time = 60 - (now - oldest)
                return False, wait_time
            
            return True, 0
    
    def select_best_ip(self, recipient_email: str) -> Optional[SendingIP]:
        """Select the best IP for sending to this recipient"""
        provider = self.get_provider(recipient_email)
        
        # Check global provider rate limit first
        can_send, wait_time = self.check_provider_rate_limit(provider)
        if not can_send:
            logger.debug(f"Provider {provider} rate limited, wait {wait_time:.1f}s")
            return None
        
        # Find available IPs
        available_ips = []
        
        with self._ip_lock:
            for ip, sending_ip in self.ip_pool.items():
                can_send, reason = sending_ip.can_send()
                if not can_send:
                    continue
                
                # Check per-IP provider rate limit
                can_send_ip, _ = self.check_ip_provider_rate_limit(ip, provider)
                if not can_send_ip:
                    continue
                
                available_ips.append(sending_ip)
        
        if not available_ips:
            logger.warning(f"No available IPs for {provider}")
            return None
        
        # Select IP with best reputation and lowest usage
        # Weighted random selection favoring better reputation
        weights = [ip.reputation_score * (1 - ip.sent_today / max(ip._warmup_limit(), 1)) for ip in available_ips]
        total_weight = sum(weights)
        
        if total_weight <= 0:
            return random.choice(available_ips)
        
        # Weighted random selection
        r = random.uniform(0, total_weight)
        cumulative = 0
        for ip, weight in zip(available_ips, weights):
            cumulative += weight
            if r <= cumulative:
                return ip
        
        return available_ips[0]
    
    def record_send(self, ip: str, recipient_email: str, success: bool):
        """Record a send attempt"""
        provider = self.get_provider(recipient_email)
        now = time.time()
        
        with self._ip_lock:
            if ip in self.ip_pool:
                self.ip_pool[ip].record_send(success)
        
        with self._rate_lock:
            self._provider_sends[provider].append(now)
            self._ip_provider_sends[ip][provider].append(now)
    
    def get_stats(self) -> dict:
        """Get current infrastructure stats"""
        stats = {
            'total_ips': len(self.ip_pool),
            'active_ips': sum(1 for ip in self.ip_pool.values() if ip.is_active),
            'ips': {}
        }
        
        for ip, sending_ip in self.ip_pool.items():
            sending_ip.reset_counters_if_needed()
            stats['ips'][ip] = {
                'hostname': sending_ip.hostname,
                'warmup_day': sending_ip.warmup_day,
                'daily_limit': sending_ip._warmup_limit(),
                'sent_today': sending_ip.sent_today,
                'sent_this_hour': sending_ip.sent_this_hour,
                'reputation': round(sending_ip.reputation_score, 2),
                'is_active': sending_ip.is_active,
            }
        
        return stats


# Global instance
_infrastructure: Optional[EmailInfrastructure] = None

def get_infrastructure() -> EmailInfrastructure:
    """Get the global email infrastructure instance"""
    global _infrastructure
    if _infrastructure is None:
        _infrastructure = EmailInfrastructure()
    return _infrastructure


# ============================================
# SMART EMAIL SENDER
# ============================================

def send_email_smart(
    from_email: str,
    from_name: str,
    to_email: str,
    subject: str,
    html_body: str = None,
    text_body: str = None,
    reply_to: str = None,
    dkim_selector: str = None,
    dkim_private_key: str = None,
    message_id: str = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    Send email using smart IP rotation
    Returns: (success, message, ip_used)
    """
    import uuid
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    infra = get_infrastructure()
    
    # Select best IP
    sending_ip = infra.select_best_ip(to_email)
    if not sending_ip:
        return False, "No available sending IPs - rate limited", None
    
    ip = sending_ip.ip
    hostname = sending_ip.hostname
    
    # Build message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"{from_name} <{from_email}>" if from_name else from_email
    msg['To'] = to_email
    msg['Reply-To'] = reply_to or from_email
    msg['Message-ID'] = message_id or f"<{uuid.uuid4()}@{hostname}>"
    msg['Date'] = time.strftime('%a, %d %b %Y %H:%M:%S +0000', time.gmtime())
    msg['X-Mailer'] = 'SendBaba/1.0'
    
    if text_body:
        msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
    if html_body:
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
    
    message_str = msg.as_string()
    
    # DKIM sign if available
    if dkim_selector and dkim_private_key:
        try:
            import dkim
            sender_domain = from_email.split('@')[1]
            sig = dkim.sign(
                message=message_str.encode(),
                selector=dkim_selector.encode(),
                domain=sender_domain.encode(),
                privkey=dkim_private_key.encode() if isinstance(dkim_private_key, str) else dkim_private_key,
                include_headers=[b'from', b'to', b'subject', b'date', b'message-id']
            )
            message_str = sig.decode() + message_str
        except Exception as e:
            logger.warning(f"DKIM signing failed: {e}")
    
    # Get MX for recipient
    try:
        recipient_domain = to_email.split('@')[1]
        mx_records = dns.resolver.resolve(recipient_domain, 'MX', lifetime=10)
        mx_hosts = sorted([(r.preference, str(r.exchange).rstrip('.')) for r in mx_records])
    except Exception as e:
        infra.record_send(ip, to_email, False)
        return False, f"MX lookup failed: {e}", ip
    
    # Try to send via each MX
    last_error = None
    for _, mx_host in mx_hosts[:3]:
        try:
            # Bind to specific IP
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(30)
            sock.bind((ip, 0))
            sock.connect((mx_host, 25))
            
            smtp = smtplib.SMTP()
            smtp.sock = sock
            smtp.file = sock.makefile('rb')
            smtp._host = mx_host
            
            # Get greeting
            code, msg_resp = smtp.getreply()
            if code != 220:
                raise smtplib.SMTPConnectError(code, msg_resp)
            
            smtp.ehlo(hostname)
            
            # Try STARTTLS
            try:
                smtp.starttls()
                smtp.ehlo(hostname)
            except:
                pass
            
            smtp.sendmail(from_email, [to_email], message_str)
            smtp.quit()
            
            infra.record_send(ip, to_email, True)
            return True, "Sent successfully", ip
            
        except smtplib.SMTPRecipientsRefused as e:
            last_error = f"Recipient refused: {e}"
            break  # Don't retry for recipient errors
        except smtplib.SMTPDataError as e:
            last_error = f"Data error: {e}"
            if b'rate limit' in str(e).lower().encode() or b'spam' in str(e).lower().encode():
                # Rate limited - mark IP as having issues
                infra.record_send(ip, to_email, False)
                break
        except Exception as e:
            last_error = str(e)
            continue
    
    infra.record_send(ip, to_email, False)
    return False, f"Send failed: {last_error}", ip
