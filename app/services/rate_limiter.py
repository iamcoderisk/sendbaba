"""
SendBaba Rate Limiter & Throttling System
==========================================
- Pulls IP limits from database
- Per-minute and per-hour throttling
- Gmail-specific throttling
- Automatic IP selection based on capacity
"""

import redis
import psycopg2
import time
import logging
from datetime import datetime
from functools import lru_cache

logger = logging.getLogger(__name__)

REDIS_URL = 'redis://:SendBabaRedis2024!@localhost:6379/0'
DB_CONFIG = {
    'host': 'localhost',
    'database': 'emailer',
    'user': 'emailer',
    'password': 'SecurePassword123'
}

# Throttling settings
THROTTLE_CONFIG = {
    # Global settings
    'global_per_minute': 500,      # Max emails per minute across all IPs
    'global_per_hour': 20000,      # Max emails per hour across all IPs
    
    # Per-IP settings (for warmup IPs)
    'warmup_per_minute': 20,       # Max per minute for warmup IPs (<= day 7)
    'warmup_per_hour': 500,        # Max per hour for warmup IPs
    
    # Per-IP settings (for established IPs)
    'established_per_minute': 100,  # Max per minute for established IPs (> day 7)
    'established_per_hour': 5000,   # Max per hour for established IPs
    
    # Gmail-specific throttling (Gmail is strict)
    'gmail_per_minute': 50,        # Max Gmail emails per minute per IP
    'gmail_per_hour': 2000,        # Max Gmail emails per hour per IP
    
    # Delay between emails (milliseconds)
    'min_delay_ms': 100,           # Minimum delay between sends
    'warmup_delay_ms': 500,        # Delay for warmup IPs
}


