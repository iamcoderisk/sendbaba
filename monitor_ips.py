#!/usr/bin/env python3
"""
IP Warmup & Deliverability Monitor for SendBaba
Run: python3 monitor_ips.py
"""

import redis
import sys
from datetime import datetime, timedelta
from tabulate import tabulate

REDIS_URL = 'redis://:SendBabaRedis2024!@localhost:6379/0'

IPS = {
    '156.67.29.186': 'Main Server',
    '75.119.153.106': 'Worker 1',
    '75.119.151.72': 'Worker 2',
    '161.97.170.33': 'Worker 3'
}

def get_redis():
    return redis.from_url(REDIS_URL, decode_responses=True)

def get_warmup_day(r, ip):
    key = f"warmup:{ip}:start_date"
    start_date = r.get(key)
    if not start_date:
        return 0  # Not started
    try:
        start = datetime.fromisoformat(start_date)
        return max(1, (datetime.now() - start).days + 1)
    except:
        return 0

def get_limits(warmup_day):
    if warmup_day == 0:
        return 0, 0
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

def get_sent_counts(r, ip):
    today = datetime.now().strftime('%Y-%m-%d')
    hour = datetime.now().strftime('%Y-%m-%d-%H')
    
    sent_today = r.get(f"sent:{ip}:{today}") or 0
    sent_hour = r.get(f"sent:{ip}:{hour}") or 0
    
    return int(sent_today), int(sent_hour)

def main():
    r = get_redis()
    
    print("\n" + "="*70)
    print(f"  SendBaba IP Warmup Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # IP Status Table
    table_data = []
    total_sent = 0
    total_capacity = 0
    
    for ip, name in IPS.items():
        warmup_day = get_warmup_day(r, ip)
        daily_limit, hourly_limit = get_limits(warmup_day)
        sent_today, sent_hour = get_sent_counts(r, ip)
        
        remaining = daily_limit - sent_today
        pct_used = (sent_today / daily_limit * 100) if daily_limit > 0 else 0
        
        status = "✅" if remaining > 0 and sent_hour < hourly_limit else "⏸️"
        if warmup_day == 0:
            status = "⚪"
        
        table_data.append([
            status,
            name,
            ip,
            warmup_day if warmup_day > 0 else "Not Started",
            f"{sent_today:,}",
            f"{daily_limit:,}",
            f"{remaining:,}",
            f"{pct_used:.1f}%",
            f"{sent_hour}/{hourly_limit}"
        ])
        
        total_sent += sent_today
        total_capacity += daily_limit
    
    headers = ["", "Server", "IP", "Day", "Sent", "Limit", "Remaining", "Used", "Hour"]
    print("\n" + tabulate(table_data, headers=headers, tablefmt="grid"))
    
    # Summary
    print(f"\n📊 DAILY SUMMARY:")
    print(f"   Total Sent Today: {total_sent:,}")
    print(f"   Total Capacity: {total_capacity:,}")
    print(f"   Remaining: {total_capacity - total_sent:,}")
    
    # Warmup projection
    print(f"\n📈 WARMUP PROJECTION (per IP):")
    projections = [
        ("Week 1 End", 7, 2000),
        ("Week 2 End", 14, 15000),
        ("Week 3 End", 21, 75000),
        ("Week 4 End", 28, 250000),
    ]
    for label, day, limit in projections:
        print(f"   {label} (Day {day}): {limit:,}/day × 4 IPs = {limit*4:,}/day")
    
    print("\n" + "="*70)

if __name__ == "__main__":
    # Install tabulate if missing
    try:
        from tabulate import tabulate
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "tabulate", "-q"])
        from tabulate import tabulate
    
    main()
