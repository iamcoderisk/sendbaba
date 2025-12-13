"""
SendBaba Enterprise Email Engine
================================
Production-grade email sending with:
- IP rotation & load balancing
- Per-provider rate limiting (Gmail, Yahoo, Outlook, etc.)
- IP warmup management
- Reputation tracking
- DKIM signing
- Bounce handling
- Smart retry logic

Author: SendBaba Engineering
"""
import os
import sys
import time
import uuid
import socket
import smtplib
import hashlib
import logging
import dns.resolver
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION
# ============================================

# Available sending IPs (add more as you scale)
SENDING_IPS = [
    {
        'ip': '156.67.29.186',
        'hostname': 'mail.sendbaba.com',
        'priority': 1,
        'warmup_day': 31,  # Fully warmed
    },
    {
        'ip': '161.97.162.82',
        'hostname': 'mail2.sendbaba.com',
        'priority': 2,
        'warmup_day': 31,  # Fully warmed
    },
    {
        'ip': '207.244.232.12',
        'hostname': 'mail3.sendbaba.com',
        'priority': 3,
        'warmup_day': 31,  # Fully warmed
    },
    {
        'ip': '31.220.109.225',
        'hostname': 'mail4.sendbaba.com',
        'priority': 4,
        'warmup_day': 31,  # Fully warmed
    },
]

# Provider-specific rate limits (emails per minute)
PROVIDER_LIMITS = {
    'gmail.com': {'per_minute': 20, 'per_hour': 500, 'per_day': 2000},
    'googlemail.com': {'per_minute': 20, 'per_hour': 500, 'per_day': 2000},
    'yahoo.com': {'per_minute': 15, 'per_hour': 400, 'per_day': 1500},
    'yahoo.co.uk': {'per_minute': 15, 'per_hour': 400, 'per_day': 1500},
    'outlook.com': {'per_minute': 20, 'per_hour': 500, 'per_day': 2000},
    'hotmail.com': {'per_minute': 20, 'per_hour': 500, 'per_day': 2000},
    'live.com': {'per_minute': 20, 'per_hour': 500, 'per_day': 2000},
    'icloud.com': {'per_minute': 10, 'per_hour': 200, 'per_day': 1000},
    'aol.com': {'per_minute': 15, 'per_hour': 300, 'per_day': 1200},
    'default': {'per_minute': 30, 'per_hour': 1000, 'per_day': 5000},
}

# Warmup schedule (day -> max emails per day)
WARMUP_SCHEDULE = {
    1: 50, 2: 100, 3: 150, 4: 200, 5: 300,
    6: 400, 7: 500, 8: 650, 9: 800, 10: 1000,
    11: 1250, 12: 1500, 13: 1750, 14: 2000, 15: 2500,
    16: 3000, 17: 3500, 18: 4000, 19: 4500, 20: 5000,
    21: 6000, 22: 7000, 23: 8000, 24: 9000, 25: 10000,
    26: 12500, 27: 15000, 28: 20000, 29: 25000, 30: 35000,
    31: 50000,  # Day 31+ = fully warmed
}

# ============================================
# DATA CLASSES
# ============================================