class EmailThrottler:
    """
    Email throttling system that:
    - Enforces rate limits per IP
    - Has special handling for Gmail
    - Pulls limits from database
    - Auto-selects best IP for sending
    """
    
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)
        self._ip_cache = {}
        self._cache_time = 0
    
    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(**DB_CONFIG)
    
    def get_ip_pools(self, force_refresh=False):
        """Get all active IPs from database (cached for 60 seconds)"""
        now = time.time()
        if not force_refresh and self._ip_cache and (now - self._cache_time) < 60:
            return self._ip_cache
        
        try:
            conn = self.get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT ip_address, hostname, daily_limit, sent_today, 
                       is_active, warmup_day, priority
                FROM ip_pools 
                WHERE is_active = true
                ORDER BY priority ASC, sent_today ASC
            """)
            
            self._ip_cache = {}
            for row in cur.fetchall():
                self._ip_cache[row[0]] = {
                    'ip': row[0],
                    'hostname': row[1],
                    'daily_limit': row[2],
                    'sent_today': row[3],
                    'is_active': row[4],
                    'warmup_day': row[5] or 1,
                    'priority': row[6] or 1,
                    'is_warmup': (row[5] or 1) <= 7
                }
            
            conn.close()
            self._cache_time = now
            return self._ip_cache
            
        except Exception as e:
            logger.error(f"Error getting IP pools: {e}")
            return self._ip_cache or {}
    
    def get_sent_counts(self, ip, period='minute'):
        """Get sent counts for an IP"""
        now = datetime.now()
        
        if period == 'minute':
            key = f"throttle:{ip}:{now.strftime('%Y-%m-%d-%H-%M')}"
        elif period == 'hour':
            key = f"throttle:{ip}:{now.strftime('%Y-%m-%d-%H')}"
        elif period == 'day':
            key = f"throttle:{ip}:{now.strftime('%Y-%m-%d')}"
        else:
            return 0
        
        count = self.redis.get(key)
        return int(count) if count else 0
    
    def get_gmail_counts(self, ip, period='minute'):
        """Get Gmail-specific sent counts"""
        now = datetime.now()
        
        if period == 'minute':
            key = f"gmail:{ip}:{now.strftime('%Y-%m-%d-%H-%M')}"
        else:
            key = f"gmail:{ip}:{now.strftime('%Y-%m-%d-%H')}"
        
        count = self.redis.get(key)
        return int(count) if count else 0
    
    def record_send(self, ip, is_gmail=False):
        """Record a sent email for throttling"""
        now = datetime.now()
        pipe = self.redis.pipeline()
        
        # Record per-minute
        minute_key = f"throttle:{ip}:{now.strftime('%Y-%m-%d-%H-%M')}"
        pipe.incr(minute_key)
        pipe.expire(minute_key, 120)  # 2 minutes TTL
        
        # Record per-hour
        hour_key = f"throttle:{ip}:{now.strftime('%Y-%m-%d-%H')}"
        pipe.incr(hour_key)
        pipe.expire(hour_key, 7200)  # 2 hours TTL
        
        # Record Gmail-specific
        if is_gmail:
            gmail_minute = f"gmail:{ip}:{now.strftime('%Y-%m-%d-%H-%M')}"
            gmail_hour = f"gmail:{ip}:{now.strftime('%Y-%m-%d-%H')}"
            pipe.incr(gmail_minute)
            pipe.expire(gmail_minute, 120)
            pipe.incr(gmail_hour)
            pipe.expire(gmail_hour, 7200)
        
        # Global counters
        global_minute = f"global:{now.strftime('%Y-%m-%d-%H-%M')}"
        global_hour = f"global:{now.strftime('%Y-%m-%d-%H')}"
        pipe.incr(global_minute)
        pipe.expire(global_minute, 120)
        pipe.incr(global_hour)
        pipe.expire(global_hour, 7200)
        
        pipe.execute()
    
    def can_send(self, ip, to_email=None):
        """
        Check if we can send from this IP.
        
        Returns: (can_send, reason, wait_seconds)
        """
        pools = self.get_ip_pools()
        
        if ip not in pools:
            return False, 'ip_not_in_pool', 0
        
        ip_info = pools[ip]
        
        # Check daily limit from database
        if ip_info['sent_today'] >= ip_info['daily_limit']:
            return False, 'daily_limit_reached', 3600
        
        # Get throttle limits based on warmup status
        if ip_info['is_warmup']:
            per_minute = THROTTLE_CONFIG['warmup_per_minute']
            per_hour = THROTTLE_CONFIG['warmup_per_hour']
        else:
            per_minute = THROTTLE_CONFIG['established_per_minute']
            per_hour = THROTTLE_CONFIG['established_per_hour']
        
        # Check per-minute limit
        sent_minute = self.get_sent_counts(ip, 'minute')
        if sent_minute >= per_minute:
            return False, 'minute_limit', 60 - datetime.now().second
        
        # Check per-hour limit
        sent_hour = self.get_sent_counts(ip, 'hour')
        if sent_hour >= per_hour:
            return False, 'hour_limit', 3600 - (datetime.now().minute * 60 + datetime.now().second)
        
        # Gmail-specific checks
        is_gmail = to_email and ('gmail.com' in to_email.lower() or 'googlemail.com' in to_email.lower())
        if is_gmail:
            gmail_minute = self.get_gmail_counts(ip, 'minute')
            gmail_hour = self.get_gmail_counts(ip, 'hour')
            
            if gmail_minute >= THROTTLE_CONFIG['gmail_per_minute']:
                return False, 'gmail_minute_limit', 60 - datetime.now().second
            if gmail_hour >= THROTTLE_CONFIG['gmail_per_hour']:
                return False, 'gmail_hour_limit', 3600 - (datetime.now().minute * 60 + datetime.now().second)
        
        # Check global limits
        now = datetime.now()
        global_minute = self.redis.get(f"global:{now.strftime('%Y-%m-%d-%H-%M')}")
        global_hour = self.redis.get(f"global:{now.strftime('%Y-%m-%d-%H')}")
        
        if global_minute and int(global_minute) >= THROTTLE_CONFIG['global_per_minute']:
            return False, 'global_minute_limit', 60 - now.second
        if global_hour and int(global_hour) >= THROTTLE_CONFIG['global_per_hour']:
            return False, 'global_hour_limit', 3600 - (now.minute * 60 + now.second)
        
        return True, 'ok', 0
    
    def select_best_ip(self, to_email=None):
        """
        Select the best IP for sending.
        
        Criteria:
        1. Must have capacity (daily limit not reached)
        2. Must pass throttle checks
        3. Prefer IPs with more remaining capacity
        4. Consider priority
        
        Returns: (ip, reason) or (None, error_reason)
        """
        pools = self.get_ip_pools(force_refresh=True)
        
        if not pools:
            return None, 'no_ips_available'
        
        # Filter and score IPs
        candidates = []
        for ip, info in pools.items():
            can_send, reason, wait = self.can_send(ip, to_email)
            if can_send:
                remaining = info['daily_limit'] - info['sent_today']
                score = remaining * (1.0 / info['priority'])  # Higher remaining + lower priority = better
                candidates.append((ip, score, info))
        
        if not candidates:
            return None, 'all_ips_throttled'
        
        # Sort by score (highest first)
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        return candidates[0][0], 'ok'
    
    def get_recommended_delay(self, ip):
        """Get recommended delay before next send (in seconds)"""
        pools = self.get_ip_pools()
        
        if ip not in pools:
            return THROTTLE_CONFIG['min_delay_ms'] / 1000
        
        if pools[ip]['is_warmup']:
            return THROTTLE_CONFIG['warmup_delay_ms'] / 1000
        
        return THROTTLE_CONFIG['min_delay_ms'] / 1000
    
    def get_status(self):
        """Get full throttling status for all IPs"""
        pools = self.get_ip_pools(force_refresh=True)
        now = datetime.now()
        
        status = {
            'timestamp': now.isoformat(),
            'global': {
                'sent_minute': int(self.redis.get(f"global:{now.strftime('%Y-%m-%d-%H-%M')}") or 0),
                'sent_hour': int(self.redis.get(f"global:{now.strftime('%Y-%m-%d-%H')}") or 0),
                'limit_minute': THROTTLE_CONFIG['global_per_minute'],
                'limit_hour': THROTTLE_CONFIG['global_per_hour'],
            },
            'ips': []
        }
        
        for ip, info in pools.items():
            can_send, reason, wait = self.can_send(ip)
            
            ip_status = {
                'ip': ip,
                'hostname': info['hostname'],
                'warmup_day': info['warmup_day'],
                'is_warmup': info['is_warmup'],
                'daily_limit': info['daily_limit'],
                'sent_today': info['sent_today'],
                'remaining_today': info['daily_limit'] - info['sent_today'],
                'sent_minute': self.get_sent_counts(ip, 'minute'),
                'sent_hour': self.get_sent_counts(ip, 'hour'),
                'gmail_minute': self.get_gmail_counts(ip, 'minute'),
                'gmail_hour': self.get_gmail_counts(ip, 'hour'),
                'can_send': can_send,
                'reason': reason,
                'wait_seconds': wait
            }
            status['ips'].append(ip_status)
        
        # Sort by remaining capacity
        status['ips'].sort(key=lambda x: x['remaining_today'], reverse=True)
        
        return status


# Global instance
throttler = EmailThrottler()


# Convenience functions
def can_send_email(ip=None, to_email=None):
    """Check if we can send an email"""
    if ip:
        return throttler.can_send(ip, to_email)
    else:
        ip, reason = throttler.select_best_ip(to_email)
        if ip:
            return True, 'ok', 0
        return False, reason, 60


def record_email_sent(ip, to_email=None):
    """Record that an email was sent"""
    is_gmail = to_email and 'gmail.com' in to_email.lower()
    throttler.record_send(ip, is_gmail)


def get_best_ip_for_sending(to_email=None):
    """Get the best IP to send from"""
    return throttler.select_best_ip(to_email)


def get_throttle_status():
    """Get full throttling status"""
    return throttler.get_status()
