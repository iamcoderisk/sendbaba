"""
Warmup-aware email sender
Respects IP limits and distributes across servers
"""

import redis
from datetime import datetime
import socket

REDIS_URL = 'redis://:SendBabaRedis2024!@localhost:6379/0'

IPS = ['156.67.29.186', '75.119.153.106', '75.119.151.72', '161.97.170.33']

class WarmupSender:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)
        self.local_ip = self._get_local_ip()
    
    def _get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return '156.67.29.186'
    
    def get_warmup_day(self, ip):
        key = f"warmup:{ip}:start_date"
        start_date = self.redis.get(key)
        if not start_date:
            return 1
        try:
            start = datetime.fromisoformat(start_date)
            return max(1, (datetime.now() - start).days + 1)
        except:
            return 1
    
    def get_limits(self, warmup_day):
        daily_schedule = {
            1: 100, 2: 200, 3: 400, 4: 600, 5: 1000,
            6: 1500, 7: 2000, 8: 3000, 9: 4000, 10: 5000,
            11: 7000, 12: 9000, 13: 12000, 14: 15000,
            15: 20000, 16: 25000, 17: 30000, 18: 40000,
            19: 50000, 20: 60000, 21: 75000,
            22: 90000, 23: 100000, 24: 125000, 25: 150000,
            26: 175000, 27: 200000, 28: 250000
        }
        daily = daily_schedule.get(warmup_day, 250000 if warmup_day > 28 else 100)
        hourly = max(10, daily // 20)
        return daily, hourly
    
    def get_sent_counts(self, ip):
        today = datetime.now().strftime('%Y-%m-%d')
        hour = datetime.now().strftime('%Y-%m-%d-%H')
        
        sent_today = int(self.redis.get(f"sent:{ip}:{today}") or 0)
        sent_hour = int(self.redis.get(f"sent:{ip}:{hour}") or 0)
        
        return sent_today, sent_hour
    
    def can_send_from_ip(self, ip):
        """Check if this IP can send"""
        warmup_day = self.get_warmup_day(ip)
        daily_limit, hourly_limit = self.get_limits(warmup_day)
        sent_today, sent_hour = self.get_sent_counts(ip)
        
        return sent_today < daily_limit and sent_hour < hourly_limit
    
    def record_send(self, ip=None):
        """Record a successful send"""
        if ip is None:
            ip = self.local_ip
        
        today = datetime.now().strftime('%Y-%m-%d')
        hour = datetime.now().strftime('%Y-%m-%d-%H')
        
        pipe = self.redis.pipeline()
        pipe.incr(f"sent:{ip}:{today}")
        pipe.expire(f"sent:{ip}:{today}", 172800)
        pipe.incr(f"sent:{ip}:{hour}")
        pipe.expire(f"sent:{ip}:{hour}", 7200)
        pipe.execute()
    
    def get_total_remaining_today(self):
        """Get total remaining capacity across all IPs"""
        total = 0
        for ip in IPS:
            warmup_day = self.get_warmup_day(ip)
            daily_limit, _ = self.get_limits(warmup_day)
            sent_today, _ = self.get_sent_counts(ip)
            total += max(0, daily_limit - sent_today)
        return total

# Global instance
warmup_sender = WarmupSender()
