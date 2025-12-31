#!/usr/bin/env python3
"""
Real-time Campaign Progress Monitor
Usage: python3 monitor_campaign.py [campaign_id]
"""
import sys
import time
import redis

r = redis.Redis(host='localhost', port=6379, password='SendBabaRedis2024!', decode_responses=True)

def monitor(campaign_id=None):
    print("=" * 60)
    print("📊 REAL-TIME CAMPAIGN MONITOR")
    print("=" * 60)
    print("Press Ctrl+C to exit\n")
    
    while True:
        # Get all campaign progress keys
        if campaign_id:
            keys = [f"campaign_progress:{campaign_id}"]
        else:
            keys = r.keys("campaign_progress:*")
        
        if not keys:
            print("No active campaigns. Waiting...", end='\r')
            time.sleep(2)
            continue
        
        print("\033[H\033[J")  # Clear screen
        print("=" * 70)
        print(f"📊 CAMPAIGN PROGRESS - {time.strftime('%H:%M:%S')}")
        print("=" * 70)
        
        for key in sorted(keys):
            data = r.hgetall(key)
            if not data:
                continue
            
            cid = key.split(':')[-1]
            sent = int(data.get('sent', 0))
            failed = int(data.get('failed', 0))
            total = int(data.get('total', 0))
            status = data.get('status', 'unknown')
            percent = int(data.get('percent', 0))
            
            # Progress bar
            bar_len = 30
            filled = int(bar_len * percent / 100)
            bar = '█' * filled + '░' * (bar_len - filled)
            
            print(f"\n🎯 {cid[:30]}")
            print(f"   [{bar}] {percent}%")
            print(f"   ✅ Sent: {sent:,} | ❌ Failed: {failed:,} | 📊 Total: {total:,}")
            print(f"   Status: {status.upper()}")
        
        time.sleep(1)

if __name__ == '__main__':
    campaign_id = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        monitor(campaign_id)
    except KeyboardInterrupt:
        print("\n\n👋 Monitor stopped")
