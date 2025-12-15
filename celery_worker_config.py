"""
SendBaba Celery Configuration - FIXED
=====================================
Simplified config matching production.
"""
import os
import sys
from celery import Celery

sys.path.insert(0, '/opt/sendbaba-staging')

from dotenv import load_dotenv
load_dotenv()

REDIS_URL = os.environ.get('REDIS_URL', 'redis://:SendBabaRedis2024!@localhost:6379/0')

celery_app = Celery(
    'sendbaba',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['app.tasks.email_tasks']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    
    task_acks_late=True,
    worker_prefetch_multiplier=2,
    task_soft_time_limit=3600,
    task_time_limit=7200,
    result_expires=86400,
    
    # Simple beat schedule - NO QUEUE ROUTING
    beat_schedule={
        'process-queued-campaigns': {
            'task': 'app.tasks.email_tasks.process_queued_campaigns',
            'schedule': 5.0,
        },
        'process-queued-emails': {
            'task': 'app.tasks.email_tasks.process_queued_single_emails',
            'schedule': 5.0,
        },
        'sync-tracking-to-db': {
            'task': 'app.tasks.email_tasks.sync_tracking_to_db',
            'schedule': 30.0,
        },
        'recover-stuck-campaigns': {
            'task': 'app.tasks.email_tasks.recover_stuck_campaigns',
            'schedule': 60.0,
        },
        'retry-failed-emails': {
            'task': 'app.tasks.email_tasks.retry_failed_emails',
            'schedule': 120.0,
        },
    },
)

celery_app.autodiscover_tasks(['app.tasks'])
