#!/usr/bin/env python3
"""
SendBaba Cluster Test Script
============================
Tests the entire email sending infrastructure end-to-end.
"""
import os
import sys
import time
import json
import redis
import psycopg2
from datetime import datetime

# Add path
sys.path.insert(0, '/opt/sendbaba-staging')

# Configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://:SendBabaRedis2024!@localhost:6379/0')
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://emailer:SecurePassword123@localhost:5432/emailer')

def test_redis():
    """Test Redis connectivity"""
    print("\n🔍 Testing Redis...")
    try:
        r = redis.from_url(REDIS_URL)
        r.ping()
        info = r.info()
        print(f"   ✅ Redis connected")
        print(f"   ├─ Connected clients: {info.get('connected_clients', 'N/A')}")
        print(f"   ├─ Used memory: {info.get('used_memory_human', 'N/A')}")
        print(f"   └─ Uptime: {info.get('uptime_in_days', 0)} days")
        return True
    except Exception as e:
        print(f"   ❌ Redis failed: {e}")
        return False

def test_database():
    """Test PostgreSQL connectivity"""
    print("\n🔍 Testing Database...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Test query
        cur.execute("SELECT COUNT(*) FROM ip_pools WHERE is_active = true")
        ip_count = cur.fetchone()[0]
        
        cur.execute("SELECT SUM(daily_limit) FROM ip_pools WHERE is_active = true")
        capacity = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM organizations")
        orgs = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM users")
        users = cur.fetchone()[0]
        
        print(f"   ✅ Database connected")
        print(f"   ├─ Active IPs: {ip_count}")
        print(f"   ├─ Daily capacity: {capacity:,}")
        print(f"   ├─ Organizations: {orgs}")
        print(f"   └─ Users: {users}")
        
        conn.close()
        return True
    except Exception as e:
        print(f"   ❌ Database failed: {e}")
        return False

def test_celery_workers():
    """Test Celery worker connectivity"""
    print("\n🔍 Testing Celery Workers...")
    try:
        from celery_worker_config import celery_app
        
        # Ping all workers
        inspector = celery_app.control.inspect()
        ping_results = inspector.ping()
        
        if ping_results:
            worker_count = len(ping_results)
            print(f"   ✅ Celery cluster online")
            print(f"   ├─ Workers responding: {worker_count}")
            
            # Get stats
            stats = inspector.stats()
            total_concurrency = 0
            for worker_name, worker_stats in (stats or {}).items():
                concurrency = worker_stats.get('pool', {}).get('max-concurrency', 0)
                total_concurrency += concurrency
            
            print(f"   └─ Total concurrency: {total_concurrency}")
            
            # List workers
            print(f"\n   Workers:")
            for worker_name in ping_results.keys():
                print(f"   ├─ {worker_name}")
            
            return True, worker_count
        else:
            print(f"   ❌ No workers responding")
            return False, 0
    except Exception as e:
        print(f"   ❌ Celery test failed: {e}")
        return False, 0

def test_send_email(test_email=None):
    """Test sending a single email through the cluster"""
    if not test_email:
        print("\n⏭️  Skipping email send test (no test email provided)")
        return True
    
    print(f"\n🔍 Testing Email Send to {test_email}...")
    try:
        from celery_worker_config import celery_app
        from worker_tasks import send_single_email_task
        
        # Create test email
        email_data = {
            'to_email': test_email,
            'from_email': 'test@sendbaba.com',
            'from_name': 'SendBaba Test',
            'subject': f'SendBaba Cluster Test - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            'html_body': '''
                <html>
                <body style="font-family: Arial, sans-serif; padding: 20px;">
                    <h1 style="color: #2563eb;">🎉 SendBaba Cluster Test Successful!</h1>
                    <p>This email confirms your SendBaba email cluster is working correctly.</p>
                    <hr>
                    <p><strong>Test Details:</strong></p>
                    <ul>
                        <li>Timestamp: {}</li>
                        <li>Workers: 11 nodes</li>
                        <li>Capacity: 302,500 emails/day</li>
                    </ul>
                    <p style="color: #059669;">✅ Your infrastructure is ready for production!</p>
                </body>
                </html>
            '''.format(datetime.now().isoformat()),
            'text_body': 'SendBaba cluster test successful!',
        }
        
        # Send via Celery
        result = send_single_email_task.apply_async(
            args=[email_data],
            queue='email_queue'
        )
        
        print(f"   📤 Task submitted: {result.id}")
        print(f"   ⏳ Waiting for result (max 30s)...")
        
        # Wait for result
        try:
            task_result = result.get(timeout=30)
            if task_result.get('success'):
                print(f"   ✅ Email sent successfully!")
                print(f"   └─ Message: {task_result.get('message', 'OK')}")
                return True
            else:
                print(f"   ❌ Email failed: {task_result.get('message', 'Unknown error')}")
                return False
        except Exception as e:
            print(f"   ⚠️  Task timeout or error: {e}")
            return False
            
    except Exception as e:
        print(f"   ❌ Email test failed: {e}")
        return False

def test_ip_rotation():
    """Test IP rotation logic"""
    print("\n🔍 Testing IP Pool...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Get IP pool status
        cur.execute("""
            SELECT 
                ip_address, 
                hostname, 
                warmup_day,
                daily_limit, 
                sent_today,
                daily_limit - sent_today as remaining
            FROM ip_pools 
            WHERE is_active = true 
            ORDER BY priority, (daily_limit - sent_today) DESC
        """)
        
        ips = cur.fetchall()
        print(f"   ✅ IP Pool Status:")
        print(f"   {'IP':<18} {'Hostname':<22} {'Day':<5} {'Limit':<8} {'Sent':<8} {'Remaining':<10}")
        print(f"   {'-'*80}")
        
        total_remaining = 0
        for ip in ips:
            remaining = ip[5] if ip[5] else ip[3]
            total_remaining += remaining
            status = "🟢" if ip[2] >= 30 else "🟡"
            print(f"   {status} {ip[0]:<16} {ip[1]:<22} {ip[2]:<5} {ip[3]:<8} {ip[4]:<8} {remaining:<10}")
        
        print(f"   {'-'*80}")
        print(f"   Total remaining capacity: {total_remaining:,} emails")
        
        conn.close()
        return True
    except Exception as e:
        print(f"   ❌ IP pool test failed: {e}")
        return False

def run_all_tests(test_email=None):
    """Run all tests"""
    print("=" * 60)
    print("       SENDBABA CLUSTER TEST SUITE")
    print("=" * 60)
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {}
    
    # Run tests
    results['redis'] = test_redis()
    results['database'] = test_database()
    results['celery'], worker_count = test_celery_workers()
    results['ip_pool'] = test_ip_rotation()
    results['email'] = test_send_email(test_email)
    
    # Summary
    print("\n" + "=" * 60)
    print("       TEST RESULTS SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {test_name.upper():<15} {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    if all_passed:
        print("   🎉 ALL TESTS PASSED - READY FOR PRODUCTION!")
    else:
        print("   ⚠️  SOME TESTS FAILED - REVIEW ABOVE")
    print("=" * 60)
    
    return all_passed

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Test SendBaba Cluster')
    parser.add_argument('--email', '-e', help='Test email address to send to')
    args = parser.parse_args()
    
    success = run_all_tests(args.email)
    sys.exit(0 if success else 1)
