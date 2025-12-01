"""
IP Warmup Tasks
Gradually increase sending volume for new IPs
"""
from celery_app import celery_app
import redis
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

REDIS_HOST = 'localhost'
REDIS_PORT = 6379

# Warmup schedule (day: max emails)
WARMUP_SCHEDULE = {
    1: 50,
    2: 100,
    3: 200,
    4: 400,
    5: 600,
    6: 900,
    7: 1200,
    14: 2500,
    21: 5000,
    28: 10000,
    35: 20000,
    42: 35000,
    49: 50000,
    56: 75000,
    63: 100000,
}

def get_redis():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def get_warmup_day(ip: str) -> int:
    """Get current warmup day for IP"""
    r = get_redis()
    start_date = r.hget(f'warmup:{ip}', 'start_date')
    
    if not start_date:
        # Start warmup today
        r.hset(f'warmup:{ip}', 'start_date', datetime.utcnow().isoformat())
        return 1
    
    start = datetime.fromisoformat(start_date)
    days = (datetime.utcnow() - start).days + 1
    return days


def get_daily_limit(ip: str) -> int:
    """Get daily sending limit for IP based on warmup"""
    day = get_warmup_day(ip)
    
    # Find appropriate limit
    for schedule_day in sorted(WARMUP_SCHEDULE.keys(), reverse=True):
        if day >= schedule_day:
            return WARMUP_SCHEDULE[schedule_day]
    
    return WARMUP_SCHEDULE[1]


def get_sent_today(ip: str) -> int:
    """Get emails sent today from IP"""
    r = get_redis()
    today = datetime.utcnow().strftime('%Y-%m-%d')
    return int(r.get(f'sent:{ip}:{today}') or 0)


def can_send(ip: str) -> bool:
    """Check if IP can send more emails today"""
    limit = get_daily_limit(ip)
    sent = get_sent_today(ip)
    return sent < limit


def increment_sent(ip: str):
    """Increment sent count for IP"""
    r = get_redis()
    today = datetime.utcnow().strftime('%Y-%m-%d')
    key = f'sent:{ip}:{today}'
    r.incr(key)
    r.expire(key, 86400 * 2)  # 2 day TTL


def get_warmup_status(ip: str) -> dict:
    """Get warmup status for IP"""
    day = get_warmup_day(ip)
    limit = get_daily_limit(ip)
    sent = get_sent_today(ip)
    
    return {
        'ip': ip,
        'warmup_day': day,
        'daily_limit': limit,
        'sent_today': sent,
        'remaining': max(0, limit - sent),
        'progress_percent': min(100, (day / 63) * 100),
        'fully_warmed': day >= 63
    }


@celery_app.task
def update_warmup_progress():
    """Update warmup progress for all IPs"""
    r = get_redis()
    
    # Get all warming IPs
    ips = r.keys('warmup:*')
    
    for ip_key in ips:
        ip = ip_key.replace('warmup:', '')
        status = get_warmup_status(ip)
        
        # Store status
        r.hset(f'warmup_status:{ip}', mapping=status)
        
        logger.info(f"IP {ip}: Day {status['warmup_day']}, Limit {status['daily_limit']}, Sent {status['sent_today']}")


@celery_app.task
def check_warmup_compliance(ip: str) -> dict:
    """Check if sending is within warmup limits"""
    status = get_warmup_status(ip)
    
    if status['sent_today'] > status['daily_limit']:
        logger.warning(f"IP {ip} exceeded warmup limit: {status['sent_today']}/{status['daily_limit']}")
        return {'compliant': False, 'exceeded_by': status['sent_today'] - status['daily_limit']}
    
    return {'compliant': True, 'status': status}