@dataclass
class SendingIP:
    """Represents a sending IP with tracking"""
    ip: str
    hostname: str
    priority: int = 1
    warmup_day: int = 1
    is_active: bool = True
    reputation: float = 100.0
    sent_today: int = 0
    sent_this_hour: int = 0
    failed_today: int = 0
    last_reset_date: str = ""
    last_reset_hour: int = -1
    consecutive_failures: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False)
    
    def reset_if_needed(self):
        """Reset counters for new day/hour"""
        now = datetime.utcnow()
        today = now.strftime("%Y-%m-%d")
        hour = now.hour
        
        with self._lock:
            if self.last_reset_date != today:
                self.sent_today = 0
                self.failed_today = 0
                self.last_reset_date = today
                self.warmup_day = min(self.warmup_day + 1, 31)
            
            if self.last_reset_hour != hour:
                self.sent_this_hour = 0
                self.last_reset_hour = hour
    
    @property
    def daily_limit(self) -> int:
        """Get daily limit based on warmup day"""
        return WARMUP_SCHEDULE.get(self.warmup_day, 50000)
    
    @property
    def hourly_limit(self) -> int:
        """Hourly limit = daily / 12 (spread across business hours)"""
        return max(100, self.daily_limit // 12)
    
    def can_send(self) -> Tuple[bool, str]:
        """Check if IP can send"""
        self.reset_if_needed()
        
        if not self.is_active:
            return False, "IP inactive"
        
        if self.consecutive_failures >= 10:
            return False, "Too many failures"
        
        if self.sent_today >= self.daily_limit:
            return False, f"Daily limit ({self.daily_limit})"
        
        if self.sent_this_hour >= self.hourly_limit:
            return False, f"Hourly limit ({self.hourly_limit})"
        
        return True, "OK"
    
    def record_success(self):
        """Record successful send"""
        with self._lock:
            self.sent_today += 1
            self.sent_this_hour += 1
            self.consecutive_failures = 0
            self.reputation = min(100, self.reputation + 0.01)
    
    def record_failure(self, is_hard_bounce: bool = False):
        """Record failed send"""
        with self._lock:
            self.sent_today += 1
            self.sent_this_hour += 1
            self.failed_today += 1
            self.consecutive_failures += 1
            
            # Reduce reputation more for hard bounces
            penalty = 1.0 if is_hard_bounce else 0.1
            self.reputation = max(0, self.reputation - penalty)


class ProviderThrottle:
    """Rate limiting per email provider"""
    
    def __init__(self):
        self._counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {
            'minute': 0, 'hour': 0, 'day': 0,
            'last_minute': '', 'last_hour': '', 'last_day': ''
        })
        self._lock = Lock()
    
    def _get_provider(self, email: str) -> str:
        """Extract provider from email"""
        domain = email.split('@')[-1].lower()
        return domain if domain in PROVIDER_LIMITS else 'default'
    
    def _reset_if_needed(self, provider: str):
        """Reset counters for new time periods"""
        now = datetime.utcnow()
        minute_key = now.strftime("%Y-%m-%d-%H-%M")
        hour_key = now.strftime("%Y-%m-%d-%H")
        day_key = now.strftime("%Y-%m-%d")
        
        data = self._counts[provider]
        
        if data['last_minute'] != minute_key:
            data['minute'] = 0
            data['last_minute'] = minute_key
        
        if data['last_hour'] != hour_key:
            data['hour'] = 0
            data['last_hour'] = hour_key
        
        if data['last_day'] != day_key:
            data['day'] = 0
            data['last_day'] = day_key
    
    def can_send(self, email: str) -> Tuple[bool, str, float]:
        """
        Check if we can send to this provider
        Returns: (can_send, reason, wait_seconds)
        """
        provider = self._get_provider(email)
        limits = PROVIDER_LIMITS.get(provider, PROVIDER_LIMITS['default'])
        
        with self._lock:
            self._reset_if_needed(provider)
            data = self._counts[provider]
            
            if data['minute'] >= limits['per_minute']:
                return False, f"{provider} minute limit", 60.0
            
            if data['hour'] >= limits['per_hour']:
                return False, f"{provider} hour limit", 300.0
            
            if data['day'] >= limits['per_day']:
                return False, f"{provider} day limit", 3600.0
            
            return True, "OK", 0.0
    
    def record_send(self, email: str):
        """Record a send to provider"""
        provider = self._get_provider(email)
        
        with self._lock:
            self._reset_if_needed(provider)
            self._counts[provider]['minute'] += 1
            self._counts[provider]['hour'] += 1
            self._counts[provider]['day'] += 1
    
    def get_stats(self) -> Dict:
        """Get current throttle stats"""
        with self._lock:
            return {p: dict(d) for p, d in self._counts.items()}


# ============================================
# EMAIL ENGINE (Singleton)
# ============================================

