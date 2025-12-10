"""
Gmail Throttling Service
Limits Gmail sending to protect IP reputation
"""

import redis
from datetime import datetime

REDIS_URL = 'redis://:SendBaba2024SecureRedis@localhost:6379/0'

# Gmail limits per IP per hour
GMAIL_HOURLY_LIMIT = 50
GMAIL_DAILY_LIMIT = 500

class GmailThrottle:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)
    
    def can_send_to_gmail(self, ip):
        """Check if we can send to Gmail from this IP"""
        hour_key = f"gmail:{ip}:{datetime.now().strftime('%Y-%m-%d-%H')}"
        day_key = f"gmail:{ip}:{datetime.now().strftime('%Y-%m-%d')}"
        
        hour_count = int(self.redis.get(hour_key) or 0)
        day_count = int(self.redis.get(day_key) or 0)
        
        if hour_count >= GMAIL_HOURLY_LIMIT:
            return False, f"Gmail hourly limit reached ({hour_count}/{GMAIL_HOURLY_LIMIT})"
        if day_count >= GMAIL_DAILY_LIMIT:
            return False, f"Gmail daily limit reached ({day_count}/{GMAIL_DAILY_LIMIT})"
        
        return True, "OK"
    
    def record_gmail_send(self, ip):
        """Record a Gmail send"""
        hour_key = f"gmail:{ip}:{datetime.now().strftime('%Y-%m-%d-%H')}"
        day_key = f"gmail:{ip}:{datetime.now().strftime('%Y-%m-%d')}"
        
        pipe = self.redis.pipeline()
        pipe.incr(hour_key)
        pipe.expire(hour_key, 7200)
        pipe.incr(day_key)
        pipe.expire(day_key, 172800)
        pipe.execute()
    
    def get_gmail_stats(self, ip):
        """Get Gmail sending stats for an IP"""
        hour_key = f"gmail:{ip}:{datetime.now().strftime('%Y-%m-%d-%H')}"
        day_key = f"gmail:{ip}:{datetime.now().strftime('%Y-%m-%d')}"
        
        return {
            'ip': ip,
            'hour_count': int(self.redis.get(hour_key) or 0),
            'hour_limit': GMAIL_HOURLY_LIMIT,
            'day_count': int(self.redis.get(day_key) or 0),
            'day_limit': GMAIL_DAILY_LIMIT
        }

gmail_throttle = GmailThrottle()

def is_gmail(email):
    """Check if email is Gmail"""
    return email.lower().endswith('@gmail.com')

def should_prioritize(email):
    """Non-Gmail emails get priority"""
    return not is_gmail(email)
