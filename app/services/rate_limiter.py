"""
Rate Limiter for IP-based email sending
Ensures each IP stays within warmup limits
"""

import redis
import time
import random
from datetime import datetime

REDIS_URL = 'redis://:SendBaba2024SecureRedis@localhost:6379/0'

# IP to server mapping
IP_SERVERS = {
    '156.67.29.186': 'main',
    '75.119.153.106': 'worker1',
    '75.119.151.72': 'worker2', 
    '161.97.170.33': 'worker3'
}

# Reverse mapping
SERVER_IPS = {v: k for k, v in IP_SERVERS.items()}

class EmailRateLimiter:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)
    
    def get_current_ip(self):
        """Get the IP of the current server"""
        import socket
        hostname = socket.gethostname()
        # Try to get from environment or detect
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return '156.67.29.186'  # Default to main
    
    def get_warmup_day(self, ip):
        """Get warmup day for IP"""
        key = f"warmup:{ip}:start_date"
        start_date = self.redis.get(key)
        if not start_date:
            # Auto-start warmup
            self.redis.set(key, datetime.now().isoformat())
            return 1
        try:
            start = datetime.fromisoformat(start_date)
            return max(1, (datetime.now() - start).days + 1)
        except:
            return 1
    
    def get_limits(self, warmup_day):
        """Get daily and hourly limits based on warmup day"""
        # Daily limits
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
        hourly = max(10, daily // 20)  # Spread across ~20 hours
        
        return daily, hourly
    
    def get_sent_counts(self, ip):
        """Get sent counts for today and this hour"""
        today = datetime.now().strftime('%Y-%m-%d')
        hour = datetime.now().strftime('%Y-%m-%d-%H')
        
        sent_today = self.redis.get(f"sent:{ip}:{today}") or 0
        sent_hour = self.redis.get(f"sent:{ip}:{hour}") or 0
        
        return int(sent_today), int(sent_hour)
    
    def can_send(self, ip=None):
        """Check if we can send from this IP"""
        if ip is None:
            ip = self.get_current_ip()
        
        warmup_day = self.get_warmup_day(ip)
        daily_limit, hourly_limit = self.get_limits(warmup_day)
        sent_today, sent_hour = self.get_sent_counts(ip)
        
        if sent_today >= daily_limit:
            return False, f"Daily limit: {sent_today}/{daily_limit}"
        if sent_hour >= hourly_limit:
            return False, f"Hourly limit: {sent_hour}/{hourly_limit}"
        
        return True, "OK"
    
    def record_send(self, ip=None):
        """Record a sent email"""
        if ip is None:
            ip = self.get_current_ip()
        
        today = datetime.now().strftime('%Y-%m-%d')
        hour = datetime.now().strftime('%Y-%m-%d-%H')
        
        pipe = self.redis.pipeline()
        pipe.incr(f"sent:{ip}:{today}")
        pipe.expire(f"sent:{ip}:{today}", 172800)  # 2 days
        pipe.incr(f"sent:{ip}:{hour}")
        pipe.expire(f"sent:{ip}:{hour}", 7200)  # 2 hours
        pipe.execute()
    
    def get_all_status(self):
        """Get status for all IPs"""
        status = []
        for ip, name in IP_SERVERS.items():
            warmup_day = self.get_warmup_day(ip)
            daily_limit, hourly_limit = self.get_limits(warmup_day)
            sent_today, sent_hour = self.get_sent_counts(ip)
            
            status.append({
                'name': name,
                'ip': ip,
                'warmup_day': warmup_day,
                'daily_limit': daily_limit,
                'hourly_limit': hourly_limit,
                'sent_today': sent_today,
                'sent_hour': sent_hour,
                'daily_remaining': daily_limit - sent_today,
                'can_send': sent_today < daily_limit and sent_hour < hourly_limit
            })
        
        return status
    
    def select_best_ip(self):
        """Select the best IP to send from (most capacity remaining)"""
        status = self.get_all_status()
        available = [s for s in status if s['can_send']]
        
        if not available:
            return None, "All IPs at limit"
        
        # Sort by remaining capacity
        available.sort(key=lambda x: x['daily_remaining'], reverse=True)
        return available[0]['ip'], "OK"

# Global instance
rate_limiter = EmailRateLimiter()