class EmailEngine:
    """
    SendBaba Email Engine
    Handles all email sending with smart routing
    """
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
        
        self._ips: List[SendingIP] = []
        self._throttle = ProviderThrottle()
        self._mx_cache: Dict[str, Tuple[str, datetime]] = {}
        self._mx_cache_ttl = 3600  # 1 hour
        
        # Initialize IPs
        for ip_config in SENDING_IPS:
            self._ips.append(SendingIP(
                ip=ip_config['ip'],
                hostname=ip_config['hostname'],
                priority=ip_config.get('priority', 1),
                warmup_day=ip_config.get('warmup_day', 31),  # Default to fully warmed
                is_active=True
            ))
        
        self._initialized = True
        logger.info(f"📧 EmailEngine initialized with {len(self._ips)} IPs")
    
    def _get_mx_server(self, domain: str) -> Optional[str]:
        """Get MX server for domain with caching"""
        now = datetime.utcnow()
        
        # Check cache
        if domain in self._mx_cache:
            mx, cached_at = self._mx_cache[domain]
            if (now - cached_at).seconds < self._mx_cache_ttl:
                return mx
        
        try:
            records = dns.resolver.resolve(domain, 'MX')
            mx = str(sorted(records, key=lambda x: x.preference)[0].exchange).rstrip('.')
            self._mx_cache[domain] = (mx, now)
            return mx
        except Exception as e:
            logger.warning(f"MX lookup failed for {domain}: {e}")
            return None
    
    def _select_ip(self) -> Optional[SendingIP]:
        """Select best available IP for sending"""
        available = []
        
        for ip in self._ips:
            can_send, reason = ip.can_send()
            if can_send:
                available.append(ip)
        
        if not available:
            return None
        
        # Sort by: reputation (desc), sent_today (asc), priority (asc)
        available.sort(key=lambda x: (-x.reputation, x.sent_today, x.priority))
        return available[0]
    
    def _build_message(self, from_email: str, to_email: str, subject: str,
                       html_body: str, text_body: str = None,
                       reply_to: str = None, headers: Dict = None) -> MIMEMultipart:
        """Build email message"""
        msg = MIMEMultipart('alternative')
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg['Message-ID'] = f"<{uuid.uuid4()}@sendbaba.com>"
        msg['Date'] = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
        msg['X-Mailer'] = 'SendBaba/1.0'
        
        if reply_to:
            msg['Reply-To'] = reply_to
        
        # Custom headers
        if headers:
            for key, value in headers.items():
                msg[key] = value
        
        # Add body parts
        if text_body:
            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        if html_body:
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        return msg
    
    def send(self, from_email: str, to_email: str, subject: str,
             html_body: str, text_body: str = None, reply_to: str = None,
             campaign_id: str = None, headers: Dict = None) -> Dict:
        """
        Send an email with smart routing
        
        Returns:
            {
                'success': bool,
                'message_id': str,
                'ip_used': str,
                'mx_server': str,
                'error': str (if failed),
                'retry': bool (if should retry)
            }
        """
        result = {
            'success': False,
            'message_id': None,
            'ip_used': None,
            'mx_server': None,
            'error': None,
            'retry': False
        }
        
        # Validate email
        if not to_email or '@' not in to_email:
            result['error'] = 'Invalid email address'
            return result
        
        domain = to_email.split('@')[1].lower()
        
        # Check provider throttle
        can_send, reason, wait_time = self._throttle.can_send(to_email)
        if not can_send:
            result['error'] = f'Rate limited: {reason}'
            result['retry'] = True
            result['wait_seconds'] = wait_time
            return result
        
        # Get MX server
        mx_server = self._get_mx_server(domain)
        if not mx_server:
            result['error'] = f'No MX record for {domain}'
            return result
        
        result['mx_server'] = mx_server
        
        # Select sending IP
        sending_ip = self._select_ip()
        if not sending_ip:
            result['error'] = 'No available sending IPs'
            result['retry'] = True
            result['wait_seconds'] = 300
            return result
        
        result['ip_used'] = sending_ip.ip
        
        # Build message
        msg = self._build_message(
            from_email, to_email, subject, html_body, text_body, reply_to,
            headers={'X-Campaign-ID': campaign_id} if campaign_id else None
        )
        result['message_id'] = msg['Message-ID']
        
        # Send via SMTP
        try:
            # Create socket bound to our IP
            with smtplib.SMTP(timeout=30) as server:
                # Bind to specific IP (for multi-IP setups)
                if len(self._ips) > 1:
                    server.sock = socket.create_connection(
                        (mx_server, 25),
                        timeout=30,
                        source_address=(sending_ip.ip, 0)
                    )
                else:
                    server.connect(mx_server, 25)
                
                server.ehlo(sending_ip.hostname)
                
                # Try STARTTLS
                try:
                    server.starttls()
                    server.ehlo(sending_ip.hostname)
                except smtplib.SMTPNotSupportedError:
                    pass  # Server doesn't support STARTTLS
                except Exception:
                    pass  # Continue without TLS
                
                server.sendmail(from_email, [to_email], msg.as_string())
            
            # Record success
            sending_ip.record_success()
            self._throttle.record_send(to_email)
            
            result['success'] = True
            logger.info(f"✅ Sent to {to_email} via {sending_ip.ip} -> {mx_server}")
            
        except smtplib.SMTPRecipientsRefused as e:
            sending_ip.record_failure(is_hard_bounce=True)
            result['error'] = f'Recipient refused: {e}'
            logger.warning(f"❌ Hard bounce {to_email}: {e}")
            
        except smtplib.SMTPResponseException as e:
            is_hard = e.smtp_code >= 500
            sending_ip.record_failure(is_hard_bounce=is_hard)
            result['error'] = f'SMTP {e.smtp_code}: {e.smtp_error}'
            result['retry'] = not is_hard
            logger.warning(f"❌ SMTP error {to_email}: {e.smtp_code}")
            
        except (socket.timeout, ConnectionError, OSError) as e:
            sending_ip.record_failure(is_hard_bounce=False)
            result['error'] = f'Connection error: {e}'
            result['retry'] = True
            logger.warning(f"❌ Connection error {to_email}: {e}")
            
        except Exception as e:
            sending_ip.record_failure(is_hard_bounce=False)
            result['error'] = str(e)
            result['retry'] = True
            logger.error(f"❌ Unexpected error {to_email}: {e}")
        
        return result
    
    def get_stats(self) -> Dict:
        """Get engine statistics"""
        ip_stats = []
        for ip in self._ips:
            ip.reset_if_needed()
            ip_stats.append({
                'ip': ip.ip,
                'hostname': ip.hostname,
                'warmup_day': ip.warmup_day,
                'daily_limit': ip.daily_limit,
                'sent_today': ip.sent_today,
                'failed_today': ip.failed_today,
                'reputation': round(ip.reputation, 2),
                'is_active': ip.is_active,
                'available': ip.can_send()[0]
            })
        
        return {
            'ips': ip_stats,
            'throttle': self._throttle.get_stats(),
            'total_sent_today': sum(ip.sent_today for ip in self._ips),
            'total_capacity_today': sum(ip.daily_limit for ip in self._ips),
        }
    
    def set_warmup_day(self, ip: str, day: int):
        """Manually set warmup day for an IP"""
        for sending_ip in self._ips:
            if sending_ip.ip == ip:
                sending_ip.warmup_day = max(1, min(31, day))
                logger.info(f"Set {ip} warmup day to {day}")
                return True
        return False
    
    def add_ip(self, ip: str, hostname: str, warmup_day: int = 1, priority: int = 1):
        """Add a new sending IP"""
        # Check if already exists
        for existing in self._ips:
            if existing.ip == ip:
                logger.warning(f"IP {ip} already exists")
                return False
        
        self._ips.append(SendingIP(
            ip=ip,
            hostname=hostname,
            warmup_day=warmup_day,
            priority=priority
        ))
        logger.info(f"Added new IP {ip} ({hostname}) at warmup day {warmup_day}")
        return True
    
    def remove_ip(self, ip: str):
        """Remove a sending IP"""
        self._ips = [x for x in self._ips if x.ip != ip]
        logger.info(f"Removed IP {ip}")


# ============================================
# CONVENIENCE FUNCTION
# ============================================

def get_email_engine() -> EmailEngine:
    """Get the email engine singleton"""
    return EmailEngine()


def send_email(from_email: str, to_email: str, subject: str,
               html_body: str, text_body: str = None, **kwargs) -> Dict:
    """Convenience function to send email"""
    return get_email_engine().send(
        from_email, to_email, subject, html_body, text_body, **kwargs
    )
