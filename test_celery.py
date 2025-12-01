#!/usr/bin/env python3
"""Test Celery setup"""
import sys
sys.path.insert(0, '/opt/sendbaba-staging')

from app.celery_config import celery_app
from app.tasks.email_tasks import send_single_email, send_campaign

print("Testing Celery connection...")

# Test ping
result = celery_app.control.ping()
if result:
    print(f"✓ Celery workers responding: {result}")
else:
    print("✗ No workers responding")

# Test queue
print("\nQueuing test task...")
task = send_single_email.apply_async(
    args=[{
        'id': 'test-001',
        'from': 'test@sendbaba.com',
        'to': 'test@example.com',
        'subject': 'Test',
        'text_body': 'Test email'
    }],
    queue='default'
)
print(f"✓ Task queued: {task.id}")

print("\nCelery is working!")
